# --- ⚠️ CRITICAL RISK WARNING - PLEASE READ BEFORE USE ⚠️ ---
#
# 1.  **关于保证金模式 (Margin Mode):**
#     本脚本会使用您 Hyperliquid 账户的 **默认保证金模式**，通常是 **全仓模式 (Cross Margin)**。
#     在全仓模式下，您账户中 **所有可用资金** 都会被用作所有持仓的保证金。
#     这意味着，**一个仓位的巨大亏损可能会耗尽您的全部账户余额，导致所有仓位一同被强制平仓。**
#     **强烈建议:** 请务必在一个 **资金隔离的专用账户** 中运行此机器人，并且账户中的资金应该是您完全可以接受损失的数额。
#     **请勿** 在存有大量资金的主账户中直接运行本脚本！
#
# 2.  **关于跟单目标 (Target Trader Risk):**
#     本脚本是一个忠实的执行者，它本身没有任何交易策略。您的盈亏完全取决于您所选择的跟单目标 (`TARGET_USER_ADDRESS`)。
#     如果目标交易员亏损，您也会按比例亏损。请在实盘前充分研究并信任您的跟单目标。
#
# 3.  **关于跟单比例 (COPY_NOTIONAL_RATIO):**
#     这是决定您风险敞口的最核心参数。它直接决定了您的仓位大小。在不完全理解其影响前，请务必从一个极小的值开始测试。
#
# 4.  **关于软件和网络风险 (Operational Risk):**
#     任何程序都有中断的可能（如网络断开、服务器维护、电脑死机等）。这可能导致您的仓位处于无人管理的状态。
#     本工具并非“一劳永逸”，您需要定期监控其运行状态和您在交易所的实际持仓。
#
# --- By running this script, you acknowledge these risks and take full responsibility for any financial outcomes. ---

import time
import json
import math
import logging
import example_utils
from hyperliquid.utils import constants

# --- 核心配置参数 ---

# ✨ 安全开关: 检查无误后，请手动改为 False 以启动实盘交易。
DRY_RUN = True

TARGET_USER_ADDRESS = "0xc20ac4dc4188660cbf555448af52694ca62b0734" # 您要跟单的目标地址 (DS)

# 我方仓位名义价值将是目标名义价值的该比例。
# 基于目标最小仓位 (XRP, ~$8.9k) 和我方最小开仓名义价值 ($10) 计算：
# 10 / 8900 ≈ 0.00112。为增加缓冲，设定为 0.0014
COPY_NOTIONAL_RATIO = 0.0014

# 仓位 SZI 大小同步的容忍度。
SZI_TOLERANCE_RATIO = 0.05

# 跟单的币种列表
TARGET_COINS = ["XRP", "DOGE", "BTC", "ETH", "SOL", "BNB"]

LOOP_SLEEP_SECONDS = 30

def get_position_info(user_state, coin_name):
    """从完整的用户状态中，查找并返回指定币种的持仓详情，如果不存在则返回None"""
    asset_positions = user_state.get("assetPositions", [])
    for position in asset_positions:
        if position.get("position", {}).get("coin") == coin_name:
            if float(position["position"]["szi"]) != 0:
                return position["position"]
    return None

def execute_action(action_msg, function, *args, **kwargs):
    """根据 DRY_RUN 模式决定是打印模拟操作还是真实执行"""
    if DRY_RUN:
        logging.info(f"[DRY RUN] {action_msg}")
        return {"status": "ok", "response": {"type": "dry_run", "data": "simulated success"}}
    else:
        logging.info(f"[LIVE] {action_msg}")
        return function(*args, **kwargs)

def process_coin(exchange, info, all_mids, my_address, target_user_state, my_user_state, coin, meta_data):
    """处理单个币种的跟单逻辑"""
    logging.info(f"--- Processing {coin} ---")
    
    mid_price = float(all_mids.get(coin, 0))
    if mid_price == 0:
        logging.warning(f"Could not get mid price for {coin}, skipping.")
        return

    asset_info = next((item for item in meta_data["universe"] if item["name"] == coin), None)
    if not asset_info:
        logging.warning(f"Could not find metadata for {coin}, skipping.")
        return
    sz_decimals = asset_info["szDecimals"]

    target_position = get_position_info(target_user_state, coin)
    my_position = get_position_info(my_user_state, coin)

    if not target_position:
        logging.info(f"Target does not have a position in {coin}.")
        if my_position:
            action_msg = f"Closing {coin} position to match target."
            close_result = execute_action(action_msg, exchange.market_close, coin)
            logging.info(f"Close result: {json.dumps(close_result)}")
        return

    target_direction_is_buy = float(target_position["szi"]) > 0
    target_leverage = int(target_position["leverage"]["value"])
    target_szi_abs = abs(float(target_position["szi"]))
    target_notional_value = target_szi_abs * mid_price
    
    my_target_szi_abs = target_szi_abs * COPY_NOTIONAL_RATIO
    my_target_notional_value = my_target_szi_abs * mid_price
    
    MIN_NOTIONAL_VALUE = 10 
    if my_target_notional_value < MIN_NOTIONAL_VALUE:
        logging.warning(f"Target {coin} position scaled value is ${my_target_notional_value:,.2f}, which is below the minimum of ${MIN_NOTIONAL_VALUE}. Skipping.")
        if my_position:
            action_msg = f"Closing {coin} because target's scaled position is too small to copy."
            close_result = execute_action(action_msg, exchange.market_close, coin)
            logging.info(f"Close result: {json.dumps(close_result)}")
        return

    rounded_my_target_szi_abs = round(my_target_szi_abs, sz_decimals)
    
    if rounded_my_target_szi_abs == 0:
        logging.warning(f"Calculated {coin} position size is 0 after rounding (from: {my_target_szi_abs}). Cannot open position, skipping.")
        return
        
    if my_position is None:
        logging.info(f"Target has {'Long' if target_direction_is_buy else 'Short'} {coin} ({target_leverage}x). We have no position. Opening new position.")
        logging.info(f"  Target Notional: ${target_notional_value:,.2f}, My Target Notional: ${my_target_notional_value:,.2f}")
        logging.info(f"  Calculated SZI: {my_target_szi_abs:.8f} -> Rounded to {sz_decimals} decimals: {rounded_my_target_szi_abs}")
        
        try:
            leverage_msg = f"Updating {coin} leverage to {target_leverage}x"
            execute_action(leverage_msg, exchange.update_leverage, target_leverage, coin)
            
            order_msg = f"Market {'Buy' if target_direction_is_buy else 'Sell'} {rounded_my_target_szi_abs} {coin}"
            order_result = execute_action(order_msg, exchange.market_open, coin, target_direction_is_buy, rounded_my_target_szi_abs, None, 0.01)
            logging.info(f"Open result: {json.dumps(order_result)}")
        except Exception as e:
            logging.error(f"Failed to open position for {coin}: {e}", exc_info=True)
            
    else:
        my_direction_is_buy = float(my_position["szi"]) > 0
        my_leverage = int(my_position["leverage"]["value"])
        my_szi_abs = abs(float(my_position["szi"]))

        if my_direction_is_buy == target_direction_is_buy and my_leverage == target_leverage:
            szi_diff = abs(my_szi_abs - rounded_my_target_szi_abs)
            szi_tolerance = rounded_my_target_szi_abs * SZI_TOLERANCE_RATIO

            if szi_diff <= szi_tolerance:
                my_position_value = my_szi_abs * mid_price
                logging.info(f"{coin} position is in sync with target. My notional value: ${my_position_value:,.2f}")
            else:
                logging.warning(f"{coin} position size mismatch! (My: {my_szi_abs:.5f}, Target should be: {rounded_my_target_szi_abs:.5f}). Re-syncing.")
                action_msg = f"Closing {coin} to re-sync position size."
                close_result = execute_action(action_msg, exchange.market_close, coin)
                logging.info(f"Close result: {json.dumps(close_result)}")
        else:
            logging.warning(f"{coin} position policy mismatch! (My: {'Long' if my_direction_is_buy else 'Short'} {my_leverage}x, "
                  f"Target: {'Long' if target_direction_is_buy else 'Short'} {target_leverage}x). Re-syncing.")
            action_msg = f"Closing {coin} to re-sync position policy."
            close_result = execute_action(action_msg, exchange.market_close, coin)
            logging.info(f"Close result: {json.dumps(close_result)}")

def main():
    # --- Logging Setup ---
    # Get the root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Remove all existing handlers to avoid duplicates
    if logger.hasHandlers():
        logger.handlers.clear()
        
    # Create file handler which logs even debug messages
    fh = logging.FileHandler('ds_copier.log', mode='a')
    fh.setLevel(logging.INFO)
    
    # Create console handler with a higher log level
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    
    # Create formatter and add it to the handlers
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
    fh.setFormatter(formatter)
    ch.setFormatter(formatter)
    
    # Add the handlers to the logger
    logger.addHandler(fh)
    logger.addHandler(ch)

    try:
        my_address, info, exchange = example_utils.setup(base_url=constants.MAINNET_API_URL)
    except Exception as e:
        logging.error(f"Failed to setup connection: {e}", exc_info=True)
        return

    logging.info("--- DS Copier Bot V2 Initializing ---")
    if DRY_RUN:
        logging.warning("--- Bot is running in DRY RUN mode. No real trades will be executed. ---")
    
    logging.info(f"My Account Address: {my_address}")
    logging.info(f"Target Account Address: {TARGET_USER_ADDRESS}")
    logging.info(f"Copy Ratio: {COPY_NOTIONAL_RATIO*100:.4f}% of target's notional value.")
    logging.info(f"SZI Tolerance: {SZI_TOLERANCE_RATIO*100}%")
    logging.info(f"Monitored Coins: {TARGET_COINS}")
    
    try:
        logging.info("Fetching exchange metadata...")
        meta_data = info.meta()
        logging.info("Target coin size decimals (szDecimals) check:")
        for coin in TARGET_COINS:
            asset_info = next((item for item in meta_data["universe"] if item["name"] == coin), None)
            if asset_info:
                logging.info(f"  - {coin}: {asset_info['szDecimals']} decimals")
            else:
                logging.warning(f"  - {coin}: Could not find metadata!")
    except Exception as e:
        logging.error(f"Failed to fetch metadata: {e}", exc_info=True)
        return

    try:
        if DRY_RUN:
            logging.info(f"----- {time.strftime('%Y-%m-%d %H:%M:%S')} - Starting single simulation run -----")
            all_mids = info.all_mids()
            target_user_state = info.user_state(TARGET_USER_ADDRESS)
            my_user_state = info.user_state(my_address)
            for coin in TARGET_COINS:
                process_coin(exchange, info, all_mids, my_address, target_user_state, my_user_state, coin, meta_data)
            logging.info("----- Simulation run finished. -----")
        else:
            while True:
                logging.info(f"----- {time.strftime('%Y-%m-%d %H:%M:%S')} - Starting new synchronization cycle -----")
                try:
                    all_mids = info.all_mids()
                    target_user_state = info.user_state(TARGET_USER_ADDRESS)
                    my_user_state = info.user_state(my_address)
                    for coin in TARGET_COINS:
                        process_coin(exchange, info, all_mids, my_address, target_user_state, my_user_state, coin, meta_data)
                except Exception as e:
                    logging.error(f"An error occurred during the sync cycle: {e}", exc_info=True)
                
                logging.info(f"Cycle finished. Waiting for {LOOP_SLEEP_SECONDS} seconds...")
                time.sleep(LOOP_SLEEP_SECONDS)

    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt detected. Shutting down bot.")
    except Exception as e:
        logging.error(f"An unexpected critical error occurred: {e}", exc_info=True)
    finally:
        logging.info("--- Bot has been terminated. ---")


if __name__ == "__main__":
    main()
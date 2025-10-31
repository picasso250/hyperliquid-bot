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
import example_utils
from hyperliquid.utils import constants

# --- 核心配置参数 ---

# ✨ 安全开关: 检查无误后，请手动改为 False 以启动实盘交易。
DRY_RUN = False

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
        print(f"【模拟操作】{action_msg}")
        return {"status": "ok", "response": {"type": "dry_run", "data": "simulated success"}}
    else:
        print(f"【实盘操作】{action_msg}")
        return function(*args, **kwargs)

def process_coin(exchange, info, all_mids, my_address, target_user_state, my_user_state, coin, meta_data):
    """处理单个币种的跟单逻辑"""
    print(f"\n--- 正在处理 {coin} ---")
    
    mid_price = float(all_mids.get(coin, 0))
    if mid_price == 0:
        print(f"❌ 警告: 无法获取 {coin} 的价格，跳过。")
        return

    asset_info = next((item for item in meta_data["universe"] if item["name"] == coin), None)
    if not asset_info:
        print(f"❌ 警告: 无法在元数据中找到 {coin} 的信息，跳过。")
        return
    sz_decimals = asset_info["szDecimals"]

    target_position = get_position_info(target_user_state, coin)
    my_position = get_position_info(my_user_state, coin)

    if not target_position:
        print(f"🟡 目标未持有 {coin} 仓位。")
        if my_position:
            action_msg = f"平仓 {coin}"
            close_result = execute_action(action_msg, exchange.market_close, coin)
            print(f"平仓结果: {json.dumps(close_result)}")
        return

    target_direction_is_buy = float(target_position["szi"]) > 0
    target_leverage = int(target_position["leverage"]["value"])
    target_szi_abs = abs(float(target_position["szi"]))
    target_notional_value = target_szi_abs * mid_price
    
    my_target_szi_abs = target_szi_abs * COPY_NOTIONAL_RATIO
    my_target_notional_value = my_target_szi_abs * mid_price
    
    MIN_NOTIONAL_VALUE = 10 
    if my_target_notional_value < MIN_NOTIONAL_VALUE:
        print(f"⚠️ 目标 {coin} 仓位按比例换算后价值 ${my_target_notional_value:,.2f}，低于最小开仓要求 ${MIN_NOTIONAL_VALUE}，跳过。")
        if my_position:
            action_msg = f"平仓 {coin} (因目标仓位过小无法跟单)"
            close_result = execute_action(action_msg, exchange.market_close, coin)
            print(f"平仓结果: {json.dumps(close_result)}")
        return

    rounded_my_target_szi_abs = round(my_target_szi_abs, sz_decimals)
    
    if rounded_my_target_szi_abs == 0:
        print(f"⚠️ 计算出的 {coin} 仓位数量经四舍五入后为0 (原始值: {my_target_szi_abs})，无法开仓，跳过。")
        return
        
    if my_position is None:
        print(f"✅ 发现目标持有 {coin} {'多单' if target_direction_is_buy else '空单'} ({target_leverage}x)。")
        print(f"   目标价值: ${target_notional_value:,.2f}, 我方应开价值: ${my_target_notional_value:,.2f}")
        print(f"   计算SZI: {my_target_szi_abs:.8f} -> 根据精度({sz_decimals}位小数)修正为 -> {rounded_my_target_szi_abs}")
        
        try:
            leverage_msg = f"更新 {coin} 杠杆为 {target_leverage}x"
            execute_action(leverage_msg, exchange.update_leverage, target_leverage, coin)
            
            order_msg = f"市价 {'开多' if target_direction_is_buy else '开空'} {rounded_my_target_szi_abs} {coin}"
            order_result = execute_action(order_msg, exchange.market_open, coin, target_direction_is_buy, rounded_my_target_szi_abs, None, 0.01)
            print(f"开仓结果: {json.dumps(order_result)}")
        except Exception as e:
            print(f"❌ 操作失败: {e}")
            
    else:
        my_direction_is_buy = float(my_position["szi"]) > 0
        my_leverage = int(my_position["leverage"]["value"])
        my_szi_abs = abs(float(my_position["szi"]))

        if my_direction_is_buy == target_direction_is_buy and my_leverage == target_leverage:
            szi_diff = abs(my_szi_abs - rounded_my_target_szi_abs)
            szi_tolerance = rounded_my_target_szi_abs * SZI_TOLERANCE_RATIO

            if szi_diff <= szi_tolerance:
                my_position_value = my_szi_abs * mid_price
                print(f"🟢 {coin} 持仓正常，与目标一致。我方价值: ${my_position_value:,.2f}")
            else:
                print(f"❗️ {coin} 仓位大小不一致！(我: {my_szi_abs:.5f}, 目标应为: {rounded_my_target_szi_abs:.5f})")
                action_msg = f"平仓 {coin} 以同步仓位大小"
                close_result = execute_action(action_msg, exchange.market_close, coin)
                print(f"平仓结果: {json.dumps(close_result)}")
        else:
            print(f"❗️ {coin} 策略不一致！(我: {'多' if my_direction_is_buy else '空'}{my_leverage}x, "
                  f"目标: {'多' if target_direction_is_buy else '空'}{target_leverage}x)")
            action_msg = f"平仓 {coin} 以同步策略"
            close_result = execute_action(action_msg, exchange.market_close, coin)
            print(f"平仓结果: {json.dumps(close_result)}")

def main():
    my_address, info, exchange = example_utils.setup(base_url=constants.MAINNET_API_URL)
    print("--- DS 完全跟单机器人 V2 ---")
    if DRY_RUN:
        print("\n⚠️  警告: 当前处于【模拟运行】模式，不会执行任何真实交易。 ⚠️\n")
    print(f"我的账户地址: {my_address}")
    print(f"跟单目标地址: {TARGET_USER_ADDRESS}")
    print(f"策略: 跟随目标 {TARGET_COINS} 的所有仓位，按目标 {COPY_NOTIONAL_RATIO*100:.4f}% 的规模开仓。")
    print(f"同步容忍度: {SZI_TOLERANCE_RATIO*100}%")
    print("-------------------------------------------------------")
    
    print("正在获取交易所元数据...")
    meta_data = info.meta()
    
    print("目标币种下单精度 (szDecimals) 核对:")
    for coin in TARGET_COINS:
        asset_info = next((item for item in meta_data["universe"] if item["name"] == coin), None)
        if asset_info:
            print(f"  - {coin}: Size Decimals = {asset_info['szDecimals']}")
        else:
            print(f"  - {coin}: 未找到元数据！")
    print("-------------------------------------------------------")

    try:
        # 根据 DRY_RUN 模式决定执行路径
        if DRY_RUN:
            # --- 模拟模式 ---
            print(f"\n=======================================================")
            print(f"----- {time.strftime('%Y-%m-%d %H:%M:%S')} - 启动模拟同步 -----")
            all_mids = info.all_mids()
            target_user_state = info.user_state(TARGET_USER_ADDRESS)
            my_user_state = info.user_state(my_address)
            for coin in TARGET_COINS:
                process_coin(exchange, info, all_mids, my_address, target_user_state, my_user_state, coin, meta_data)
            print(f"\n=======================================================")
            print("✅ 模拟运行结束。")
        else:
            # --- 实盘模式 ---
            while True:
                print(f"\n=======================================================")
                print(f"----- {time.strftime('%Y-%m-%d %H:%M:%S')} - 启动新一轮同步 -----")
                try:
                    all_mids = info.all_mids()
                    target_user_state = info.user_state(TARGET_USER_ADDRESS)
                    my_user_state = info.user_state(my_address)
                    for coin in TARGET_COINS:
                        process_coin(exchange, info, all_mids, my_address, target_user_state, my_user_state, coin, meta_data)
                except Exception as e:
                    print(f"❌ 循环中发生错误: {e}，将在 {LOOP_SLEEP_SECONDS} 秒后重试。")
                
                print(f"\n=======================================================")
                print(f"等待 {LOOP_SLEEP_SECONDS} 秒后进入下一轮...")
                time.sleep(LOOP_SLEEP_SECONDS)

    except KeyboardInterrupt:
        print("\n检测到手动中断 (Ctrl+C)，机器人正在关闭...")
    except Exception as e:
        print(f"\n❌ 发生未知错误: {e}")
    finally:
        print("程序已退出。")


if __name__ == "__main__":
    main()
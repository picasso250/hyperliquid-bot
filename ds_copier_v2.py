import time
import json
import math
import example_utils
from hyperliquid.utils import constants

# --- 核心配置参数 ---
TARGET_USER_ADDRESS = "0xc20ac4dc4188660cbf555448af52694ca62b0734" # 您要跟单的目标地址 (DS)

# 我方仓位名义价值将是目标名义价值的该比例。例如 0.1 表示跟单目标 10% 的仓位规模
# 基于目标最小仓位 (XRP, $8,866) 和我方最小开仓名义价值 ($10) 计算：
# 10 / 8866 ≈ 0.001128。为增加价格波动和滑点的缓冲，设定为 0.0012
COPY_NOTIONAL_RATIO = 0.0012

# 仓位 SZI 大小同步的容忍度。如果我方 SZI 与目标 SZI 的比例差距超过此值，则平仓重开。
# 设置为 0.05 (5%) 可以减少因微小滑点或网络延迟造成的频繁平仓，从而节省手续费。
SZI_TOLERANCE_RATIO = 0.05

# 跟单的币种列表 (根据您提供的图片信息)
TARGET_COINS = ["XRP", "DOGE", "BTC", "ETH", "SOL", "BNB"]

LOOP_SLEEP_SECONDS = 30   # 每次循环之间的等待时间

# --- 辅助函数：从用户状态中提取特定币种的持仓信息 ---
def get_position_info(user_state, coin_name):
    """从完整的用户状态中，查找并返回指定币种的持仓详情，如果不存在则返回None"""
    asset_positions = user_state.get("assetPositions", [])
    for position in asset_positions:
        if position.get("position", {}).get("coin") == coin_name:
            # 确保仓位不是零
            if float(position["position"]["szi"]) != 0:
                return position["position"]
    return None

def process_coin(exchange, info, all_mids, my_address, target_user_state, my_user_state, coin):
    """处理单个币种的跟单逻辑"""
    print(f"\n--- 正在处理 {coin} ---")
    
    mid_price = float(all_mids.get(coin, 0))
    if mid_price == 0:
        print(f"❌ 警告: 无法获取 {coin} 的价格，跳过。")
        return

    target_position = get_position_info(target_user_state, coin)
    my_position = get_position_info(my_user_state, coin)

    # --- 1. 目标未持仓 ---
    if not target_position:
        print(f"🟡 目标未持有 {coin} 仓位。")
        if my_position:
            # 目标已平仓，我方也应平仓
            print(f"❗️ 目标已平仓，但我仍持有 {coin} 仓位。执行同步平仓！")
            close_result = exchange.market_close(coin)
            print(f"平仓结果: {json.dumps(close_result)}")
        return

    # --- 2. 目标已持仓 ---
    
    # 提取目标仓位信息
    target_direction_is_buy = float(target_position["szi"]) > 0
    target_leverage = int(target_position["leverage"]["value"])
    target_szi_abs = abs(float(target_position["szi"]))
    target_notional_value = target_szi_abs * mid_price
    
    # 计算我方应开仓的规模 (SZI)
    my_target_szi_abs = target_szi_abs * COPY_NOTIONAL_RATIO
    my_target_notional_value = my_target_szi_abs * mid_price
    
    # 容错：如果目标仓位过小，导致我方开仓规模低于最小名义价值，则跳过
    # 假设最小开仓名义价值为 $10
    MIN_NOTIONAL_VALUE = 10 
    if my_target_notional_value < MIN_NOTIONAL_VALUE:
        print(f"⚠️ 目标 {coin} 仓位按比例换算后价值 ${my_target_notional_value:,.2f}，低于最小开仓要求 ${MIN_NOTIONAL_VALUE}，跳过跟单。")
        # 确保我方没有残留仓位
        if my_position:
            print(f"❗️ 目标仓位过小无法跟单，但我仍持有 {coin} 仓位。执行平仓！")
            close_result = exchange.market_close(coin)
            print(f"平仓结果: {json.dumps(close_result)}")
        return

    # --- 2a. 我方未持仓 -> 执行开仓 ---
    if my_position is None:
        print(f"✅ 发现目标持有 {coin} {'多单' if target_direction_is_buy else '空单'} ({target_leverage}x)。")
        print(f"执行等比例跟单，目标价值: ${target_notional_value:,.2f}, 我方价值: ${my_target_notional_value:,.2f}")

        try:
            # 1. 设置与目标一致的杠杆
            exchange.update_leverage(target_leverage, coin)
            # 2. 执行开仓
            order_result = exchange.market_open(coin, target_direction_is_buy, my_target_szi_abs, None, 0.01)
            print(f"开仓结果: {json.dumps(order_result)}")
        except Exception as e:
            print(f"❌ 开仓失败: {e}")
            
    # --- 2b. 我方已持仓 -> 检查一致性 ---
    else:
        my_direction_is_buy = float(my_position["szi"]) > 0
        my_leverage = int(my_position["leverage"]["value"])
        my_szi_abs = abs(float(my_position["szi"]))

        # 检查方向和杠杆是否一致
        if my_direction_is_buy == target_direction_is_buy and my_leverage == target_leverage:
            # ✅ 方向和杠杆一致 -> 检查仓位大小是否在容忍范围内
            szi_diff = abs(my_szi_abs - my_target_szi_abs)
            szi_tolerance = my_target_szi_abs * SZI_TOLERANCE_RATIO

            if szi_diff <= szi_tolerance:
                # ✅ 仓位大小也一致 -> 监控中
                my_position_value = my_szi_abs * mid_price
                print(f"🟢 {coin} 持仓正常，与目标 ({target_leverage}x, 价值${target_notional_value:,.2f}) 一致。")
                print(f"   我方仓位价值: ${my_position_value:,.2f}。SZI 差异 ({szi_diff:.5f}) 在容忍范围 ({szi_tolerance:.5f}) 内。")
            else:
                # ❌ 仓位大小不匹配 -> 先平仓，下一轮再重开
                print(f"❗️ {coin} 仓位大小不一致！(我: {my_szi_abs:.5f}, 目标应为: {my_target_szi_abs:.5f})")
                print(f"   SZI 差异 ({szi_diff:.5f}) 超过容忍范围 ({szi_tolerance:.5f})。执行平仓以同步...")
                close_result = exchange.market_close(coin)
                print(f"平仓结果: {json.dumps(close_result)}")

        else:
            # ❌ 方向或杠杆不一致 -> 先平仓，下一轮再重开
            print(f"❗️ {coin} 策略不一致！(我: {'多' if my_direction_is_buy else '空'}{my_leverage}x, "
                  f"目标: {'多' if target_direction_is_buy else '空'}{target_leverage}x)")
            print("为同步策略，执行平仓...")
            close_result = exchange.market_close(coin)
            print(f"平仓结果: {json.dumps(close_result)}")


def main():
    # --- 1. 初始化 ---
    my_address, info, exchange = example_utils.setup(base_url=constants.MAINNET_API_URL)
    print("--- DS 完全跟单机器人 V2 ---")
    print(f"我的账户地址: {my_address}")
    print(f"跟单目标地址: {TARGET_USER_ADDRESS}")
    print(f"策略: 跟随目标 {TARGET_COINS} 的所有仓位，按目标 {COPY_NOTIONAL_RATIO*100}% 的规模开仓。")
    print(f"同步容忍度: {SZI_TOLERANCE_RATIO*100}%")
    print("-------------------------------------------------------")

    try:
        # --- 2. 进入主循环 ---
        while True:
            print(f"\n=======================================================")
            print(f"----- {time.strftime('%Y-%m-%d %H:%M:%S')} - 启动新一轮同步 -----")
            
            # --- a. 数据采集 ---
            try:
                print("正在获取最新数据...")
                all_mids = info.all_mids()
                target_user_state = info.user_state(TARGET_USER_ADDRESS)
                my_user_state = info.user_state(my_address)
            except Exception as e:
                print(f"❌ 数据采集失败: {e}，等待 {LOOP_SLEEP_SECONDS} 秒后重试。")
                time.sleep(LOOP_SLEEP_SECONDS)
                continue

            # --- b. 逐个币种处理 ---
            for coin in TARGET_COINS:
                process_coin(exchange, info, all_mids, my_address, target_user_state, my_user_state, coin)
            
            # --- c. 休眠 ---
            print(f"\n=======================================================")
            print(f"等待 {LOOP_SLEEP_SECONDS} 秒后进入下一轮...")
            time.sleep(LOOP_SLEEP_SECONDS)

    except KeyboardInterrupt:
        print("\n检测到手动中断 (Ctrl+C)，机器人正在关闭...")
    except Exception as e:
        print(f"\n❌ 发生未知错误: {e}")
    finally:
        print("关闭后台WebSocket连接...")
        if 'info' in locals() and info.ws_manager:
            info.ws_manager.close()
        print("程序已退出。")


if __name__ == "__main__":
    main()
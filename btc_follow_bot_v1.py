import time
import json
import example_utils
from hyperliquid.utils import constants

# --- 核心配置参数 ---
TARGET_USER_ADDRESS = "0xc20ac4dc4188660cbf555448af52694ca62b0734" # 您要跟单的目标地址
MY_INVESTMENT_USD = 14.0  # 每次跟单的初始投入金额 (USD)
TAKE_PROFIT_USD = 21.0    # 止盈目标 (USD)
COIN = "BTC"              # 只跟单这个币种
LOOP_SLEEP_SECONDS = 30   # 每次循环之间的等待时间

# --- 辅助函数：从用户状态中提取特定币种的持仓信息 ---
def get_position_info(user_state, coin_name):
    """从完整的用户状态中，查找并返回指定币种的持仓详情，如果不存在则返回None"""
    asset_positions = user_state.get("assetPositions", [])
    for position in asset_positions:
        if position.get("position", {}).get("coin") == coin_name:
            return position["position"]
    return None

def main():
    # --- 1. 初始化 ---
    my_address, info, exchange = example_utils.setup(base_url=constants.MAINNET_API_URL)
    print("--- BTC跟单机器人 V1 ---")
    print(f"我的账户地址: {my_address}")
    print(f"跟单目标地址: {TARGET_USER_ADDRESS}")
    print(f"策略: 跟随目标的 {COIN} 仓位，投入 ${MY_INVESTMENT_USD}，目标盈利 ${TAKE_PROFIT_USD}。")
    print("-------------------------------------------------------")

    try:
        # --- 2. 进入主循环 ---
        while True:
            print(f"\n----- {time.strftime('%Y-%m-%d %H:%M:%S')} -----")
            # --- a. 数据采集 ---
            print("正在获取最新数据...")
            all_mids = info.all_mids()
            target_user_state = info.user_state(TARGET_USER_ADDRESS)
            my_user_state = info.user_state(my_address)
            
            btc_price = float(all_mids.get(COIN, 0))
            if btc_price == 0:
                print(f"❌ 警告: 无法获取 {COIN} 的价格，跳过本轮循环。")
                time.sleep(LOOP_SLEEP_SECONDS)
                continue

            target_btc_position = get_position_info(target_user_state, COIN)
            my_btc_position = get_position_info(my_user_state, COIN)

            # --- b. 目标有效性检查 ---
            if not target_btc_position:
                print(f"🟡 目标当前未持有 {COIN} 仓位。继续等待...")
                if my_btc_position:
                    print(f"❗️ 警告: 目标已平仓，但我仍持有 {COIN} 仓位。为安全起见，执行平仓！")
                    close_result = exchange.market_close(COIN)
                    print(f"平仓结果: {json.dumps(close_result)}")
                time.sleep(LOOP_SLEEP_SECONDS)
                continue

            # --- c. 我的状态评估 ---
            target_direction_is_buy = float(target_btc_position["szi"]) > 0
            target_leverage = int(target_btc_position["leverage"]["value"])

            if my_btc_position is None:
                # --- 情况一：我没有BTC仓位 -> 跟单开仓 ---
                print(f"✅ 发现目标持有 {COIN} {'多单' if target_direction_is_buy else '空单'} (杠杆: {target_leverage}x)。")
                print(f"执行跟单，开立价值 ${MY_INVESTMENT_USD} 的仓位...")

                sz = round(MY_INVESTMENT_USD / btc_price, 5)
                
                # 设置与目标一致的杠杆
                exchange.update_leverage(target_leverage, COIN)
                # 执行开仓
                order_result = exchange.market_open(COIN, target_direction_is_buy, sz, None, 0.01)
                print(f"开仓结果: {json.dumps(order_result)}")
            
            else:
                # --- 情况二：我有BTC仓位 -> 监控或调整 ---
                my_direction_is_buy = float(my_btc_position["szi"]) > 0
                my_leverage = int(my_btc_position["leverage"]["value"])
                
                # 一致性检查
                if my_direction_is_buy == target_direction_is_buy and my_leverage == target_leverage:
                    # ✅ 一致 -> 监控盈利
                    my_position_size = abs(float(my_btc_position["szi"]))
                    my_position_value = my_position_size * btc_price
                    print(f"🟢 持仓正常，与目标一致。当前仓位价值: ${my_position_value:.2f}")

                    if my_position_value >= TAKE_PROFIT_USD:
                        print(f"🎉 达到止盈目标! (${my_position_value:.2f} >= ${TAKE_PROFIT_USD})，执行市价平仓！")
                        close_result = exchange.market_close(COIN)
                        print(f"平仓结果: {json.dumps(close_result)}")
                        print("任务完成，机器人退出。")
                        break # 退出 while 循环，结束脚本
                    
                else:
                    # ❌ 不一致 -> 平掉现有仓位
                    print(f"❗️ 仓位不一致！(我: {'多' if my_direction_is_buy else '空'}{my_leverage}x, "
                          f"目标: {'多' if target_direction_is_buy else '空'}{target_leverage}x)")
                    print("为同步策略，执行平仓...")
                    close_result = exchange.market_close(COIN)
                    print(f"平仓结果: {json.dumps(close_result)}")
            
            # --- d. 休眠 ---
            print(f"等待 {LOOP_SLEEP_SECONDS} 秒后进入下一轮...")
            time.sleep(LOOP_SLEEP_SECONDS)

    except KeyboardInterrupt:
        print("\n检测到手动中断 (Ctrl+C)，机器人正在关闭...")
    except Exception as e:
        print(f"\n❌ 发生未知错误: {e}")
    finally:
        print("关闭后台WebSocket连接...")
        info.ws_manager.close()
        print("程序已退出。")


if __name__ == "__main__":
    main()
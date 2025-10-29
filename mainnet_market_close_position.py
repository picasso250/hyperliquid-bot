import json
import time

import example_utils
from hyperliquid.utils import constants

def main():
    # --- 需要平仓的目标币种 ---
    COIN_TO_CLOSE = "BTC" 

    print(f"--- Hyperliquid主网市价平仓脚本 ---")
    print(f"警告: 此脚本将在主网 MAINNET 对 {COIN_TO_CLOSE} 的现有仓位执行市价平仓。")
    print(f"成本: 这笔交易会真实成交并产生手续费。")
    print("-------------------------------------------------------")
    
    # 在执行真实操作前，给用户一个确认时间
    for i in range(5, 0, -1):
        print(f"{i}秒后将执行平仓操作... (按 Ctrl+C 中止)")
        time.sleep(1)

    # --- 1. 初始化与主网的连接 ---
    address, info, exchange = example_utils.setup(base_url=constants.MAINNET_API_URL, skip_ws=True)
    print(f"\n步骤1: 成功连接到主网账户: {address}")

    # --- 2. 执行市价平仓 ---
    # market_close 是一个非常方便的函数。
    # 它会自动检测你是多头还是空头，然后执行一笔相反的市价单来关闭你的仓位。
    print(f"\n步骤2: 尝试市价平掉所有 {COIN_TO_CLOSE} 的仓位...")
    close_result = exchange.market_close(COIN_TO_CLOSE)

    # --- 3. 打印最终成交结果 ---
    print("\n--- 最终平仓结果 ---")
    if close_result["status"] == "ok":
        print("✅ 平仓订单已成功提交至服务器并成交!")
        try:
            # 平仓本质上也是一个 'filled' 状态
            status = close_result["response"]["data"]["statuses"][0]
            if "filled" in status:
                filled = status["filled"]
                direction = "多头" if filled["side"] == "B" else "空头" # 'B' for Buy, 'A' for Ask/Sell

                print(f"  - 订单方向: 市价 {'卖出' if direction == '多头' else '买入'} 平仓")
                print(f"  - 订单ID (OID): {filled['oid']}")
                print(f"  - 平均成交价: ${filled['avgPx']}")
                print(f"  - 平仓数量: {filled['totalSz']} {COIN_TO_CLOSE}")

                print("\n验证操作:")
                print("1. 请登录 https://app.hyperliquid.xyz。")
                print(f"2. 在 '持仓' (Positions) 面板中，您应该看不到任何 {COIN_TO_CLOSE} 的仓位了。")
            elif "error" in status:
                print(f"❌ 订单提交后发生错误: {status['error']}")

        except (KeyError, IndexError) as e:
            print(f"❌ 解析服务器响应时发生意外错误: {e}")
            print("原始响应:", json.dumps(close_result, indent=2))
    else:
        print("❌ 订单提交失败!")
        print("错误信息:", json.dumps(close_result, indent=2))
    
    # 脚本结束，但ws连接可能仍在后台，需要手动停止程序
    print("\n平仓脚本执行完毕。")


if __name__ == "__main__":
    main()
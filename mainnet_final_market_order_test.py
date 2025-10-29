import json
import time

import example_utils
from hyperliquid.utils import constants


def main():
    # --- 实盘测试核心参数 ---
    COIN = "BTC"
    LEVERAGE = 5
    USD_AMOUNT = 10.0  # 更新：满足交易所最低 $10 的订单价值要求
    IS_BUY = True  # True = 买入开多, False = 卖出开空
    IS_CROSS_MARGIN = False # 更新：False 代表使用 "逐仓模式 (Isolated Margin)"

    print("--- Hyperliquid主网最终市价单测试脚本 (逐仓模式) ---")
    print(f"警告: 此脚本将在主网 MAINNET 执行一笔真实的市价单交易。")
    print(f"模式: {'全仓 (Cross)' if IS_CROSS_MARGIN else '逐仓 (Isolated)'} 模式")
    print(f"目标: 为 {COIN} 设置 {LEVERAGE}x 杠杆, 并开立一个价值约 ${USD_AMOUNT} 的多单仓位。")
    print(f"成本: 这笔交易会真实成交并产生手续费。")
    print("-------------------------------------------------------")
    time.sleep(3)  # 给用户3秒时间阅读警告信息

    # --- 1. 初始化与主网的连接 ---
    address, info, exchange = example_utils.setup(base_url=constants.MAINNET_API_URL, skip_ws=True)
    print(f"\n步骤1: 成功连接到主网账户: {address}")

    # --- 2. 设置杠杆和保证金模式 ---
    print(f"\n步骤2: 尝试将 {COIN} 的杠杆设置为 {LEVERAGE}x ({'全仓' if IS_CROSS_MARGIN else '逐仓'}模式)...")
    leverage_result = exchange.update_leverage(LEVERAGE, COIN, IS_CROSS_MARGIN)
    if leverage_result["status"] == "ok":
        print(f"✅ 杠杆及保证金模式设置成功。")
    else:
        print(f"❌ 杠杆设置失败: {json.dumps(leverage_result, indent=2)}")
        # 如果设置失败，可能因为已有全仓仓位，此处只打印警告而不退出
        print("警告: 如果您已有该币种的全仓仓位，则无法切换到逐仓。脚本将继续尝试下单...")


    # --- 3. 获取市价并计算下单数量 ---
    print(f"\n步骤3: 获取 {COIN} 的当前市场价格以计算下单数量...")
    all_mids = info.all_mids()
    try:
        price = float(all_mids[COIN])
        print(f"获取到 {COIN} 当前的市场中间价为: ${price}")
    except KeyError:
        print(f"❌ 错误: 无法从API获取 {COIN} 的价格。脚本终止。")
        return

    # 根据投入的USD金额计算币的数量 (sz)
    sz = round(USD_AMOUNT / price, 5)
    print(f"根据投入的 ${USD_AMOUNT} 和当前价格，计算出下单数量为: {sz} {COIN}")

    # --- 4. 执行市价开仓 ---
    print(f"\n步骤4: 尝试市价 {'买入开多' if IS_BUY else '卖出开空'} {sz} {COIN}...")
    order_result = exchange.market_open(COIN, IS_BUY, sz, None, 0.01)

    # --- 5. 打印最终成交结果 ---
    print("\n--- 最终成交结果 ---")
    if order_result["status"] == "ok":
        print("✅ 市价单已成功提交至服务器并成交!")
        try:
            for status in order_result["response"]["data"]["statuses"]:
                if "filled" in status:
                    filled = status["filled"]
                    print(f"  - 订单ID (OID): {filled['oid']}")
                    print(f"  - 平均成交价: ${filled['avgPx']}")
                    print(f"  - 成交数量: {filled['totalSz']} {COIN}")
                    print(f"  - 手续费: {filled['fee']} USDC")
                    print("\n验证操作:")
                    print("1. 请登录 https://app.hyperliquid.xyz。")
                    print(f"2. 在 '持仓' (Positions) 面板中，您应该能看到一个新的 BTC 多头仓位。")
                    print("3. 请注意观察该仓位的 '保证金' 和 '预估强平价'，以确认其为逐仓模式。")
                    break
                elif "error" in status:
                    print(f"❌ 订单提交后发生错误: {status['error']}")
        except (KeyError, IndexError):
            print("❌ 无法从服务器响应中解析成交状态。")
            print("原始响应:", json.dumps(order_result, indent=2))
    else:
        print("❌ 订单提交失败!")
        print("错误信息:", json.dumps(order_result, indent=2))


if __name__ == "__main__":
    main()
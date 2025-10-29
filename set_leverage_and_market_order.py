import json
import time

import example_utils
from hyperliquid.utils import constants


def main():
    # --- 配置参数 ---
    COIN = "ETH"
    LEVERAGE = 5
    USD_AMOUNT = 10  # 计划投入的USD金额
    IS_BUY = True  # True 表示开多单, False 表示开空单

    # --- 1. 初始化连接 ---
    address, info, exchange = example_utils.setup(constants.TESTNET_API_URL, skip_ws=True)
    print(f"成功连接到账户: {address}")

    # --- 2. 设置杠杆 ---
    print(f"\n步骤1: 尝试将 {COIN} 的杠杆设置为 {LEVERAGE}x (全仓模式)...")
    # 默认使用全仓模式 (is_cross=True)
    leverage_result = exchange.update_leverage(LEVERAGE, COIN)
    print("设置杠杆结果:", json.dumps(leverage_result, indent=2))

    # --- 3. 获取价格并计算下单大小 ---
    print(f"\n步骤2: 获取 {COIN} 的市场中间价以计算下单数量...")
    all_mids = info.all_mids()
    try:
        price = float(all_mids[COIN])
        print(f"{COIN} 当前价格: ${price}")
    except KeyError:
        print(f"错误: 无法获取 {COIN} 的价格。")
        return

    # 根据投入的USD金额计算币的数量 (sz)
    # Hyperliquid API要求sz为币本位数量
    sz = round(USD_AMOUNT / price, 5)  # 保留5位小数以获得合适的精度
    print(f"根据投入的 ${USD_AMOUNT} 和当前价格，计算出下单数量为: {sz} {COIN}")

    # --- 4. 执行市价开仓 ---
    print(f"\n步骤3: 尝试市价 {'买入开多' if IS_BUY else '卖出开空'} {sz} {COIN}...")
    # 使用0.01 (1%) 的滑点保护
    order_result = exchange.market_open(COIN, IS_BUY, sz, None, 0.01)

    # --- 5. 打印订单结果 ---
    if order_result["status"] == "ok":
        for status in order_result["response"]["data"]["statuses"]:
            try:
                filled = status["filled"]
                print(f'订单 #{filled["oid"]} 成交! 成交数量: {filled["totalSz"]}, 平均成交价: ${filled["avgPx"]}')
            except KeyError:
                print(f'错误或未成交: {status.get("error", "未知错误")}')
    else:
        print("下单失败:", json.dumps(order_result, indent=2))


if __name__ == "__main__":
    main()
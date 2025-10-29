import json
import time

import example_utils
from hyperliquid.utils import constants


def main():
    # --- 安全测试核心参数 ---
    COIN = "BTC"
    LEVERAGE = 5
    USD_AMOUNT = 10.0  # 我们希望挂单的名义价值
    SAFE_BUY_PRICE = 111000.0  # 一个远低于当前市价的安全价格，确保不会成交
    IS_BUY = True  # True = 买入开多, False = 卖出开空

    print("--- Hyperliquid主网安全测试脚本 ---")
    print(f"警告: 此脚本将连接到主网 MAINNET。")
    print(f"目标: 在主网为 {COIN} 设置 {LEVERAGE}x 杠杆, 并提交一个价值 ${USD_AMOUNT} 的安全限价买单。")
    print(f"安全价格设置为: ${SAFE_BUY_PRICE}，此订单预期不会被成交。")
    print("------------------------------------")
    time.sleep(3)  # 给用户3秒时间阅读警告信息

    # --- 1. 初始化与主网的连接 ---
    # 我们明确指定 base_url 为 MAINNET_API_URL
    address, info, exchange = example_utils.setup(base_url=constants.MAINNET_API_URL, skip_ws=True)
    print(f"\n步骤1: 成功连接到主网账户: {address}")

    # --- 2. 设置杠杆 ---
    print(f"\n步骤2: 尝试将 {COIN} 的杠杆设置为 {LEVERAGE}x (全仓模式)...")
    leverage_result = exchange.update_leverage(LEVERAGE, COIN)
    if leverage_result["status"] == "ok":
        print(f"✅ 杠杆设置成功。")
    else:
        print(f"❌ 杠杆设置失败: {json.dumps(leverage_result, indent=2)}")
        return  # 如果失败则终止脚本

    # --- 3. 计算下单数量 (sz) ---
    # API要求sz为币本位数量
    sz = round(USD_AMOUNT / SAFE_BUY_PRICE, 5)  # BTC精度要求较高，保留5位小数
    print(f"\n步骤3: 计算下单数量...")
    print(f"名义价值 ${USD_AMOUNT} / 安全价格 ${SAFE_BUY_PRICE} = {sz} {COIN}")

    # --- 4. 提交安全的限价单 ---
    print(f"\n步骤4: 提交限价 {'买单' if IS_BUY else '卖单'}...")
    # 参考 basic_order.py 的实现, 使用 {"limit": {"tif": "Gtc"}}
    # Gtc = Good 'til Canceled, 意味着订单会一直有效直到被手动取消
    order_type = {"limit": {"tif": "Gtc"}}
    order_result = exchange.order(COIN, IS_BUY, sz, SAFE_BUY_PRICE, order_type)

    print("\n--- 最终结果 ---")
    if order_result["status"] == "ok":
        print("✅ 订单已成功提交至服务器!")
        # 提取并打印关键信息
        try:
            status = order_result["response"]["data"]["statuses"][0]
            if "resting" in status:
                oid = status["resting"]["oid"]
                print(f"  - 订单ID (OID): {oid}")
                print(f"  - 状态: Resting (已在订单簿中挂单)")
                print("\n验证操作:")
                print("1. 请登录 https://app.hyperliquid.xyz。")
                print(f"2. 在交易界面的 '订单' 面板中，您应该能看到一个为 {COIN} 设置的、价格为 ${SAFE_BUY_PRICE} 的有效订单。")
                print("3. 测试完成后，请记得手动取消此订单。")
            else:
                 print(f"订单未挂起，状态未知: {status}")
        except (KeyError, IndexError):
            print("❌ 无法从服务器响应中解析订单状态。")
            print("原始响应:", json.dumps(order_result, indent=2))
    else:
        print("❌ 订单提交失败!")
        print("错误信息:", json.dumps(order_result, indent=2))


if __name__ == "__main__":
    main()
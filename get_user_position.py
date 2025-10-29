import example_utils
from hyperliquid.utils import constants

# 目标地址，从您的 addr.md 文件中获取
TARGET_USER_ADDRESS = "0xc20ac4dc4188660cbf555448af52694ca62b0734"

def main():
    # 关键修正：我们使用 example_utils.setup() 来进行初始化，这才是官方示例中的标准做法。
    # 它会处理好账户、签名、API配置等所有细节。
    # 因为目标地址是主网地址，所以我们这里必须使用 MAINNET_API_URL。
    # setup 函数返回的 address 是我们自己本地钱包的地址，这里用下划线 _ 忽略它。
    _, info, _ = example_utils.setup(constants.MAINNET_API_URL)

    print(f"正在查询地址: {TARGET_USER_ADDRESS} 的持仓信息...")

    # 核心函数不变：调用 user_state 来获取指定地址的完整状态
    try:
        user_state = info.user_state(TARGET_USER_ADDRESS)
    except Exception as e:
        print(f"查询失败，发生错误: {e}")
        print("请检查：")
        print("1. 目标地址是否正确。")
        print("2. 您的网络是否可以访问 Hyperliquid 主网 API。")
        print("3. config.json 文件中的设置是否正确（尽管查询公开信息通常不依赖私钥）。")
        return

    # 从返回结果中提取持仓部分 (assetPositions)
    positions = user_state.get("assetPositions")

    if not positions:
        print("该地址当前没有持仓，或返回数据为空。")
        print("完整返回数据:", user_state)
        return

    print("-----------------------------------------")
    print(f"查询成功！找到 {len(positions)} 个持仓:")
    print("-----------------------------------------")

    # 遍历并打印每一个持仓的详细信息
    for position in positions:
        position_details = position.get("position", {})
        coin = position_details.get("coin")
        entry_price = position_details.get("entryPx")
        leverage = position_details.get("leverage", {}).get("value")
        position_size = position_details.get("szi")
        unrealized_pnl = position_details.get("unrealizedPnl")
        
        # 判断是多头还是空头
        direction = "多头" if float(position_size) > 0 else "空头"

        print(f"币种: {coin}")
        print(f"  方向: {direction}")
        print(f"  仓位大小: {position_size} {coin}")
        print(f"  开仓均价: ${entry_price}")
        print(f"  杠杆倍数: {leverage}x")
        print(f"  未实现盈亏: ${unrealized_pnl}")
        print("---")

if __name__ == "__main__":
    main()
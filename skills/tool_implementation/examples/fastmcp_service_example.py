"""
FastMCP Tool实现示例 - 共享单车客服场景
========================================

本文件展示基于FastMCP框架的MCP Tool实现模式。
提取自: mcp-benchmark/release/scenarios/bikeshare/env/bikeshare_service.py

核心模式：
1. 使用 FastMCP 创建服务实例
2. 使用 @mcp.tool() 装饰器定义工具
3. 使用 Annotated[type, Field(...)] 定义参数描述
4. 全局数据存储 + 工具函数直接操作
"""

import json
import os
from typing import Any, Dict, Annotated
from pydantic import Field
from datetime import datetime
from fastmcp import FastMCP

# =========================================
# 1. 服务初始化
# =========================================

# 创建MCP服务实例
mcp = FastMCP(name="bikeshare_service")

# 全局数据存储
FOLDER_PATH = None
data = None

# 固定系统时间（评测场景使用）
FIXED_SYSTEM_TIME = datetime(2025, 7, 3, 14, 0, 0)


def get_current_time() -> datetime:
    """获取当前系统时间（评测场景使用固定时间）"""
    return FIXED_SYSTEM_TIME


# =========================================
# 2. 数据加载和持久化
# =========================================

def load_data() -> Dict[str, Any]:
    """
    加载JSONL格式的数据文件

    数据文件约定：
    - users.jsonl: 用户数据，主键 uuid
    - orders.jsonl: 订单数据，主键 order_guid
    - bikes.jsonl: 单车数据，主键 bike_id
    """
    global data

    users_data = {}
    orders_data = {}
    bikes_data = {}

    file_configs = [
        ("users.jsonl", users_data, "uuid"),
        ("orders.jsonl", orders_data, "order_guid"),
        ("bikes.jsonl", bikes_data, "bike_id"),
    ]

    for filename, data_dict, primary_key in file_configs:
        file_path = os.path.join(FOLDER_PATH, filename)
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        record = json.loads(line.strip())
                        key = record.get(primary_key)
                        if key:
                            data_dict[key] = record

    return {"users": users_data, "orders": orders_data, "bikes": bikes_data}


def save_data_to_file(data_type: str, data_dict: dict) -> bool:
    """保存数据到JSONL文件"""
    file_mapping = {
        "users": "users.jsonl",
        "orders": "orders.jsonl",
        "bikes": "bikes.jsonl",
    }

    try:
        file_path = os.path.join(FOLDER_PATH, file_mapping[data_type])
        with open(file_path, "w", encoding="utf-8") as f:
            for record in data_dict.values():
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True
    except Exception as e:
        print(f"Error saving {data_type}: {e}")
        return False


# =========================================
# 3. Tool定义 - 查询类（只读）
# =========================================

@mcp.tool()
def get_user_info(user_uuid: str) -> Dict[str, Any]:
    """
    获取用户详细信息

    Args:
        user_uuid: 用户UUID

    Returns:
        用户信息字典
    """
    global data
    users = data.get("users", {})

    if user_uuid not in users:
        return {"error": f"用户 {user_uuid} 未找到"}

    return users[user_uuid]


@mcp.tool()
def get_order_details(
    order_guid: Annotated[str, Field(description="订单GUID")]
) -> Dict[str, Any]:
    """
    获取订单详细信息

    使用Annotated为参数添加描述，帮助Agent理解参数含义
    """
    global data
    orders = data.get("orders", {})

    if order_guid not in orders:
        return {"error": f"订单 {order_guid} 未找到"}

    return orders[order_guid]


# =========================================
# 4. Tool定义 - 操作类（写入）
# =========================================

@mcp.tool()
def adjust_order_fee(
    order_guid: Annotated[str, Field(description="订单GUID")],
    new_fee: Annotated[float, Field(description="新的费用金额")],
    reason: Annotated[str, Field(description="调整原因")] = "客服手动调整"
) -> Dict[str, Any]:
    """
    调整订单费用

    操作类Tool的标准模式：
    1. 验证输入参数
    2. 执行业务逻辑
    3. 持久化数据
    4. 返回标准格式结果
    """
    global data
    orders = data.get("orders", {})

    # 验证
    if order_guid not in orders:
        return {"error": f"订单不存在: {order_guid}"}

    order = orders[order_guid]
    old_fee = order.get("fee", 0.0)

    # 执行操作
    order["fee"] = new_fee
    order["fee_adjustment_reason"] = reason

    # 持久化
    if save_data_to_file("orders", data["orders"]):
        return {
            "status": "success",
            "data": {
                "order_guid": order_guid,
                "old_fee": old_fee,
                "new_fee": new_fee,
                "reason": reason,
                "message": "订单费用已成功调整"
            }
        }
    else:
        # 回滚
        order["fee"] = old_fee
        order.pop("fee_adjustment_reason", None)
        return {"error": "保存失败，操作已回滚"}


@mcp.tool()
def issue_coupon(
    user_uuid: Annotated[str, Field(description="用户UUID")],
    coupon_type: Annotated[str, Field(
        description="优惠券类型",
        json_schema_extra={"examples": ["VIP专享券", "用户关怀券"]}
    )],
    value: Annotated[float, Field(description="优惠券面额")]
) -> Dict[str, Any]:
    """
    发放优惠券给用户

    展示如何使用json_schema_extra提供参数示例
    """
    global data
    users = data.get("users", {})

    if user_uuid not in users:
        return {"error": f"用户不存在: {user_uuid}"}

    user = users[user_uuid]
    current_time = get_current_time()

    # 创建优惠券
    new_coupon = {
        "coupon_id": f"c_{int(current_time.timestamp())}",
        "type": coupon_type,
        "value": value,
        "expiry_date": "2025-08-03T23:59:59Z"
    }

    # 添加到用户
    if "coupons" not in user:
        user["coupons"] = []
    user["coupons"].append(new_coupon)

    # 持久化
    if save_data_to_file("users", data["users"]):
        return {
            "status": "success",
            "data": {
                "coupon_id": new_coupon["coupon_id"],
                "user_uuid": user_uuid,
                "message": "优惠券已成功发放"
            }
        }
    else:
        user["coupons"].pop()
        return {"error": "保存失败，操作已回滚"}


# =========================================
# 5. 服务启动
# =========================================

def main():
    """主函数"""
    global FOLDER_PATH, data

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("data_path", nargs="?", default="./")
    args = parser.parse_args()

    FOLDER_PATH = os.path.abspath(args.data_path)
    data = load_data()

    print(f"数据加载完成: {len(data['users'])} users, {len(data['orders'])} orders")

    # 启动MCP服务器（stdio模式）
    mcp.run()


if __name__ == "__main__":
    main()

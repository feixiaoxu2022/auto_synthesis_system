---
name: tool-implementation
description: 实现Agent评测场景的业务工具(MCP Tools)。当需要为新场景创建工具、理解工具设计原则时使用此技能。基于FastMCP框架。
---

# Tool实现指南

## 核心原则：Agent责任制

**工具应该"傻一点"，只完成基本功能。**

| 正确做法 | 错误做法 |
|---------|---------|
| 基本CRUD操作 | 复合业务操作 |
| 无业务逻辑 | 内置规则校验 |
| 简单成功/失败 | 智能推荐建议 |
| 让Agent决策 | 工具自动决策 |

---

## 框架：FastMCP

开源版使用 [FastMCP](https://github.com/jlowin/fastmcp) 框架，通过装饰器定义Tool。

### 基本结构

```python
from typing import Dict, Any, Annotated
from pydantic import Field
from fastmcp import FastMCP

# 1. 创建服务实例
mcp = FastMCP(name="my_service")

# 2. 全局数据存储
data = None

# 3. 定义Tool
@mcp.tool()
def get_user(user_id: str) -> Dict[str, Any]:
    """获取用户信息"""
    if user_id not in data["users"]:
        return {"error": f"用户 {user_id} 未找到"}
    return data["users"][user_id]

# 4. 启动服务
if __name__ == "__main__":
    mcp.run()
```

---

## Tool定义模式

### 查询类Tool（只读）

```python
@mcp.tool()
def get_order_details(
    order_guid: Annotated[str, Field(description="订单GUID")]
) -> Dict[str, Any]:
    """获取订单详细信息"""
    orders = data.get("orders", {})

    if order_guid not in orders:
        return {"error": f"订单 {order_guid} 未找到"}

    return orders[order_guid]
```

### 操作类Tool（写入）

```python
@mcp.tool()
def adjust_order_fee(
    order_guid: Annotated[str, Field(description="订单GUID")],
    new_fee: Annotated[float, Field(description="新的费用金额")],
    reason: Annotated[str, Field(description="调整原因")] = "手动调整"
) -> Dict[str, Any]:
    """调整订单费用"""
    orders = data.get("orders", {})

    # 1. 验证
    if order_guid not in orders:
        return {"error": f"订单不存在: {order_guid}"}

    order = orders[order_guid]
    old_fee = order.get("fee", 0.0)

    # 2. 执行操作
    order["fee"] = new_fee
    order["fee_adjustment_reason"] = reason

    # 3. 持久化
    if save_data_to_file("orders", data["orders"]):
        return {
            "status": "success",
            "data": {
                "order_guid": order_guid,
                "new_fee": new_fee,
                "message": "费用已调整"
            }
        }
    else:
        # 4. 回滚
        order["fee"] = old_fee
        return {"error": "保存失败，操作已回滚"}
```

---

## 参数定义

使用 `Annotated` + `Field` 为参数添加描述：

```python
from typing import Annotated
from pydantic import Field

@mcp.tool()
def issue_coupon(
    user_uuid: Annotated[str, Field(description="用户UUID")],
    coupon_type: Annotated[str, Field(
        description="优惠券类型",
        json_schema_extra={"examples": ["VIP专享券", "关怀券"]}
    )],
    value: Annotated[float, Field(description="优惠券面额")]
) -> Dict[str, Any]:
    ...
```

---

## 数据持久化模式

### JSONL文件存储

```python
FOLDER_PATH = None  # 运行时设置

def load_data() -> Dict[str, Any]:
    """加载JSONL数据文件"""
    users = {}
    file_path = os.path.join(FOLDER_PATH, "users.jsonl")

    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                record = json.loads(line.strip())
                users[record["uuid"]] = record

    return {"users": users}

def save_data_to_file(data_type: str, data_dict: dict) -> bool:
    """保存数据到JSONL文件"""
    file_path = os.path.join(FOLDER_PATH, f"{data_type}.jsonl")

    with open(file_path, "w", encoding="utf-8") as f:
        for record in data_dict.values():
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return True
```

---

## 服务启动

```python
def main():
    global FOLDER_PATH, data

    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("data_path", nargs="?", default="./")
    args = parser.parse_args()

    FOLDER_PATH = os.path.abspath(args.data_path)
    data = load_data()

    # stdio模式启动
    mcp.run()

if __name__ == "__main__":
    main()
```

---

## servers.json配置

```json
{
  "mcpServers": {
    "bikeshare_service": {
      "command": "python",
      "args": ["env/bikeshare_service.py", "./"]
    }
  }
}
```

---

## 设计检查清单

- [ ] 工具只做CRUD，不做业务判断
- [ ] 使用 `@mcp.tool()` 装饰器定义
- [ ] 参数使用 `Annotated[type, Field(...)]` 添加描述
- [ ] 错误返回 `{"error": "..."}`
- [ ] 成功返回 `{"status": "success", "data": {...}}`
- [ ] 写操作后持久化数据
- [ ] 持久化失败时回滚

---

## Reference Files

| 文件 | 说明 |
|-----|------|
| [fastmcp_service_example.py](examples/fastmcp_service_example.py) | 完整的FastMCP服务示例 |

> 完整实现参考：`mcp-benchmark/release/scenarios/*/env/*.py`

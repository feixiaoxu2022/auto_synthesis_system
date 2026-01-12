# Tool设计原则详解

## Agent责任制设计原则

### 核心理念

工具应该"傻一点"，只完成基本功能。评测框架测试的是**Agent的业务推理能力**，而不是工具的智能程度。

### 责任分工

| 角色 | 责任范围 |
|-----|---------|
| **Agent** | 业务逻辑判断、条件检查、多工具协调、错误处理、决策推理 |
| **Tool** | 数据操作、状态更新、基础验证、结果返回 |

### 设计原则

1. **基本CRUD操作**: 工具只提供Create、Read、Update、Delete基础功能
2. **无业务逻辑**: 工具内部不做非必要的业务规则检查和验证
3. **无复杂判断**: 避免在工具中实现复杂的业务逻辑决策
4. **简单成功/失败**: 工具返回简单的成功/失败状态，不做智能推荐

### 避免的反模式

- **过度智能**: 不要"把饭喂到嘴边"，让Agent自己进行业务推理
- **复合操作**: 不要将多个业务步骤合并成一个工具调用
- **自动化决策**: 不要让工具自动做出业务决策

---

## 正确示例 vs 错误示例

### 示例1：预约创建

```python
# 错误 - 过度智能的工具
def smart_appointment_service(patient_id, appointment_time):
    # 工具内部做了太多智能判断
    if patient.membership_tier == "vip":
        priority_booking()
    if check_conflict_automatically():
        suggest_alternative_time()
    if need_medical_records():
        auto_fetch_records()
    return "智能预约已完成"

# 正确 - Agent责任制工具
def create_appointment(patient_id, doctor_id, appointment_time):
    # 工具只负责基础的创建操作
    appointment_id = generate_id()
    appointment = {
        "appointment_id": appointment_id,
        "patient_id": patient_id,
        "doctor_id": doctor_id,
        "appointment_time": appointment_time,
        "status": "scheduled"
    }
    state["appointments"].append(appointment)
    return {"status": "success", "appointment_id": appointment_id}
```

### 示例2：余额查询

```python
# 错误 - 包含业务建议
def check_balance_with_advice(user_id):
    balance = get_user_balance(user_id)
    if balance < 100:
        return {
            "balance": balance,
            "advice": "余额不足，建议充值",  # 工具不应给建议
            "recommended_amount": 500
        }
    return {"balance": balance}

# 正确 - 只返回数据
def get_user_balance(user_id):
    user = find_user(user_id)
    return {
        "user_id": user_id,
        "balance": user["balance"],
        "currency": "CNY"
    }
```

---

## StateManager使用规范

### 为什么使用StateManager

1. **统一数据源**: 所有工具通过同一个状态管理器访问数据
2. **状态追踪**: 便于评测框架追踪数据变化
3. **隔离性**: 每个评测样本使用独立的状态副本

### 标准用法

```python
from ..simulators.state_manager import get_state_manager

class MyTool(BaseTool):
    def execute(self, **params) -> ToolResult:
        # 获取状态管理器
        state_manager = get_state_manager()

        # 获取当前状态
        state = state_manager.get_current_state()

        # 读取数据
        users = state.get("users", [])
        orders = state.get("orders", [])

        # 查找特定实体
        user = next(
            (u for u in users if u["user_id"] == params["user_id"]),
            None
        )

        # 修改数据
        new_order = {
            "order_id": generate_id(),
            "user_id": params["user_id"],
            "status": "created"
        }
        state["orders"].append(new_order)

        # 提交状态更新
        state_manager.update_state(state)

        return self.create_success_result(
            data={"order_id": new_order["order_id"]},
            message="订单创建成功"
        )
```

### 禁止的做法

```python
# 禁止：硬编码文件路径
with open("scenarios/my_scenario/data/users.json") as f:
    users = json.load(f)

# 禁止：直接访问全局变量
users = GLOBAL_USERS_DATA

# 禁止：使用legacy数据源
from ..legacy.data_loader import load_data
```

---

## MCP协议实现要求

### 必须遵循

1. **HTTP REST API实现**: 所有MCP通信必须基于HTTP协议
2. **禁止fastmcp Client**: 不得在tool_manager.py中使用 `from fastmcp import Client`
3. **统一协议架构**: MCP服务器提供HTTP REST API，工具管理器使用HTTP客户端调用

### 工具注册

```python
# 在mcp_server.py中注册工具
from .tools import MyServiceTool

mcp_server = MCPServer()
mcp_server.register_tool(MyServiceTool())
```

### 工具Schema生成

```python
def get_enhanced_schema(self) -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": self.name,
            "description": self.description,
            "parameters": self.get_parameter_schema(),
            "operation_type": self.get_operation_type().value
        }
    }
```

---

## CRUD操作类型详解

### 为什么强制声明CRUD类型

1. **验证一致性**: 确保工具行为与声明一致
2. **覆盖度检查**: 验证场景工具集的CRUD完整性
3. **分类管理**: 便于工具分类和文档生成

### 类型定义

```python
class CRUDOperation(Enum):
    CREATE = "create"  # 创建新实体
    READ = "read"      # 查询数据
    UPDATE = "update"  # 更新现有实体
    DELETE = "delete"  # 删除实体
```

### 使用装饰器

```python
from .crud_decorators import crud_operation, CRUDOperation

class OrderServiceTool(BaseTool):
    @crud_operation(CRUDOperation.CREATE)
    def create_order(self, **params):
        ...

    @crud_operation(CRUDOperation.READ)
    def get_order(self, **params):
        ...

    @crud_operation(CRUDOperation.UPDATE)
    def update_order_status(self, **params):
        ...

    @crud_operation(CRUDOperation.DELETE)
    def cancel_order(self, **params):
        ...
```

### CRUD覆盖度验证

```python
# 验证工具集的CRUD覆盖度
coverage = BaseTool.validate_crud_coverage([
    OrderServiceTool(),
    UserServiceTool(),
    ...
])

print(coverage["summary"])
# 输出: "CRUD覆盖度: 4/4 (完整)"
```

---

## 参数设计规范

### 必需参数 vs 可选参数

```python
def get_required_parameters(self) -> Set[str]:
    """必需参数 - 调用时必须提供"""
    return {"user_id", "order_type"}

def get_optional_parameters(self) -> Set[str]:
    """可选参数 - 有默认值或可省略"""
    return {"priority", "notes"}
```

### 参数Schema

```python
def get_parameter_schema(self) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "user_id": {
                "type": "string",
                "description": "用户唯一标识"
            },
            "amount": {
                "type": "number",
                "description": "金额（元）"
            },
            "status": {
                "type": "string",
                "enum": ["pending", "completed", "cancelled"],
                "description": "订单状态"
            }
        },
        "required": ["user_id", "amount"]
    }
```

---

## 输出Schema设计

### 声明工具能产生的输出

```python
def can_produce_output(self, output_field: str) -> bool:
    """声明工具能产生哪些输出字段"""
    producible = {"order_id", "status", "created_time"}
    return output_field in producible

def get_output_schema(self) -> Dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "order_id": {"type": "string"},
            "status": {"type": "string"},
            "created_time": {"type": "string", "format": "datetime"}
        }
    }
```

### 与Checker的关系

Checker只能验证Tool声明能产生的输出：
- Tool声明 `can_produce_output("order_id")` = True
- Checker可以验证 `entity_attribute_equals("order_id", "xxx")`

---

## 质量验证

### CRUD合规性验证

```bash
python templates/scripts/check_crud_compliance.py scenarios/{scenario_name}
```

验证内容：
- 所有工具函数有 `@crud_operation` 装饰器
- CRUD操作类型声明正确
- 工具正确导入和使用state_manager

### 质量标准

- CRUD声明率: 100%
- 模块导入成功率: 100%
- state_manager使用率: 100%

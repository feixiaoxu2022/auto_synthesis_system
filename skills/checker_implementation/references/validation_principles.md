# Checker验证原则详解

## 评测验证层次体系

### 验证优先级原理

评测框架的目标是验证Agent是否正确执行了业务规则。不同的验证方式有不同的可靠性：

| 优先级 | 验证类型     | 验证对象        | 判断方式   | 可靠性 |
| ------ | ------------ | --------------- | ---------- | ------ |
| 1      | 环境状态验证 | final_state数据 | Rule-based | 最高   |
| 2      | 内容生成验证 | Agent生成的文件 | Rule + LLM | 中高   |
| 3      | Response验证 | Agent回复文本   | Rule + LLM | 中等   |
| 4      | 工具调用验证 | 工具调用轨迹    | Rule-based | 特定场景必需 |

### 1. 环境状态验证（最高优先级）

**验证对象**: final_state中的实体属性变化

**适用场景**: 大部分业务规则的核心动作

**验证方式**:

- `entity_attribute_equals` - 验证属性值
- `create_operation_verified` - 验证实体创建
- `delete_operation_verified` - 验证实体删除

**示例**:

```json
{
  "check_type": "create_operation_verified",
  "params": {
    "entity_type": "appointments",
    "filter_conditions": {
      "patient_id": "pat_001",
      "status": "scheduled"
    },
    "min_count": 1
  },
  "description": "验证数据库中存在已创建的预约记录"
}
```

**优势**:

- 客观、可量化
- 不依赖文本表述
- 直接反映业务结果

---

### 2. 内容生成验证（中高优先级）

**验证对象**: Agent生成的结构化或非结构化文本内容

**适用场景**:

- 报告生成（法律文书、市场分析）
- 代码生成
- 邮件/文档起草

**验证方式**: `generated_content_checker`

**示例**:

```json
{
  "check_type": "generated_content_checker",
  "params": {
    "golden_answer_file": "golden_answers/risk_report_001.md",
    "key_points": [
      "风险点：交付日期模糊",
      "缺失条款：知识产权归属",
      "修改建议：明确交付时间"
    ]
  }
}
```

**验证维度**:

- 关键词匹配
- 关键信息点覆盖
- 逻辑一致性
- 格式合规性

---

### 3. Response内容验证（中等优先级）

**验证对象**: Agent回复给用户的文本内容

**适用场景**: 无需工具调用的确认、安抚、说明类动作

**验证方式**:

- `response_contains_keywords` - 关键词检查
- `response_compliance` - 合规性检查

**示例**:

```json
{
  "check_type": "response_contains_keywords",
  "params": {
    "keywords": ["预约成功", "已安排", "确认"],
    "check_last_only": false,
    "semantic_check": true,
    "semantic_criteria": "判断Agent是否明确告知用户预约已成功安排"
  }
}
```

**语义检查功能**:

- 智能理解同义表述
- 识别变形表达
- 双重验证（关键词 + 语义）

---

### 4. 工具调用验证（特定场景必需）

工具调用验证**不是最低优先级**，而是有其**不可替代的场景**。

#### 必须使用工具调用验证的场景

| 场景 | 为什么环境状态验证不够 | Checker |
|------|----------------------|---------|
| **执行顺序验证** | 环境状态只反映最终结果，无法体现执行顺序 | `prerequisite_check_performed` |
| **无状态动作验证** | 动作不改变数据库，环境中无痕迹 | `tool_called_with_params` |

**场景1：执行顺序验证**

```yaml
# 业务规则要求：创建工单前必须先检查历史
rule_3_1:
  description: "在创建维修工单前，必须先检查该车辆是否在过去24小时内已有报修记录"
```

```json
{
  "check_type": "prerequisite_check_performed",
  "params": {
    "prerequisite_tool": "check_maintenance_history",
    "business_tool": "create_maintenance_ticket",
    "related_entity_id": "bike_id"
  }
}
```

**场景2：无状态动作验证（如转人工）**

```yaml
# 风控触发时必须转人工，但转人工不改变数据库
rule_1_2:
  condition: "用户30天内申诉次数 > 4"
  required_action: transfer_to_human
```

```json
{
  "check_type": "tool_called_with_params",
  "params": {
    "tool_name": "transfer_to_human",
    "expected_params": {"reason": null}
  }
}
```

为什么不用Response验证？因为Agent可能说了"帮您转人工"但实际没调用工具，**说了不算，做了才算**。

#### 不需要使用工具调用验证的场景

| 场景 | 为什么环境状态验证更好 |
|------|---------------------|
| "禁止发券" | 用`create_operation_verified`的`should_not_exist: true`验证券不存在 |
| 大部分业务操作 | 操作结果会体现在环境状态中，直接验证结果更可靠 |

```json
// 验证"没有发券"用环境状态验证更可靠
{
  "check_type": "create_operation_verified",
  "params": {
    "entity_type": "coupons",
    "filter_conditions": {"user_id": "user_001"},
    "should_not_exist": true
  }
}
```

---

## 参数格式规范

### tool_called_with_params

```json
{
  "check_type": "tool_called_with_params",
  "params": {
    "tool_name": "create_appointment",
    "expected_params": {
      "patient_id": "pat_001",
      "doctor_id": null,
      "appointment_time": null
    }
  }
}
```

**通配符机制**:

- `null`值作为通配符，接受任意有效值
- 用于Agent需要自主决策的参数
- 避免过度约束Agent行为

### response_contains_keywords

```json
{
  "check_type": "response_contains_keywords",
  "params": {
    "keywords": ["关键词1", "关键词2"],
    "check_last_only": false,
    "semantic_check": true,
    "semantic_criteria": "语义检查标准描述"
  }
}
```

**参数说明**:

- `keywords`: 必须是列表格式
- `check_last_only`: 是否只检查最后一条回复
- `semantic_check`: 启用LLM语义检查
- `semantic_criteria`: 语义检查的具体标准

### create_operation_verified

```json
{
  "check_type": "create_operation_verified",
  "params": {
    "entity_type": "appointments",
    "filter_conditions": {
      "patient_id": "pat_001",
      "status": "scheduled"
    },
    "min_count": 1,
    "should_not_exist": false
  }
}
```

**参数说明**:

- `entity_type`: 实体类型（复数形式）
- `filter_conditions`: 字典格式的筛选条件
- `min_count`: 最少匹配数量
- `should_not_exist`: 设为true验证实体不存在

---

## JSON字符串自动解析

所有Checker自动支持JSON字符串参数解析：

```python
# 格式1：字典对象（标准）
"arguments": {"patient_id": "pat_001", "doctor_id": "doc_001"}

# 格式2：JSON字符串（自动解析）
"arguments": "{\"patient_id\":\"pat_001\",\"doctor_id\":\"doc_001\"}"
```

不同LLM可能返回不同格式的工具调用参数，Checker自动处理两种格式。

---

## Checker与Tool的约束关系

### 核心原则

**Checker只能验证Tool声明能产生的输出。**

### 验证流程

```
Tool.can_produce_output("order_id") → True
    ↓
Checker可以验证 entity_attribute_equals("order_id", "xxx")
```

### 示例

```python
# Tool声明
class OrderTool(BaseTool):
    def can_produce_output(self, output_field: str) -> bool:
        return output_field in {"order_id", "status", "created_time"}

# Checker验证（合法）
{
  "check_type": "entity_attribute_equals",
  "params": {
    "field": "order_id",  # Tool声明可以产生
    "expected_value": "xxx"
  }
}

# Checker验证（非法 - Tool未声明此输出）
{
  "check_type": "entity_attribute_equals",
  "params": {
    "field": "internal_code",  # Tool未声明可以产生
    "expected_value": "yyy"
  }
}
```

---

## BaseChecker实现规范

### 必须实现的方法

```python
class MyChecker(BaseChecker):
    @staticmethod
    def get_required_datasources() -> Set[str]:
        """声明需要的数据源"""
        return {"final_state", "conversation_history"}

    @staticmethod
    def get_validatable_outcomes() -> Set[str]:
        """声明能验证的结果类型"""
        return {"entity_created", "status_updated"}

    def check(self, datasources: Dict[str, Any], **params) -> CheckerResult:
        """执行检查逻辑"""
        ...
```

### CheckerResult格式

```python
@dataclass
class CheckerResult:
    passed: bool      # 是否通过
    score: float      # 得分 (0.0-1.0)
    details: str      # 详细说明
    issues: list      # 问题列表（可选）
```

### 创建结果的辅助方法

```python
# 通过
return self.create_result(
    passed=True,
    score=1.0,
    details="检查通过：成功创建预约记录"
)

# 失败
return self.create_result(
    passed=False,
    score=0.0,
    details="检查失败：未找到符合条件的预约记录",
    issues=[
        ConstraintIssue(
            level=IssueLevel.CRITICAL,
            message="预约记录不存在",
            source="create_operation_verified"
        )
    ]
)
```

---

## 常见错误

### 错误1：优先级使用不当

```json
// 错误 - 过度依赖工具调用验证
{
  "check_list": [
    {"check_type": "tool_called_with_params", ...},
    {"check_type": "tool_called_with_params", ...}
  ]
}

// 正确 - 优先使用状态验证
{
  "check_list": [
    {"check_type": "create_operation_verified", ...},
    {"check_type": "tool_called_with_params", ...}
  ]
}
```

### 错误2：参数格式错误

```json
// 错误 - expected_params用列表
{
  "expected_params": ["patient_id", "doctor_id"]
}

// 正确 - expected_params用字典
{
  "expected_params": {"patient_id": "pat_001", "doctor_id": null}
}
```

### 错误3：未使用通配符

```json
// 错误 - 硬编码Agent应该决策的值
{
  "expected_params": {
    "doctor_id": "doc_001",
    "appointment_time": "2024-03-20 10:00"
  }
}

// 正确 - Agent决策的值用null
{
  "expected_params": {
    "doctor_id": null,
    "appointment_time": null
  }
}
```

---

## 质量验证

### 参数格式验证

```bash
python templates/src/validation/checker_parameter_validator.py \
    scenarios/{scenario_name}/scripts/sample_generator_{domain}/generated_samples/ \
    --spec templates/format_specifications/checker_parameter_specifications.json
```

### 质量标准

- 参数格式符合率: 100%
- Checker与Tool输出一致性: 100%
- 验证优先级合理性: 通过审查

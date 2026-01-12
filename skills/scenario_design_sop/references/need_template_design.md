# 需求模板设计指南

## 什么是需求模板

需求模板（user_need_templates）是样本多样性的核心，每个模板代表一种**具体的用户需求场景**。通过组合不同的数据条件，一个模板可以生成多个测试样本。

```
需求模板 + 数据池匹配 → 多个测试样本
```

---

## 变量化设计原则（核心）

**核心目标**：一个模板能自动生成多个不同的样本，而不是每次手动改值。

### 错误示例（硬编码）

```yaml
# 问题：日期、人员都写死，无法自动生成变体
leave_start_date: '2024-03-25'
leave_end_date: '2024-03-27'
leave_time_description: 下周一到周三
work_handover_person_name: 李建国
work_handover_person_id: EP_02
```

### 正确示例（变量化）

```yaml
# 参数定义（支持自动生成变体）
parameters:
  leave_days:
    type: range
    min: 1
    max: 3

  leave_start:
    type: relative_date
    base: "system_time"
    offset: "+7d"              # 相对当前时间+7天

  handover_person:
    type: entity_reference
    entity: employees
    filter: "department == {{employee.department}} AND id != {{employee.id}}"

# 业务参数引用
leave_days: "{{parameters.leave_days}}"
leave_start_date: "{{parameters.leave_start}}"
leave_end_date: "{{parameters.leave_start + parameters.leave_days - 1}}"
handover_person: "{{parameters.handover_person.id}}"
```

### 变量类型

| 类型 | 说明 | 示例 |
|-----|------|------|
| `range` | 数值范围 | `min: 1, max: 5` |
| `enum` | 枚举选择 | `values: [A, B, C]` |
| `relative_date` | 相对日期 | `offset: "+7d"` |
| `entity_reference` | 实体引用 | `entity: employees, filter: ...` |
| `computed` | 计算值 | `formula: "{{a}} + {{b}}"` |

### 设计检查

- [ ] 所有日期使用相对时间，不用绝对日期
- [ ] 所有人员/实体引用使用动态筛选
- [ ] validation_checks中的expected_value全部用`{{}}`引用
- [ ] 没有任何硬编码的ID、姓名、日期

---

## 模板基础结构

```yaml
templates:
- need_template_id: LA_ANNUAL_WITH_COMPENSATORY
  description: 年假申请,调休充足优先扣除
  test_type: positive

  # 用户需求描述（用于生成query，带占位符）
  user_need_description: |
    你的需求：
    - 请假类型：{{leave_type_cn}}
    - 请假时间：{{leave_time_description}}
    - 请假天数：{{leave_days}}天
    - 请假原因：{{leave_reason}}

  # 参数定义（变量化）
  parameters:
    leave_days:
      type: range
      min: 1
      max: 3
    leave_start:
      type: relative_date
      offset: "+7d"

  # 数据筛选条件
  employee_filter_conditions:
    - field: compensatory_leave_balance
      operator: '>='
      value: "{{parameters.leave_days}}"
    - field: annual_leave_balance
      operator: '>='
      value: 1

  # 业务参数（引用变量）
  leave_days: "{{parameters.leave_days}}"
  leave_type: annual_leave
  leave_start_date: "{{parameters.leave_start}}"
  leave_end_date: "{{parameters.leave_start + parameters.leave_days - 1}}"
  leave_reason: 个人事务

  # 信息披露节奏
  disclosure_pace: progressive

  # 期望结果
  expected_outcome: 优先从调休扣除,创建Tier1审批申请

  # 验证点（全部用变量引用）
  validation_checks:
    - check_type: create_operation_verified
      entity_type: leave_applications
      filter_conditions:
        leave_type: annual_leave
        leave_days: "{{leave_days}}"
        leave_start_date: "{{leave_start_date}}"
```

---

## 核心字段详解

### 1. user_need_description（必需）

**作用**：用于生成样本的query字段，支持占位符`{{variable}}`

**示例**：

```yaml
user_need_description: |
  你的需求：
  - 请假类型：{{leave_type_cn}}
  - 请假时间：{{leave_time_description}}
  - 请假天数：{{leave_days}}天
```

样本生成时会替换占位符，产生具体的query文本。

### 2. need_template_id

**命名规范**：`{业务类型}_{场景特征}_{可选后缀}`

```yaml
# 好的命名
LA_ANNUAL_WITH_COMPENSATORY      # 请假-年假-有调休
LA_SICK_URGENT                   # 请假-病假-紧急
MR_LARGE_CONFERENCE_EQUIPMENT    # 会议室-大型会议-需设备
TA_MULTI_SEGMENT_BUDGET_EXCEED   # 差旅-多段行程-超预算

# 不好的命名
TEST_001                         # 无意义
SCENARIO_A                       # 无法识别内容
```

### 3. test_type

```yaml
test_type: positive    # 正向测试：预期成功的场景
test_type: negative    # 负向测试：预期失败/拒绝的场景
test_type: boundary    # 边界测试：临界条件的场景
```

**场景分布建议**：
- 正向测试：60%（主要业务流程）
- 负向测试：25%（异常和拒绝场景）
- 边界测试：15%（临界值和边界条件）

### 4. employee_filter_conditions（数据筛选条件）

从数据池中筛选符合条件的实体：

```yaml
employee_filter_conditions:
  # 数值比较
  - field: compensatory_leave_balance
    operator: '>='
    value: 3

  # 枚举匹配
  - field: level
    operator: '=='
    value: 'manager'

  # 范围检查
  - field: monthly_meeting_count
    operator: '<'
    value: 10

  # 多值匹配
  - field: department
    operator: 'in'
    value: ['hr', 'finance', 'marketing']
```

**支持的操作符**：
| 操作符 | 说明 | 示例 |
|-------|------|------|
| == | 等于 | value: 'manager' |
| != | 不等于 | value: 'junior' |
| > | 大于 | value: 5 |
| >= | 大于等于 | value: 3 |
| < | 小于 | value: 10 |
| <= | 小于等于 | value: 7 |
| in | 在列表中 | value: ['a', 'b'] |
| not_in | 不在列表中 | value: ['x', 'y'] |

### 5. disclosure_pace（信息披露节奏）

控制用户模拟器如何披露信息：

```yaml
disclosure_pace: upfront      # 一开始就给出所有信息
disclosure_pace: progressive  # 逐步补充信息
disclosure_pace: responsive   # 只在被问到时才回答
disclosure_pace: reluctant    # 需要被多次追问才给出
```

**使用建议**：

| 披露节奏 | 适用场景 | 测试能力 |
|---------|---------|---------|
| upfront | 急迫用户、简单请求 | 基础理解能力 |
| progressive | 普通用户、标准流程 | 对话管理能力 |
| responsive | 被动用户、复杂需求 | 主动引导能力 |
| reluctant | 困难用户、敏感信息 | 深度挖掘能力 |

### 6. validation_checks（验证点）

定义如何验证Agent的执行结果：

```yaml
validation_checks:
  # 创建操作验证
  - check_type: create_operation_verified
    entity_type: leave_applications
    filter_conditions:
      leave_type: annual_leave
      approval_tier: tier1_manager_only
      leave_days: '{{leave_days}}'           # 变量引用

  # 属性值验证
  - check_type: entity_attribute_equals
    entity_type: leave_applications
    field: compensatory_leave_deducted
    expected_value: '{{compensatory_leave_deducted}}'

  # 关键词验证
  - check_type: response_contains_keywords
    keywords:
      - 病例
      - 附件
    check_last_only: false
    semantic_check: true
    semantic_criteria: "判断Agent是否明确提醒用户需要补充提交病例附件"
```

**验证类型优先级**：
1. **状态验证**（最高）：检查final_state中的实体属性
2. **操作验证**：验证是否执行了必要的创建/更新操作
3. **内容验证**（最低）：检查回复中的关键词或语义

---

## 常见模板模式

### 模式1：正向标准流程

```yaml
- need_template_id: LA_ANNUAL_STANDARD
  description: 标准年假申请流程
  test_type: positive
  employee_filter_conditions:
    - field: annual_leave_balance
      operator: '>='
      value: 5
  leave_days: 3
  leave_type: annual_leave
  disclosure_pace: progressive
  expected_outcome: 成功创建年假申请
  validation_checks:
    - check_type: create_operation_verified
      entity_type: leave_applications
      filter_conditions:
        leave_type: annual_leave
        status: pending
```

### 模式2：负向拒绝场景

```yaml
- need_template_id: LA_INSUFFICIENT_BALANCE
  description: 余额不足被拒绝
  test_type: negative
  employee_filter_conditions:
    - field: annual_leave_balance
      operator: '<'
      value: 3
  leave_days: 5
  leave_type: annual_leave
  disclosure_pace: upfront
  expected_outcome: 告知余额不足,建议替代方案
  validation_checks:
    - check_type: response_contains_keywords
      keywords:
        - 余额不足
        - 调休
      semantic_check: true
```

### 模式3：边界条件测试

```yaml
- need_template_id: LA_TIER2_BOUNDARY
  description: 审批层级边界测试(恰好7天)
  test_type: boundary
  employee_filter_conditions:
    - field: annual_leave_balance
      operator: '>='
      value: 7
  leave_days: 7                          # 恰好在tier2上限
  leave_type: annual_leave
  disclosure_pace: responsive
  expected_outcome: 创建tier2审批(非tier3)
  validation_checks:
    - check_type: entity_attribute_equals
      entity_type: leave_applications
      field: approval_tier
      expected_value: tier2_manager_director  # 不是tier3
```

### 模式4：多条件组合

```yaml
- need_template_id: LA_MIXED_DEDUCTION
  description: 调休+年假组合扣除
  test_type: positive
  employee_filter_conditions:
    - field: compensatory_leave_balance
      operator: '>'
      value: 0
    - field: compensatory_leave_balance
      operator: '<'
      value: 5
    - field: annual_leave_balance
      operator: '>='
      value: 3
  leave_days: 5
  disclosure_pace: progressive
  expected_outcome: 先扣调休再扣年假
  validation_checks:
    - check_type: entity_attribute_equals
      entity_type: leave_applications
      field: compensatory_leave_deducted
      expected_value: '{{initial_compensatory_leave_balance}}'
    - check_type: entity_attribute_equals
      entity_type: leave_applications
      field: annual_leave_deducted
      expected_value: '{{5 - initial_compensatory_leave_balance}}'
```

---

## 设计检查清单

### 变量化检查（最重要）
- [ ] 所有日期使用相对时间（`+7d`），不用绝对日期（`2024-03-25`）
- [ ] 所有人员/实体引用使用动态筛选，不硬编码ID/姓名
- [ ] validation_checks中的expected_value全部用`{{}}`引用
- [ ] user_need_description使用占位符（`{{variable}}`），不硬编码具体值

### 覆盖度检查
- [ ] 正向场景覆盖主要业务流程
- [ ] 负向场景覆盖常见异常情况
- [ ] 边界场景覆盖临界值
- [ ] 披露节奏覆盖多种用户类型

### 质量检查
- [ ] need_template_id命名清晰有意义
- [ ] filter_conditions能筛选出足够的数据
- [ ] validation_checks可客观验证
- [ ] expected_outcome描述准确
- [ ] user_need_description自然流畅，符合真实用户表达

### 一致性检查
- [ ] 模板参数与BusinessRules一致
- [ ] 验证点与业务规则对应
- [ ] 变量引用正确（{{variable}}）

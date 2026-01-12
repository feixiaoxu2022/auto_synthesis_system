---
name: scenario-design
description: 设计Agent评测场景的统一配置文件(unified_scenario_design.yaml)。当需要创建新评测场景、设计需求模板、提升样本难度时使用此技能。这是init阶段最核心的工作，决定了样本质量和难度。
---

# 场景设计指南

## Overview

场景设计是评测框架的init阶段核心工作，产出**unified_scenario_design.yaml**作为后续所有环节的输入。

核心原则：**难度来自真实业务复杂性，而非人为刁难；可验证是底线**。

## Agent能力评测体系（9个核心能力）

场景设计的最终目标是全方位评测LLM Agent在实际落地中的必备能力。每个场景应至少测试其中2-3个能力：

| 能力维度 | 定义 | 典型测试场景 |
|---------|------|------------|
| **1. 多模态理解** | 处理和融合文本、图像等多模态信息 | 文档审阅、图表分析、截图问题诊断 |
| **2. 复杂上下文理解** | 跨轮整合上下文并保持一致性 | 多轮对话任务、需求收集、上下文依赖推理 |
| **3. Prompt遵循** | 理解并遵循用户指令与业务规则 | 复杂业务规则执行、约束条件遵守 |
| **4. Tool Use** | 准确选择工具并构造参数 | 工具选择、参数构造、错误处理 |
| **5. 任务规划与工具组合** | 任务分解与工具编排 | 多步骤流程、工具链组合、依赖关系处理 |
| **6. 多轮对话管理与用户引导** | 结构化收集信息与清晰反馈 | 信息收集、澄清确认、进度同步 |
| **7. 反思与动态调整** | 基于执行结果诊断并调整策略 | 错误恢复、异常处理、策略调整 |
| **8. 多源信息深度融合与洞察** | 处理多源数据的一致性与权衡 | 数据冲突处理、优先级判断、信息整合 |
| **9. 结合领域知识的自主规划** | 利用领域知识做出专业决策 | 专业领域任务、技术实现、算法选择 |

### 设计方法与能力的映射

| 设计方法 | 主要测试能力 | 辅助测试能力 |
|---------|-------------|-------------|
| **复杂业务规则** | 3-Prompt遵循, 8-多源信息融合 | 4-Tool Use, 5-任务规划 |
| **领域知识门槛** | 9-领域知识自主规划 | 3-Prompt遵循 |
| **人类共识任务** | 8-多源信息融合, 6-用户引导 | 2-上下文理解 |
| **多轮需求变更** | 2-上下文理解, 6-用户引导 | 7-反思与调整 |
| **信息洋葱** | 5-任务规划, 4-Tool Use | 2-上下文理解, 7-反思与调整 |

### 场景设计时的能力覆盖检查

设计场景时，建议在YAML中增加`tested_capabilities`字段标注测试的能力：

```yaml
tested_capabilities:
  - capability: "Prompt遵循"
    测试方式: "复杂业务规则中的条件判断和优先级处理"
  - capability: "Tool Use"
    测试方式: "正确选择工具和构造参数以完成状态更新"
  - capability: "多源信息融合"
    测试方式: "从多个实体中提取信息并做出决策"
```

## 五种设计方法

根据场景特点选择合适的设计方法（可组合使用）：

| 方法 | 适用场景 | 复杂性来源 | 验证方式 |
|-----|---------|-----------|---------|
| **复杂业务规则** | 任务分配、费用计算、资源调度 | 条件分支+状态更新+算法映射 | final_state状态验证 |
| **领域知识门槛** | 技术任务、算法实现、安全评测 | 专家常识盲区 | 隐藏Boss测试 |
| **人类共识任务** | 信息记忆、优先级判断、质量评估 | 设计阶段/评估阶段共识 | Rule-based或人工标注 |
| **多轮需求变更** | 客服对话、需求收集、项目管理 | 上下文累积+需求变化 | final_state状态验证 |
| **信息洋葱** | 审批流程、工单处理、多级查询 | 多步推理链（GAIA思想） | 最终答案验证 |

**推荐组合**：多轮变更 + 信息洋葱 + 复杂规则

**详细指南**：[references/scenario_design_patterns.md](references/scenario_design_patterns.md)

## YAML核心结构

```yaml
scenario_name: "场景名称"
sub_scenario_type: "子场景类型"
description: "场景描述"

runtime_config:           # 时间基准
  system_time: "2025-07-16T10:00:00Z"

entities:                 # 实体定义
  主实体:
    attributes: {...}
    relationships: [...]

business_rules:           # 业务规则
  rule_X:
    trigger_conditions: {...}
    required_actions: [...]
    success_criteria: [...]
    sample_generation:
      query_templates: [...]
      data_variations: [...]
```

**完整模板**：[references/scenario_template.yaml](references/scenario_template.yaml)

## 环境隔离设计（重要）

**执行机制**：每个样本在独立临时目录中执行，由executor自动创建和清理。

**何时需要environment字段**：
- 样本需要数据文件（JSONL/JSON/CSV）、数据库（SQLite）、或配置文件

**environment格式**：
```yaml
environment:
  - type: file          # file/db/binary/sh
    path: "data.jsonl"  # 相对路径
    content: "..."
```

**servers.json中使用占位符**：
```yaml
mcpServers:
  filesystem:
    args: ["${ENV_DIR}"]  # executor自动替换为临时目录路径
```

## 需求模板设计

需求模板是样本多样性的核心，每个模板代表一种用户需求场景：

```yaml
templates:
- need_template_id: LA_ANNUAL_WITH_COMPENSATORY
  description: 年假申请,调休充足优先扣除
  test_type: positive                    # positive/negative
  user_need_description: |               # 用户需求描述（用于生成query）
    你的需求：
    - 请假类型：{{leave_type_cn}}
    - 请假时间：{{leave_time_description}}
  employee_filter_conditions:            # 数据筛选条件
    - field: compensatory_leave_balance
      operator: '>='
      value: 3
  disclosure_pace: progressive           # 信息披露节奏
  validation_checks:                     # 验证点
    - check_type: create_operation_verified
      entity_type: leave_applications
      filter_conditions: {...}
```

**详细指南**：[references/need_template_design.md](references/need_template_design.md)

## 设计流程（3步）

| 步骤 | 内容 | 关键动作 |
|-----|------|---------|
| 1 | 选择设计方法 | 根据场景特点从五种方法中选择（可组合） |
| 2 | 定义实体和规则 | 设计entities、business_rules、success_criteria |
| 3 | 设计需求模板 | 设计user_need_templates覆盖正向/负向/边界场景 |

## 质量快速检查

- [ ] entities覆盖所有业务实体和关键属性
- [ ] business_rules的success_criteria可客观验证
- [ ] need_templates覆盖正向/负向/边界场景
- [ ] 难度设计能有效区分不同模型能力

## Reference Files

| 文件 | 内容 | 何时读取 |
|-----|------|---------|
| [scenario_design_patterns.md](references/scenario_design_patterns.md) | 五种设计方法详解+算法映射表 | 开始新场景设计时 |
| [scenario_template.yaml](references/scenario_template.yaml) | 完整YAML模板（带详细注释） | 编写配置文件时 |
| [need_template_design.md](references/need_template_design.md) | 需求模板设计指南 | 设计测试用例时 |

## 优秀案例

| 案例 | 核心设计模式 |
|-----|-------------|
| [ad_campaign](examples/ad_campaign_scenario.yaml) | ROI矩阵、渠道约束、预算分配（复杂规则+算法映射） |
| [task_assignment](examples/task_assignment_scenario.yaml) | 优先级排序、负载计算、技能匹配（CSP约束满足） |
| [office_admin](examples/office_admin_scenario.yaml) | 信息收集、审批流程、异常处理（多轮变更+信息洋葱） |
| [bikeshare_prototypes](examples/bikeshare_prototypes/) | 多层用户体系、费用计算（复杂规则） |

## 关键原则

1. **方法可组合** - 一个场景可以同时使用多种设计方法
2. **难度来自业务** - 真实业务复杂性，而非人为设计的陷阱
3. **可验证是底线** - 所有success_criteria必须客观可验证
4. **覆盖要全面** - 正向/负向/边界场景都要设计

## 可验证性设计指南（关键）

### 验证方式优先级

| 优先级 | 验证方式 | 适用场景 | 示例 |
|-------|---------|---------|------|
| 1 | Rule-based状态检查 | 实体属性变化 | 检查order.status == 'completed' |
| 2 | Rule-based工具调用 | 调用记录验证 | 检查是否调用了create_order |
| 3 | Rule-based内容匹配 | 关键词/格式验证 | 检查回复包含订单号 |
| 4 | LLM Judge | 纯语义判断 | 检查回复语气是否专业 |

### 设计时的可验证性自检

设计每个check_item时问自己：

```
Q1: 这个检查点能通过final_state的字段值验证吗？
    → YES: 使用 entity_attribute_equals
    → NO: 继续Q2

Q2: 这个检查点是验证工具是否被调用/参数是否正确吗？
    → YES: 使用 tool_called_with_params
    → NO: 继续Q3

Q3: 这个检查点是验证Agent回复中的特定内容吗？
    → YES: 使用 response_contains_keywords (先尝试关键词匹配)
    → NO: 继续Q4

Q4: 这个检查点必须理解语义才能判断吗？
    → YES: 使用 use_llm_judge: true（最后手段）
    → NO: 重新审视检查点设计
```

### 反模式（必须避免）

| 反模式 | 问题 | 正确做法 |
|-------|------|---------|
| 用LLM判断数值计算结果 | LLM算数不可靠 | 检查final_state中的计算结果字段 |
| 用LLM判断是否调用了某工具 | 结构化数据用规则判断 | tool_called_with_params |
| 用LLM判断实体状态变化 | final_state有确定性答案 | entity_attribute_equals |
| 所有检查都用LLM | 成本高、结果不稳定 | 按优先级选择验证方式 |

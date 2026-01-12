---
name: failure-analysis
description: 对Agent评测失败案例进行根因分析，准确区分Agent能力问题、样本设计问题、用户模拟器问题和系统问题。当需要分析评测失败原因、归因问题类型、提供改进建议时使用此技能。
---

# 失败案例归因分析指南

## Overview

对评测失败案例进行根因分析，准确区分问题类型并提供改进建议。核心原则：**基于事实证据进行归因，不停留在表面现象**。

## Quick Start

```python
# 1. 读取样本数据
sample = read_json("evaluation_results/xxx.json")

# 2. 按8步流程分析（见下方）

# 3. 使用决策树归因（见 references/decision_tree.md）

# 4. 生成分析报告并保存
analysis_report = {
    "scenario_id": "LA_ST_SICK_LEAVE_001",
    "model": "gpt-4o",
    "failure_summary": "...",
    "analysis": {...},
    "final_state_validation": {...},
    "root_causes": [...],
    "improvements": [...]
}

# 5. 写入文档（必须！）
from datetime import datetime
timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
output_path = f"analysis/{scenario_id}_analysis_{timestamp}.json"
write_json(output_path, analysis_report)
```

**重要**：
- ⚠️ **必须将分析结论写入JSON文件**，路径格式：`analysis/{scenario_id}_analysis_{timestamp}.json`（相对于工作目录）
- ⚠️ JSON格式必须符合 `templates/analysis_report_schema.json` 的定义（相对于本SKILL.md的路径）
- ⚠️ 确保包含完整的分析思路、证据链和改进建议
- ⚠️ 时间戳格式：`YYYYMMDD_HHMMSS`，避免重复分析时文件覆盖

## 输出格式

**文件位置**：`analysis/{scenario_id}_analysis_{timestamp}.json`（相对于工作目录）

**命名示例**：`LA_ST_SICK_LEAVE_001_analysis_20260108_153042.json`

**JSON Schema**：[templates/analysis_report_schema.json](templates/analysis_report_schema.json)

**必需字段**：
- `scenario_id` - 样本ID
- `model` - 被评测模型
- `evaluation_file` - 评测结果文件路径
- `failure_summary` - 失败简要总结
- `analysis` - 基础分析（指标、关键轮次、期望vs实际）
- `final_state_validation` - final_state三层验证
- `root_causes` - 根因分析（类型、维度、证据、推理）
- `improvements` - 改进建议（领域、措施、负责方、优先级）

## 两层失败分析框架

```
第一层：业务失败原因分析
├── 核心业务目标达成情况
├── 关键业务节点执行状态
├── 业务流程断链位置识别
└── 根本失败原因定位

第二层：过程违规行为分析
├── 信息编造和虚构内容
├── 技术痕迹暴露问题
├── 数据一致性问题
└── 合规控制缺陷
```

**层次关联**：业务失败往往伴随违规行为增加，成功率越低的模型通常违规程度越严重。

## 四类归因分类

| 类型 | 定义 | 典型表现 |
|-----|------|---------|
| **Agent能力问题** | Agent未按业务规则执行必要操作 | 有机会但未询问、明确需求未响应、执行顺序错误 |
| **样本设计问题** | 测试样本本身的设计存在缺陷 | Checker过严/过宽、规则未明确、Prompt矛盾 |
| **用户模拟器执行问题** | 实际行为偏离预设prompt | 角色偏离、信息透露时机不对、STOP时机异常 |
| **系统问题** | 工具/Checker/框架代码存在bug | 工具未更新状态、返回数据错误、Checker逻辑错误 |

## Agent能力问题的细分维度

当归因为**Agent能力问题**时，需要进一步映射到9个核心能力维度：

| 能力维度 | 典型失败表现 | 分析关键点 |
|---------|-------------|-----------|
| **1. 多模态理解** | 未理解图像/文档内容、信息提取错误 | 检查是否正确解析了多模态输入 |
| **2. 复杂上下文理解** | 多轮信息丢失、前后不一致、未整合上下文 | 检查是否记住并使用了之前轮次的信息 |
| **3. Prompt遵循** | 违反业务规则、未遵循约束条件、漏执行必要步骤 | 对比BusinessRules和Agent实际行为 |
| **4. Tool Use** | 工具选择错误、参数构造错误、未处理工具返回 | 检查工具调用记录和参数准确性 |
| **5. 任务规划与工具组合** | 步骤遗漏、顺序错误、工具链断裂 | 检查完整业务流程是否按顺序执行 |
| **6. 多轮对话管理与用户引导** | 未主动询问、信息收集不完整、反馈不清晰 | 检查是否给用户表达需求的机会 |
| **7. 反思与动态调整** | 错误后未调整、未处理异常、策略僵化 | 检查遇到问题后是否有调整行为 |
| **8. 多源信息深度融合与洞察** | 数据冲突未解决、优先级错误、信息遗漏 | 检查是否整合了所有相关数据源 |
| **9. 结合领域知识的自主规划** | 专业判断错误、算法选择不当、技术实现错误 | 检查是否应用了必要的领域知识 |

### 能力维度归因示例

```json
{
  "root_causes": [
    {
      "type": "Agent能力问题",
      "dimension": ["多轮对话管理", "Prompt遵循"],
      "evidence": [
        "Agent未主动询问用户对活动B的调整需求（轮次3）",
        "BusinessRules明确要求'主动了解清楚用户的调整要求'但Agent未执行"
      ],
      "reasoning": "Agent在识别出多个活动后，应该逐个询问用户期望，但仅被动响应了明确需求，违反了系统prompt的主动引导要求"
    }
  ]
}
```

## 8步分析流程

| 步骤 | 内容 | 关键动作 |
|-----|------|---------|
| 1 | 基础信息收集 | 提取评测指标、失败点、checklist结果 |
| 2 | 逐轮对话分析 | 按时间顺序分析每轮对话的关键信息 |
| 3 | 期望vs实际对比 | 对比user_simulator_prompt与用户实际表达 |
| 4 | 失败根因推导 | 基于事实证据逐步推导根本原因 |
| 5 | final_state验证 | 检查Agent操作的实际结果 |
| 6 | 用户模拟器行为验证 | 验证用户行为是否符合预设prompt |
| 7 | 关键证据验证 | 检查数据验证推论的正确性 |
| 8 | 归因结论确定 | 给出明确分类和改进建议 |

**详细流程：** [references/analysis_workflow.md](references/analysis_workflow.md)

## 三层验证机制

当final_state与expected_state不符时，按以下顺序验证：

```
验证层1：工具职责边界验证
  └─ 工具应该负责该状态更新?
     ├─ 是但未更新 → 系统问题
     └─ 否 → 进入层2

验证层2：Agent操作完整性验证
  └─ Agent是否遗漏了必要操作?
     ├─ 调用了但未生效 → 系统问题
     ├─ 遗漏了调用 → 进入层3
     └─ 调用参数错误 → Agent能力问题

验证层3：业务规则明确性验证
  └─ BusinessRules是否明确要求该操作?
     ├─ 明确要求但Agent未做 → Agent能力问题
     └─ 未明确要求 → 样本设计问题
```

**详细决策树：** [references/decision_tree.md](references/decision_tree.md)

## 质量快速检查（5项核心）

- [ ] 完整阅读了所有对话内容
- [ ] 结论基于对话事实而非prompt假设
- [ ] 区分了用户实际表达vs设定期望
- [ ] 验证了final_state与Agent操作意图的一致性
- [ ] 每个结论都有明确的事实支撑

**完整检查清单：** [references/quality_checklist.md](references/quality_checklist.md)

## Reference Files

| 文件 | 内容 | 何时读取 |
|-----|------|---------|
| [analysis_workflow.md](references/analysis_workflow.md) | 8步分析流程详解 | 执行分析时 |
| [decision_tree.md](references/decision_tree.md) | 归因决策树和判断表 | 归因不确定时 |
| [quality_checklist.md](references/quality_checklist.md) | 完整自检清单 | 分析完成后 |
| [common_mistakes.md](references/common_mistakes.md) | 18个常见错误速查 | 遇到问题时 |

## 优秀案例

分析遇到困难时，**加载对应类型的案例学习归因思路**：

| 归因类型 | 案例文件 | 核心问题 |
|---------|---------|---------|
| Agent能力-Tool Use | [LA_ST_SICK_LEAVE_001](examples/LA_ST_SICK_LEAVE_001_manual_annotation.json) | 参数类型错误 |
| Agent能力-边界判断 | [LA_ST_TIER2_BOUNDARY_001](examples/LA_ST_TIER2_BOUNDARY_001_manual_annotation.json) | 临界值误判 |
| Agent能力-约束漂移 | [MT_RCC_017_AGGRESSIVE](examples/MT_RCC_017_AGGRESSIVE_manual_annotation.json) | 擅自改变业务约束 |
| 样本设计-描述不完整 | [SQL_PROJ_004](examples/SQL_PROJ_004_QUERY_INCOMPLETE_manual_annotation.json) | Query-Checklist不一致 |
| 样本设计-命名约定 | [SQL_PROJ_009](examples/SQL_PROJ_009_NAMING_CONVENTION_manual_annotation.json) | 字段命名缺失 |
| 系统问题-Checker错误 | [LA_ST_INSUFFICIENT_BALANCE_001](examples/LA_ST_INSUFFICIENT_BALANCE_001_manual_annotation.json) | Checker配置不合理 |

**完整案例索引**：[examples/README.md](examples/README.md)（含学习路径和场景对比分析）

## 关键原则

1. **完整阅读** - 必须从conversation_history第一轮开始逐轮阅读
2. **事实vs假设** - 只能基于对话事实归因，不能基于prompt推断
3. **层次验证** - final_state异常时必须运用三层验证机制
4. **证据链完整** - 每个结论必须有具体证据支撑

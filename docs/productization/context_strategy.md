# Context 传递策略设计

## 文档版本
- 版本号: v2.0
- 创建日期: 2026-01-04
- 最后更新: 2026-01-04
- 状态: 接口协议定义

---

## 核心设计原则

### 1. 落盘优先（Persistence First）
所有执行数据必须完整落盘，包括：
- 样本内容（samples/*.json）
- 执行轨迹（execution_traces/*.json）
- 评测结果（evaluation_results/*.json）
- 归因分析（attribution_analysis/*.json）
- 问题报告（layer1_problems_report.json）

**目的**：完整性、可调试性、防止丢失

### 2. 路径传递（Path Reference）
Context 中只传递文件路径和索引，不传递完整内容。

**目的**：Context 保持轻量（2K-5K tokens），防止窗口打满

### 3. 按需加载（Load on Demand）
Init Agent 根据实际需要决定读取深度和截断策略。

**约束**：建议控制 token 消耗在合理范围（约40K），但可根据问题复杂度自主调整

---

## Context Package 基础结构

### 统一 Context 接口

```python
from typing import Literal, Optional, Dict, Any, List
from pydantic import BaseModel, Field

class ContextPackage(BaseModel):
    """所有 handoff context 的基类"""

    # === 必需字段（所有版本） ===
    version: str = "2.0"  # Context schema 版本
    handoff_type: Literal["init_to_execute", "execute_to_init"]
    timestamp: str

    # === 可扩展字段 ===
    metadata: Dict[str, Any] = Field(default_factory=dict)  # 扩展点

    class Config:
        extra = "allow"  # 允许添加额外字段而不报错
```

---

## Handoff 1: Init → Execute

### Context 数据结构

```python
class InitToExecuteContext(ContextPackage):
    """Init Agent 向 Execute Agent 传递的 context"""

    handoff_type: Literal["init_to_execute"] = "init_to_execute"

    # === 必需字段 ===
    user_requirement: str  # 原始用户需求

    design_artifacts: Dict[str, str]  # 设计文件路径
    # {
    #     "unified_scenario_design_path": "path/to/yaml",
    #     "business_rules_path": "path/to/BusinessRules.md",
    #     "format_specifications_path": "path/to/format.json"
    # }

    # === 可选字段（扩展预留）===
    design_rationale: Optional[str] = None  # Layer 1 设计意图和权衡
    design_iterations: Optional[List[Dict]] = None  # HITL-1 的修改历史
    known_constraints: Optional[List[str]] = None  # 已知约束条件
```

### 传递示例

```json
{
  "version": "2.0",
  "handoff_type": "init_to_execute",
  "timestamp": "2026-01-04T10:30:00",
  "user_requirement": "生成请假申请场景的评测样本",
  "design_artifacts": {
    "unified_scenario_design_path": "scenarios/leave_application/unified_scenario_design.yaml",
    "business_rules_path": "scenarios/leave_application/BusinessRules.md",
    "format_specifications_path": "scenarios/leave_application/format_specifications.json"
  }
}
```

**Token 估算**：约 200-300 tokens

---

## Handoff 2: Execute → Init

### 数据落盘结构（Execute Agent 交付要求）

Execute Agent 完成评测后，必须将所有数据落盘到以下结构：

```
scenarios/leave_application/
├── execution_outputs/
│   ├── iteration_12/                    # 第12次迭代
│   │   ├── samples/                     # 所有样本
│   │   │   ├── BS_MT_001.json
│   │   │   ├── BS_MT_002.json
│   │   │   └── ...
│   │   ├── execution_traces/            # 每个样本的执行trace
│   │   │   ├── BS_MT_001_trace.json     # conversation_history + tool_calls + states
│   │   │   ├── BS_MT_002_trace.json
│   │   │   └── ...
│   │   ├── evaluation_results/          # 评测结果
│   │   │   ├── BS_MT_001_eval.json      # checker结果 + LLM评判
│   │   │   ├── BS_MT_002_eval.json
│   │   │   └── ...
│   │   ├── attribution_analysis/        # 归因分析（详细）
│   │   │   ├── BS_MT_001_attribution.json
│   │   │   ├── BS_MT_002_attribution.json
│   │   │   └── ...
│   │   ├── failure_summary.json         # 失败样本汇总
│   │   └── layer1_problems_report.json  # Layer 1问题详细报告
```

### Context 数据结构

```python
class ExecuteToInitContext(ContextPackage):
    """Execute Agent 返回 Init Agent 时传递的 context"""

    handoff_type: Literal["execute_to_init"] = "execute_to_init"

    # === 必需字段：路径 + 索引 ===

    # 1. 执行输出目录路径
    execution_output_dir: str  # "scenarios/leave_application/execution_outputs/iteration_12"

    # 2. 触发信息
    trigger_reason: str  # 为什么返回Init Agent
    iteration_summary: Dict[str, Any]  # 迭代统计信息

    # 3. 失败样本索引（只传ID和关键指标，不传完整内容）
    failure_samples_index: List[Dict[str, Any]]
    # [
    #   {
    #     "sample_id": "BS_MT_001",
    #     "sample_path": "samples/BS_MT_001.json",
    #     "trace_path": "execution_traces/BS_MT_001_trace.json",
    #     "evaluation_path": "evaluation_results/BS_MT_001_eval.json",
    #     "attribution_path": "attribution_analysis/BS_MT_001_attribution.json",
    #     "failure_type": "Layer1_BusinessRule",
    #     "conversation_turns": 8,
    #     "checkers_failed": ["leave_balance_deducted"],
    #     "priority": "high"  # high/medium/low - 基于影响范围和严重程度
    #   },
    #   ...
    # ]

    # 4. Layer 1 问题报告路径（详细报告在文件中）
    layer1_problems_report_path: str  # "layer1_problems_report.json"

    # 5. 修改建议摘要（简短版本，详细内容在report文件中）
    modification_suggestions_summary: List[str]  # 3-5条最关键的建议
```

### 传递示例

```json
{
  "version": "2.0",
  "handoff_type": "execute_to_init",
  "timestamp": "2026-01-04T15:30:00",

  "execution_output_dir": "scenarios/leave_application/execution_outputs/iteration_12",

  "trigger_reason": "Critical问题占比35%，超过30%阈值，自动修复无效",

  "iteration_summary": {
    "total_iterations": 12,
    "final_quality": 0.67,
    "layer2_iterations": 3,
    "layer3_iterations": 8,
    "total_samples": 27,
    "failed_samples": 18
  },

  "failure_samples_index": [
    {
      "sample_id": "BS_MT_001",
      "sample_path": "samples/BS_MT_001.json",
      "trace_path": "execution_traces/BS_MT_001_trace.json",
      "evaluation_path": "evaluation_results/BS_MT_001_eval.json",
      "attribution_path": "attribution_analysis/BS_MT_001_attribution.json",
      "failure_type": "Layer1_BusinessRule",
      "conversation_turns": 8,
      "checkers_failed": ["leave_balance_deducted"],
      "priority": "high"
    },
    {
      "sample_id": "BS_MT_003",
      "sample_path": "samples/BS_MT_003.json",
      "trace_path": "execution_traces/BS_MT_003_trace.json",
      "evaluation_path": "evaluation_results/BS_MT_003_eval.json",
      "attribution_path": "attribution_analysis/BS_MT_003_attribution.json",
      "failure_type": "Layer1_BusinessRule",
      "conversation_turns": 12,
      "checkers_failed": ["leave_balance_deducted", "application_status_correct"],
      "priority": "high"
    }
  ],

  "layer1_problems_report_path": "layer1_problems_report.json",

  "modification_suggestions_summary": [
    "在BusinessRules明确添加：创建请假申请后必须调用update_employee_leave_balance扣减余额",
    "将leave_balance_deducted checker改为容忍0.01天的浮点误差",
    "在BusinessRules中明确跨年度请假的余额计算规则"
  ]
}
```

**Token 估算**：约 2K-5K tokens（取决于失败样本数量）

---

## Init Agent 如何使用 Context

Init Agent 收到 ExecuteToInitContext 后，可以：

1. **读取 layer1_problems_report.json** - 了解问题概览和修改建议
2. **根据需要读取具体失败样本** - 通过 failure_samples_index 中的路径
3. **自主决定读取深度**：
   - 可以只读问题报告摘要
   - 可以读取几个典型 case 的详细内容
   - 可以深度分析所有 case
   - 可以对长对话历史进行截断（保留开头、结尾、关键轮次）

**约束**：
- 数据完整落盘，永久可追溯
- Context 只传路径，Init Agent 按需加载
- 建议控制 token 消耗在合理范围（约40K），但可根据实际需要调整

---

## layer1_problems_report.json 文件结构

Execute Agent 必须生成此文件，包含详细的归因分析和修改建议：

```json
{
  "report_version": "1.0",
  "generated_at": "2026-01-04T15:30:00",
  "iteration": 12,
  "total_samples": 27,
  "failed_samples": 18,
  "failure_rate": 0.67,

  "layer1_problems": [
    {
      "problem_id": "L1P_001",
      "problem_type": "BusinessRule_Unclear",
      "severity": "critical",
      "title": "余额扣减时机未明确",
      "description": "BusinessRules.md 未明确说明余额必须在创建申请时同步扣减",
      "affected_samples": ["BS_MT_001", "BS_MT_003", "BS_MT_007", "..."],
      "affected_count": 9,
      "evidence_summary": "9个case中Agent都创建了申请但未扣减余额",
      "typical_case_id": "BS_MT_001",
      "suggested_fix": {
        "target": "BusinessRules.md",
        "section": "## 请假申请流程",
        "modification": "在步骤2后添加：必须立即调用 update_employee_leave_balance 扣减余额",
        "rationale": "明确业务规则，避免Agent遗漏关键操作"
      }
    },
    {
      "problem_id": "L1P_002",
      "problem_type": "Checker_Design",
      "severity": "high",
      "title": "余额checker容忍度过严",
      "description": "leave_balance_deducted要求精确相等，但存在浮点误差",
      "affected_samples": ["BS_MT_010", "BS_MT_015", "BS_MT_021"],
      "affected_count": 3,
      "evidence_summary": "预期7.0天但实际6.999999天",
      "typical_case_id": "BS_MT_010",
      "suggested_fix": {
        "target": "unified_scenario_design.yaml",
        "section": "checkers.leave_balance_deducted",
        "modification": "将validation_logic改为容忍0.01天误差",
        "rationale": "处理浮点数精度问题"
      }
    }
  ],

  "modification_priority": [
    {
      "priority": 1,
      "problem_id": "L1P_001",
      "impact": "解决9个失败case",
      "estimated_improvement": "+33%"
    },
    {
      "priority": 2,
      "problem_id": "L1P_002",
      "impact": "解决3个失败case",
      "estimated_improvement": "+11%"
    }
  ]
}
```

---

## 核心价值

### Context 大小对比

| Handoff | Context 本身 | Init Agent 加载后 |
|---------|-------------|------------------|
| Init → Execute | 200-300 tokens | 200-300 tokens |
| Execute → Init | 2K-5K tokens | 约40K tokens（建议） |

### 关键优势

1. **完整性**：所有数据落盘，可追溯、可调试
2. **轻量性**：Context 本身很小，不会打满窗口
3. **灵活性**：Agent 根据需要自主决定加载策略
4. **工程化**：符合生产环境的最佳实践

---

**注**：本文档定义接口协议和交付要求，具体实现由 Agent 自主决策。

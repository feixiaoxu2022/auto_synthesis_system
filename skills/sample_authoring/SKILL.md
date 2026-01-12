---
name: sample-authoring
description: 合成评测样本。基于unified_scenario_design.yaml和业务规则，生成数据池、构建规则原型、实现样本生成器，产出可用于评测的样本文件。这是Step 3.3-3.6的核心工作。
---

# 样本合成指南

## Overview

样本合成是评测框架Step 3的核心工作，将场景设计转化为可执行的评测样本。

**输入**：unified_scenario_design.yaml + BusinessRules.md
**输出**：符合格式规范的样本JSONL文件

```
unified_scenario_design.yaml
         ↓
   ┌─────┴─────┐
   ↓           ↓
数据池      Prototypes
(entities)  (规则原型)
   └─────┬─────┘
         ↓
    样本生成器
         ↓
   samples/eval.jsonl
```

## 三步流程

| 步骤 | 内容 | 输出 |
|-----|------|------|
| 1 | **数据池设计** | `data_pools/{entity}.jsonl` - 结构化实体数据（不含query） |
| 2 | **需求模板构建** | 基于YAML的`user_need_templates`（含query模板） |
| 3 | **生成器实现** | 动态生成query（模板+实体数据） → `samples/eval.jsonl` |

## 文件组织

**工作目录结构**（所有路径相对于工作目录）：

```
<工作目录>/
├── unified_scenario_design.yaml
├── BusinessRules.md
├── tools/
│   └── *.py
├── checkers/
│   └── checker.py
├── data_pools/              # 数据池目录
│   ├── users.jsonl
│   ├── orders.jsonl
│   └── {entity}.jsonl
├── samples/                 # 最终样本输出
│   └── eval.jsonl
└── scripts/                 # 样本生成器（可选）
    └── sample_generator/
        └── main.py
```

**路径规范**：
- 数据池文件：`data_pools/{entity}.jsonl`
- 最终样本：`samples/eval.jsonl`
- 所有路径使用相对于工作目录的相对路径
- 工作目录由调用方（Agent）通过 context 提供

## 核心组件

### 数据池 (Data Pool)

为每个entity生成测试数据，覆盖所有业务场景。

**目录位置**：`data_pools/`（相对于工作目录）

```
data_pools/
├── users.jsonl         # 用户数据
├── orders.jsonl        # 订单数据
├── bikes.jsonl         # 单车数据（场景相关）
└── ...
```

**关键要求**：
- 数据分布要覆盖所有筛选条件组合
- ID引用关系必须一致
- 时间戳与system_time保持逻辑一致
- 使用JSONL格式（每行一条JSON记录）

### 需求模板 (User Need Templates)

定义用户需求场景，是样本多样性的核心：

```yaml
user_need_templates:
- need_template_id: LA_ANNUAL_WITH_COMPENSATORY
  description: 年假申请,调休充足优先扣除
  test_type: positive
  employee_filter_conditions:
    - field: compensatory_leave_balance
      operator: '>='
      value: 3
```

**详细指南**：见scenario_design_sop/references/need_template_design.md

### Query生成

**原则**：Query不存储在数据池，由样本生成器动态生成。

**生成流程**：

```
need_template["user_need_description"] + data_pools/{entity}.jsonl
    ↓
resolve_placeholders() 替换占位符
    ↓
base_query（结构化表达）
    ↓
LLM润色（可选，增加自然度和多样性）
    ↓
最终query
```

**LLM润色约束**（如使用）：
- **必须保留**：所有关键要素内容（数字、日期、实体名称、业务术语）
- **可以调整**：表达方式、语序、口语化程度
- **目标**：增加自然度和多样性，但不改变语义
- **配置**：使用Execute Agent的模型（确保所有被评测模型面对相同的query）

**Prompt示例**：
```
将以下查询改写得更自然口语化，但必须保留所有关键信息（数字、日期、名称）：

原文：你的需求：- 请假类型：年假 - 请假天数：3天 - 请假时间：下周一到周三

要求：只调整表达方式，不改变任何关键要素。
```

### 用户模拟器 (User Simulator)

多轮场景的核心组件，定义用户行为模式：

```markdown
## 角色定义
你是公司员工张小明...

## 需求描述
- 请假类型：年假
- 请假时间：3天

## 信息披露策略
采用progressive模式：先说核心需求，Agent询问时再提供细节

## 结束条件
当Agent成功处理你的申请时，输出 ###STOP###
```

**详细指南**：[references/user_simulator_design.md](references/user_simulator_design.md)

### 样本生成器 (Sample Generator)

主程序结构：

```python
import json
from pathlib import Path

class SampleGenerator:
    def __init__(self, data_dir, output_dir):
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        # 加载JSONL数据
        self.users = self.load_jsonl("users.jsonl")
        self.orders = self.load_jsonl("orders.jsonl")
        self.business_rules = self.load_file("BusinessRules.md")

    def load_jsonl(self, filename) -> list:
        """加载JSONL文件"""
        records = []
        with open(self.data_dir / filename, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    records.append(json.loads(line))
        return records

    def load_file(self, filename) -> str:
        with open(self.data_dir / filename, 'r', encoding='utf-8') as f:
            return f.read()

    def build_environment(self, user, order) -> list:
        """构建环境数据（JSONL格式字符串）"""
        return [
            {
                "path": "users.jsonl",
                "type": "file",
                "content": json.dumps(user, ensure_ascii=False)
            },
            {
                "path": "orders.jsonl",
                "type": "file",
                "content": json.dumps(order, ensure_ascii=False)
            }
        ]

    def build_checklist(self, template, user, order) -> list:
        """根据规则构建验证清单"""
        check_list = []
        # 根据业务规则添加检查项
        check_list.append({
            "check_type": "entity_attribute_equals",
            "params": {
                "entity_type": "orders",
                "target_id": order["order_guid"],
                "attribute_key": "骑行状态",
                "expected_value": "已结束"
            },
            "description": "校验点源于规则 xxx"
        })
        return check_list

    def generate_sample(self, template, user, order) -> dict:
        """组装完整样本（扁平结构）"""
        return {
            "data_id": f"BS_{template['id']:03d}",
            "query": template["query"],
            "system": self.business_rules,
            "servers": ["bikeshare_customer_service"],
            "environment": self.build_environment(user, order),
            "check_list": self.build_checklist(template, user, order),
            "user_simulator_prompt": template.get("user_simulator_prompt"),
            "extension": {}
        }

    def save_samples(self, samples: list):
        """保存为JSONL格式"""
        output_path = self.output_dir / "eval.jsonl"
        with open(output_path, 'w', encoding='utf-8') as f:
            for sample in samples:
                f.write(json.dumps(sample, ensure_ascii=False) + '\n')
```

## 样本格式

**⚠️ 重要**：样本格式是**全局统一的**，所有场景必须遵循`references/sample_format_spec.json`中定义的规范。

**格式规范文件**：`skills/sample_authoring/references/sample_format_spec.json`
- 包含完整的JSON Schema定义
- 定义了所有必需字段和可选字段
- 提供了每个checker类型的params结构
- 包含完整的示例

样本采用扁平结构，核心字段位于顶层：

```json
{
  "data_id": "BS_001",
  "query": "我都快被气死了，锁怎么都关不上！\n\n[系统识别相关订单：ord_001]",
  "system": "# 智能客服业务规则库\n\n你是一名专业的B端智能客服...",
  "servers": ["bikeshare_customer_service"],
  "environment": [
    {
      "path": "users.jsonl",
      "type": "file",
      "content": "{\"uuid\": \"usr_001\", \"name\": \"王晶\", \"user_loyalty_level\": \"gold\"...}"
    },
    {
      "path": "orders.jsonl",
      "type": "file",
      "content": "{\"order_guid\": \"ord_001\", \"user_uuid\": \"usr_001\"...}"
    }
  ],
  "check_list": [
    {
      "check_type": "entity_attribute_equals",
      "params": {
        "entity_type": "orders",
        "target_id": "ord_001",
        "attribute_key": "骑行状态",
        "expected_value": "已结束"
      },
      "description": "校验点源于规则 标准流程：应成功为用户远程关锁。"
    }
  ],
  "user_simulator_prompt": "你是员工张小明...",
  "extension": {}
}
```

### 核心字段说明

| 字段 | 必填 | 说明 |
|-----|-----|------|
| `data_id` | ✅ | 样本唯一标识 |
| `query` | ✅ | 用户初始查询 |
| `system` | ✅ | 系统提示词（BusinessRules内容） |
| `servers` | ✅ | 需要启动的MCP服务列表 |
| `environment` | ✅ | 环境数据文件列表 |
| `check_list` | ✅ | 评测检查点列表 |
| `user_simulator_prompt` | 多轮必填 | 用户模拟器提示词 |
| `extension` | ❌ | 扩展字段，用于场景特定元数据 |

### environment格式

**注意：environment 是 array，每个元素是一个文件配置对象**

```json
[
  {
    "path": "users.jsonl",
    "type": "file",
    "content": "{...jsonl内容，每行一条记录...}"
  }
]
```

### check_list格式

```json
{
  "check_type": "entity_attribute_equals",
  "params": {
    "entity_type": "orders",
    "target_id": "ord_001",
    "attribute_key": "status",
    "expected_value": "completed"
  },
  "description": "描述此检查点的业务意义"
}
```

**可用check_type**：见 `checker_implementation` skill

## 质量检查清单

- [ ] 数据池覆盖所有筛选条件组合
- [ ] 实体间ID引用关系一致
- [ ] check_list与业务规则完全对应
- [ ] 正向/负向/边界场景都有覆盖
- [ ] 样本格式符合上述扁平结构规范

## Reference Files

| 文件 | 内容 | 何时读取 |
|-----|------|---------|
| [sample_format_spec.json](references/sample_format_spec.json) | 样本格式JSON Schema | 实现生成器时 |
| [datapool_generator_template.py](references/datapool_generator_template.py) | 数据池生成器代码模板 | 生成实体数据时 |
| [user_simulator_design.md](references/user_simulator_design.md) | 用户模拟器设计指南 | 多轮场景设计时 |

> 完整样本示例参考：`mcp-benchmark/release/scenarios/*/samples/eval.jsonl`

## 案例代码

样本合成器的完整实现参考（供学习算法逻辑）：

| 场景 | 说明 |
|-----|------|
| bikeshare | Prototype驱动 + 规则引擎 |
| task_assignment | CSP约束求解 |

**重要**：参考代码时应：
- 学习其**算法逻辑**（条件匹配、规则引擎、check_list生成）
- 使用本文档展示的**输出格式**（扁平结构、JSONL）
- 输出到工作目录的 `samples/eval.jsonl`

### 两种生成模式对比

| 特性 | task_assignment | bikeshare |
|-----|-----------------|-----------|
| 算法类型 | CSP约束求解 | 规则匹配引擎 |
| Checklist生成 | 从分配结果推导 | 规则引擎动态计算 |
| 适用场景 | 资源分配类 | 业务规则判断类 |

### 格式转换示例代码

本skill提供了基于原始合成器修改后的完整示例代码：

| 场景 | 示例文件 | 说明 |
|-----|---------|------|
| bikeshare | [examples/bikeshare/sample_generator.py](examples/bikeshare/sample_generator.py) | 格式转换核心代码 |
| bikeshare | [examples/bikeshare/rule_engine.py](examples/bikeshare/rule_engine.py) | 规则引擎算法（计算check_list） |
| task_assignment | [examples/task_assignment/sample_generator.py](examples/task_assignment/sample_generator.py) | 格式转换核心代码 |
| task_assignment | [examples/task_assignment/assignment_algorithm.py](examples/task_assignment/assignment_algorithm.py) | CSP约束求解算法（任务分配+check_list生成） |

**代码结构**：
- `sample_generator.py` - 格式相关函数（`build_environment`、`format_sample`、`save_samples`）
- `rule_engine.py` / `assignment_algorithm.py` - 核心算法逻辑（条件匹配、check_list计算）

## 常见问题

**Q: 数据池要生成多少条数据？**
A: 确保每种筛选条件组合至少有3条匹配数据，总量通常在50-200条。

**Q: Prototype文件还需要吗？**
A: 如果YAML中有完整的`user_need_templates`，可以跳过独立的prototype文件。

**Q: check_list怎么设计？**
A: 从business_rules.success_criteria反推，确保每个规则的关键验证点都有对应checker。

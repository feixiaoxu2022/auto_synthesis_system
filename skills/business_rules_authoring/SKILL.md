---
name: business-rules-authoring
description: 编写Agent评测场景的业务规则文档(BusinessRules.md)。当需要为新场景定义Agent行为规范、业务约束和标准回复时使用此技能。适用于：(1)创建新场景的业务规则 (2)优化现有规则文档 (3)检查规则文档质量
---

# 业务规则编写指南

## Overview

BusinessRules.md是待测Agent的System Prompt，定义Agent的行为规范和业务约束。

**两大核心原则**：
1. **只写必要内容**：每条规则必须对应check_item或行业共识（不写工具文档、实体模型、系统设计）
2. **业务视角表达**：像给人类员工写工作手册，而非技术说明书（不泄露工具名、字段名、Checker逻辑）

**长度标准**：
遵循"每条规则必须师出有名"的原则，长度会自然合理。作为参考：
- 建议范围：大多数场景在50-300行
- 警惕信号：>500行很可能写了不该写的内容（工具文档、实体模型、伪代码等）
- 重点检查：如果超过建议范围，仔细检查是否每条规则都对应check_item

## 编写流程

**BusinessRules.md的定位**：基于unified_scenario_design.yaml，提取被测Agent需要知道的约束性规则，转化为业务语言。

```
Step 1: 读取设计文件
  └─ unified_scenario_design.yaml（完整场景设计，包含entities定义）
  └─ checklist（检查项列表）

Step 2: 识别约束性规则
  └─ 从checklist中识别所有check_item
  └─ 找到对应的业务约束和规则
  └─ 识别行业共识的必备知识

Step 3: 转化为业务语言
  └─ 将YAML中的技术配置转化为自然语言规则
  └─ 使用"触发条件-动作-回复"三要素格式
  └─ 避免泄露工具名、字段名等技术细节

Step 4: 质量检查
  └─ 确保每条规则都有对应的check_item
  └─ 检查长度是否合理（建议≤300行）
  └─ 参考 references/quality_checklist.md
```

**核心原则**：不是从零设计规则，而是从YAML中提取和转化规则。

## 标准规则格式

```markdown
**规则X.Y（规则名称）：**
- 当{业务条件1}，{业务条件2}时
- 动作：{自然语言描述的业务动作}
- 完成后回复："{标准回复模板}"
```

**示例：**
```markdown
**规则1.1（标准会议室预订）：**
- 当用户意图为"预订会议室"，预订时长≤8小时，且存在可用会议室时
- 动作：为用户安排合适的会议室，考虑参会人数和设备需求
- 完成后回复："您的会议室预订已成功处理。会议室{room_name}已为您预留，时间为{date} {start_time}-{end_time}。"
```

## 核心原则1：只写必要内容

**黄金法则：每条规则必须师出有名**

- ✅ **必须写**：对应checklist中check_item的约束性规则
- ✅ **必须写**：行业共识的必备知识（如医疗场景的隐私保护）
- ❌ **严禁写**：工具使用文档（应该在tools/*.py或YAML中）
- ❌ **严禁写**：实体模型字段定义（应该在unified_scenario_design.yaml的entities中）
- ❌ **严禁写**：执行流程伪代码、错误处理策略、重试逻辑
- ❌ **严禁写**：开发最佳实践、性能优化建议
- ❌ **严禁写**：示例场景、Checker设计说明

**自检问题**：写每条规则前问自己：
1. 这条规则对应哪个check_item？
2. 如果Agent违反这条规则，Checker会检测到吗？
3. 是否透露了工具名、字段名、判分标准？
4. 如果都答不出，说明这条规则不必要，删掉。

## 核心原则2：业务视角

| 必须包含 | 严格禁止 |
|---------|---------|
| 业务术语触发条件 | 工具名称/函数调用 |
| "做什么"的动作描述 | 数据库字段名 |
| 专业礼貌的回复 | Checker验证逻辑 |
| 业务约束边界 | 评测框架细节 |

**对比：**
```markdown
❌ 调用create_booking工具，传入room_id参数
✅ 为用户安排合适的会议室

❌ 当user.tier == 'vip'时
✅ 当用户为VIP客户时

❌ 成功标准：booking.status == 'confirmed'
✅ 完成后回复："您的预订已成功处理"
```

## 文档标准结构

```markdown
# {场景名称} - 业务规则

## 系统角色定义
{角色和职责}

## 核心能力
- {能力1} - {能力2} - {能力3}

## 业务规则
### 规则组1：{名称}
### 规则组2：{名称}

## 通用约束和原则
### 数据完整性原则
### 用户体验原则

## 异常情况处理
{至少4个异常场景}
```

## 编写流程（5阶段）

| 阶段 | 内容 | 时间 |
|-----|------|-----|
| 1. 框架搭建 | 复制模板，填写基本信息 | 15分钟 |
| 2. 规则设计 | 编写核心规则，设计优先级 | 45-90分钟 |
| 3. 通用约束 | 定义数据/用户体验/合规原则 | 20分钟 |
| 4. 异常处理 | 识别并定义异常场景 | 30分钟 |
| 5. 自检优化 | 运行质量检查 | 20分钟 |

**详细流程指南：** [references/writing_guide.md](references/writing_guide.md)

## 质量快速检查（5项核心）

- [ ] 所有规则都有"触发条件-动作-回复"三要素
- [ ] 全文没有工具名称、字段名等技术细节
- [ ] 至少定义4个异常场景
- [ ] 每条规则都对应checklist中的check_item
- [ ] 通用约束和原则完整

**完整检查清单：** [references/quality_checklist.md](references/quality_checklist.md)

## Reference Files

| 文件 | 内容 | 何时读取 |
|-----|------|---------|
| [writing_guide.md](references/writing_guide.md) | 5阶段详细编写流程 | 编写新规则时 |
| [quality_checklist.md](references/quality_checklist.md) | 8部分完整检查清单 | 质量审查时 |
| [common_mistakes.md](references/common_mistakes.md) | 15个常见错误对照表 | 遇到问题时查阅 |

## 优秀案例

编写规则时，**参考优秀案例学习设计模式和编写方法**：

| 案例文件 | 核心特点 |
|---------|---------|
| [ad_campaign_BusinessRules.md](examples/ad_campaign_BusinessRules.md) | 数据驱动决策、多维度分析、渐进式信息收集 |
| [intelligent_task_assignment_BusinessRules.md](examples/intelligent_task_assignment_BusinessRules.md) | 优先级排序、负载计算、技能匹配 |

**完整案例索引**：[examples/README.md](examples/README.md)（含设计模式提取和质量对比分析）

## 相关技能

- **format_specification_guide**：定义工具返回的数据格式规范

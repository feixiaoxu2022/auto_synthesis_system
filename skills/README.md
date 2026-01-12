# Skills 体系总览

## 简介

Skills是为LLM Agent评测场景自动合成系统设计的**标准化知识模块体系**，提供从场景设计到失败分析的全流程方法论支持。

**核心特点**：
- **项目解耦**：skills内容与具体项目目录结构无关，可移植到任何项目
- **模块化设计**：每个skill专注一个领域，可独立使用或组合使用
- **Agent友好**：通过`use_skill`工具调用，Agent可按需获取领域知识
- **完整方法论**：覆盖设计、实现、评测、分析全生命周期（7个标准skill模块）

## 评测目标：9个核心能力

Skills体系的最终目标是支持构建能够全方位评测LLM Agent在实际落地中所必备能力的自动化评测系统：

| 能力维度 | 定义 |
|---------|------|
| **1. 多模态理解** | 处理和融合文本、图像等多模态信息 |
| **2. 复杂上下文理解** | 跨轮整合上下文并保持一致性 |
| **3. Prompt遵循** | 理解并遵循用户指令与业务规则 |
| **4. Tool Use** | 准确选择工具并构造参数 |
| **5. 任务规划与工具组合** | 任务分解与工具编排 |
| **6. 多轮对话管理与用户引导** | 结构化收集信息与清晰反馈 |
| **7. 反思与动态调整** | 基于执行结果诊断并调整策略 |
| **8. 多源信息深度融合与洞察** | 处理多源数据的一致性与权衡 |
| **9. 结合领域知识的自主规划** | 利用领域知识做出专业决策 |

## Skills索引

### 🎨 设计阶段

| Skill | 用途 | 核心内容 |
|-------|------|---------|
| [scenario_design_sop](scenario_design_sop/) | 场景设计SOP | 五种设计方法、YAML结构、需求模板设计、能力覆盖映射 |
| [business_rules_authoring](business_rules_authoring/) | 业务规则编写 | 结构化模板、可验证性原则、规则设计模式 |

### ⚙️ 实现阶段

| Skill | 用途 | 核心内容 |
|-------|------|---------|
| [tool_implementation](tool_implementation/) | MCP工具实现 | 设计原则、代码模板、参数规范、错误处理 |
| [checker_implementation](checker_implementation/) | Checker实现 | 验证策略、类型选择、rule-based优先原则 |
| [sample_authoring](sample_authoring/) | 样本合成 | 格式规范、质量标准、生成器模板、JSONL格式 |

### 🧪 评测阶段

| Skill | 用途 | 核心内容 |
|-------|------|---------|
| [evaluation_execution](evaluation_execution/) | 评测执行 | benchkit使用、命令规范、调试技巧、3次失败规则 |

### 📊 分析阶段

| Skill | 用途 | 核心内容 |
|-------|------|---------|
| [failure_analysis](failure_analysis/) | 失败归因分析 | 四类归因、8步流程、三层验证、能力维度映射 |

## Skills工作流

```
┌─────────────────────────────────────────────────────────────┐
│                         设计阶段                              │
├─────────────────────────────────────────────────────────────┤
│  scenario_design_sop     ──→  unified_scenario_design.yaml  │
│  business_rules_authoring ──→  BusinessRules.md             │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓ 设计完成
┌─────────────────────────────────────────────────────────────┐
│                        实现阶段                               │
├─────────────────────────────────────────────────────────────┤
│  tool_implementation     ──→  tools/*.py                    │
│  checker_implementation  ──→  checkers/*.py                 │
│  sample_authoring        ──→  samples/eval.jsonl            │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓ 样本生成完成
┌─────────────────────────────────────────────────────────────┐
│                        评测阶段                               │
├─────────────────────────────────────────────────────────────┤
│  evaluation_execution    ──→  evaluation_outputs/*.json     │
└────────────────────┬────────────────────────────────────────┘
                     │
                     ↓ 发现失败案例
┌─────────────────────────────────────────────────────────────┐
│                        分析阶段                               │
├─────────────────────────────────────────────────────────────┤
│  failure_analysis        ──→  analysis/*_analysis_*.json    │
│                          ──→  改进建议和问题定位              │
└─────────────────────────────────────────────────────────────┘
```

## 如何使用

### 方式1：Agent通过use_skill工具调用

```python
# Agent调用示例
use_skill(skill_type="scenario_design_sop")
use_skill(skill_type="sample_authoring")
use_skill(skill_type="failure_analysis")
```

### 方式2：直接阅读skill文档

每个skill目录包含：
- **SKILL.md**：快速入门和核心内容
- **references/**：详细参考文档
- **templates/**：代码模板和配置模板
- **examples/**：优秀案例

### 方式3：移植到其他项目

1. 复制整个skills目录到目标项目
2. 在Agent system prompt中注入目录约定
3. Agent通过`use_skill`工具访问（需要实现UseSkill工具）

## Skills设计原则

### 1. 项目解耦

**问题**：早期版本skills中硬编码了项目特定路径（如`outputs/`、`场景目录`），导致无法移植。

**解决方案**：
- Skills使用通用概念（如"工作目录"）
- 具体路径由Agent system prompt注入
- 参考：`AGENT_DIRECTORY_CONVENTIONS.md`

**示例对比**：

```markdown
# ❌ 硬编码路径（旧版本）
样本文件位置：outputs/<scenario_name>/samples/eval.jsonl

# ✅ 通用概念（新版本）
样本文件位置：<工作目录>/samples/eval.jsonl
（工作目录由Agent context提供）
```

### 2. 模块化与可组合

每个skill专注一个领域，可独立使用或组合使用：

- **单独使用**：只需要sample_authoring来了解样本格式
- **组合使用**：scenario_design_sop + business_rules_authoring完成设计
- **全流程**：从设计到分析，7个skill覆盖完整链路

### 3. Agent友好

- **结构化内容**：表格、清单、决策树，便于LLM解析
- **分层展示**：SKILL.md提供快速入门，references/提供详细指南
- **实例驱动**：每个概念都有examples/中的真实案例

### 4. 可验证性优先

Skills强调"可验证性是底线"：

- **scenario_design_sop**：验证方式优先级（Rule-based > LLM Judge）
- **checker_implementation**：Checker类型选择决策树
- **failure_analysis**：三层验证机制

## 能力体系的贯穿

9个核心能力在skills中的体现：

| 能力 | 在scenario_design_sop中 | 在failure_analysis中 |
|-----|------------------------|---------------------|
| **设计时** | 明确每个场景测试哪些能力 | - |
| **分析时** | - | 将Agent失败映射到能力维度 |

**设计侧**：scenario_design_sop提供"设计方法与能力的映射"表格，指导设计者有意识地覆盖核心能力。

**分析侧**：failure_analysis提供"Agent能力问题的细分维度"表格，帮助分析者准确定位能力缺陷。

## 贡献指南

### 添加新skill

1. 创建目录：`skills/your_skill_name/`
2. 创建SKILL.md：遵循现有格式（name、description、Overview、Quick Start）
3. 添加references/和examples/（如需要）
4. 更新本README的索引表
5. 在skills.json中注册（如有）

### 优化现有skill

1. 确保修改不破坏项目解耦原则
2. 更新相关examples/
3. 如涉及格式规范，同步更新templates/

## 许可证

本skills体系遵循项目根目录的许可证。

## 联系方式

- **Issues**：在GitHub仓库提交issue
- **讨论**：在项目discussions区讨论设计思路

---

**版本**：v1.0
**最后更新**：2026-01-12
**维护者**：Universal Scenario Framework Team

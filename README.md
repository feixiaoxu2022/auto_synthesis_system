# Auto Synthesis System

**Agent驱动的评测样本自动合成系统**

[![License](https://img.shields.io/badge/license-MIT-green)]()

## 简介

Auto Synthesis System是一个由LLM Agent驱动的自动化系统，用于生成高质量的Agent评测样本。系统从用户需求出发，自动完成工具实现、Checker编写、样本合成和评测执行的全流程。

**核心特点**：
- **全流程自动化**：从场景设计到评测执行，一站式完成
- **Agent驱动**：基于Claude Sonnet的智能Agent自主决策和执行
- **Skills支持**：集成7个标准化skill模块，提供领域知识指导
- **Checkpoint恢复**：支持断点续跑，可随时暂停和恢复
- **MCP工具生态**：使用FastMCP快速实现业务工具

## 系统架构

```
用户需求
    ↓
┌────────────────────────────────────┐
│    Scenario Builder Agent           │
│  ┌──────────────────────────────┐  │
│  │ Step 1: 工具实现 (tools/)    │  │
│  └──────────────────────────────┘  │
│  ┌──────────────────────────────┐  │
│  │ Step 2: Checker实现          │  │
│  └──────────────────────────────┘  │
│  ┌──────────────────────────────┐  │
│  │ Step 3: 样本合成 (JSONL)     │  │
│  └──────────────────────────────┘  │
│  ┌──────────────────────────────┐  │
│  │ Step 4: 评测执行 (benchkit)  │  │
│  └──────────────────────────────┘  │
│  ┌──────────────────────────────┐  │
│  │ Step 5: 失败分析 (可选)      │  │
│  └──────────────────────────────┘  │
└────────────────────────────────────┘
    ↓
评测报告 + 样本文件
```

## 快速开始

### 安装依赖

```bash
pip install -r requirements.txt
```

### 基本使用

```bash
# 从需求描述开始生成样本
python main.py "为会议室预订场景生成评测样本"

# 指定工作目录
python main.py "生成请假审批场景样本" --work-dir ./my_work

# 使用不同模型
python main.py "生成短剧创作场景样本" --model claude-opus-4-5

# 从checkpoint恢复
python main.py --resume
```

### 目录结构

```
work/<scenario_name>/           # 工作目录
├── tools/                       # MCP工具实现
│   ├── __init__.py
│   └── business_tools.py
├── checkers/                    # Checker实现
│   └── checker.py
├── samples/                     # 合成的样本
│   └── eval.jsonl
├── evaluation_outputs/          # 评测结果
│   ├── execution/
│   └── evaluation/
└── analysis/                    # 失败分析（可选）
    └── *_analysis_*.json
```

## Skills体系

系统集成了7个标准化的skill模块，为Agent提供领域知识支持：

| Skill | 用途 | 路径 |
|-------|------|------|
| **tool_implementation** | MCP工具实现指南 | `.claude/skills/tool_implementation/` |
| **checker_implementation** | Checker实现指南 | `.claude/skills/checker_implementation/` |
| **sample_authoring** | 样本合成SOP | `.claude/skills/sample_authoring/` |
| **evaluation_execution** | 评测执行指南 | `.claude/skills/evaluation_execution/` |
| **failure_analysis** | 失败归因分析方法论 | `.claude/skills/failure_analysis/` |

Skills已独立维护在：[agent-evaluation-skills](https://github.com/feixiaoxu2022/agent-evaluation-skills)

> **注意**：scenario_design_sop 和 business_rules_authoring 两个skill已从系统中移除，因为场景设计阶段由人工完成更为高效。

## Agent工作流程

### Step 1: 工具实现
- 基于场景需求，使用FastMCP实现MCP工具
- 遵循tool_implementation skill的设计原则
- 输出：`work/<scenario>/tools/*.py`

### Step 2: Checker实现
- 根据验证需求，实现独立的Checker脚本
- 优先使用已有的成熟checker类型
- 输出：`work/<scenario>/checkers/checker.py`

### Step 3: 样本合成
- 基于场景配置，生成多样化的评测样本
- 严格遵循JSONL格式规范
- 输出：`work/<scenario>/samples/eval.jsonl`

### Step 4: 评测执行
- 使用benchkit框架批量执行样本
- 收集执行结果和评测报告
- 输出：`work/<scenario>/evaluation_outputs/`

### Step 5: 失败分析（可选）
- 对失败案例进行深度归因分析
- 区分Agent能力问题 vs 系统问题
- 输出：改进建议和问题定位

## Checkpoint与Resume

系统自动保存checkpoint，支持断点续跑：

```bash
# 查看最近的checkpoint
ls checkpoints/

# 从最近的checkpoint恢复
python main.py --resume

# 恢复后继续执行
python main.py --resume "继续执行评测"
```

## 配套框架

- **MCP-Benchmark**: 评测框架，提供executor、evaluator等运行时组件
  - 仓库：https://github.com/feixiaoxu2022/mcp-benchmark
- **Agent Evaluation Skills**: 标准化知识模块体系
  - 仓库：https://github.com/feixiaoxu2022/agent-evaluation-skills

## 贡献指南

欢迎提交Issue和Pull Request！

### 开发约定

- 遵循PEP 8代码风格
- 测试脚本放在`test/`目录
- 避免写fallback逻辑，保持代码简洁
- 所有相对路径基于工作目录

## 许可证

MIT License

---

**版本**：v2.0 (单Agent架构)
**最后更新**：2026-01-12
**维护者**：Universal Scenario Framework Team

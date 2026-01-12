# Agent 目录约定（合成系统特定）

本文档定义了 Auto Synthesis System 中的目录结构约定。这些约定应注入到 Agent 的 System Prompt 中，而 Skills 本身保持通用性。

## 目录结构

```
<workspace_root>/
├── outputs/                          # 场景输出根目录
│   └── <scenario_name>/              # 单个场景的工作目录
│       ├── unified_scenario_design.yaml
│       ├── BusinessRules.md
│       ├── data_pools/               # 数据池目录
│       │   └── *.jsonl
│       ├── scripts/
│       │   └── sample_generator/     # 样本合成器代码
│       │       ├── generate_samples.py
│       │       └── ...
│       ├── samples/                  # 生成的样本
│       │   └── eval.jsonl
│       ├── tools/                    # MCP 工具实现
│       │   └── *.py
│       ├── checker/                  # Checker 实现
│       │   └── *.py
│       ├── benchkit/                 # 评测框架（自动拷贝）
│       │   ├── executor.py
│       │   ├── evaluator.py
│       │   └── model_config.json
│       └── evaluation_outputs/       # 评测结果
│           ├── execution/
│           └── evaluation/
└── .claude/
    └── skills/                       # Skills 库（通用，已移至 .claude 目录便于维护）
```

## Init Agent 目录约定

**工作目录**：`outputs/<scenario_name>/`（由 Orchestrator 通过 context 传入）

**输出路径**：
- 设计文件：`unified_scenario_design.yaml`（工作目录下）
- 业务规则：`BusinessRules.md`（工作目录下）
- 数据池：`data_pools/*.jsonl`（工作目录下）

**样本合成器代码位置**：`scripts/sample_generator/`（工作目录下）

## Execute Agent 目录约定

**工作目录**：`outputs/<scenario_name>/`（从 Init Agent 继承）

**输入路径**：
- 设计文件：`unified_scenario_design.yaml`
- 业务规则：`BusinessRules.md`
- 样本文件：`samples/eval.jsonl`
- 工具实现：`tools/*.py`
- Checker实现：`checker/*.py`

**输出路径**：
- 评测结果：`evaluation_outputs/execution/`（Executor 输出）
- 评估结果：`evaluation_outputs/evaluation/`（Evaluator 输出）

**Benchkit 位置**：`benchkit/`（工作目录下，系统自动拷贝）

## 路径使用原则

1. **相对路径优先**：Skills 中的所有路径示例使用相对于工作目录的相对路径
2. **工作目录由 Context 提供**：Agent 从 `context["output_dir"]` 或 `context["working_dir"]` 获取
3. **Skills 不假设目录名**：不写死 "outputs"、"scenarios" 等具体名称

## 注入到 System Prompt 的文本

### Init Agent System Prompt 片段

```markdown
## 目录结构约定

你的工作目录是：`{context["output_dir"]}`

请将生成的文件放置在以下位置（相对于工作目录）：
- **设计文件**：`unified_scenario_design.yaml`
- **业务规则**：`BusinessRules.md`
- **数据池**：`data_pools/<entity_name>.jsonl`
- **样本合成器**：`scripts/sample_generator/generate_samples.py`

所有使用 file_writer 工具时的路径都是相对于工作目录的相对路径。
```

### Execute Agent System Prompt 片段

```markdown
## 目录结构约定

你的工作目录是：`{context["working_dir"]}`

关键文件位置（相对于工作目录）：
- **设计文件**：`unified_scenario_design.yaml`
- **业务规则**：`BusinessRules.md`
- **样本文件**：`samples/eval.jsonl`
- **Benchkit**：`benchkit/`（已自动拷贝）
- **评测输出**：`evaluation_outputs/`

执行 benchkit 命令时，确保在工作目录下执行，所有路径使用相对路径。
```

## 迁移指南

如果要在其他项目中使用这些 Skills：

1. 保持 Skills 目录原样复制
2. 修改 Agent System Prompt，定义新的目录约定
3. 调整 Orchestrator 传入的 context 中的路径字段
4. 无需修改 Skills 本身的内容

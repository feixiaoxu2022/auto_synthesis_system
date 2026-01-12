# Agent 目录约定（合成系统特定）

本文档定义了 Auto Synthesis System 中的目录结构约定。这些约定应注入到 Agent 的 System Prompt 中，而 Skills 本身保持通用性。

## 目录结构

```
<workspace_root>/
├── work/                              # 工作根目录
│   └── <scenario_name>/               # 单个场景的工作目录
│       ├── tools/                     # MCP 工具实现
│       │   ├── __init__.py
│       │   └── business_tools.py
│       ├── checkers/                  # Checker 实现
│       │   └── checker.py
│       ├── samples/                   # 生成的样本
│       │   └── eval.jsonl
│       ├── benchkit/                  # 评测框架（自动拷贝）
│       │   ├── executor.py
│       │   ├── evaluator.py
│       │   └── model_config.json
│       ├── evaluation_outputs/        # 评测结果
│       │   ├── execution/
│       │   └── evaluation/
│       └── analysis/                  # 失败分析（可选）
│           └── *_analysis_*.json
├── checkpoints/                       # Checkpoint 存储
│   ├── latest.json
│   └── <timestamp>.json
└── .claude/
    └── skills/                        # Skills 库（通用）
        ├── tool_implementation/
        ├── checker_implementation/
        ├── sample_authoring/
        ├── evaluation_execution/
        └── failure_analysis/
```

## Scenario Builder Agent 目录约定

**工作目录**：`work/<scenario_name>/`（由 Orchestrator 通过 context 传入）

**输入路径**：
- 场景配置：由用户或外部提供（unified_scenario_design.yaml, BusinessRules.md等）
- Skills：`.claude/skills/`（通过skill工具访问）

**输出路径**：
- 工具实现：`tools/*.py`（工作目录下）
- Checker实现：`checkers/checker.py`（工作目录下）
- 样本文件：`samples/eval.jsonl`（工作目录下）
- 评测结果：`evaluation_outputs/`（工作目录下）
  - Executor输出：`evaluation_outputs/execution/`
  - Evaluator输出：`evaluation_outputs/evaluation/`
- 失败分析：`analysis/*_analysis_*.json`（可选，工作目录下）

**Benchkit 位置**：`benchkit/`（工作目录下，系统自动拷贝）

## 路径使用原则

1. **相对路径优先**：Skills 中的所有路径示例使用相对于工作目录的相对路径
2. **工作目录由 Context 提供**：Agent 从 `context["work_dir"]` 获取
3. **Skills 不假设目录名**：不写死 "work"、"scenarios" 等具体名称
4. **所有相对路径都基于工作目录**：执行benchkit命令、读写文件等都使用相对路径

## 注入到 System Prompt 的文本

### Scenario Builder Agent System Prompt 片段

```markdown
## 目录结构约定

你的工作目录是：`{context["work_dir"]}`

请将生成的文件放置在以下位置（相对于工作目录）：
- **工具实现**：`tools/<tool_name>.py`
- **Checker实现**：`checkers/checker.py`
- **样本文件**：`samples/eval.jsonl`
- **Benchkit**：`benchkit/`（已自动拷贝）
- **评测输出**：`evaluation_outputs/`

执行 benchkit 命令时，确保在工作目录下执行，所有路径使用相对路径。

示例命令：
```bash
python benchkit/executor.py \\
  --scenario . \\
  --samples samples/eval.jsonl \\
  --results-dir evaluation_outputs/execution
```
```

## 工作流程中的目录使用

### Step 1: 工具实现
- 输出目录：`work/<scenario>/tools/`
- 文件命名：根据业务功能命名，如 `meeting_room_tools.py`

### Step 2: Checker实现
- 输出目录：`work/<scenario>/checkers/`
- 文件命名：`checker.py`（标准名称）

### Step 3: 样本合成
- 输出目录：`work/<scenario>/samples/`
- 文件命名：`eval.jsonl`（标准名称）

### Step 4: 评测执行
- Benchkit位置：`work/<scenario>/benchkit/`（自动拷贝）
- 输出目录：`work/<scenario>/evaluation_outputs/`
  - Executor：`evaluation_outputs/execution/`
  - Evaluator：`evaluation_outputs/evaluation/`

### Step 5: 失败分析（可选）
- 输出目录：`work/<scenario>/analysis/`
- 文件命名：`<sample_id>_analysis_<timestamp>.json`

## 迁移指南

如果要在其他项目中使用这个系统：

1. 保持 Skills 目录原样复制
2. 修改 Agent System Prompt，定义新的目录约定
3. 调整 Orchestrator 传入的 context 中的路径字段
4. 无需修改 Skills 本身的内容

## Checkpoint 约定

Checkpoints 存储在独立目录 `checkpoints/`，不在工作目录下：
- 最新checkpoint：`checkpoints/latest.json`
- 历史checkpoint：`checkpoints/<timestamp>.json`
- 包含内容：对话历史、工作状态、产物路径等

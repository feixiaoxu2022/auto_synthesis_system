---
name: evaluation-execution
description: 执行Agent自动评测。理解BenchKit框架架构，配置和运行评测任务，收集评测结果。这是Step 4的核心执行工作。
---
# 评测执行指南

## Overview

评测执行是Step 4的核心工作，使用BenchKit框架批量执行样本任务并评估Agent表现。

**输入**：工作目录 + 样本文件(JSONL) + 模型配置
**输出**：执行结果 + 评测报告

```
样本文件 (JSONL)
       ↓
   ┌───┴───┐
   ↓       ↓
executor  MCP Servers
   └───┬───┘
       ↓
 执行结果 (JSON)
       ↓
   evaluator
       ↓
 评测报告 (JSON)
```

---

## ⚠️ 工作环境（重要）

**工作目录**：由调用方（Agent）通过 context 指定

**benchkit位置**：工作目录下的 `benchkit/` 子目录

- 系统已自动将benchkit拷贝到工作目录
- 配置文件：`benchkit/model_config.json`
- 执行器：`benchkit/executor.py`

**所有相对路径都基于工作目录**：

- `benchkit/executor.py` → 工作目录下的benchkit
- `samples/eval.jsonl` → 工作目录下的samples
- `tools/xxx.py` → 工作目录下的tools

---

## ⚠️ 核心要点

### 1. executor.py 不会自动读取配置文件

**必须通过CLI参数显式传递**：`--model`, `--base-url`, `--api-key`

❌ 错误：不带这些参数，期望自动读取
❌ 错误：使用 `--model-config` 参数（不存在）
✅ 正确：从配置文件提取值，通过CLI参数传递

### 2. 配置文件位置和格式

**位置**：`benchkit/model_config.json`（工作目录下）

**格式**：

```json
{
  "judge": {"model": "claude-sonnet-4-5-20250929", "base_url": "http://...", "api_key": "sk-..."},
  "agent": {"model": "gpt-5", "base_url": "http://...", "api_key": "sk-..."},
  "simulator": {"model": "gemini-3-pro-preview", "base_url": "http://...", "api_key": "sk-..."}
}
```

---

## 快速开始

**建议工作流程**：

1. **先测试5个样本**：在执行命令中加 `--limit 5` 参数
2. **查看结果**：检查 `evaluation_outputs/execution/` 目录确认输出正常
3. **全量评测**：移除 `--limit 5` 参数重新运行

**完整命令见下方【两阶段流程】**。

**重要提示**：
- benchkit是基础设施，直接调用即可，无需理解内部实现
- 遇到问题时调用ask_human寻求帮助

---

## 框架架构

### 核心组件

| 组件                   | 职责                          |
| ---------------------- | ----------------------------- |
| `executor.py`        | Agent任务执行器，批量执行样本 |
| `evaluator.py`       | Checker评估器，验证执行结果   |
| `agent.py`           | MCP Agent核心，处理工具调用   |
| `mcp_client.py`      | MCP协议客户端                 |
| `check_runner.py`    | Checker运行器                 |
| `user_simulator.py`  | 用户模拟器(多轮对话)          |
| `server_launcher.py` | MCP服务启停管理               |
| `tools_discovery.py` | 工具动态发现                  |

### 目录布局

```
<工作目录>/                     # Execute Agent的工作目录
├── benchkit/                    # 评测框架（自动拷贝）
│   ├── executor.py
│   ├── evaluator.py
│   ├── model_config.json        # 模型配置
│   └── ...
├── samples/*.jsonl              # 样本文件
├── checkers/checker.py          # 检查器实现
├── tools/*.py                   # 工具实现
└── evaluation_outputs/          # 评测结果
    ├── execution/               # executor输出
    └── evaluation/              # evaluator输出
```

---

## 两阶段流程

评测分为两个独立阶段，按顺序执行：

### 阶段1: Agent执行 (executor.py)

执行Agent任务，生成对话历史和工具调用记录。

```bash
# 读取配置
AGENT_MODEL=$(python -c "import json; print(json.load(open('benchkit/model_config.json'))['agent']['model'])")
AGENT_BASE_URL=$(python -c "import json; print(json.load(open('benchkit/model_config.json'))['agent']['base_url'])")
AGENT_API_KEY=$(python -c "import json; print(json.load(open('benchkit/model_config.json'))['agent']['api_key'])")

# 执行评测
python benchkit/executor.py \
  --scenario . \
  --samples samples/eval.jsonl \
  --results-dir evaluation_outputs/execution \
  --model "$AGENT_MODEL" \
  --base-url "$AGENT_BASE_URL" \
  --api-key "$AGENT_API_KEY"
```

**输出**: `evaluation_outputs/execution/{data_id}.json` - 包含conversation_history、tool_call_list、final_state等

### 阶段2: Checker评估 (evaluator.py)

对执行结果运行检查器，生成评测报告。

```bash
# 读取配置
JUDGE_MODEL=$(python -c "import json; print(json.load(open('benchkit/model_config.json'))['judge']['model'])")
JUDGE_BASE_URL=$(python -c "import json; print(json.load(open('benchkit/model_config.json'))['judge']['base_url'])")
JUDGE_API_KEY=$(python -c "import json; print(json.load(open('benchkit/model_config.json'))['judge']['api_key'])")

# 运行评估
python benchkit/evaluator.py \
  --scenario . \
  --results-dir evaluation_outputs/execution \
  --output-dir evaluation_outputs/evaluation \
  --judge-model "$JUDGE_MODEL" \
  --base-url "$JUDGE_BASE_URL" \
  --api-key "$JUDGE_API_KEY" \
  --skip-env-check
```

**输出**: `evaluation_outputs/evaluation/summary.json` - 包含整体指标和每个样本的检查结果

### 常用参数

**executor.py**:
- `--limit N`: 限制执行数量（测试用）
- `--offset M`: 跳过前M个样本
- `--offset M --limit N`: 测试第M+1到M+N个样本
- `--resume`: 跳过已完成样本（断点续跑）
- `--max-concurrency 2-4`: 并发执行（注意rate limit）
- `--max-turns 20`: 最大对话轮数
- `--temperature 0.0`: 采样温度

**evaluator.py**:
- `--samples`: 指定样本文件（必须与executor使用的一致，否则data_id不匹配）
- `--skip-env-check`: 跳过MCP服务器启动（大多数场景适用，GitHub等实时场景不用）
- `--resume`: 跳过已完成检查（断点恢复）
- `--max-concurrency 2-4`: 并发检查
- `--max-retries 2`: LLM API限速重试次数

---

## 模型配置

### 配置文件位置

模型配置在 `benchkit/model_config.json`中定义，包含judge/agent/simulator三种模型的端点和密钥。

### 三种模型角色

| 角色      | 环境变量前缀      | 用途               |
| --------- | ----------------- | ------------------ |
| Agent     | `BENCH_AGENT_*` | 待测模型           |
| Judge     | `BENCH_CHECK_*` | 检查模型(语义检查) |
| Simulator | `BENCH_SIM_*`   | 用户模拟器         |

### 配置优先级

executor/evaluator的配置读取顺序：

1. **CLI参数**（`--model`, `--base-url`, `--api-key`）**← 推荐使用**
2. 环境变量（`OPENAI_BASE_URL`, `OPENAI_API_KEY`）
3. 框架默认值

**推荐做法**：从 `benchkit/model_config.json`读取配置，通过CLI参数传递给executor（见上方"快速开始"示例）。

### 配置文件格式

```json
{
  "judge": {"model": "deepseek-v3", "base_url": "...", "api_key": "..."},
  "agent": {"model": "gpt-4.1", "base_url": "...", "api_key": "..."},
  "simulator": {"model": "gpt-4.1-mini", "base_url": "...", "api_key": "..."}
}
```

---

## 常用运行模式

### 测试模式(限制数量)

```bash
python executor.py ... --limit 5
```

### 断点续跑

```bash
python executor.py ... --resume
```

### 指定样本范围

```bash
# 测试第6-10个样本
python executor.py ... --offset 5 --limit 5

# 从第11个样本测试到最后
python executor.py ... --offset 10
```

### 并发执行

```bash
python executor.py ... --max-concurrency 4
```

### 详细日志

```bash
python executor.py ... --verbose
```

---

## 结果判定规则

评测框架统一识别 `overall_result`字段：

| 值          | 含义         |
| ----------- | ------------ |
| `Success` | 通过所有检查 |
| `Failure` | 未通过检查   |
| `Error`   | 执行异常     |

**场景差异**：

- 大部分场景：`overall_result`
- data_analysis：`final_conclusion`
- trip/crm：`passed`(布尔值)

---

## 完整评测示例

```python
import json

# 读取模型配置（当前工作目录）
with open('benchkit/model_config.json') as f:
    config = json.load(f)

agent_cfg = config['agent']
judge_cfg = config['judge']

# 1. 执行Agent任务
executor_cmd = f"""python benchkit/executor.py \
  --scenario . \
  --samples samples/eval.jsonl \
  --results-dir evaluation_outputs/execution \
  --model {agent_cfg['model']} \
  --base-url {agent_cfg['base_url']} \
  --api-key {agent_cfg['api_key']} \
  --max-concurrency 2 \
  --resume"""

bash(command=executor_cmd)

# 2. 运行评估
evaluator_cmd = f"""python benchkit/evaluator.py \
  --scenario . \
  --results-dir evaluation_outputs/execution \
  --output-dir evaluation_outputs/evaluation \
  --judge-model {judge_cfg['model']} \
  --base-url {judge_cfg['base_url']} \
  --api-key {judge_cfg['api_key']} \
  --skip-env-check"""

bash(command=evaluator_cmd)
```

---

## 常见问题

**Q: executor.py 会自动读取 model_config.json 吗？**
A: **不会**。必须通过 `--model`, `--base-url`, `--api-key` 参数显式传递。

**Q: 为什么提示 `required arguments: --model`？**
A: 缺少必需参数。检查命令是否包含 `--model`, `--base-url`, `--api-key`（参考"快速开始"示例）。

**Q: 可以使用 `--model-config` 参数吗？**
A: **不可以**，这个参数不存在。必须从配置文件提取值，分别传递 `--model`, `--base-url`, `--api-key`。

**Q: 找不到 benchkit/model_config.json 怎么办？**
A: benchkit已自动拷贝到工作目录。检查工作目录下是否有 `benchkit/`子目录，如果没有，说明初始化有问题。

**Q: 执行中断了怎么办？**
A: 使用 `--resume`参数重新运行，会自动跳过已完成的样本。

**Q: Rate limit怎么处理？**
A: 降低 `--max-concurrency`到2或1，框架内置了重试机制。

**Q: 如何只测试部分样本？**
A: 使用 `--limit N` 和 `--offset M` 参数：
  - `--limit 5` - 测试前5个样本
  - `--offset 5 --limit 5` - 测试第6-10个样本
  - `--offset 10` - 从第11个样本测试到最后

**Q: checker报错怎么排查？**
A: 检查 `final_state`是否正确、检查checker.py的check_list定义是否与样本匹配。

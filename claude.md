# Auto Synthesis System - Claude Code 约定

本文档定义了在使用Claude Code开发和维护Auto Synthesis System时的约定和最佳实践。

## 代码约定

1. **测试脚本位置**：所有测试脚本必须放在 `test/` 目录下
2. **避免fallback逻辑**：非特别必要的情况，不要写fallback逻辑；如果要写，必须向用户确认
3. **遵循PEP 8**：Python代码遵循PEP 8风格指南
4. **相对路径**：所有文件路径使用相对于工作目录的相对路径

## 系统架构

Auto Synthesis System v2.0采用**单Agent架构**：
- **Scenario Builder Agent**：负责从工具实现到评测执行的全流程
- **Orchestrator**：负责Agent生命周期管理和Checkpoint管理
- **Skills**：7个标准化知识模块，通过`use_skill`工具调用

## Agent开发约定

### System Prompt 注入
- 目录结构约定必须注入到Agent的system prompt
- 详见 `AGENT_DIRECTORY_CONVENTIONS.md`

### Skills使用
- Agent通过`use_skill(skill_name)`工具访问领域知识
- Skills路径：`.claude/skills/<skill_name>/SKILL.md`
- 可用skills：
  - tool_implementation
  - checker_implementation
  - sample_authoring
  - evaluation_execution
  - failure_analysis

### 工作目录约定
- 工作根目录：`work/`
- 场景目录：`work/<scenario_name>/`
- 所有相对路径基于工作目录

## Checkpoint机制

- **自动保存**：每次工具调用后自动保存checkpoint
- **断点续跑**：使用 `--resume` 参数恢复
- **存储位置**：`checkpoints/`目录
- **包含内容**：对话历史、工作状态、产物路径

## 工作流程

```
Step 1: 工具实现 (tools/)
  ↓
Step 2: Checker实现 (checkers/checker.py)
  ↓
Step 3: 样本合成 (samples/eval.jsonl)
  ↓
Step 4: 评测执行 (benchkit)
  ↓
Step 5: 失败分析 (analysis/, 可选)
```

## 开发提示

- Agent应该自主决策工作流程，避免硬编码步骤
- 优先使用已有的成熟checker类型
- 样本格式必须严格遵循 `.claude/skills/sample_authoring/references/sample_format_spec.json`
- Benchkit命令的所有路径使用相对路径

## 注意事项

- ⚠️ 不要将场景设计阶段纳入自动化（scenario_design_sop和business_rules_authoring已从系统移除）
- ⚠️ 确保benchkit在工作目录下执行
- ⚠️ 所有文件读写操作使用相对路径

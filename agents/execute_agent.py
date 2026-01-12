"""
Execute Agent - 负责执行、评测和优化（Layer 2-3-4）

工具集：file_reader, file_writer, file_editor, bash, use_skill
使用独立tools模块实现
"""
import json
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, List

from .base_agent import BaseAgent, AgentResult, Tool, ContextConfig
from tools import FileReader, FileWriter, FileEditor, BashExecutor, UseSkill, AskHuman
from tools.validate_sample_format import validate_jsonl_file


class ExecuteAgent(BaseAgent):
    """
    Execute Agent - 执行评测Agent

    职责:
    - Layer 2: 组件生成（tools, checkers, data_pools）
    - Layer 3: 样本合成
    - Layer 4: 评测归因

    决策:
    - 成功率>=85% → 完成
    - Critical问题>30% → 返回Init
    - 其他 → 继续下一个step
    """

    # Execute Agent的Context配置
    # 注意：Bedrock claude-sonnet-4-5 实际限制是200K tokens，不是1M！
    DEFAULT_CONTEXT_CONFIG = ContextConfig(
        compact_threshold=120_000,  # 60% of 200K，留足buffer
        api_hard_limit=200_000,     # Bedrock实际限制
        keep_recent_steps=3         # 减少保留步数，防止最近几步本身就过大
    )

    def __init__(
        self,
        skills_dir: str = ".claude/skills",
        model: str = "claude-sonnet-4-5-20250929",
        max_iterations: int = 200,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None
    ):
        self.skills_dir = Path(skills_dir)
        self.scenario_dir: Optional[Path] = None
        self.current_iteration = 0
        self.iteration_history: List[Dict] = []

        # 工具实例（延迟初始化，需要scenario_dir）
        self._file_reader: Optional[FileReader] = None
        self._file_writer: Optional[FileWriter] = None
        self._file_editor: Optional[FileEditor] = None
        self._bash: Optional[BashExecutor] = None
        self._use_skill = UseSkill(skills_dir=self.skills_dir)
        self._ask_human = AskHuman()  # 可由 Orchestrator 注入自定义 handler

        # 样本格式验证状态标志
        self._samples_validation_reminded = False

        # 定义工具
        tools = self._create_tools()

        super().__init__(
            model=model,
            max_iterations=max_iterations,
            tools=tools,
            base_url=base_url,
            api_key=api_key
        )

    def _setup_benchkit_for_scenario(self, scenario_dir: Path):
        """拷贝benchkit到场景目录"""
        target_benchkit = scenario_dir / "benchkit"

        if target_benchkit.exists():
            return  # 已存在，跳过

        # 源benchkit路径：auto_synthesis_system/benchkit
        source_benchkit = Path(__file__).parent.parent / "benchkit"

        if not source_benchkit.exists():
            raise FileNotFoundError(f"源benchkit不存在: {source_benchkit}")

        # 直接拷贝整个目录
        shutil.copytree(source_benchkit, target_benchkit)

        from .base_agent import _console
        _console.print(f"  ✓ 已拷贝benchkit到场景目录", style="green")

    def _init_tools_for_scenario(self, scenario_dir: Path):
        """为场景初始化工具"""
        self.scenario_dir = scenario_dir

        # 1. 确保benchkit已拷贝到场景目录
        self._setup_benchkit_for_scenario(scenario_dir)

        # 2. 所有工具的base_dir/work_dir设为场景目录
        #    Agent工作在场景目录下，所有相对路径都基于场景目录
        self._file_reader = FileReader(base_dir=scenario_dir)
        self._file_writer = FileWriter(base_dir=scenario_dir)
        self._file_editor = FileEditor(base_dir=scenario_dir)
        self._bash = BashExecutor(work_dir=scenario_dir)

        # 3. 创建execution_outputs目录用于记录（如果需要）
        execution_output_dir = scenario_dir / "execution_outputs" / f"iteration_{self.current_iteration}"
        execution_output_dir.mkdir(parents=True, exist_ok=True)

    def _create_tools(self) -> List[Tool]:
        """创建Execute Agent的工具集"""
        return [
            Tool(
                name="file_reader",
                description="读取文件内容，支持Text、JSON、Python、Markdown等格式",
                input_schema={
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "文件路径。可以使用：(1)绝对路径 (2)相对于场景目录的相对路径，如'unified_scenario_design.yaml'、'tools/xxx.py'"
                        },
                        "max_lines": {
                            "type": "integer",
                            "description": "最大读取行数，默认1000",
                            "default": 1000
                        }
                    },
                    "required": ["filename"]
                },
                handler=self._handle_file_reader
            ),
            Tool(
                name="file_writer",
                description="创建新文件或覆盖已有文件（如tools/*.py, checkers/*.py, samples/*.json）",
                input_schema={
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "文件路径，必须使用相对于场景目录的相对路径。例如：'tools/xxx.py'、'checkers/checker.py'、'samples/eval.jsonl'。不要包含场景目录名本身！"
                        },
                        "content": {
                            "type": "string",
                            "description": "文件内容"
                        },
                        "overwrite": {
                            "type": "boolean",
                            "description": "是否覆盖已有文件，默认true",
                            "default": True
                        }
                    },
                    "required": ["filename", "content"]
                },
                handler=self._handle_file_writer
            ),
            Tool(
                name="file_editor",
                description="编辑已有文件，支持精确字符串替换和行范围编辑",
                input_schema={
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "文件路径。可以使用：(1)绝对路径 (2)相对于场景目录的相对路径，如'tools/xxx.py'、'BusinessRules.md'"
                        },
                        "mode": {
                            "type": "string",
                            "enum": ["replace", "line_range"],
                            "description": "编辑模式"
                        },
                        "old_string": {
                            "type": "string",
                            "description": "replace模式：要替换的原字符串"
                        },
                        "new_string": {
                            "type": "string",
                            "description": "replace模式：替换后的新字符串"
                        },
                        "replace_all": {
                            "type": "boolean",
                            "description": "是否替换所有匹配项",
                            "default": False
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "line_range模式：起始行号"
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "line_range模式：结束行号"
                        },
                        "new_content": {
                            "type": "string",
                            "description": "line_range模式：替换内容"
                        }
                    },
                    "required": ["filename", "mode"]
                },
                handler=self._handle_file_editor
            ),
            Tool(
                name="bash",
                description="执行shell命令（安全受限），用于运行测试、评测脚本等",
                input_schema={
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "要执行的shell命令"
                        },
                        "timeout": {
                            "type": "integer",
                            "description": "超时时间（秒），默认120",
                            "default": 120
                        }
                    },
                    "required": ["command"]
                },
                handler=self._handle_bash
            ),
            Tool(
                name="use_skill",
                description=self._use_skill.description,  # 使用UseSkill类的详细描述
                input_schema={
                    "type": "object",
                    "properties": {
                        "skill_type": {
                            "type": "string",
                            "enum": [
                                "tool_implementation",
                                "checker_implementation",
                                "sample_authoring",
                                "evaluation_execution",
                                "failure_analysis",
                                "execute_to_init_context",
                                "business_rules_authoring",
                                "scenario_design_sop"
                            ],
                            "description": "技能类型（见上方description中的完整列表）"
                        }
                    },
                    "required": ["skill_type"]
                },
                handler=self._handle_use_skill
            ),
            Tool(
                name="ask_human",
                description="请求人工介入。当需要人工审批、确认或补充信息时调用。",
                input_schema={
                    "type": "object",
                    "properties": {
                        "request": {
                            "type": "string",
                            "description": "向人提出的请求或问题"
                        },
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "可选的预设选项"
                        }
                    },
                    "required": ["request"]
                },
                handler=self._handle_ask_human
            ),
            Tool(
                name="request_layer1_fix",
                description="请求返回Init Agent进行设计修改。当发现问题需要修改设计文件（BusinessRules.md、unified_scenario_design.yaml等）时调用。",
                input_schema={
                    "type": "object",
                    "properties": {
                        "trigger_reason": {
                            "type": "string",
                            "description": "触发原因简述（1句话），如'Critical问题占比35%，超过30%阈值'"
                        },
                        "problem_details": {
                            "type": "string",
                            "description": "问题详细描述，说明具体发现了什么问题"
                        },
                        "modification_suggestions": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "具体修改建议列表，每条建议应明确指出需要修改什么"
                        }
                    },
                    "required": ["trigger_reason", "modification_suggestions"]
                },
                handler=self._handle_request_layer1_fix
            )
        ]

    # ========== 工具处理器 ==========

    def _handle_file_reader(self, filename: str, max_lines: int = 1000) -> str:
        """处理file_reader调用"""
        path = Path(filename)

        # 如果是绝对路径，尝试从中推断scenario_dir
        if path.is_absolute() and path.exists():
            for parent in path.parents:
                if (parent / "unified_scenario_design.yaml").exists():
                    if self.scenario_dir is None:
                        self._init_tools_for_scenario(parent)
                    break

        # 如果工具未初始化，使用临时reader
        if self._file_reader is None:
            temp_reader = FileReader(base_dir=Path.cwd())
            result = temp_reader.execute(filename=filename, max_lines=max_lines)
        else:
            result = self._file_reader.execute(filename=filename, max_lines=max_lines)

        return json.dumps(result, ensure_ascii=False)

    def _handle_file_writer(self, filename: str, content: str, overwrite: bool = True) -> str:
        """处理file_writer调用"""
        if self._file_writer is None:
            return json.dumps({"error": "未设置scenario_dir，请先读取设计文件"})

        # 自动修正嵌套路径问题
        # 如果 filename 包含 scenario_dir 的路径，自动去除
        if self.scenario_dir:
            scenario_name = self.scenario_dir.name
            # 检查各种可能的嵌套模式
            prefixes_to_strip = [
                f"outputs/{scenario_name}/",
                f"{scenario_name}/",
                str(self.scenario_dir) + "/",
            ]
            for prefix in prefixes_to_strip:
                if filename.startswith(prefix):
                    filename = filename[len(prefix):]
                    break

        result = self._file_writer.execute(filename=filename, content=content, overwrite=overwrite)
        return json.dumps(result, ensure_ascii=False)

    def _handle_file_editor(self, filename: str, mode: str, **kwargs) -> str:
        """处理file_editor调用"""
        if self._file_editor is None:
            return json.dumps({"error": "未设置scenario_dir"})

        if mode == "replace":
            result = self._file_editor.execute_replace(
                filename=filename,
                old_string=kwargs.get("old_string", ""),
                new_string=kwargs.get("new_string", ""),
                replace_all=kwargs.get("replace_all", False)
            )
        elif mode == "line_range":
            result = self._file_editor.execute_line_range(
                filename=filename,
                start_line=kwargs.get("start_line", 1),
                end_line=kwargs.get("end_line", 1),
                new_content=kwargs.get("new_content", "")
            )
        else:
            result = {"error": f"未知的编辑模式: {mode}"}
        return json.dumps(result, ensure_ascii=False)

    def _handle_bash(self, command: str, timeout: int = 120) -> str:
        """处理bash调用，对输出做截断保护"""
        if self._bash is None:
            # 临时bash，工作目录为当前目录
            temp_bash = BashExecutor(work_dir=Path.cwd(), timeout=timeout)
            result = temp_bash.execute(command=command, timeout=timeout)
        else:
            result = self._bash.execute(command=command, timeout=timeout)

        # 对stdout/stderr做截断保护，防止超大输出导致context爆炸
        MAX_OUTPUT_CHARS = 20000  # 每个输出最多保留20K字符

        if result.get("stdout") and len(result["stdout"]) > MAX_OUTPUT_CHARS:
            truncated_len = len(result["stdout"])
            result["stdout"] = result["stdout"][:MAX_OUTPUT_CHARS] + f"\n\n... (输出被截断，原始长度: {truncated_len} 字符，仅显示前 {MAX_OUTPUT_CHARS} 字符)"
            result["truncated"] = True

        if result.get("stderr") and len(result["stderr"]) > MAX_OUTPUT_CHARS:
            truncated_len = len(result["stderr"])
            result["stderr"] = result["stderr"][:MAX_OUTPUT_CHARS] + f"\n\n... (错误输出被截断，原始长度: {truncated_len} 字符)"
            result["truncated"] = True

        return json.dumps(result, ensure_ascii=False)

    def _handle_use_skill(self, skill_type: str) -> str:
        """处理use_skill调用"""
        result = self._use_skill.execute(skill_type=skill_type)
        return json.dumps(result, ensure_ascii=False)

    def _handle_ask_human(self, request: str, options: List[str] = None) -> str:
        """处理ask_human调用"""
        result = self._ask_human.execute(request=request, options=options)
        return json.dumps(result, ensure_ascii=False)

    def _handle_request_layer1_fix(self, trigger_reason: str, modification_suggestions: List[str], problem_details: str = "") -> str:
        """处理request_layer1_fix调用 - 请求返回Init Agent"""
        # 设置标志，让 extract_result() 返回 need_layer1_fix 状态
        self._need_layer1_fix = True
        self._layer1_context = {
            "trigger_reason": trigger_reason,
            "problem_details": problem_details,
            "modification_suggestions": modification_suggestions,
            "execution_output_dir": str(self.scenario_dir / "execution_outputs" / f"iteration_{self.current_iteration}") if self.scenario_dir else ""
        }

        return json.dumps({
            "success": True,
            "action": "return_to_init",
            "message": "已设置返回Init Agent标志，系统将在本轮结束后切换回设计阶段",
            "trigger_reason": trigger_reason
        }, ensure_ascii=False)

    # ========== Agent接口实现 ==========

    def get_system_prompt(self, context: Dict[str, Any]) -> str:
        """获取系统提示词"""
        # 获取工作目录（从design_artifacts中提取）
        working_dir = context.get("design_artifacts", {}).get("scenario_dir", "outputs/<scenario_name>/")

        base_prompt = f"""## 定位

你是Execute Agent，负责合成高质量、高难度的Agent评测样本（Layer 2-3-4）。

你有一个设计师伙伴**Init Agent**负责Layer 1设计工作（BusinessRules.md、unified_scenario_design.yaml等）。当你发现设计文件有问题时，使用`request_layer1_fix`工具请求Init Agent修改，不要自己改设计文件。

**接收的Context**：
- `design_artifacts["scenario_dir"]`: 场景目录（你的工作根目录）
- `design_artifacts`: Init Agent的设计产物（场景名、各设计文件路径）
- `user_requirement`: 用户原始需求
- `iteration`: 当前迭代次数

如果用户要求修改**设计文件本身**（BusinessRules.md、unified_scenario_design.yaml），这超出了你的职责。应该使用 `request_layer1_fix` 工具请求返回设计阶段，系统会自动切换回Init Agent进行设计修改。

如果是修改**执行层面的代码**（tools/*.py、checkers/*.py、样本生成逻辑），这是你的职责，可以往下工作。

## 目录结构约定

你的工作目录是：`{working_dir}`

关键文件位置（相对于工作目录）：
- **设计文件**：`unified_scenario_design.yaml`
- **业务规则**：`BusinessRules.md`
- **样本文件**：`samples/eval.jsonl`
- **Benchkit**：`benchkit/`（已自动拷贝）
- **评测输出**：`evaluation_outputs/`

执行 benchkit 命令时，确保在工作目录下执行，所有路径使用相对路径。

## 核心目标

**最终交付物**：高质量、高难度、有区分度的Agent评测样本集

**关键原则**：
- ✅ 样本质量和难度是核心目标
- ✅ 评测是为了发现和修复**样本设计问题**和**系统问题**
- ❌ **不追求高成功率** - 样本应该有难度，失败是正常的
- ❌ **不降低难度来提高成功率** - 这完全背离目标

## 评测结果的正确使用

**评测的作用**：诊断问题，而非证明样本好

当评测失败时，分析失败原因：
1. **样本设计问题**：
   - Checker配置不合理（过严/过松、临界值错误）
   - BusinessRules描述模糊、矛盾
   - Checklist与Query不一致
   - 用户模拟器prompt设计不当
   → **修复样本设计**

2. **系统问题**：
   - Tool实现有bug
   - Checker逻辑错误
   - Tool返回格式不符合规范
   → **修复代码**

3. **Agent能力问题**：
   - Agent未遵循规则、信息收集不足、执行错误等
   → **这是正常的评测结果，保留样本**

**错误做法示例**：
- ❌ "成功率只有60%，我要简化样本来提高成功率"
- ❌ "太多失败了，我要放宽checker条件"
- ✅ "成功率60%，分析失败原因：3个样本设计问题已修复，5个是Agent能力问题（符合预期）"

## 完成条件

任务完成的判断标准：
1. **样本质量合格**：无样本设计缺陷、无系统bug
2. **难度和覆盖面达标**：有效测试目标能力、有足够区分度
3. **数量充足**：达到预期样本数量

**不是**"成功率>=85%"！成功率取决于被测模型能力和样本难度。

**完成后的行为**：使用`ask_human`工具汇报完成情况（哪些层完成、样本数量、评测结果），请求人工确认是否满意或需要进一步优化。

## 执行流程（Layer 2-4）

**必须按顺序完成以下步骤**：

### Layer 2: 组件代码生成
1. **生成tools/** - 根据unified_scenario_design.yaml中的tools定义实现MCP工具
2. **生成checkers/** - 根据checkers定义实现验证逻辑
3. **生成data_pools/** - 根据entities定义创建测试数据（JSONL格式）
   - ⚠️ **必须生成**，即使场景初始状态为空也要创建目录结构
   - 每个entity对应一个`data_pools/{entity}.jsonl`文件
   - 数据要覆盖所有筛选条件组合，确保样本生成时能匹配到数据
4. 运行单元测试验证组件正确性（可选）

### Layer 3: 样本合成
5. **生成样本生成器** - 基于data_pools、user_need_templates实现
6. **运行生成器** - 产出`samples/eval.jsonl`
   - ⚠️ **样本格式必须严格遵循规范**：`.claude/skills/sample_authoring/references/sample_format_spec.json`
   - 必需字段：data_id, query, system, servers, environment, check_list
   - 在实现生成器前，**必须先用file_reader读取sample_format_spec.json**了解格式
7. 验证样本格式和质量

### Layer 4: 评测与迭代
8. 运行小规模评测（5-10个样本）
9. 分析失败原因（样本问题/系统问题/Agent能力问题）
10. 修复样本设计问题和系统bug
11. （可选）运行完整评测并生成报告

## 交付物（使用相对路径）

**重要**：所有文件路径必须是相对于场景目录的相对路径，不要包含场景目录本身！

正确写法：
- tools/xxx.py
- checkers/checker.py
- data_pools/xxx.jsonl
- samples/eval.jsonl

错误写法（绝对不要这样）：
- outputs/场景名/tools/xxx.py  ← 错误！会导致嵌套
- /Users/.../tools/xxx.py     ← 错误！

目录结构：
```
<场景目录>/           # file_writer 的 base_dir，不需要写这部分
├── tools/           # 写 "tools/xxx.py"
├── checkers/        # 写 "checkers/checker.py"
├── data_pools/      # 写 "data_pools/xxx.jsonl"
├── samples/         # 写 "samples/eval.jsonl"
└── execution_outputs/
```

## 禁止行为

- ❌ 创建冗余的"完成报告"、"状态总结"、"使用指南"等markdown文档（如COMPLETION_REPORT.md、FINAL_STATUS.md、QUICK_START.md）
- ❌ 创建额外的测试样本文件（如test_5.jsonl、test_sample.jsonl），应直接使用samples/eval.jsonl配合executor的--limit参数
- ❌ 反复展示样本内容、统计信息、验证结果
- ❌ 在达到完成条件后继续创建文档或执行操作，应立即调用`ask_human`请求确认

## 可用技能

通过use_skill工具获取参考资源（详细列表见工具描述）：
- **scenario_design_sop**: 五种难度提升方法（复杂规则、领域知识、多轮变更等）
- **tool_implementation**: 工具实现模板和示例
- **checker_implementation**: Checker实现指南
- **sample_authoring**: 样本合成SOP（质量标准、格式规范）
- **evaluation_execution**: 评测执行指南（benchkit使用）
- **failure_analysis**: 失败案例归因分析（区分样本问题/系统问题/Agent能力问题）
"""

        # 动态追加场景配置信息
        design_artifacts = context.get("design_artifacts", {})
        iteration = context.get("iteration", 1)

        # 直接从artifacts获取场景目录（必须提供）
        scenario_dir = design_artifacts.get("scenario_dir")

        # 如果有场景配置信息，追加到system prompt
        if scenario_dir:
            config_section = f"""

## 工作环境

**场景目录**: {scenario_dir}

**所有工具的工作目录**: 场景目录（{scenario_dir}）
- file_reader/file_writer/file_editor: 相对路径基于场景目录
- bash: 工作目录就是场景目录
- 例如: file_reader("tools/xxx.py") 读取 {scenario_dir}/tools/xxx.py
- 例如: bash("python benchkit/executor.py ...") 在 {scenario_dir} 下执行

**benchkit位置**: {scenario_dir}/benchkit/
- 系统已自动将benchkit拷贝到场景目录
- 配置文件: benchkit/model_config.json
- 执行器: benchkit/executor.py

## ⚠️ Benchkit使用规范（重要）

**关键原则**：Benchkit是黑盒评测工具，遇到问题时**不要深入debug，立即ask_human**

**正确使用方式**：
1. **必须使用** `use_skill(skill_type="evaluation_execution")` 获取正确的使用指南
2. **严格按照skill文档中的命令执行**，不要自行修改路径或参数

**🚨 强制规则：3次失败必须停止**

执行benchkit命令时，如果遇到错误：
- **第1次失败**：检查命令拼写、参数是否完整
- **第2次失败**：检查配置文件benchkit/model_config.json是否存在
- **第3次失败**：**立即调用ask_human**，提供完整的命令、错误信息、已尝试的方案

**绝对禁止**：
- ❌ 连续尝试5次以上不同的命令变体
- ❌ 阅读benchkit源码试图理解内部实现
- ❌ 修改benchkit源代码或配置来"修复"问题
- ❌ 发明benchkit不支持的CLI参数（如--model-config）
- ❌ 在场景目录下创建benchkit/model_config.json副本

**遇到以下情况立即ask_human**：
- 连续3次出现 `required arguments` 错误
- 出现 `API connection error` 或 `401 Unauthorized`
- 找不到 `benchkit/model_config.json`
- MCP服务器启动失败
- executor.py的`--help`输出与skill文档不符
"""
            return base_prompt + config_section

        return base_prompt

    def build_initial_message(self, context: Dict[str, Any]) -> str:
        """
        构建用户消息

        只负责用户消息内容，不混入系统配置信息。
        系统配置（场景目录、迭代信息等）已在get_system_prompt()中提供。
        """
        design_artifacts = context.get("design_artifacts", {})
        iteration = context.get("iteration", 1)
        user_requirement = context.get("user_requirement", "")

        self.current_iteration = iteration

        # 初始化工具（如果有设计文件）
        scenario_dir = design_artifacts.get("scenario_dir")
        if scenario_dir:
            self._init_tools_for_scenario(Path(scenario_dir))

        # 如果有用户主动输入，直接返回
        if user_requirement:
            return user_requirement

        # 首次启动，返回简单的启动指令
        if design_artifacts:
            return "请开始执行评测任务：读取设计文件，生成必要的组件代码、评测样本，运行评测并分析结果。"
        else:
            return ""

    def _validate_sample_format(self) -> Optional[Dict[str, Any]]:
        """
        验证样本格式，返回验证结果

        Returns:
            None: 样本文件不存在
            {"valid": True, ...}: 格式合规
            {"valid": False, "errors": [...], "error_summary": "..."}: 格式不合规
        """
        if not self.scenario_dir:
            return None

        samples_file = self.scenario_dir / "samples" / "eval.jsonl"
        if not samples_file.exists():
            return None

        # 直接调用验证函数
        return validate_jsonl_file(samples_file)

    def _check_and_inject_sample_validation_feedback(self, raw_messages: List[Dict]) -> bool:
        """
        检查样本格式并在不合规时注入反馈

        Args:
            raw_messages: 对话历史消息列表

        Returns:
            True: 注入了反馈消息
            False: 未注入（格式合规或已提醒过）
        """
        # 已经提醒过，跳过
        if self._samples_validation_reminded:
            return False

        # 验证格式
        validation_result = self._validate_sample_format()

        # 文件不存在或格式合规
        if not validation_result or validation_result["valid"]:
            return False

        # 格式不合规，构建反馈消息
        errors = validation_result.get("errors", [])
        error_summary = validation_result.get("error_summary", "格式错误")

        # 只显示前5个错误
        error_details = "\n".join(f"  - {e}" for e in errors[:5])
        if len(errors) > 5:
            error_details += f"\n  ... 以及其他 {len(errors) - 5} 个错误"

        reminder = f"""⚠️  刚才写入的样本文件 samples/eval.jsonl 格式验证未通过！

{error_summary}

详细错误：
{error_details}

请读取 .claude/skills/sample_authoring/references/sample_format_spec.json 了解正确格式，然后修正生成器或直接编辑样本文件。"""

        # 注入反馈消息 - 作为独立的user消息
        from .base_agent import _console
        _console.print(f"  [验证Hook] 样本格式不合规，注入即时反馈", style="yellow")

        raw_messages.append({"role": "user", "content": reminder})
        self._samples_validation_reminded = True

        return True

    def extract_result(self, response_text: str, context: Dict[str, Any]) -> Optional[AgentResult]:
        """提取结构化结果"""
        # 检查是否请求返回Init
        if hasattr(self, "_need_layer1_fix") and self._need_layer1_fix:
            # 安全获取context
            ctx = getattr(self, "_layer1_context", None)
            self._need_layer1_fix = False

            if ctx:
                return AgentResult(
                    status="need_layer1_fix",
                    message="识别出Layer 1问题",
                    context_for_handoff=ctx
                )
            # context不存在，忽略这个标志

        # 检查是否完成执行
        if hasattr(self, "_execution_completed") and self._execution_completed:
            artifacts = getattr(self, "_execution_artifacts", {})
            self._execution_completed = False
            return AgentResult(
                status="completed",
                artifacts=artifacts,
                message="评测执行完成"
            )

        return None

    def run(self, context: Dict[str, Any], continue_from_checkpoint: bool = False) -> AgentResult:
        """
        覆写 run 方法，初始化工具和重置状态

        Args:
            context: Agent执行上下文
            continue_from_checkpoint: 是否从checkpoint恢复
        """
        # 重置状态（仅在非resume时）
        if not continue_from_checkpoint:
            self._samples_validation_reminded = False

        # 初始化工具（必须在调用父类run前完成）
        design_artifacts = context.get("design_artifacts", {})
        iteration = context.get("iteration", 1)
        self.current_iteration = iteration

        scenario_dir = design_artifacts.get("scenario_dir")
        if scenario_dir:
            self._init_tools_for_scenario(Path(scenario_dir))

        # 调用父类的 run 方法
        return super().run(context, continue_from_checkpoint=continue_from_checkpoint)

    def _after_tool_execution(self, response, raw_messages: List[Dict]):
        """
        Hook方法：工具执行后检查样本格式

        当file_writer写入samples/eval.jsonl时，立即验证格式并注入反馈
        """
        # 检测是否写入了样本文件
        samples_file_written = False
        for block in response.content:
            if block.type == "tool_use" and block.name == "file_writer":
                filename = block.input.get("filename", "")
                if "samples/eval.jsonl" in filename or filename.endswith("eval.jsonl"):
                    samples_file_written = True
                    break

        # 样本文件刚写入，立即触发验证Hook
        if samples_file_written:
            self._check_and_inject_sample_validation_feedback(raw_messages)

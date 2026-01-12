"""
Init Agent - 负责场景设计（Layer 1）

工具集：file_reader, file_writer, file_editor, use_skill
使用独立tools模块实现
"""
import json
from pathlib import Path
from typing import Dict, Any, Optional, List

from .base_agent import BaseAgent, AgentResult, Tool, ContextConfig
from tools import FileReader, FileWriter, FileEditor, UseSkill, AskHuman


class InitAgent(BaseAgent):
    """
    Init Agent - 场景设计Agent

    职责:
    - 基于用户需求生成场景设计文件
    - 基于Execute Agent反馈修改设计

    交付物:
    - unified_scenario_design.yaml
    - BusinessRules.md
    - format_specifications.json
    - 场景目录结构
    """

    # Init Agent的Context配置（适度保守：不要太早压缩，保留更多步骤）
    DEFAULT_CONTEXT_CONFIG = ContextConfig(
        compact_threshold=300_000,  # 30万tokens触发压缩（延后触发）
        api_hard_limit=200_000,
        keep_recent_steps=8  # 保留最近8步（避免丢失关键文件创建记录）
    )

    def __init__(
        self,
        output_dir: str = "outputs",
        skills_dir: str = ".claude/skills",
        model: str = "claude-sonnet-4-5-20250929",
        max_iterations: int = 200,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None
    ):
        self.output_dir = Path(output_dir)
        self.skills_dir = Path(skills_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 追踪设计确认状态
        self._design_confirmed = False
        self._design_files_complete = False

        # 初始化工具实例
        self._file_reader = FileReader(base_dir=self.output_dir)
        self._file_writer = FileWriter(base_dir=self.output_dir)
        self._file_editor = FileEditor(base_dir=self.output_dir)
        self._use_skill = UseSkill(skills_dir=self.skills_dir)
        self._ask_human = AskHuman()  # 可由 Orchestrator 注入自定义 handler

        # 定义工具
        tools = self._create_tools()

        super().__init__(
            model=model,
            max_iterations=max_iterations,
            tools=tools,
            base_url=base_url,
            api_key=api_key
        )

    def _create_tools(self) -> List[Tool]:
        """创建Init Agent的工具集"""
        return [
            Tool(
                name="file_reader",
                description="读取文件内容，支持Text、JSON、CSV等格式，自动识别类型",
                input_schema={
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "文件路径（相对于工作目录或绝对路径）"
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
                description="创建新文件或覆盖已有文件",
                input_schema={
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "文件路径（相对于工作目录）"
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
                description="编辑已有文件，支持精确字符串替换和行范围编辑两种模式",
                input_schema={
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "文件路径"
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
                            "description": "replace模式：是否替换所有匹配项",
                            "default": False
                        },
                        "start_line": {
                            "type": "integer",
                            "description": "line_range模式：起始行号（从1开始）"
                        },
                        "end_line": {
                            "type": "integer",
                            "description": "line_range模式：结束行号（包含）"
                        },
                        "new_content": {
                            "type": "string",
                            "description": "line_range模式：替换的新内容"
                        }
                    },
                    "required": ["filename", "mode"]
                },
                handler=self._handle_file_editor
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
                                "business_rules_authoring",
                                "scenario_design_sop",
                                "tool_implementation",
                                "checker_implementation",
                                "sample_authoring",
                                "evaluation_execution",
                                "failure_analysis"
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
                            "description": "可选的预设选项，如 ['approve', 'reject', 'revise']"
                        }
                    },
                    "required": ["request"]
                },
                handler=self._handle_ask_human
            )
        ]

    # ========== 工具处理器 ==========

    def _handle_file_reader(self, filename: str, max_lines: int = 1000) -> str:
        """处理file_reader调用"""
        result = self._file_reader.execute(filename=filename, max_lines=max_lines)
        return json.dumps(result, ensure_ascii=False)

    def _handle_file_writer(self, filename: str, content: str, overwrite: bool = True) -> str:
        """处理file_writer调用"""
        result = self._file_writer.execute(filename=filename, content=content, overwrite=overwrite)
        return json.dumps(result, ensure_ascii=False)

    def _handle_file_editor(self, filename: str, mode: str, **kwargs) -> str:
        """处理file_editor调用"""
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

    def _handle_use_skill(self, skill_type: str) -> str:
        """处理use_skill调用"""
        result = self._use_skill.execute(skill_type=skill_type)
        return json.dumps(result, ensure_ascii=False)

    def _handle_ask_human(self, request: str, options: List[str] = None) -> str:
        """处理ask_human调用"""
        result = self._ask_human.execute(request=request, options=options)

        # 如果是设计确认请求，标记已确认
        if self._design_files_complete:
            self._design_confirmed = True

        return json.dumps(result, ensure_ascii=False)

    def _check_design_files_complete(self) -> Optional[Dict[str, str]]:
        """检查设计文件是否已完成，返回 artifacts 或 None（返回最新的完整场景目录）"""
        candidates = []

        for item in self.output_dir.iterdir():
            if item.is_dir():
                yaml_file = item / "unified_scenario_design.yaml"
                rules_file = item / "BusinessRules.md"

                if yaml_file.exists() and rules_file.exists():
                    # 记录目录和最新修改时间
                    latest_mtime = max(
                        yaml_file.stat().st_mtime,
                        rules_file.stat().st_mtime
                    )
                    candidates.append({
                        "scenario_name": item.name,
                        "scenario_dir": str(item.absolute()),  # 场景目录绝对路径
                        "unified_scenario_design_path": str(yaml_file),
                        "business_rules_path": str(rules_file),
                        "mtime": latest_mtime
                    })

        if not candidates:
            return None

        # 返回最新修改的场景目录
        latest = max(candidates, key=lambda x: x["mtime"])
        # 移除mtime字段，只返回artifacts
        del latest["mtime"]
        return latest

    # ========== Agent接口实现 ==========

    def get_system_prompt(self, context: Dict[str, Any]) -> str:
        """获取系统提示词"""
        output_dir = context.get("output_dir", "outputs/<scenario_name>/")
        base_prompt = f"""## 定位

你是Init Agent，负责Agent评测场景的设计工作（Layer 1）。

## 交付物

你必须按以下结构创建场景：

```
<场景名>/                           # 必须先创建场景子目录（英文命名，如 file_operation）
├── unified_scenario_design.yaml   # tools、checkers、entities、user_need_templates定义
└── BusinessRules.md               # 业务规则和流程描述
```

**重要**：
1. 必须先用 file_writer 创建场景子目录（写入 `<场景名>/任意文件` 会自动创建目录）
2. 所有设计文件必须放在场景子目录下，不能直接放在根目录

## 目录结构约定

你的工作目录是：`{output_dir}`

请将生成的文件放置在以下位置（相对于工作目录）：
- **设计文件**：`unified_scenario_design.yaml`
- **业务规则**：`BusinessRules.md`
- **数据池**：`data_pools/<entity_name>.jsonl`
- **样本合成器**：`scripts/sample_generator/generate_samples.py`

所有使用 file_writer 工具时的路径都是相对于工作目录的相对路径。

## 约束

- 设计必须可被Execute Agent执行
- 所有业务规则必须明确、无歧义
- coverage_matrix必须覆盖核心能力测试点

## 可验证性原则（核心）

**验证方式优先级（必须遵循）**：
1. **Rule-based优先** - 能用规则判断的，绝不用LLM
2. **环境状态验证优先** - 优先检查final_state中的实体属性变化
3. **LLM Judge只作为最后手段** - 仅用于纯语义判断（如回复语气、措辞质量）

**设计时自检**：
- 每个check_item能否用`entity_attribute_equals`验证？→ 优先使用
- 需要验证工具调用？→ 用`tool_called_with_params`，Agent决策参数用null通配
- 只有回复文本需要判断？→ 才考虑`use_llm_judge: true`

**反面案例**：
- ❌ 用LLM判断"Agent是否正确扣减了余额" → 应检查final_state中的balance字段
- ❌ 用LLM判断"是否调用了正确的工具" → 应用tool_called_with_params

## 可用技能

通过use_skill工具获取参考资源：
- scenario_design_sop: 场景设计SOP和模板
- business_rules_authoring: 业务规则编写指南
- tool_implementation: Tool设计规范（设计unified_scenario_design.yaml中tools定义时必须参考）
- checker_implementation: Checker设计规范（设计checkers定义时必须参考）

**重要**：在设计unified_scenario_design.yaml中的tools和checkers时，必须先查看对应的implementation skill，确保设计的格式和字段符合Execute Agent的实现规范，避免设计与实现不一致。
"""

        # 如果有Execute Agent反馈，添加到prompt
        if context.get("feedback_from_execute"):
            feedback = context["feedback_from_execute"]
            feedback_prompt = f"""

## Execute Agent反馈

Execute Agent识别出需要修改设计的问题：
- 触发原因: {feedback.get('trigger_reason', '未知')}
- 修改建议: {feedback.get('modification_suggestions_summary', [])}

请基于上述反馈修改设计。你可以读取以下目录中的详细数据：
- execution_output_dir: {feedback.get('execution_output_dir', '未提供')}
"""
            base_prompt += feedback_prompt

        return base_prompt

    def build_initial_message(self, context: Dict[str, Any]) -> str:
        """构建初始用户消息"""
        user_requirement = context.get("user_requirement", "")
        iteration = context.get("iteration", 1)

        if context.get("feedback_from_execute"):
            return f"""这是第 {iteration} 轮设计（Step {iteration}）。

Execute Agent反馈了Layer 1问题，请基于反馈修改设计。

原始用户需求：{user_requirement}

请读取反馈中提到的详细数据，分析问题，然后修改设计文件。"""
        else:
            return user_requirement

    def extract_result(self, response_text: str, context: Dict[str, Any]) -> Optional[AgentResult]:
        """提取结构化结果 - 检查是否创建了场景文件且已确认"""
        artifacts = self._check_design_files_complete()

        if artifacts:
            # 设计文件已完成
            if self._design_confirmed:
                # 用户已确认，返回完成
                return AgentResult(
                    status="completed",
                    artifacts=artifacts,
                    message="场景设计完成"
                )
            else:
                # 设计完成但未确认，不返回完成（让 run 方法处理）
                self._design_files_complete = True
                return None

        # 没有创建文件，返回None使用默认文本响应
        return None

    def run(self, context: Dict[str, Any], continue_from_checkpoint: bool = False) -> AgentResult:
        """
        覆写 run 方法，添加设计确认检查

        当设计文件完成但未调用 ask_human 确认时，注入提醒消息

        Args:
            context: Agent执行上下文
            continue_from_checkpoint: 是否从checkpoint恢复
        """
        import json
        from .base_agent import AgentResult, _console

        # 重置状态（仅在非resume时）
        if not continue_from_checkpoint:
            self._design_confirmed = False
            self._design_files_complete = False

        system_prompt = self.get_system_prompt(context)
        tool_definitions = self._get_tool_definitions()

        # 检查是否从checkpoint恢复
        if continue_from_checkpoint and self._conversation_history:
            raw_messages = self._conversation_history.copy()
        else:
            initial_message = self.build_initial_message(context)
            raw_messages = [{"role": "user", "content": initial_message}]

        for iteration in range(self.max_iterations):
            _console.print(f"[{self.__class__.__name__}] Step {iteration + 1}", style="bold")

            # 构建发送给API的messages
            api_messages = self._build_messages_for_api(raw_messages)

            # 检查是否需要Compact
            if self._should_compact(api_messages, system_prompt):
                raw_messages = self._compact_messages(raw_messages, system_prompt)
                api_messages = self._build_messages_for_api(raw_messages)

            # 调用Claude
            response = self.client.messages.create(
                model=self.model,
                max_tokens=32768,
                system=system_prompt,
                tools=tool_definitions if tool_definitions else None,
                messages=api_messages
            )

            # 打印响应
            for block in response.content:
                if hasattr(block, "text") and block.text.strip():
                    _console.print(f"  {block.text}", style="dim", overflow="ignore", no_wrap=False, crop=False)
                elif block.type == "tool_use":
                    pass  # 下面会打印

            # 保存assistant响应
            assistant_message = {"role": "assistant", "content": response.content}
            raw_messages.append(assistant_message)

            # 处理不同的停止原因
            if response.stop_reason == "end_turn":
                # Agent 决定结束，检查是否完成
                text_content = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        text_content += block.text

                result = self.extract_result(text_content, context)

                if result:
                    # 保存对话历史（用于checkpoint）
                    self._conversation_history = raw_messages.copy()
                    return result

                # 设计完成但未确认 - 注入提醒
                if self._design_files_complete and not self._design_confirmed:
                    artifacts = self._check_design_files_complete()
                    reminder = f"""我注意到你已经完成了场景设计文件的创建：
- {artifacts.get('scenario_name', 'unknown')} 目录
- unified_scenario_design.yaml
- BusinessRules.md
- format_specifications.json

但你还没有调用 ask_human 工具让用户确认设计。请使用 ask_human 工具询问用户是否满意这个设计，用户可能有修改建议。

示例调用：
ask_human(request="场景设计已完成，请确认是否满意？如有修改建议请告诉我", options=["确认通过", "需要修改"])
"""
                    _console.print(f"  [提醒] 设计完成但未确认，注入反馈...", style="yellow")
                    raw_messages.append({"role": "user", "content": reminder})
                    continue

                # 普通结束 - 保存对话历史（用于checkpoint）
                self._conversation_history = raw_messages.copy()

                return AgentResult(
                    status="completed",
                    message=text_content
                )

            elif response.stop_reason == "tool_use":
                # 处理工具调用
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        params_str = json.dumps(block.input, ensure_ascii=False, indent=None)
                        if len(params_str) > 100:
                            params_str = params_str[:100] + "..."
                        _console.print(f"  调用工具: [cyan]{block.name}[/cyan]({params_str})")

                        result = self._handle_tool_call(block.name, block.input)
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result
                        })

                raw_messages.append({"role": "user", "content": tool_results})

            elif response.stop_reason == "max_tokens":
                _console.print(f"  [继续] 输出被截断，继续生成...", style="yellow")
                has_tool_use = any(block.type == "tool_use" for block in response.content)

                if has_tool_use:
                    tool_results = []
                    for block in response.content:
                        if block.type == "tool_use":
                            params_str = json.dumps(block.input, ensure_ascii=False, indent=None)
                            if len(params_str) > 100:
                                params_str = params_str[:100] + "..."
                            _console.print(f"  调用工具: [cyan]{block.name}[/cyan]({params_str})")

                            result = self._handle_tool_call(block.name, block.input)
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result
                            })
                    raw_messages.append({"role": "user", "content": tool_results})
                else:
                    raw_messages.append({"role": "user", "content": "请继续"})
            else:
                _console.print(f"[警告] 未知的停止原因: {response.stop_reason}", style="yellow")
                break

        # 达到最大step数 - 保存对话历史（用于checkpoint）
        self._conversation_history = raw_messages.copy()

        return AgentResult(
            status="failed",
            message=f"达到最大step数 {self.max_iterations}"
        )

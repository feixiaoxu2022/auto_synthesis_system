"""
Base Agent - 基础Agent类，提供与Claude API交互的能力

Context管理策略参考: docs/productization/agent_context_strategy.md
"""
import os
import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Callable
from anthropic import Anthropic
import httpx
from rich.console import Console

# 配置日志 - 写入文件，不输出到terminal
logger = logging.getLogger(__name__)
if not logger.handlers:
    logger.setLevel(logging.DEBUG)
    # 日志文件handler
    log_dir = os.path.join(os.path.dirname(__file__), "..", "logs")
    os.makedirs(log_dir, exist_ok=True)
    file_handler = logging.FileHandler(
        os.path.join(log_dir, "agent.log"),
        encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    ))
    logger.addHandler(file_handler)
    # 阻止传播到root logger（避免输出到terminal）
    logger.propagate = False

# 创建一个全局 Console 用于格式化输出
_console = Console()


@dataclass
class AgentResult:
    """Agent执行结果"""
    status: str  # "completed" | "need_approval" | "need_layer1_fix" | "failed"
    artifacts: Dict[str, str] = field(default_factory=dict)
    message: str = ""
    context_for_handoff: Optional[Dict[str, Any]] = None


@dataclass
class Tool:
    """工具定义"""
    name: str
    description: str
    input_schema: Dict[str, Any]
    handler: Callable[..., str]


@dataclass
class ContextConfig:
    """Context管理配置"""
    # Compact触发阈值（tokens）
    compact_threshold: int = 120_000
    # API硬限制
    api_hard_limit: int = 200_000
    # 保留最近N步完整对话
    keep_recent_steps: int = 3
    # 每token约4字符（粗略估计）
    chars_per_token: int = 4


class BaseAgent(ABC):
    """
    基础Agent类

    提供:
    - Claude API调用
    - 工具调用处理
    - Step控制
    - Context管理（拼接 + Compact）

    支持自定义端点:
    - base_url: API基础URL
    - api_key: API密钥
    """

    # 默认配置，子类可覆盖
    DEFAULT_CONTEXT_CONFIG = ContextConfig()

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        max_iterations: int = 20,
        tools: Optional[List[Tool]] = None,
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        context_config: Optional[ContextConfig] = None,
        on_tool_call_complete: Optional[Callable[[], None]] = None
    ):
        # 从参数或环境变量获取配置
        self.base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL")
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")

        # 创建客户端（设置长超时，支持大 max_tokens）
        client_kwargs = {
            "timeout": httpx.Timeout(600.0, connect=10.0)  # 10分钟超时
        }
        if self.api_key:
            client_kwargs["api_key"] = self.api_key
        if self.base_url:
            client_kwargs["base_url"] = self.base_url

        self.client = Anthropic(**client_kwargs)
        self.model = model
        self.max_iterations = max_iterations
        self.tools = tools or []
        self._tool_handlers: Dict[str, Callable] = {}

        # Context配置
        self.context_config = context_config or self.DEFAULT_CONTEXT_CONFIG

        # 对话历史（用于 checkpoint/resume）
        self._conversation_history: List[Dict] = []

        # 缓存最后一次的system_prompt和context（用于manual_compact）
        self._last_system_prompt: str = ""
        self._last_context: Dict[str, Any] = {}

        # 工具调用完成回调（用于触发checkpoint保存）
        self.on_tool_call_complete = on_tool_call_complete

        # 注册工具处理器
        for tool in self.tools:
            self._tool_handlers[tool.name] = tool.handler

    @abstractmethod
    def get_system_prompt(self, context: Dict[str, Any]) -> str:
        """获取系统提示词"""
        pass

    @abstractmethod
    def build_initial_message(self, context: Dict[str, Any]) -> str:
        """构建初始用户消息"""
        pass

    def extract_result(self, response_text: str, context: Dict[str, Any]) -> Optional[AgentResult]:
        """
        从响应中提取结构化结果（可选覆盖）

        默认返回None，表示直接使用文本响应。
        子类可覆盖此方法来提取特定格式的结果（如检查文件是否创建）。
        """
        return None

    def _get_tool_definitions(self) -> List[Dict[str, Any]]:
        """获取工具定义（Anthropic格式）"""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "input_schema": tool.input_schema
            }
            for tool in self.tools
        ]

    def _handle_tool_call(self, tool_name: str, tool_input: Dict[str, Any]) -> str:
        """处理工具调用"""
        if tool_name not in self._tool_handlers:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

        handler = self._tool_handlers[tool_name]
        try:
            result = handler(**tool_input)
            return result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})

    def _after_tool_execution(self, response, raw_messages: List[Dict]):
        """
        Hook方法：工具执行后的回调

        子类可覆写此方法来注入自定义逻辑（如格式验证、状态检查等）

        Args:
            response: Claude API响应对象
            raw_messages: 对话历史消息列表（已包含tool_results）
        """
        pass

    # ========== Context 管理 ==========

    def _estimate_tokens(self, text: str) -> int:
        """粗略估计token数量"""
        return len(text) // self.context_config.chars_per_token

    def _estimate_messages_tokens(self, messages: List[Dict]) -> int:
        """估计messages的总token数"""
        total = 0
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str):
                total += self._estimate_tokens(content)
            elif isinstance(content, list):
                # tool_use 或 tool_result 列表
                for item in content:
                    if isinstance(item, dict):
                        total += self._estimate_tokens(json.dumps(item, ensure_ascii=False))
                    else:
                        total += self._estimate_tokens(str(item))
        return total

    def _format_messages_summary(self, messages: List[Dict]) -> str:
        """格式化messages的概览（用于日志）"""
        summary = []
        for i, msg in enumerate(messages):
            role = msg.get("role", "?")
            content = msg.get("content", "")

            if isinstance(content, str):
                preview = content[:100].replace("\n", " ")
                if len(content) > 100:
                    preview += "..."
                summary.append(f"[{i}] {role}: {preview}")
            elif isinstance(content, list):
                # tool_result 或 tool_use
                items = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "tool_result":
                            items.append(f"tool_result({item.get('tool_use_id', '?')[:8]}...)")
                        elif item.get("type") == "tool_use":
                            items.append(f"tool_use({item.get('name', '?')})")
                        else:
                            items.append(f"{item.get('type', '?')}")
                    else:
                        items.append(str(type(item).__name__))
                summary.append(f"[{i}] {role}: [{', '.join(items)}]")
            else:
                summary.append(f"[{i}] {role}: <{type(content).__name__}>")

        return "\n".join(summary)

    def _build_messages_for_api(self, raw_messages: List[Dict]) -> List[Dict]:
        """
        构建发送给API的messages

        策略：
        - History（早期消息）：删除 tool_use 和 tool_result，只保留纯文本
        - 最近N步：完整保留

        重要：删除tool_result时，必须确保对应的tool_use也被删除
        """
        n = self.context_config.keep_recent_steps
        recent_count = n * 2

        if len(raw_messages) <= recent_count:
            return raw_messages

        # 分离 history 和 recent
        history = raw_messages[:-recent_count]
        recent = raw_messages[-recent_count:]

        # 收集history中保留的所有tool_use_id
        preserved_tool_use_ids = set()
        for msg in history:
            if msg.get("role") == "assistant":
                content = msg.get("content")
                if isinstance(content, list):
                    for block in content:
                        if isinstance(block, dict) and block.get("type") == "tool_use":
                            preserved_tool_use_ids.add(block.get("id"))

        # 处理 history：删除 tool_use 和 tool_result，只保留纯文本
        processed_history = []
        for msg in history:
            role = msg.get("role")
            content = msg.get("content")

            if role == "user":
                if isinstance(content, list):
                    # 过滤：只保留text，跳过tool_result
                    text_blocks = []
                    for item in content:
                        if isinstance(item, dict):
                            if item.get("type") == "text":
                                text_blocks.append(item.get("text", ""))
                            # tool_result被跳过

                    if text_blocks:
                        processed_history.append({
                            "role": "user",
                            "content": "\n".join(text_blocks)
                        })
                elif isinstance(content, str):
                    processed_history.append(msg)

            elif role == "assistant":
                if isinstance(content, str):
                    processed_history.append(msg)
                elif isinstance(content, list):
                    text_parts = []
                    for block in content:
                        if hasattr(block, "text"):
                            text_parts.append(block.text)
                        elif isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(block.get("text", ""))

                    if text_parts:
                        processed_history.append({
                            "role": "assistant",
                            "content": "\n".join(text_parts)
                        })

        # 处理recent：检查tool_result是否有对应的tool_use
        # 如果tool_use在history中被删除了，这里的tool_result也必须删除
        processed_recent = []
        for msg in recent:
            role = msg.get("role")
            content = msg.get("content")

            if role == "user" and isinstance(content, list):
                # 过滤掉引用了已删除tool_use的tool_result
                filtered_content = []
                for item in content:
                    if isinstance(item, dict) and item.get("type") == "tool_result":
                        tool_use_id = item.get("tool_use_id")
                        # 检查这个tool_use_id是否在history中被保留了
                        # 如果在preserved_tool_use_ids中，说明tool_use被删了，这个result也要删
                        if tool_use_id not in preserved_tool_use_ids:
                            # tool_use不在history的删除列表中，保留这个result
                            filtered_content.append(item)
                        # 否则跳过这个tool_result
                    else:
                        # 非tool_result的内容（如text），保留
                        filtered_content.append(item)

                if filtered_content:
                    processed_recent.append({
                        "role": "user",
                        "content": filtered_content
                    })
            else:
                # 其他消息直接保留
                processed_recent.append(msg)

        return processed_history + processed_recent

    def _should_compact(self, messages: List[Dict], system_prompt: str) -> bool:
        """检查是否需要触发Compact"""
        total_tokens = self._estimate_tokens(system_prompt) + self._estimate_messages_tokens(messages)
        return total_tokens > self.context_config.compact_threshold

    def _generate_summary(self, messages: List[Dict], system_prompt: str) -> str:
        """生成Summary（通过Mock user消息让LLM总结）"""
        compact_prompt = {
            "role": "user",
            "content": """请对当前工作进行总结，**必须**保留以下关键信息：

0. **用户需求**（最重要！）：
   - 用户原始需求的完整内容
   - 用户最后一条消息的完整内容（如果不同于原始需求）

1. **已创建的文件和目录**（非常重要！）：
   - 完整的文件路径列表
   - 每个文件的用途说明
   - 场景目录名称

2. **当前任务的核心要点和进展**：
   - 任务目标
   - 当前完成到哪一步

3. **已完成的关键操作**：
   - 已调用的工具及其重要结果
   - 已完成的分析和决策

4. **待办事项清单**：
   - 下一步需要做什么
   - 遗留问题

5. **关键文件路径和数据**：
   - 配置文件路径
   - 重要的ID、名称等标识符

总结格式使用JSON，确保信息完整但简洁。**特别注意：用户需求、已创建的文件和目录信息绝对不能丢失！**"""
        }

        # 清理所有工具调用细节，只保留纯文本对话
        text_only_messages = []
        for msg in messages:
            role = msg.get("role")
            content = msg.get("content")

            if role == "user":
                if isinstance(content, str):
                    text_only_messages.append(msg)
                elif isinstance(content, list):
                    # 只提取text，忽略tool_result
                    text_parts = []
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            text_parts.append(item.get("text", ""))
                    if text_parts:
                        text_only_messages.append({
                            "role": "user",
                            "content": "\n".join(text_parts)
                        })
            elif role == "assistant":
                if isinstance(content, str):
                    text_only_messages.append(msg)
                elif isinstance(content, list):
                    # 只提取text，忽略tool_use
                    text_parts = []
                    for block in content:
                        if hasattr(block, "text"):
                            text_parts.append(block.text)
                        elif isinstance(block, dict) and block.get("type") == "text":
                            text_parts.append(block.get("text", ""))
                    if text_parts:
                        text_only_messages.append({
                            "role": "assistant",
                            "content": "\n".join(text_parts)
                        })

        # 如果还是太长，只保留最近的消息
        estimated_tokens = self._estimate_tokens(system_prompt) + self._estimate_messages_tokens(text_only_messages) + 1000
        if estimated_tokens > self.context_config.api_hard_limit - 4000:  # 留4000给summary输出
            # 保留第一条和最后50条消息
            logger.warning(f"对话历史太长({estimated_tokens} tokens)，只使用最近50条消息生成summary")
            first_msg = text_only_messages[0] if text_only_messages else {"role": "user", "content": ""}
            recent_msgs = text_only_messages[-50:] if len(text_only_messages) > 50 else text_only_messages[1:]
            text_only_messages = [first_msg] + recent_msgs

        messages_for_compact = text_only_messages + [compact_prompt]

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4000,
            system=system_prompt,
            messages=messages_for_compact,
            temperature=0.0
        )

        summary_text = ""
        for block in response.content:
            if hasattr(block, "text"):
                summary_text += block.text

        return summary_text

    def manual_compact(self) -> bool:
        """
        用户手动触发compact压缩

        Returns:
            bool: 是否成功执行压缩（如果消息太少会跳过）
        """
        if len(self._conversation_history) < 10:
            _console.print("[yellow]消息历史太短，无需压缩[/yellow]")
            return False

        _console.print("[cyan]开始手动压缩对话历史...[/cyan]")
        # 使用缓存的system_prompt，如果没有则用最后的context重新生成
        system_prompt = self._last_system_prompt or self.get_system_prompt(self._last_context)
        self._conversation_history = self._compact_messages(self._conversation_history, system_prompt)
        _console.print(f"[green]✓ 压缩完成，当前消息数: {len(self._conversation_history)}[/green]")
        return True

    def _compact_messages(self, messages: List[Dict], system_prompt: str) -> List[Dict]:
        """
        执行Compact压缩

        流程：
        1. Mock user消息触发Summary生成
        2. LLM生成Summary
        3. 构建压缩后的messages: 第一条真实user消息 + Summary + 最近N步
        """
        logger.info("触发Compact压缩...")

        n = self.context_config.keep_recent_steps
        recent_count = n * 2

        # 生成Summary
        summary_text = self._generate_summary(messages, system_prompt)

        # 构建压缩后的messages
        # 保留第一条user message（原始需求）
        first_user_message = messages[0] if messages else {"role": "user", "content": ""}

        summary_message = {
            "role": "assistant",
            "content": f"<compact_summary>\n{summary_text}\n</compact_summary>"
        }

        # 保留最近N步
        recent_messages = messages[-recent_count:] if len(messages) >= recent_count else messages

        compressed = [first_user_message, summary_message] + recent_messages

        old_tokens = self._estimate_messages_tokens(messages)
        new_tokens = self._estimate_messages_tokens(compressed)
        logger.info(f"Compact完成: {old_tokens} -> {new_tokens} tokens")

        return compressed

    # ========== 主运行循环 ==========

    def run(self, context: Dict[str, Any], continue_from_checkpoint: bool = False) -> AgentResult:
        """
        执行Agent任务

        使用agentic loop模式:
        1. 发送消息给Claude
        2. 处理工具调用
        3. 检查是否完成
        4. 循环直到完成或达到最大step数

        Context管理:
        - 每次API调用前构建优化的messages（删除history中的tool result）
        - 超过阈值时触发Compact压缩

        Args:
            context: Agent执行上下文
            continue_from_checkpoint: 是否从checkpoint恢复（使用已保存的对话历史）
        """
        system_prompt = self.get_system_prompt(context)
        tool_definitions = self._get_tool_definitions()

        # 缓存system_prompt和context（供manual_compact使用）
        self._last_system_prompt = system_prompt
        self._last_context = context

        # Step 1: 初始化或恢复对话历史
        if continue_from_checkpoint and self._conversation_history:
            # 从checkpoint恢复历史
            raw_messages = self._conversation_history.copy()
            logger.info(f"=== {self.__class__.__name__} 从checkpoint恢复 ===")
            logger.info(f"恢复 {len(raw_messages)} 条历史消息")
        else:
            # 新对话，空历史
            raw_messages = []
            logger.info(f"=== {self.__class__.__name__} 启动 ===")
            logger.debug(f"System Prompt:\n{system_prompt}")

        # Step 2: 构建并追加新的用户消息（永远都要做，不管是新对话还是继续）
        new_user_message = self.build_initial_message(context)
        if new_user_message:  # 如果有新消息，追加
            raw_messages.append({"role": "user", "content": new_user_message})
            logger.info(f"追加新用户消息: {new_user_message[:100]}...")
            logger.debug(f"完整用户消息:\n{new_user_message}")

        logger.debug(f"Tools: {[t['name'] for t in tool_definitions]}")

        for iteration in range(self.max_iterations):
            _console.print(f"[{self.__class__.__name__}] Step {iteration + 1}", style="bold")

            # 构建发送给API的messages（应用拼接策略）
            api_messages = self._build_messages_for_api(raw_messages)

            # 检查是否需要Compact
            if self._should_compact(api_messages, system_prompt):
                logger.info(f"触发Compact压缩前: {len(raw_messages)} 条messages")
                logger.debug(f"压缩前messages概览: {self._format_messages_summary(raw_messages)}")

                raw_messages = self._compact_messages(raw_messages, system_prompt)
                api_messages = self._build_messages_for_api(raw_messages)

                logger.info(f"Compact压缩后: {len(raw_messages)} 条messages")
                logger.debug(f"压缩后messages概览: {self._format_messages_summary(raw_messages)}")

            # 打印发送给API的messages概览
            logger.debug(f"发送给API的messages: {len(api_messages)} 条")
            logger.debug(f"API messages概览: {self._format_messages_summary(api_messages)}")

            # 调用Claude
            response = self.client.messages.create(
                model=self.model,
                max_tokens=32768,  # 32K - 平衡长度和响应时间
                system=system_prompt,
                tools=tool_definitions if tool_definitions else None,
                messages=api_messages
            )

            # 日志：记录响应
            logger.debug(f"Response stop_reason: {response.stop_reason}")
            for block in response.content:
                if hasattr(block, "text"):
                    logger.debug(f"Response text: {block.text[:500]}...")
                    # 打印到 terminal，让用户看到 Agent 思考过程
                    if block.text.strip():
                        # Agent 思考文本用淡色显示（完整输出，不截断）
                        _console.print(f"  {block.text}", style="dim", overflow="ignore", no_wrap=False, crop=False)
                elif block.type == "tool_use":
                    logger.debug(f"Tool call: {block.name}({json.dumps(block.input, ensure_ascii=False)[:200]}...)")

            # 保存assistant响应到raw_messages
            assistant_message = {"role": "assistant", "content": response.content}
            raw_messages.append(assistant_message)

            # 检查停止原因
            if response.stop_reason == "end_turn":
                # Agent决定结束，提取文本响应
                text_content = ""
                for block in response.content:
                    if hasattr(block, "text"):
                        text_content += block.text

                # 尝试提取结构化结果（如果有）
                result = self.extract_result(text_content, context)

                # 保存对话历史（用于checkpoint）
                self._conversation_history = raw_messages.copy()

                return result if result else AgentResult(
                    status="completed",
                    message=text_content
                )

            elif response.stop_reason == "tool_use":
                # 处理工具调用
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        # 格式化参数显示
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

                # 保存工具结果到raw_messages
                raw_messages.append({"role": "user", "content": tool_results})

                # 立即更新对话历史（在触发checkpoint前）
                self._conversation_history = raw_messages.copy()

                # 🔥 Hook点：子类可在此注入自定义逻辑（如格式验证）
                self._after_tool_execution(response, raw_messages)

                # 触发checkpoint保存回调
                if self.on_tool_call_complete:
                    self.on_tool_call_complete()

            elif response.stop_reason == "max_tokens":
                # max_tokens: 模型输出被截断
                _console.print(f"  [继续] 输出被截断，继续生成...", style="yellow")

                # 检查截断的响应中是否有 tool_use
                # 如果有，必须先处理它们并返回 tool_result，否则 API 会报错
                has_tool_use = any(
                    block.type == "tool_use" for block in response.content
                )

                if has_tool_use:
                    # 有 tool_use，先处理工具调用
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

                    # 保存工具结果，然后继续
                    raw_messages.append({"role": "user", "content": tool_results})

                    # 立即更新对话历史（在触发checkpoint前）
                    self._conversation_history = raw_messages.copy()

                    # 触发checkpoint保存回调
                    if self.on_tool_call_complete:
                        self.on_tool_call_complete()
                else:
                    # 没有 tool_use，直接添加继续提示
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

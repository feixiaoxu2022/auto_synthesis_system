#!/usr/bin/env python3
"""
CLI - Claude Code风格的终端界面

Usage:
    python -m cli.app                    # 交互模式
    python -m cli.app "设计一个场景"      # 直接执行
    python -m cli.app --demo             # 演示模式

Environment Variables:
    ANTHROPIC_API_KEY     - API密钥
    ANTHROPIC_BASE_URL    - 自定义API端点
"""
import sys
import os
import argparse
from pathlib import Path
from typing import Optional, Dict, Any

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from cli.terminal_ui import TerminalUI, ui
from orchestrator import Orchestrator, AgentPhase
from agents import InitAgent, ExecuteAgent


class SynthesisCLI:
    """
    CLI主程序 - 连接UI和后端
    """

    def __init__(
        self,
        output_dir: str = "outputs",
        skills_dir: str = "skills",
        base_url: Optional[str] = None,
        api_key: Optional[str] = None,
        model: str = "claude-sonnet-4-5-20250929"
    ):
        self.ui = TerminalUI()
        self.output_dir = output_dir
        self.skills_dir = skills_dir
        self.base_url = base_url or os.environ.get("ANTHROPIC_BASE_URL")
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = model
        self.orchestrator: Optional[Orchestrator] = None

    def show_welcome(self):
        """显示欢迎信息"""
        self.ui.banner("Auto Synthesis System")
        self.ui.print_dim("  Type your requirement to start, or use commands:")
        self.ui.print_dim("  /help - Show help    /quit - Exit    /demo - Run demo\n")

    def show_help(self):
        """显示帮助"""
        help_text = """
## Available Commands

| Command | Description |
|---------|-------------|
| `/help` | Show this help message |
| `/quit` or `/exit` or `/q` | Exit the CLI |
| `/status` | Show current execution status |
| `/result` | Show generated artifacts |
| `/redesign` | Switch back to Init phase for design modifications |
| `/demo` | Run a demo with mock agents |
| `/clear` | Clear the screen |

## Usage

Simply type your requirement and press Enter to start the synthesis process.

Example:
```
>>> 设计一个会议室预订场景
```

## Phase Switching

- **Automatic**: System auto-switches Init→Execute after design completion
- **Manual**: Use `/redesign` to go back to design phase when in Execute phase
"""
        self.ui.print_markdown(help_text)

    def run_demo(self):
        """运行演示"""
        self.ui.print_info("Running demo with mock agents...")
        self.ui.rule("Demo Mode")

        # Import mock agents
        from orchestrator.orchestrator import MockInitAgent, MockExecuteAgent

        # Create orchestrator with mock agents
        self.orchestrator = Orchestrator(
            init_agent=MockInitAgent(should_succeed=True),
            execute_agent=MockExecuteAgent(result_sequence=["completed"]),
            output_dir=self.output_dir
        )

        # 运行
        requirement = "设计一个会议室预订场景（演示）"
        self.ui.print(f"Requirement: {requirement}\n")
        self.orchestrator.run(requirement)

        # 进入交互模式
        self._enter_interactive_mode()

    def run_resume(self, checkpoint_id: Optional[str] = None):
        """从 checkpoint 恢复执行"""
        from orchestrator.checkpoint import CheckpointManager

        # 如果没有指定 checkpoint_id，显示列表让用户选择
        if checkpoint_id is None:
            checkpoint_id = self._select_checkpoint()
            if checkpoint_id is None:
                return  # 用户取消

        self.ui.print_info(f"Resuming from checkpoint {checkpoint_id}...")

        # Check API key
        if not self.api_key:
            self.ui.print_error("API key not configured")
            self.ui.print_dim("Set via --api-key or ANTHROPIC_API_KEY environment variable")
            return

        # 创建 agents
        with self.ui.spinner("Loading agents..."):
            init_agent = InitAgent(
                output_dir=self.output_dir,
                skills_dir=self.skills_dir,
                model=self.model,
                base_url=self.base_url,
                api_key=self.api_key
            )
            execute_agent = ExecuteAgent(
                skills_dir=self.skills_dir,
                model=self.model,
                base_url=self.base_url,
                api_key=self.api_key
            )

        # 恢复 orchestrator
        self.orchestrator = Orchestrator.resume(
            init_agent=init_agent,
            execute_agent=execute_agent,
            checkpoint_id=checkpoint_id,
            output_dir=self.output_dir,
        )

        if self.orchestrator is None:
            self.ui.print_error("Failed to load checkpoint")
            return

        # 显示resume信息
        self.ui.print_success(f"Resumed from checkpoint")
        self.ui.print_dim(f"  Requirement: {self.orchestrator.user_requirement[:60]}...")
        self.ui.print_dim(f"  State: {self.orchestrator.state.value}")
        self.ui.print_dim(f"  Scenario: {self.orchestrator.scenario_name or 'N/A'}")
        self.ui.print_dim(f"  Steps: Init={self.orchestrator.init_iterations}, Execute={self.orchestrator.execute_iterations}")
        self.ui.print()

        # 显示最近的对话历史（最多显示最后3轮）
        self._show_recent_conversation(max_turns=3)

        # 进入交互模式
        self._enter_interactive_mode()

    def _show_recent_conversation(self, max_turns: int = 3):
        """显示最近的对话历史"""
        if not self.orchestrator:
            return

        # 根据当前状态选择要显示的agent
        from orchestrator import AgentPhase

        if self.orchestrator.state == AgentPhase.INIT:
            agent = self.orchestrator.init_agent
            agent_name = "Init Agent"
        else:
            agent = self.orchestrator.execute_agent
            agent_name = "Execute Agent"

        if not agent or not hasattr(agent, '_conversation_history'):
            self.ui.print_dim("No conversation history available (old checkpoint)\n")
            return

        history = agent._conversation_history
        if not history:
            self.ui.print_dim("No conversation history available (old checkpoint)\n")
            return

        # 只显示最后max_turns轮对话
        recent_messages = history[-(max_turns * 2):] if len(history) > max_turns * 2 else history

        self.ui.rule("Recent Conversation")
        self.ui.print()

        for msg in recent_messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")

            if role == "user":
                # 用户消息或工具结果
                if isinstance(content, str):
                    # 真正的用户输入
                    display_content = content[:200] + "..." if len(content) > 200 else content
                    self.ui.print(f"[bold cyan]User:[/bold cyan] {display_content}")
                elif isinstance(content, list):
                    # 工具执行结果（tool_results）
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "tool_result":
                            tool_id = item.get("tool_use_id", "")[:8]
                            result_content = item.get("content", "")

                            # 尝试解析JSON结果
                            try:
                                import json
                                result_obj = json.loads(result_content) if isinstance(result_content, str) else result_content

                                # 智能显示
                                if isinstance(result_obj, dict):
                                    if "error" in result_obj:
                                        display = f"❌ {result_obj['error']}"
                                    else:
                                        # 显示前100字符
                                        display = str(result_obj)[:100] + "..." if len(str(result_obj)) > 100 else str(result_obj)
                                else:
                                    display = str(result_obj)[:100] + "..." if len(str(result_obj)) > 100 else str(result_obj)
                            except:
                                # 非JSON，直接显示前100字符
                                display = result_content[:100] + "..." if len(result_content) > 100 else result_content

                            self.ui.print_dim(f"  ← Result [{tool_id}]: {display}")
                else:
                    # 其他类型
                    self.ui.print_dim(f"[bold cyan]User:[/bold cyan] [unknown content type]")

            elif role == "assistant":
                # Agent消息
                if isinstance(content, str):
                    display_content = content[:200] + "..." if len(content) > 200 else content
                    self.ui.print(f"[bold green]{agent_name}:[/bold green] {display_content}")
                elif isinstance(content, list):
                    # 提取文本和工具调用
                    texts = []
                    tool_calls = []
                    for block in content:
                        if isinstance(block, dict):
                            if block.get("type") == "text":
                                texts.append(block.get("text", ""))
                            elif block.get("type") == "tool_use":
                                tool_name = block.get("name", "unknown")
                                tool_input = block.get("input", {})

                                # 格式化参数
                                import json
                                params_str = json.dumps(tool_input, ensure_ascii=False)
                                if len(params_str) > 50:
                                    params_str = params_str[:50] + "..."

                                tool_calls.append(f"{tool_name}({params_str})")

                    # 显示
                    if texts:
                        text_content = " ".join(texts)
                        display_content = text_content[:150] + "..." if len(text_content) > 150 else text_content
                        self.ui.print(f"[bold green]{agent_name}:[/bold green] {display_content}")

                    if tool_calls:
                        for call in tool_calls:
                            self.ui.print_dim(f"  → {call}")
                else:
                    self.ui.print(f"[bold green]{agent_name}:[/bold green] [response]")

            self.ui.print()

        self.ui.print_dim(f"... showing last {len(recent_messages)//2} turns\n")

    def _select_checkpoint(self) -> Optional[str]:
        """让用户选择要恢复的 checkpoint"""
        import inquirer
        from orchestrator.checkpoint import CheckpointManager

        manager = CheckpointManager(checkpoint_dir="checkpoints")
        checkpoints = manager.list_checkpoints()

        if not checkpoints:
            self.ui.print_error("No checkpoints found")
            self.ui.print_dim("Run a task first to create a checkpoint")
            return None

        # 构建选项列表
        choices = []
        for i, cp in enumerate(checkpoints, 1):
            # 格式化时间
            created_at = cp.get("created_at", "Unknown")[:19]  # 只取 YYYY-MM-DD HH:MM:SS

            # 格式化需求（截断）
            requirement = cp.get("requirement", "")
            if len(requirement) > 60:
                requirement = requirement[:57] + "..."

            # 场景名和step信息
            scenario_name = cp.get("scenario_name", "")
            state = cp.get("state", "unknown")
            init_iter = cp.get("init_iterations", 0)
            exec_iter = cp.get("execute_iterations", 0)

            # 构建选项文本
            label = f"{created_at} | {requirement}"
            if scenario_name:
                label += f" | {scenario_name}"
            label += f" | {state} (I:{init_iter}, E:{exec_iter})"

            choices.append((label, cp["id"]))

        # 使用 inquirer 进行选择
        try:
            self.ui.rule("选择要恢复的会话")
            self.ui.print_dim("使用 ↑/↓ 箭头选择，Enter 确认，Ctrl+C 取消\n")

            questions = [
                inquirer.List(
                    'checkpoint',
                    message="请选择要恢复的会话",
                    choices=choices,
                ),
            ]

            answers = inquirer.prompt(questions)

            if answers is None:  # 用户按了 Ctrl+C
                self.ui.print_dim("\n已取消")
                return None

            return answers['checkpoint']

        except KeyboardInterrupt:
            self.ui.print_dim("\n已取消")
            return None

    def _enter_interactive_mode(self):
        """进入交互模式，让用户继续输入"""
        # Setup handlers
        self._setup_orchestrator_handlers()
        self.ui.print()  # 空行

        while True:
            try:
                user_input = self.ui.prompt().strip()

                if not user_input:
                    continue

                # 显示用户输入（有样式区分）
                self.ui.print(f"[bold cyan]User:[/bold cyan] {user_input}")
                self.ui.print()

                # 处理命令
                if user_input.startswith("/"):
                    cmd = user_input.lower()
                    # 检查是否是已知命令
                    known_commands = ["/quit", "/exit", "/q", "/status", "/result", "/redesign", "/compact"]

                    if cmd in ("/quit", "/exit", "/q"):
                        self.ui.print_dim("Goodbye!")
                        break
                    elif cmd == "/status":
                        self._show_orchestrator_status()
                        continue
                    elif cmd == "/result":
                        self._show_current_artifacts()
                        continue
                    elif cmd == "/compact":
                        # 手动触发对话历史压缩
                        result = self.orchestrator.continue_with_input("/compact")
                        continue
                    elif cmd == "/redesign":
                        # 强制切换回Init阶段进行设计修改
                        if self.orchestrator.state.value == "execute":
                            self.orchestrator.state = AgentPhase("init")
                            self.ui.print_success("已切换回设计阶段 (Init Agent)")
                            self.ui.print_dim("现在可以修改unified_scenario_design.yaml、BusinessRules.md等设计文件")
                            continue
                        else:
                            self.ui.print_info("当前已经在设计阶段")
                            continue
                    else:
                        # 不是已知命令，检查是否是文件路径
                        from pathlib import Path
                        if Path(user_input).exists() or "/" in user_input[1:]:
                            # 看起来是文件路径，作为普通输入传给Agent
                            pass  # 继续下面的正常处理流程
                        else:
                            self.ui.print_error(f"Unknown command: {user_input}")
                            self.ui.print_dim("提示: 如果要发送文件路径，请确保路径存在")
                            continue

                # 传给Orchestrator处理
                result = self.orchestrator.continue_with_input(user_input)

                # Agent执行完一轮，继续等待用户输入
                self.ui.print()
                self.ui.print_dim(f"当前状态: {self.orchestrator.state.value}")
                continue

            except KeyboardInterrupt:
                self.ui.print("\n")
                self.ui.print_warning("使用 /quit 退出")
                continue
            except EOFError:
                self.ui.print_dim("\nGoodbye!")
                break
            except Exception as e:
                self.ui.print_error(f"Error: {e}")
                import traceback
                traceback.print_exc()
                continue

    def _setup_orchestrator_handlers(self):
        """设置Orchestrator的phase handlers"""
        if not self.orchestrator:
            return

        # Override phase handlers to show progress
        original_handle_init = self.orchestrator._handle_init_phase
        original_handle_execute = self.orchestrator._handle_execute_phase

        def wrapped_init():
            self.ui.show_state("init_phase", {"step": self.orchestrator.init_iterations + 1})
            with self.ui.spinner("Init Agent working..."):
                original_handle_init()
            # 换行分隔思考过程和spinner
            self.ui.print()

        def wrapped_execute():
            self.ui.show_state("execute_phase", {"step": self.orchestrator.execute_iterations + 1})
            with self.ui.spinner("Execute Agent working..."):
                original_handle_execute()
            # 换行分隔思考过程和spinner
            self.ui.print()

        self.orchestrator._handle_init_phase = wrapped_init
        self.orchestrator._handle_execute_phase = wrapped_execute

    def _show_orchestrator_status(self):
        """显示Orchestrator当前状态"""
        if not self.orchestrator:
            self.ui.print_info("No active orchestrator")
            return

        self.ui.rule("当前状态")
        self.ui.print(f"State: {self.orchestrator.state.value}")
        self.ui.print(f"Scenario: {self.orchestrator.scenario_name or 'N/A'}")
        self.ui.print(f"Steps: Init={self.orchestrator.init_iterations}, Execute={self.orchestrator.execute_iterations}")
        self.ui.print()

    def _show_current_artifacts(self):
        """显示当前生成的产物"""
        if not self.orchestrator:
            self.ui.print_info("No active orchestrator")
            return

        self.ui.rule("当前产物")

        if self.orchestrator.design_artifacts:
            self.ui.print("\n[info]Design Artifacts:[/info]")
            for k, v in self.orchestrator.design_artifacts.items():
                self.ui.print(f"  • {k}: {v}")

        if self.orchestrator.execution_artifacts:
            self.ui.print("\n[info]Execution Artifacts:[/info]")
            for k, v in self.orchestrator.execution_artifacts.items():
                self.ui.print(f"  • {k}: {v}")

        if not self.orchestrator.design_artifacts and not self.orchestrator.execution_artifacts:
            self.ui.print_dim("尚未生成产物")

        self.ui.print()

    def run_real(self, requirement: str):
        """运行真实Agent"""
        self.ui.print_info("Initializing agents...")

        # Check API key
        if not self.api_key:
            self.ui.print_error("API key not configured")
            self.ui.print_dim("Set via --api-key or ANTHROPIC_API_KEY environment variable")
            return

        # Show config
        if self.base_url:
            self.ui.print_dim(f"  Base URL: {self.base_url}")
        self.ui.print_dim(f"  Model: {self.model}")

        with self.ui.spinner("Loading agents..."):
            init_agent = InitAgent(
                output_dir=self.output_dir,
                skills_dir=self.skills_dir,
                model=self.model,
                base_url=self.base_url,
                api_key=self.api_key
            )
            execute_agent = ExecuteAgent(
                skills_dir=self.skills_dir,
                model=self.model,
                base_url=self.base_url,
                api_key=self.api_key
            )

            self.orchestrator = Orchestrator(
                init_agent=init_agent,
                execute_agent=execute_agent,
                output_dir=self.output_dir
            )

        # 首次运行
        self.orchestrator.run(requirement)

        # 进入交互模式
        self._enter_interactive_mode()


    def repl(self):
        """交互式REPL"""
        self.show_welcome()

        while True:
            try:
                user_input = self.ui.prompt().strip()

                if not user_input:
                    continue

                # 显示用户输入（有样式区分）
                self.ui.print(f"[bold cyan]User:[/bold cyan] {user_input}")
                self.ui.print()

                # Handle commands
                if user_input.startswith("/"):
                    cmd = user_input.lower()
                    # 检查是否是已知命令
                    known_commands = ["/quit", "/exit", "/q", "/help", "/demo", "/clear", "/status", "/redesign"]

                    if cmd in ("/quit", "/exit", "/q"):
                        self.ui.print_dim("Goodbye!")
                        break
                    elif cmd == "/help":
                        self.show_help()
                    elif cmd == "/demo":
                        self.run_demo()
                    elif cmd == "/clear":
                        self.ui.clear()
                        self.show_welcome()
                    elif cmd == "/status":
                        if self.orchestrator:
                            self.ui.show_state(
                                self.orchestrator.state.value,
                                {"steps": f"init={self.orchestrator.init_iterations}, execute={self.orchestrator.execute_iterations}"}
                            )
                        else:
                            self.ui.print_info("No active execution")
                    elif cmd == "/redesign":
                        if self.orchestrator and self.orchestrator.state.value == "execute":
                            self.orchestrator.state = AgentPhase("init")
                            self.ui.print_success("已切换回设计阶段 (Init Agent)")
                            self.ui.print_dim("现在可以修改unified_scenario_design.yaml、BusinessRules.md等设计文件")
                        elif self.orchestrator:
                            self.ui.print_info("当前已经在设计阶段")
                        else:
                            self.ui.print_info("No active execution")
                    else:
                        # 不是已知命令，检查是否是文件路径
                        from pathlib import Path
                        if Path(user_input).exists() or "/" in user_input[1:]:
                            # 看起来是文件路径，作为requirement处理
                            self.run_real(user_input)
                            break
                        else:
                            self.ui.print_error(f"Unknown command: {user_input}")
                            self.ui.print_dim("提示: 如果要发送文件路径，请确保路径存在")
                else:
                    # Treat as requirement
                    self.run_real(user_input)
                    # 运行完一个任务后退出REPL（用户在任务交互模式中quit即表示完全退出）
                    break

            except KeyboardInterrupt:
                self.ui.print("\n")
                continue
            except EOFError:
                self.ui.print_dim("\nGoodbye!")
                break


def main():
    parser = argparse.ArgumentParser(
        description="Auto Synthesis System - Terminal Interface",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m cli.app                    # Interactive mode
  python -m cli.app "设计一个场景"      # Run directly
  python -m cli.app -r                 # Resume from last checkpoint
  python -m cli.app --demo             # Demo mode

  # With custom endpoint:
  python -m cli.app --base-url https://your-api.com/v1 --api-key your_key "需求"

Environment Variables:
  ANTHROPIC_API_KEY     - API key
  ANTHROPIC_BASE_URL    - Custom API endpoint
        """
    )

    parser.add_argument(
        "requirement",
        nargs="?",
        help="User requirement (optional, starts interactive mode if not provided)"
    )

    parser.add_argument(
        "-r", "--resume",
        action="store_true",
        help="Resume from the last checkpoint"
    )

    parser.add_argument(
        "--checkpoint-id",
        help="Resume from a specific checkpoint ID"
    )

    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run demo with mock agents"
    )

    parser.add_argument(
        "--output-dir",
        default="outputs",
        help="Output directory (default: outputs)"
    )

    parser.add_argument(
        "--skills-dir",
        default="skills",
        help="Skills directory (default: skills)"
    )

    parser.add_argument(
        "--base-url",
        help="Custom API base URL (or set ANTHROPIC_BASE_URL)"
    )

    parser.add_argument(
        "--api-key",
        help="API key (or set ANTHROPIC_API_KEY)"
    )

    parser.add_argument(
        "--model",
        default="claude-sonnet-4-5-20250929",
        help="Model name (default: claude-sonnet-4-5-20250929)"
    )

    args = parser.parse_args()

    cli = SynthesisCLI(
        output_dir=args.output_dir,
        skills_dir=args.skills_dir,
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model
    )

    if args.resume or args.checkpoint_id:
        cli.run_resume(checkpoint_id=args.checkpoint_id)
    elif args.demo:
        cli.run_demo()
    elif args.requirement:
        cli.run_real(args.requirement)
    else:
        cli.repl()


if __name__ == "__main__":
    main()

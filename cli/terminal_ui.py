"""
Terminal UI Components - Rich-based terminal rendering with fixed bottom input
"""
import sys
import time
from typing import Optional, Generator, Callable, List
from rich.console import Console, Group
from rich.panel import Panel
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.live import Live
from rich.spinner import Spinner
from rich.text import Text
from rich.table import Table
from rich.rule import Rule
from rich.style import Style
from rich.theme import Theme

from prompt_toolkit import PromptSession
from prompt_toolkit.styles import Style as PTStyle
from prompt_toolkit.formatted_text import HTML, FormattedText
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.containers import HSplit, VSplit, Window, FloatContainer, Float, ConditionalContainer
from prompt_toolkit.layout.controls import FormattedTextControl, BufferControl
from prompt_toolkit.layout.dimension import Dimension, D
from prompt_toolkit.widgets import TextArea, Frame, Box
from prompt_toolkit.application import Application
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.document import Document


# Custom theme (Claude Code style - minimal, clean)
CUSTOM_THEME = Theme({
    "info": "cyan",
    "warning": "yellow",
    "error": "red bold",
    "success": "green",
    "tool": "magenta",
    "dim": "dim white",
    "highlight": "bold white",
})


class TerminalUI:
    """终端UI组件 - Claude Code 风格，输入框固定在底部"""

    def __init__(self):
        self.console = Console(theme=CUSTOM_THEME)
        self._spinner_active = False
        self._input_history = InMemoryHistory()

        # prompt_toolkit 样式 (Claude Code 风格)
        self._pt_style = PTStyle.from_dict({
            'prompt': '#888888',
            'input': '#ffffff bold',
            'bottom-toolbar': 'bg:#1a1a1a #666666',
            'placeholder': '#666666',
        })

        # 使用 PromptSession 实现更好的输入体验
        self._session = PromptSession(
            history=self._input_history,
            style=self._pt_style,
            erase_when_done=False,
        )

        # 输出缓冲区（用于显示历史输出）
        self._output_lines: List[str] = []

    # ========== 基础输出 ==========

    def print(self, text: str = "", style: str = None):
        """普通输出"""
        self.console.print(text, style=style)

    def print_error(self, text: str):
        """错误输出"""
        self.console.print(f"[error]Error:[/error] {text}")

    def print_success(self, text: str):
        """成功输出"""
        self.console.print(f"[success]✓[/success] {text}")

    def print_warning(self, text: str):
        """警告输出"""
        self.console.print(f"[warning]Warning:[/warning] {text}")

    def print_info(self, text: str):
        """信息输出"""
        self.console.print(f"[info]ℹ[/info] {text}")

    def print_dim(self, text: str):
        """淡色输出"""
        self.console.print(text, style="dim")

    # ========== 分隔线 ==========

    def rule(self, title: str = "", style: str = "dim"):
        """分隔线"""
        self.console.print(Rule(title, style=style))

    # ========== Markdown渲染 ==========

    def print_markdown(self, content: str):
        """渲染Markdown"""
        md = Markdown(content)
        self.console.print(md)

    # ========== 代码高亮 ==========

    def print_code(self, code: str, language: str = "python", line_numbers: bool = False):
        """代码高亮输出"""
        syntax = Syntax(code, language, theme="monokai", line_numbers=line_numbers)
        self.console.print(syntax)

    # ========== 面板 ==========

    def panel(self, content: str, title: str = "", style: str = "blue"):
        """面板输出"""
        panel = Panel(content, title=title, border_style=style)
        self.console.print(panel)

    def tool_panel(self, tool_name: str, params: dict, result: str = None):
        """工具调用面板"""
        # 参数表格
        param_text = "\n".join([f"  {k}: {v}" for k, v in params.items()])

        content = f"[tool]Parameters:[/tool]\n{param_text}"
        if result:
            # 截断过长结果
            display_result = result[:500] + "..." if len(result) > 500 else result
            content += f"\n\n[success]Result:[/success]\n{display_result}"

        panel = Panel(
            content,
            title=f"[tool]Tool: {tool_name}[/tool]",
            border_style="magenta"
        )
        self.console.print(panel)

    # ========== 流式输出 ==========

    def stream_print(self, text_generator: Generator[str, None, None]):
        """流式输出文本"""
        for chunk in text_generator:
            self.console.print(chunk, end="")
        self.console.print()  # 换行

    def stream_markdown(self, text_generator: Generator[str, None, None]):
        """流式输出并最终渲染为Markdown"""
        full_text = ""
        with Live(console=self.console, refresh_per_second=10) as live:
            for chunk in text_generator:
                full_text += chunk
                # 实时更新显示
                live.update(Markdown(full_text))

    # ========== 进度指示 ==========

    def spinner(self, text: str = "Thinking..."):
        """显示加载动画（返回context manager）"""
        return self.console.status(f"[info]{text}[/info]", spinner="dots")

    # ========== 状态显示 ==========

    def show_state(self, state: str, details: dict = None):
        """显示当前状态"""
        state_colors = {
            "init_phase": "cyan",
            "init_hitl": "yellow",
            "execute_phase": "blue",
            "layer1_hitl": "yellow",
            "completed": "green",
            "failed": "red",
        }
        color = state_colors.get(state, "white")

        self.console.print(f"\n[{color}]● State: {state}[/{color}]")

        if details:
            for k, v in details.items():
                self.console.print(f"  [dim]{k}:[/dim] {v}")

    # ========== 表格 ==========

    def table(self, headers: list, rows: list, title: str = ""):
        """表格输出"""
        table = Table(title=title, show_header=True, header_style="bold")
        for h in headers:
            table.add_column(h)
        for row in rows:
            table.add_row(*[str(x) for x in row])
        self.console.print(table)

    # ========== 用户输入 ==========

    def prompt(self, message: str = "", placeholder: str = "") -> str:
        """
        简洁的输入提示 - 底部工具栏固定显示，输入框带边框
        """
        # 输入框上边界
        self.console.print()
        self.console.print("┌" + "─" * 78 + "┐", style="dim")

        # 底部工具栏
        def get_bottom_toolbar():
            return HTML(
                '<style bg="#1a1a1a" fg="#666666">'
                ' <b>Enter</b> 提交  '
                '<b>/quit</b> 退出  '
                '<b>/help</b> 帮助'
                '</style>'
            )

        try:
            result = self._session.prompt(
                message=HTML('<style fg="#888888">│ >>> </style>'),
                bottom_toolbar=get_bottom_toolbar,
            )
            # 输入框下边界
            self.console.print("└" + "─" * 78 + "┘", style="dim")
            return result
        except (EOFError, KeyboardInterrupt):
            # 输入框下边界
            self.console.print("└" + "─" * 78 + "┘", style="dim")
            return '/quit'

    def prompt_multiline(self, message: str = "") -> str:
        """多行输入（Ctrl+D 或 Esc+Enter 提交）"""
        def get_toolbar():
            return HTML(
                '<style bg="#1a1a1a" fg="#666666">'
                ' <b>Esc+Enter</b> 提交  '
                '<b>Ctrl+C</b> 取消 '
                '</style>'
            )

        try:
            result = self._session.prompt(
                message=HTML(f'<style fg="#888888">{message}</style>') if message else '',
                bottom_toolbar=get_toolbar,
                multiline=True,
            )
            return result
        except (EOFError, KeyboardInterrupt):
            return ''

    def confirm(self, message: str) -> bool:
        """确认提示"""
        response = self.console.input(f"{message} [y/n]: ").strip().lower()
        return response in ('y', 'yes')

    def select(self, message: str, options: list) -> str:
        """选择提示"""
        self.console.print(f"\n{message}")
        for i, opt in enumerate(options, 1):
            self.console.print(f"  [{i}] {opt}")

        while True:
            choice = self.console.input("Enter choice: ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(options):
                return options[int(choice) - 1]
            self.print_error(f"Please enter 1-{len(options)}")

    # ========== 清屏 ==========

    def clear(self):
        """清屏"""
        self.console.clear()

    # ========== Logo/Banner ==========

    def banner(self, text: str = "Auto Synthesis System"):
        """显示Banner"""
        banner_text = f"""
╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   {text:^53}   ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝
"""
        self.console.print(banner_text, style="cyan")


# 默认实例
ui = TerminalUI()

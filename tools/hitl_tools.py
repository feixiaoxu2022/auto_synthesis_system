"""
HITL工具 - 人机交互
"""
from typing import Dict, Any, List, Optional, Callable
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown

try:
    import questionary
    HAS_QUESTIONARY = True
except ImportError:
    HAS_QUESTIONARY = False

_console = Console()


class AskHuman:
    """请求人工介入的工具"""

    name = "ask_human"
    description = (
        "请求人工介入。当需要人工审批、确认、或补充信息时调用此工具。"
        "人会看到你的request内容并给出反馈。"
    )

    def __init__(self, handler: Optional[Callable[[str, Optional[List[str]]], Dict[str, str]]] = None):
        """
        Args:
            handler: 实际执行人机交互的回调函数
                     签名: (request: str, options: list[str] | None) -> {"choice": str, "message": str}
                     如果不提供，使用默认的 CLI 交互
        """
        self.handler = handler or self._default_cli_handler

    def _default_cli_handler(self, request: str, options: Optional[List[str]] = None) -> Dict[str, str]:
        """默认的CLI交互处理"""
        # 使用Panel美化显示
        _console.print()
        panel = Panel(
            Markdown(request),
            border_style="cyan",
            padding=(1, 2)
        )
        _console.print(panel)

        if HAS_QUESTIONARY:
            return self._questionary_handler(request, options)
        else:
            return self._fallback_handler(request, options)

    def _questionary_handler(self, request: str, options: Optional[List[str]] = None) -> Dict[str, str]:
        """使用 questionary 的交互处理（上下箭头选择）"""
        if options:
            # 添加自定义输入选项
            choices = options + ["[自定义输入]"]

            choice = questionary.select(
                "请选择操作:",
                choices=choices,
                use_arrow_keys=True,
                use_shortcuts=True
            ).ask()

            if choice == "[自定义输入]":
                message = questionary.text("请输入:").ask() or ""
                return {"choice": "custom", "message": message}
            else:
                message = questionary.text("补充说明（可选，回车跳过）:").ask() or ""
                return {"choice": choice, "message": message}
        else:
            message = questionary.text("请输入回复:").ask() or ""
            return {"choice": "custom", "message": message}

    def _fallback_handler(self, request: str, options: Optional[List[str]] = None) -> Dict[str, str]:
        """回退的简单交互处理（数字选择）"""
        if options:
            print("可选操作:")
            for i, opt in enumerate(options, 1):
                print(f"  [{i}] {opt}")
            print(f"  [0] 自定义输入")
            print()

            while True:
                choice = input("请选择: ").strip()
                if choice.isdigit():
                    idx = int(choice)
                    if idx == 0:
                        message = input("请输入: ").strip()
                        return {"choice": "custom", "message": message}
                    elif 1 <= idx <= len(options):
                        message = input("补充说明（可选，回车跳过）: ").strip()
                        return {"choice": options[idx - 1], "message": message}
                print(f"请输入 0-{len(options)} 的数字")
        else:
            message = input("请输入回复: ").strip()
            return {"choice": "custom", "message": message}

    def execute(self, request: str, options: Optional[List[str]] = None) -> Dict[str, Any]:
        """执行人机交互

        Args:
            request: Agent 的请求内容
            options: 预设选项列表

        Returns:
            {"choice": str, "message": str}
        """
        return self.handler(request, options)

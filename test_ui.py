#!/usr/bin/env python3
"""
UI样式测试脚本 - 演示三处改进效果
"""
import sys
from pathlib import Path

# Add parent to path
sys.path.insert(0, str(Path(__file__).parent))

from cli.terminal_ui import TerminalUI
import time

def test_ui_improvements():
    """测试UI改进"""
    ui = TerminalUI()

    ui.banner("UI样式改进测试")
    ui.print()

    # 测试1：step 替代 iteration
    ui.rule("改进1: 迭代计数改为Step")
    ui.show_state("init_phase", {"step": 1})
    time.sleep(1)
    ui.show_state("execute_phase", {"step": 5})
    ui.print()

    # 测试2：思考过程换行
    ui.rule("改进2: 思考过程换行显示")
    ui.print("原来: Execute Agent working... 我发现了问题...")
    ui.print()
    ui.print("现在:")
    with ui.spinner("Execute Agent working..."):
        time.sleep(2)
    ui.print()  # 换行
    ui.print("我发现了问题：评测脚本没有实际执行Agent的动作...")
    ui.print()

    # 测试3：输入框边框
    ui.rule("改进3: 输入框加边框")
    ui.print_info("请输入任意内容测试输入框效果（输入quit退出）")

    while True:
        user_input = ui.prompt()
        if user_input.lower() == 'quit':
            break
        ui.print(f"[cyan]你输入了:[/cyan] {user_input}")

    ui.print_success("测试完成！")

if __name__ == "__main__":
    test_ui_improvements()

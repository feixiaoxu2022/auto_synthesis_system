"""
Terminal UI v2 - 固定底部输入框的实时界面
"""
from typing import Optional, Callable
from prompt_toolkit import Application
from prompt_toolkit.layout.layout import Layout
from prompt_toolkit.layout.containers import HSplit, Window, FloatContainer
from prompt_toolkit.layout.controls import FormattedTextControl, BufferControl
from prompt_toolkit.layout.dimension import D
from prompt_toolkit.widgets import TextArea
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.buffer import Buffer
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML, ANSI
from prompt_toolkit.output import Output
import threading
import queue


class FixedBottomUI:
    """
    终端UI - 上方输出区域 + 下方固定输入框
    """

    def __init__(self):
        # 输出缓冲区
        self.output_buffer = []
        self.output_lock = threading.Lock()

        # 输入队列
        self.input_queue = queue.Queue()
        self.waiting_for_input = False
        self.input_prompt_text = ""

        # 创建输出控件
        def get_output_text():
            with self.output_lock:
                return ANSI("\n".join(self.output_buffer[-100:]))  # 最多显示最近100行

        self.output_control = FormattedTextControl(
            text=get_output_text,
            focusable=False
        )

        # 创建输入框
        self.input_buffer = Buffer(
            multiline=False,
            on_text_changed=self._on_input_changed
        )

        self.input_area = TextArea(
            prompt=HTML('<style fg="#888888">│ >>> </style>'),
            style="class:input-field",
            buffer=self.input_buffer,
            height=D(min=1, max=1),
            dont_extend_height=True
        )

        # 底部工具栏
        def get_toolbar_text():
            if self.waiting_for_input:
                status = f'<style fg="#00aa00">● 等待输入</style>'
            else:
                status = f'<style fg="#888888">● Agent工作中</style>'

            return HTML(
                f'{status}  '
                '<style fg="#666666">'
                '<b>Enter</b> 提交  '
                '<b>Ctrl+C</b> 中断  '
                '<b>/quit</b> 退出'
                '</style>'
            )

        self.toolbar_control = FormattedTextControl(
            text=get_toolbar_text
        )

        # 布局
        self.root_container = HSplit([
            # 输出区域（可滚动）
            Window(
                content=self.output_control,
                wrap_lines=True,
                scrollbar=True,
            ),
            # 分隔线
            Window(height=1, char='─', style='class:separator'),
            # 输入框
            self.input_area,
            # 底部工具栏
            Window(height=1, content=self.toolbar_control, style='class:toolbar'),
        ])

        # 按键绑定
        self.kb = KeyBindings()

        @self.kb.add('enter')
        def _(event):
            """提交输入"""
            if self.waiting_for_input:
                text = self.input_buffer.text
                self.input_queue.put(text)
                self.input_buffer.text = ""
                self.waiting_for_input = False

        @self.kb.add('c-c')
        def _(event):
            """中断"""
            event.app.exit(exception=KeyboardInterrupt)

        # 样式
        self.style = Style.from_dict({
            'input-field': '#ffffff',
            'toolbar': 'bg:#1a1a1a #666666',
            'separator': '#333333',
        })

        # 创建Application
        self.app = Application(
            layout=Layout(self.root_container),
            key_bindings=self.kb,
            style=self.style,
            full_screen=True,
            mouse_support=True
        )

    def _on_input_changed(self, buffer):
        """输入变化时的回调"""
        pass

    def append_output(self, text: str):
        """追加输出"""
        with self.output_lock:
            self.output_buffer.append(text)
        # 刷新显示
        if self.app.is_running:
            self.app.invalidate()

    def print(self, text: str = "", style: str = None):
        """打印输出"""
        self.append_output(text)

    def print_error(self, text: str):
        """错误输出"""
        self.append_output(f"\033[31m[Error] {text}\033[0m")

    def print_success(self, text: str):
        """成功输出"""
        self.append_output(f"\033[32m✓ {text}\033[0m")

    def prompt(self, message: str = "") -> str:
        """
        等待用户输入
        """
        self.waiting_for_input = True
        self.input_prompt_text = message

        if message:
            self.append_output(f"\n{message}")

        # 刷新界面
        self.app.invalidate()

        # 等待输入
        result = self.input_queue.get()
        self.waiting_for_input = False

        return result

    def run(self, callback: Callable):
        """
        运行UI应用

        Args:
            callback: 在后台线程中执行的任务函数
        """
        # 启动后台任务线程
        task_thread = threading.Thread(target=callback, args=(self,))
        task_thread.daemon = True
        task_thread.start()

        # 运行UI主循环
        try:
            self.app.run()
        except KeyboardInterrupt:
            pass


# 测试代码
if __name__ == "__main__":
    import time

    def test_task(ui: FixedBottomUI):
        """测试任务"""
        ui.print("欢迎使用Auto Synthesis System")
        ui.print("")

        time.sleep(1)
        ui.print("[InitAgent] Step 1")
        time.sleep(1)
        ui.print("正在读取设计文件...")
        time.sleep(1)
        ui.print("生成场景结构...")

        # 请求用户输入
        user_input = ui.prompt("请输入场景名称:")
        ui.print(f"收到输入: {user_input}")

        time.sleep(1)
        ui.print_success("设计完成")

    ui = FixedBottomUI()
    ui.run(test_task)

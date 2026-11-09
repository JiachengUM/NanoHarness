"""
智能驾舱助手终端用户界面模块

该模块实现了智能驾舱助手的终端用户界面，使用 Textual 框架构建，包括：
1. 多窗口布局：聊天窗口、日志窗口、任务窗口
2. 交互式界面：支持快捷键操作和输入注入
3. 流式显示：逐字显示聊天消息，提升用户体验
4. 录屏功能：可录制终端界面操作
5. 实时任务状态：显示后台任务和流式任务的状态

核心组件：
- TUIApp：终端用户界面应用类
- main：命令行入口函数

使用场景：
- 在终端中运行智能驾舱助手，获得更丰富的界面体验
- 监控智能驾舱助手的运行状态和任务执行情况
"""

from datetime import datetime
from typing import AsyncIterable

import typer

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, RichLog, Input, Static
from textual.containers import Container, Vertical
from textual.binding import Binding

from projects.mind.demo.runtime.runner import AgentRunner, create_agent_runner
from projects.mind.demo.task_manager.fake import FakeTaskManager

from projects.mind.demo.utils.screen_recorder import ScreenRecorder


class TUIApp(App):
    """
    智能驾舱模拟器 UI 类
    
    负责构建和管理终端 UI 界面，包括布局设计、事件处理、录屏功能等。
    基于 Textual 框架实现，提供了一个交互式的终端界面。
    
    属性说明：
    - runner: AgentRunner - 智能驾舱助手核心运行器
    - record: bool - 是否启用录屏功能
    - typing_widget: Optional[Static] - 打字指示器组件
    - inject_input_widget: Optional[Input] - 注入输入组件
    - screen_recorder: ScreenRecorder - 屏幕录制器实例
    - typing_buffer: str - 打字缓冲区，用于逐字拼接消息
    """
    
    # CSS 样式定义，控制界面布局和外观
    CSS = """
    #main-container {
        layout: vertical;
        height: 1fr;
    }
    
    #main-container > Vertical:first-child {
        height: 3fr;
    }
    
    #main-container > Container {
        layout: horizontal;
        height: 2fr;
    }
    
    #main-container > Container > Vertical {
        width: 1fr;
    }
    RichLog {
        height: 1fr;
        border: round $primary;
        padding: 0 1;
    }
    #input-area {
        height: auto;
        padding: 1 2;
    }
    #typing-container {
        layout: vertical;
        height: 3;
        border-top: solid $primary;
        padding: 0 1;
    }
    #typing-indicator {
        color: $accent;
    }
    
    .window-title {
        color: $primary;
        border-bottom: solid $primary;
        margin-bottom: 1;
        padding: 0 1;
    }
    """
    
    # 快捷键绑定
    BINDINGS = [
        Binding("i", "inject_input", "注入指令"),      # 按 i 注入自定义指令
        Binding("s", "refresh_tasks", "刷新任务"),      # 按 s 刷新任务状态
        Binding("h", "show_help", "帮助"),            # 按 h 显示帮助
        Binding("q,escape", "quit", "退出"),          # 按 q 或 ESC 退出
    ]

    def __init__(self, runner: AgentRunner, record: bool = False):
        """
        初始化 TUIApp 实例
        
        接受AgentRunner实例作为参数，设置录屏相关属性
        
        参数：
        - runner: AgentRunner - 智能驾舱助手核心运行器
        - record: bool - 是否启用录屏功能，默认 False
        """
        super().__init__()
        
        self.record = record
        self.runner = runner
        self.typing_widget = None
        self.inject_input_widget = None
        # 录屏相关属性
        self.screen_recorder = ScreenRecorder()
        # 打字缓冲区，用于逐字拼接消息
        self.typing_buffer = ""

    def compose(self) -> ComposeResult:
        """
        构建 UI 布局
        
        定义应用的 UI 结构，包括标题栏、打字指示器、聊天窗口、日志窗口和任务窗口
        
        返回：
        - ComposeResult - UI 组件的组合结果
        """
        # 顶部标题栏
        yield Header()
        
        # 打字指示器区域
        with Container(id="typing-container"):
            yield Static("", id="typing-indicator")
        
        # 主容器
        with Container(id="main-container"):
            # 聊天窗口：占据整个宽度
            with Vertical():
                yield Static("💬 聊天", classes="window-title")
                yield RichLog(id="chat", auto_scroll=True)
            
            # 日志和任务窗口：各占一半宽度
            with Container():
                # 日志窗口
                with Vertical():
                    yield Static("📋 日志", classes="window-title")
                    yield RichLog(id="log", auto_scroll=True)
                # 任务窗口
                with Vertical():
                    yield Static("✅ 任务", classes="window-title")
                    yield RichLog(id="tasks", auto_scroll=False)
        
        # 底部状态栏
        yield Footer()

    async def _handle_chat_message(self, char_generator: AsyncIterable[str]):
        """
        处理聊天消息生成器
        
        消费生成器并更新聊天窗口或打字指示器，实现逐字显示效果
        
        参数：
        - char_generator: AsyncIterable[str] - 异步可迭代对象，生成聊天消息
        """
        async def consume_generator():
            async for message in char_generator:
                self.typing_buffer += message
                typing_indicator = self.query_one("#typing-indicator", Static)
                typing_indicator.update(self.typing_buffer)
            
            typing_indicator = self.query_one("#typing-indicator", Static)
            typing_indicator.update("")
            
            if self.typing_buffer:
                chat_log = self.query_one("#chat", RichLog)
                chat_log.write(self.typing_buffer)
                self.typing_buffer = ""
        
        await consume_generator()

    def _handle_log_message(self, message: str):
        """
        处理日志消息
        
        更新日志窗口，显示系统日志信息
        
        参数：
        - message: str - 要处理的日志消息
        """
        log_log = self.query_one("#log", RichLog)
        ts = datetime.now().strftime("%H:%M:%S")
        log_log.write(f"[{ts}] {message}")

    def on_mount(self):
        """
        应用挂载时的初始化操作
        
        根据 record 参数决定是否启动录屏、运行智能驾舱助手主循环、
        模拟用户输入、设置任务刷新间隔
        """
        # 根据 record 参数决定是否开始录屏
        if self.record:
            print("🎬 应用启动，开始录屏...")
            self.screen_recorder.start_recording()
        
        # 使用 Textual 的 run_worker 启动智能驾舱助手
        async def run_runner():
            await self.runner.run()
            # 运行完成后退出应用
            self.exit("用户退出")
        
        self.run_worker(run_runner())
        
        # 设置任务刷新间隔，每1秒刷新一次
        self.set_interval(1.0, self._refresh_tasks)

    def on_unmount(self):
        """
        应用卸载时的清理操作
        
        停止录屏，确保资源正确释放
        """
        # 只在启用录屏时停止
        if self.record:
            print("🎬 应用即将退出，停止录屏...")
            self.screen_recorder.stop_recording()

    def _refresh_tasks(self):
        """
        刷新任务状态
        
        更新任务窗口显示的任务状态信息
        """
        if self.runner.is_running():
            # 获取任务摘要信息
            summary = self.runner.get_all_tasks_summary()
            tasks_view = self.query_one("#tasks", RichLog)
            # 清空任务窗口并写入新的任务状态
            tasks_view.clear()
            tasks_view.write(summary)

    def action_inject_input(self):
        """
        按 'i' 触发输入
        
        显示输入框，允许用户注入自定义语音指令
        """
        if self.inject_input_widget is None:
            # 创建输入框
            self.inject_input_widget = Input(
                placeholder="请输入模拟语音指令...",
                id="inject-input"
            )
            # 设置输入框获得焦点
            self.inject_input_widget.focus()
            # 挂载输入框到界面
            self.mount(self.inject_input_widget, before="#main-container")

            # 处理输入提交
            async def handle_submit(value: str):
                if value.strip():
                    # 注入用户输入
                    await self.runner.inject_input(value.strip())
                # 移除输入框
                await self.inject_input_widget.remove()  # type: ignore
                self.inject_input_widget = None
            
            # 设置输入框的提交处理函数
            self.inject_input_widget.on_submit = handle_submit # type: ignore

    def action_refresh_tasks(self):
        """
        按 's' 刷新任务状态
        """
        self._refresh_tasks()

    def action_show_help(self):
        """
        按 'h' 显示帮助
        """
        help_text = """
⌨️ 快捷键说明:
   i : 注入自定义语音指令
   s : 立即刷新任务状态
   h : 显示本帮助
   q / ESC : 退出程序
        """
        # 在日志窗口显示帮助信息
        self._handle_log_message("\n" + "="*50)
        self._handle_log_message(help_text)
        self._handle_log_message("="*50)

    def action_quit(self):
        """
        按 'q' 或 'ESC' 退出
        """
        # 只在启用录屏时停止
        if self.record:
            print("🎬 用户按下退出键，停止录屏...")
            self.screen_recorder.stop_recording()
        
        # 停止智能驾舱助手
        self.runner.stop()
        # 退出应用
        self.exit("用户退出")


# 创建 Typer 应用
cli_app = typer.Typer()


@cli_app.command()
def main(
    record: bool = False, 
    auto_quit: bool = True, 
    chat_dummy: bool = False, 
    intent_dummy: bool = False,
    chat_only: bool = False,
    task_manager: bool = False,
    ):
    """
    智能驾舱模拟器 (终端界面版)
    
    参数：
    - record: bool - 是否启用录屏功能，默认 False
    - auto_quit: bool - 是否在模拟输入完成后自动退出，默认 True
    - chat_dummy: bool - 是否使用模拟聊天模式，默认 False
    - intent_dummy: bool - 是否使用模拟意图分类模式，默认 False
    - chat_only: bool - 是否仅启用闲聊模式，默认 False
    - task_manager: bool - 是否启用任务管理器，默认 False
    """
    # 显示配置信息
    if record:
        print("🎬 录屏功能已启用")
    else:
        print("🎬 录屏功能已禁用")
    
    if auto_quit:
        print("🔄 模拟输入完成后将自动退出")
    else:
        print("🔄 模拟输入完成后需手动退出")
    
    if chat_dummy:
        print("🤖 使用模拟聊天模式")
    else:
        print("🤖 使用真实模型聊天模式")
    
    if intent_dummy:
        print("🤖 使用模拟意图分类模式")
    else:
        print("🤖 使用真实模型意图分类模式")
    
    if task_manager:
        print("✅ 任务管理器已启用")
    else:
        print("⚠️  任务管理器已禁用")
    
    # 创建回调函数容器
    class CallbackContainer:
        def __init__(self):
            self.app = None
        
        def handle_log_message(self, message: str):
            """处理日志消息的回调函数"""
            if self.app:
                self.app._handle_log_message(message)
        
        async def handle_chat_message(self, char_generator):
            """处理聊天消息的回调函数"""
            if self.app:
                await self.app._handle_chat_message(char_generator)
    
    # 创建回调容器实例
    callbacks = CallbackContainer()
    
    # 创建AgentRunner实例
    runner = create_agent_runner(
        log_callback=callbacks.handle_log_message,
        chat_callback=callbacks.handle_chat_message,
        chat_dummy=chat_dummy,
        intent_dummy=intent_dummy,
        auto_quit=auto_quit,
        chat_only=chat_only,
        task_manager=FakeTaskManager() if task_manager else None,
    )
    
    # 创建TUIApp实例
    demo_app = TUIApp(runner=runner, record=record)
    
    # 设置回调容器的app引用
    callbacks.app = demo_app # type: ignore
    
    # 运行终端用户界面
    demo_app.run()


if __name__ == "__main__":
    # 运行typer应用
    cli_app()

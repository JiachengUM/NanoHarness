"""
智能驾舱助手命令行界面模块

该模块实现了智能驾舱助手的命令行界面，包括：
1. 命令行交互：处理用户输入和输出
2. 颜色和格式：使用rich库提供彩色输出
3. 流式显示：逐字显示聊天消息，提升用户体验
4. 日志管理：显示系统日志信息

核心组件：
- CLIApp：命令行智能驾舱助手类
- main：命令行入口函数

使用场景：
- 在命令行中运行智能驾舱助手
- 测试和调试智能驾舱助手的功能
"""

import asyncio
import sys
from datetime import datetime
from typing import AsyncIterable

from rich.console import Console

import typer

from projects.mind.demo.runtime.runner import AgentRunner, create_agent_runner
from projects.mind.demo.task_manager.fake import FakeTaskManager

# 创建控制台实例，用于输出彩色文本
console = Console()


class CLIApp:
    """
    命令行智能驾舱助手类
    
    负责在命令行中运行智能驾舱助手，处理输入输出，
    用颜色和格式区分日志和聊天消息。
    
    属性说明：
    - runner: AgentRunner - 智能驾舱助手核心运行器
    - typing_buffer: str - 打字缓冲区，用于逐字拼接消息
    """
    
    def __init__(self, runner: AgentRunner):
        """
        初始化CLIApp实例
        
        参数：
        - runner: AgentRunner - 智能驾舱助手核心运行器
        """
        self.runner = runner
        self.typing_buffer = ""
    
    def _handle_log_message(self, message: str):
        """
        处理日志消息
        
        使用特定颜色和格式在命令行中显示日志消息
        
        参数：
        - message: str - 要处理的日志消息
        """
        # 获取当前时间戳
        ts = datetime.now().strftime("%H:%M:%S")
        # 使用蓝色显示日志时间，青色显示日志内容
        console.print(f"[blue][LOG {ts}][/blue] [cyan]{message}[/cyan]")
    
    async def _handle_chat_message(self, char_generator: AsyncIterable[str]):
        """
        处理聊天消息生成器
        
        消费生成器并在命令行中显示聊天消息，逐字输出
        
        参数：
        - char_generator: AsyncIterable[str] - 异步可迭代对象，生成聊天消息
        """
        async def consume_generator():
            async for message in char_generator:
                console.print(f"[yellow]{message}[/yellow]", end="", highlight=False)
                sys.stdout.flush()
            print()
        
        await consume_generator()
    
    async def run(self):
        """
        运行CLI智能驾舱助手
        
        启动智能驾舱助手主循环，模拟用户输入，处理命令行交互
        """
        # 打印欢迎信息
        console.print("=" * 80)
        console.print("[bold yellow]🎯 智能驾舱助手 (命令行版)[/bold yellow]")
        console.print("=" * 80)
        console.print("按 Ctrl+C 退出程序")
        console.print()
        
        # 运行智能驾舱助手主循环
        await self.runner.run()
        
        # 打印退出信息
        console.print("=" * 80)
        console.print("程序已退出")
        console.print("=" * 80)


# 创建typer应用，用于处理命令行参数
app = typer.Typer()


@app.command()
def main(
    auto_quit: bool = True, 
    chat_dummy: bool = False, 
    intent_dummy: bool = False,
    chat_only: bool = False,
    task_manager: bool = False,
    ):
    """
    智能驾舱助手 (命令行版)
    
    参数：
    - auto_quit: bool - 是否在模拟输入完成后自动退出，默认 True
    - chat_dummy: bool - 是否使用模拟聊天模式，默认 False
    - intent_dummy: bool - 是否使用模拟意图分类模式，默认 False
    - chat_only: bool - 是否仅启用闲聊模式，默认 False
    - task_manager: bool - 是否启用任务管理器，默认 False
    """
    
    # 创建回调函数容器，用于存储回调函数
    class CallbackContainer:
        def __init__(self):
            self.cli_app = None
        
        def handle_log_message(self, message: str):
            """处理日志消息的回调函数"""
            if self.cli_app:
                self.cli_app._handle_log_message(message)
        
        async def handle_chat_message(self, char_generator):
            """处理聊天消息的回调函数"""
            if self.cli_app:
                await self.cli_app._handle_chat_message(char_generator)
    
    # 创建回调容器实例
    callbacks = CallbackContainer()
    
    # 创建AgentRunner实例
    runner = create_agent_runner(
        log_callback=callbacks.handle_log_message,
        chat_callback=callbacks.handle_chat_message,
        chat_dummy=chat_dummy,
        intent_dummy=intent_dummy,
        auto_quit=auto_quit,
        chat_only = chat_only,
        task_manager=FakeTaskManager() if task_manager else None,
    )
    
    # 创建CLIApp实例
    cli_agent = CLIApp(runner=runner)
    
    # 设置回调容器的cli_app引用
    callbacks.cli_app = cli_agent # type: ignore
    
    # 运行CLI应用
    asyncio.run(cli_agent.run())


if __name__ == "__main__":
    # 运行typer应用
    app()

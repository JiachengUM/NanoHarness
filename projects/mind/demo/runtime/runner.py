"""
智能驾舱助手运行器模块

该模块负责管理智能驾舱助手的运行时环境，包括：
1. 异步任务管理（后台任务和流式任务）
2. 用户输入处理和分发
3. 任务状态跟踪和回调
4. 并发控制和任务中断

核心组件：
- AgentRunner: 智能驾舱助手运行器类，管理整个运行时环境
- create_agent_runner: 工厂函数，用于创建和配置AgentRunner实例

使用场景：
- 作为智能驾舱助手的主运行入口
- 处理用户输入并分发到不同的任务处理流程
- 管理后台任务和流式任务的执行
"""

import asyncio
import time

from typing import Protocol, Callable, AsyncGenerator

from projects.mind.demo.agents import AgentBase, Task
from projects.mind.demo.user_env.user_env import UserEnv, UserDataSource, SimulatedDataSource
from projects.mind.demo.task_manager.fake import FakeTaskManager

from projects.mind.demo.task_manager.base import TaskManager

from projects.mind.demo.task import ALL_CATEGORIES

from projects.mind.demo.user_env.simulated_data import TEST_SHORT, TEST_LONG, TEST_JUST_TALK


class LogCallback(Protocol):
    """
    日志回调函数协议
    
    用于处理日志消息的回调函数接口
    """
    def __call__(self, message: str) -> None:
        """
        处理日志消息
        
        参数：
        - message: str - 日志消息文本
        """
        ...


# 聊天回调函数类型定义
# 接受一个异步可迭代对象作为参数，用于处理流式聊天消息
class ChatCallback(Protocol):
    async def __call__(self, gen: AsyncGenerator[str, None]) -> None:
        """
        处理流式聊天消息
        
        参数：
        - gen: AsyncGenerator[str, None] - 异步生成器，生成聊天消息的流
        
        选择AsyncGenerator而不是AsyncIterator的原因：
        - 所有调用点都使用异步生成器（chat_stream_dummy和ChatResultAsyncStream）
        - 前者属于后者。使用更具体的类型可以提供更准确的类型提示和检查, 防止误传非协程的异步迭代器；
        - 未来可扩展：若需 asend() 支持（如流式取消信号），无需改类型；
        - 符合惯例：与 Python中llm的异步生态一致。
        """
        ...



class AgentRunner:
    """
    智能驾舱助手运行器类
    
    负责管理智能驾舱助手的运行时环境，包括异步任务、队列管理、状态跟踪等。
    调用AgentBase实现具体的业务逻辑。
    
    核心异步机制：
    1. 主循环 (run_main_loop)：从输入队列获取用户指令，放入任务队列
    2. 流式任务处理 (_streaming_worker)：消费任务队列，处理 agent.run() 的产出
    3. 后台任务轮询 (_poll_loop)：监控已提交的后台任务状态
    4. 任务中断机制：新任务可以打断正在执行的任务
    
    属性说明：
    - agent: AgentBase - 智能驾舱助手核心实例，处理具体的业务逻辑
    - input_env: UserEnv - 用户输入环境实例，管理用户输入队列
    - log_callback: LogCallback - 日志回调函数，用于输出日志信息
    - chat_callback: ChatCallback - 聊天回调函数，用于处理流式聊天消息
    - task_manager: TaskManager - 任务管理器实例，管理后台任务
    - auto_quit: bool - 是否在模拟输入完成后自动退出
    - running: bool - 运行状态标志
    - tasks: dict[str, float] - 存储正在执行的后台任务ID和创建时间
    - chat_queue: asyncio.Queue - 任务队列，存储待处理的用户输入
    - current_chat_task: asyncio.Task | None - 当前正在执行的流式任务
    """
    
    def __init__(
        self, 
        agent: AgentBase, 
        input_env: UserEnv, 
        log_callback: LogCallback, 
        chat_callback: ChatCallback,
        task_manager: TaskManager | None = None,
        *, 
        chat_only: bool = False,
        auto_quit: bool = True
        ):
        """
        初始化 AgentRunner 实例
        
        参数：
        - agent: AgentBase - 智能驾舱助手核心实例，处理具体的业务逻辑
        - input_env: UserEnv - 用户输入环境实例，管理用户输入队列
        - log_callback: Callable - 日志回调函数，用于输出日志信息
        - chat_callback: ChatCallback - 聊天回调函数，用于处理流式聊天消息
        - task_manager: TaskManager | None - 任务管理器实例，管理后台任务，为 None 时后台任务功能失效
        - auto_quit: bool - 是否在模拟输入完成后自动退出，默认 True
        """
        self.agent = agent
        self.input_env = input_env
        self.input_env.set_callback(
            agent_running_callback=self.is_running,  # 检查代理是否仍在运行的回调
            completion_callback=self._on_input_completed     # 模拟输入完成的回调
        )


        self.log_callback = log_callback
        self.chat_callback = chat_callback
        self.task_manager = task_manager
        self.chat_only = chat_only
        self.auto_quit = auto_quit
        self.running = True
        
        # 后台任务字典：任务ID -> 创建时间
        # 用于跟踪正在执行的后台任务及其运行时间
        self.tasks: dict[str, float] = {}
        
        # 流式任务队列：存储待处理的闲聊任务
        # 支持任务中断，新任务会打断正在执行的闲聊任务
        self.chat_queue = asyncio.Queue()
        
        # 当前正在执行的流式聊天任务
        # 用于跟踪和管理正在进行的闲聊任务
        self.current_chat_task: asyncio.Task | None = None
    
    def get_all_tasks_summary(self) -> str:
        """
        获取所有任务的摘要信息
        
        返回：
        - str - 任务摘要文本，包含后台任务和流式任务的状态信息
        """
        # 构建任务摘要文本
        lines = []
        
        # 后台任务部分
        if self.task_manager is not None:
            # 获取待处理和已完成的任务列表
            pending_tasks = self.task_manager.get_pending_tasks()
            completed_tasks = self.task_manager.get_completed_tasks()
            
            lines.append(f"📬 后台任务 ({len(pending_tasks) + len(completed_tasks)}):")
            
            # 显示进行中任务
            for rid, created in self.tasks.items():
                task_run = self.task_manager.get_task(rid)
                if task_run:
                    # 计算任务运行时间
                    age = time.time() - created
                    lines.append(f"  • {rid[:10]} | {task_run.status} | {age:.1f}s")
            
            # 显示最近完成的5个任务
            for task_run in reversed(completed_tasks[-5:]):
                lines.append(f"  ✓ {task_run.task_id[:10]} | 完成")
        else:
            lines.append("📬 后台任务:")
            lines.append("  • 任务管理器未启用")
        
        # 显示流式任务状态
        lines.append("\n💬 流式任务:")
        if self.current_chat_task and not self.current_chat_task.done():
            lines.append("  • 正在处理中（可被新任务打断）")
        else:
            lines.append("  • 空闲")
        
        return "\n".join(lines)
    
    def is_running(self) -> bool:
        """
        检查运行状态
        
        返回：
        - bool - 运行状态，True表示正在运行，False表示已停止
        """
        return self.running
    
    async def inject_input(self, text: str):
        """
        注入用户输入
        
        核心职责：
        - 将用户输入添加到输入队列，供主循环处理
        
        异步机制：
        - 直接调用 input_env.inject_input()，将输入放入输入队列
        - 该方法是 async 的，因为底层的队列操作是异步的
        
        参数：
        - text: str - 要注入的用户输入文本
        """
        await self.input_env.inject_input(text)
    
    def stop(self):
        """
        停止运行
        
        核心职责：
        - 设置运行状态为 False
        - 停止输入环境
        
        同步机制：
        - 该方法是同步的，因为只修改状态和调用同步方法
        - 调用后，主循环会在下一次检查 running 状态时退出
        """
        self.running = False
        self.input_env.stop()
    
    def _on_input_completed(self):
        """
        模拟输入完成的回调函数
        
        当auto_quit为True时，自动退出程序
        """
        if self.auto_quit:
            print("🔄 模拟输入完成，自动退出程序...")
            self.stop()
    
    async def _poll_loop(self):
        """
        后台任务轮询循环
        
        核心职责：
        1. 定期检查后台任务的执行状态
        2. 处理完成或失败的任务
        3. 发送任务完成/失败的通知
        
        异步机制：
        - 每0.5秒轮询一次任务状态
        - 复制任务ID列表，避免在迭代过程中修改字典
        - 处理完成任务：发送完成消息，记录日志，从任务字典移除
        - 处理失败任务：记录日志，从任务字典移除
        """
        while self.running:
            if self.task_manager is not None and self.tasks:
                # 复制任务ID列表，避免在迭代过程中修改字典
                rids = list(self.tasks.keys())
                for rid in rids:
                    # 查询任务状态
                    data = self.task_manager.query(rid)
                    
                    # 处理完成的任务
                    if data.status == "completed":
                        # 获取任务结果
                        content = data.content
                        
                        # 创建任务完成消息生成器
                        async def task_message_generator() -> AsyncGenerator[str, None]:
                            yield f"🎯 {content}"
                        
                        # 通过回调函数发送任务完成消息
                        await self.chat_callback(task_message_generator())
                        self.log_callback(f"✅ 后台任务完成: {rid}")
                        
                        # 从任务字典中移除已完成的任务
                        self.tasks.pop(rid, None)
                    
                    # 处理失败的任务
                    elif data.status == "failed":
                        self.log_callback(f"❌ 后台任务失败: {rid}")
                        self.tasks.pop(rid, None)
            
            # 轮询间隔
            await asyncio.sleep(0.5)
    
    async def _streaming_worker(self):
        """
        流式任务处理工作线程
        
        核心职责：
        1. 从任务队列中获取用户输入
        2. 显示用户消息
        3. 处理任务中断（新任务打断旧任务）
        4. 消费 agent.run() 生成器，处理其产出
        
        异步流程：
        - 从 chat_queue 获取任务（阻塞）
        - 显示用户消息
        - 检查并处理中断
        - 创建 process_task 协程处理当前任务
        - 等待任务完成，处理取消异常
        - 重置任务状态，标记队列任务完成
        """
        while self.running:
            # 从队列中获取流式任务（阻塞直到有任务）
            prompt = await self.chat_queue.get()
            
            # 输出用户消息
            async def user_message_generator() -> AsyncGenerator[str, None]:
                yield f"🎤 用户: {prompt}"
            
            # 显示用户消息
            await self.chat_callback(user_message_generator())
            
            # 检查是否有正在执行的流式任务
            if self.current_chat_task and not self.current_chat_task.done():
                # 取消正在执行的任务
                self.current_chat_task.cancel()
                try:
                    await self.current_chat_task
                except asyncio.CancelledError:
                    # 处理任务取消的情况
                    async def handle_cancel() -> AsyncGenerator[str, None]:
                        yield "⏹️ 上一段闲聊已被打断"

                    await self.chat_callback(handle_cancel())
            
            # 处理当前任务
            async def process_task():
                """
                处理单个任务的内部协程
                
                职责：
                1. 消费 agent.run() 生成器
                2. 区分处理 str（聊天内容）和 Task（后台任务）
                3. 流式处理聊天内容，提交后台任务
                """
                # 收集字符串产出的队列
                str_queue = asyncio.Queue()
                chat_task = None
                
                async def str_generator():
                    """
                    流式聊天消息生成器
                    
                    从 str_queue 中获取消息块并 yield，直到收到 None 信号
                    """
                    while True:
                        chunk = await str_queue.get()
                        if chunk is None:
                            break
                        yield chunk
                
                try:
                    # 遍历 agent.run() 的产出
                    async for item in self.agent.run(prompt):
                        if isinstance(item, str):
                            # 首次收到 str 时，启动聊天回调
                            if chat_task is None:
                                chat_task = asyncio.create_task(
                                    self.chat_callback(str_generator())
                                )
                            # 将消息块放入队列
                            await str_queue.put(item)
                        elif isinstance(item, Task):
                            # 处理后台任务
                            if self.task_manager is not None:
                                rid = self.task_manager.submit(item)
                                self.tasks[rid] = time.time()
                                self.log_callback(f"📤 提交后台任务({item.task_type}): {prompt[:30]}...")
                            else:
                                # 任务管理器未启用，跳过后台任务
                                self.log_callback(f"⚠️  任务管理器未启用，跳过后台任务: {item.task_type}")
                finally:
                    # 任务完成后，发送结束信号并等待聊天回调完成
                    if chat_task is not None:
                        await str_queue.put(None)
                        await chat_task
            
            # 创建新的流式任务
            self.current_chat_task = asyncio.create_task(process_task())
            try:
                # 等待任务完成
                await self.current_chat_task
            except asyncio.CancelledError:
                # 任务被取消，忽略异常
                pass
            finally:
                # 任务完成或被取消后，重置当前任务状态
                self.current_chat_task = None
                
            # 标记队列任务为完成
            self.chat_queue.task_done()

    async def run_main_loop(self, input_queue: asyncio.Queue):
        """
        主运行循环
        
        核心职责：
        1. 启动后台任务轮询和流式任务处理线程
        2. 从输入队列获取用户指令
        3. 将用户指令放入任务队列
        
        异步机制：
        - 使用 asyncio.wait_for() 为 input_queue.get() 添加超时，避免阻塞
        - 超时后检查 running 状态，确保程序能及时退出
        - 异常处理：捕获超时异常，继续循环
        - 资源清理：在 finally 块中取消所有任务
        
        参数：
        - input_queue: asyncio.Queue - 用户输入队列，从该队列中获取用户输入
        """
        # 启动后台任务轮询线程
        poll_task = asyncio.create_task(self._poll_loop())
        
        # 启动流式任务处理线程
        stream_task = asyncio.create_task(self._streaming_worker())
        
        try:
            while self.running:
                # 这里不能直接写 await input_queue.get()
                # 问题：当数据源耗尽时，completion_callback被调用，stop方法被执行，
                # 但主循环仍阻塞在input_queue.get()上，导致程序无法退出
                # 解决方案：使用asyncio.wait_for()为get()操作添加超时，
                # 这样即使队列中没有新数据，也能定期检查running状态
                # 超时时间设置为0.1秒，平衡了响应速度和CPU使用率
                try:
                    user_utterance = await asyncio.wait_for(input_queue.get(), timeout=0.1)
                    if not self.running:  # 再次检查（防止 stop() 在 get() 期间被调用）
                        break
                    # 直接将用户输入放入队列，由 _streaming_worker 处理
                    await self.chat_queue.put(user_utterance)
                except asyncio.TimeoutError:
                    # 超时后继续循环，检查running状态
                    # 这是正常现象，不是错误
                    pass
        finally:
            # 清理资源，取消所有任务
            poll_task.cancel()
            stream_task.cancel()
            self.running = False
    
    async def run(self):
        """
        运行智能驾舱助手
        
        核心职责：
        1. 启动主循环任务
        2. 启动模拟用户输入任务
        3. 等待所有任务完成
        4. 处理键盘中断
        5. 清理资源
        
        异步机制：
        - 使用 asyncio.create_task() 创建异步任务
        - 使用 asyncio.gather() 等待多个任务完成
        - 捕获 KeyboardInterrupt 异常，优雅退出
        - 在 finally 块中取消所有任务，确保资源正确释放
        - 生产者（模拟输入）应先于消费者（主循环）停止
        """
        # 启动主循环任务
        main_loop_task = asyncio.create_task(self.run_main_loop(self.input_env.input_queue))
        
        # 启动模拟用户输入任务
        simulate_input_task = asyncio.create_task(
            self.input_env.start_listening())
        
        try:
            # 等待所有任务完成
            await asyncio.gather(main_loop_task, simulate_input_task)
        except KeyboardInterrupt:
            # 处理键盘中断
            print("\n🔄 用户中断，退出程序...")
            self.stop()
        finally:
            # 取消所有任务，确保资源被正确释放。生产者应先于消费者停止。
            simulate_input_task.cancel()
            main_loop_task.cancel()
            try:
                await main_loop_task
                await simulate_input_task
            except asyncio.CancelledError:
                # 忽略任务取消异常
                pass


def create_agent_runner(
    log_callback: LogCallback,
    chat_callback: Callable,
    chat_dummy: bool = False,
    intent_dummy: bool = False,
    auto_quit: bool = True,
    chat_only: bool = False,
    task_manager: TaskManager | None = None,
    data_sources: list[UserDataSource] | None = None,
) -> AgentRunner:
    """
    创建并配置AgentRunner实例
    
    工厂函数，用于创建和配置AgentRunner实例，简化依赖注入
    
    参数：
    - log_callback: Callable - 日志回调函数，用于输出日志信息
    - chat_callback: Callable - 聊天消息回调函数，用于处理流式聊天消息
    - chat_dummy: bool - 是否使用dummy聊天模式，默认False
    - intent_dummy: bool - 是否使用dummy意图分类模式，默认False
    - auto_quit: bool - 是否在模拟输入完成后自动退出，默认True
    - task_manager: TaskManager | None - 任务管理器实例，管理后台任务，为 None 时后台任务功能失效
    - data_sources: list[UserDataSource] | None - 数据源列表，默认使用TEST_SHORT模拟数据
    
    返回：
    - AgentRunner - 配置好的AgentRunner实例
    """
    # 保持 task_manager 原样，不做默认值处理
    # 这样调用者可以显式传入 None 来禁用任务管理器
    # 注意：如果传入 None，后台任务功能将被禁用
    
    # 创建AgentBase实例
    agent = AgentBase(
        chat_dummy=chat_dummy,
        intent_dummy=intent_dummy,
        intent_categories=ALL_CATEGORIES,
    )
    
    # 如果没有提供数据源，使用默认的模拟数据源
    if data_sources is None:
        # 使用短测试数据
        feed = TEST_SHORT
        data_sources =[SimulatedDataSource(feed)]

    # 创建UserEnv实例，管理用户输入
    input_env = UserEnv(data_sources=data_sources)
    
    # 创建AgentRunner实例，注入所有依赖
    runner = AgentRunner(
        agent=agent,
        input_env=input_env,
        log_callback=log_callback,
        chat_callback=chat_callback,
        task_manager=task_manager,
        auto_quit=auto_quit,
        chat_only=chat_only,
    )
    
    return runner

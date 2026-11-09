"""
智能驾舱模拟器 Demo

本文件实现了一个基于 Textual 框架的智能驾舱模拟器，模拟了一个智能语音助手在汽车环境中的交互过程。

整体设计架构：
1. 后端逻辑层：AgentCore 类负责处理业务逻辑，包括任务管理、流式响应等
2. UI 展示层：AgentUI 类负责构建和管理终端 UI 界面
3. 数据链路：
   - 用户输入 → AgentCore → 任务处理 → UI 展示
   - 模拟输入 → 输入队列 → AgentCore → 任务处理 → UI 展示
4. 录屏功能：通过 MSS 库捕获屏幕，OpenCV 生成视频

背后设计思想：
1. 模块化设计：将业务逻辑与 UI 分离，便于维护和扩展
2. 异步处理：使用 asyncio 处理并发任务，提高响应速度
3. 流式输出：模拟真实语音助手的逐字输出效果
4. 真实场景模拟：按时间顺序排列的指令序列，模拟用户一天的使用场景
5. 多任务管理：区分后台任务和流式任务，提高系统灵活性

UI 界面使用：
1. 布局结构：
   - 顶部：应用标题栏
   - 打字指示器：显示正在输入的文本
   - 聊天窗口：占据整个宽度，显示用户和助手的对话
   - 日志和任务窗口：各占一半宽度，分别显示系统日志和任务状态
   - 底部：状态栏，显示快捷键提示
2. 快捷键：
   - i: 注入自定义语音指令
   - s: 立即刷新任务状态
   - h: 显示帮助信息
   - q/ESC: 退出程序
3. 录屏功能：
   - 通过命令行参数 --record 或 -r 启用
   - 启用时应用启动自动开始录屏
   - 退出时自动停止并生成视频文件
   - 视频文件命名格式：terminal_demo_时间戳.mp4

使用方法：
1. 运行命令（禁用录屏，默认）：python projects\mind\experiments\mind_demo.py
2. 运行命令（启用录屏）：python projects\mind\experiments\mind_demo.py --record
3. 观察模拟用户与助手的交互过程
4. 可按 i 键注入自定义指令
5. 按 q 或 ESC 键退出，启用录屏时会自动生成视频
"""
import asyncio
import time
import random
import threading
from datetime import datetime
from typing import Dict, Optional, List
import typer

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, RichLog, Input, Static
from textual.containers import Container, Vertical
from textual import events
from textual.binding import Binding

# ========== 模拟后端逻辑 ==========

# 模拟任务数据库，存储正在处理的任务
FAKE_TASKS_DB: Dict[str, dict] = {}

# 已完成任务列表，存储已处理完成的任务
COMPLETED_TASKS: List[dict] = []

def fake_submit(prompt: str) -> str:
    """
    模拟提交任务
    
    创建一个模拟任务并添加到任务数据库中
    
    参数：
    - prompt: str - 任务提示内容
    
    返回：
    - str - 任务 ID
    """
    response_id = f"resp-{int(time.time())}-{random.randint(1000, 9999)}"
    FAKE_TASKS_DB[response_id] = {
        "status": "in_progress",
        "prompt": prompt,
        "created_at": time.time(),
        "result_after": time.time() + random.uniform(1.0, 3.0)
    }
    return response_id

def fake_get_response(response_id: str) -> dict:
    """
    模拟获取任务响应
    
    检查任务状态，如果任务已完成则返回响应
    
    参数：
    - response_id: str - 任务 ID
    
    返回：
    - dict - 任务响应，包含状态和内容
    """
    task = FAKE_TASKS_DB.get(response_id)
    if not task:
        return {"status": "failed", "error": "Task not found"}
    
    now = time.time()
    if now >= task["result_after"]:
        task["status"] = "completed"
        task["content"] = f"✅ 已处理指令: {task['prompt']}"
        COMPLETED_TASKS.append(task.copy())
    return {
        "status": task["status"],
        "choices": [{"message": {"content": task.get("content", "")}}] if task["status"] == "completed" else []
    }

class AgentCore:
    """
    智能驾舱助手核心逻辑类
    
    负责处理用户指令、管理后台任务、生成流式响应等核心业务逻辑。
    是整个系统的后端处理中心，与 UI 层通过回调函数进行通信。
    
    属性：
    - tasks: Dict[str, float] - 存储正在处理的任务及其创建时间
    - streaming_queue: asyncio.Queue - 流式任务队列
    - current_streaming_task: Optional[asyncio.Task] - 当前正在执行的流式任务
    - running: bool - 运行状态标志
    - ui_callback: Callable - UI 回调函数，用于向界面发送消息
    - chat_buffer: str - 聊天消息缓冲区，用于逐字显示
    """
    def __init__(self):
        """
        初始化 AgentCore 实例
        
        设置初始状态和属性，准备处理用户指令
        """
        self.tasks: Dict[str, float] = {}
        self.streaming_queue = asyncio.Queue()
        self.current_streaming_task: Optional[asyncio.Task] = None
        self.running = True
        self.ui_callback = None
        # 聊天消息缓冲区，用于逐字显示
        self.chat_buffer = ""

    def log(self, message: str):
        """
        记录系统日志
        
        向 UI 发送格式化的日志消息，包含时间戳
        
        参数：
        - message: str - 要记录的日志消息
        """
        if self.ui_callback:
            ts = datetime.now().strftime("%H:%M:%S")
            self.ui_callback("log", f"[{ts}] {message}")

    def chat(self, message: str):
        """
        发送聊天消息
        
        向 UI 发送聊天消息，直接写入聊天窗口
        
        参数：
        - message: str - 要发送的聊天消息
        """
        if self.ui_callback:
            # 直接写入消息，不使用缓冲区
            # 由于 RichLog 每次 write() 都会添加换行符，
            # 我们将整个消息一次性写入，以确保整句在同一行显示
            self.ui_callback("chat", message)

    async def submit_task(self, prompt: str) -> str:
        """
        提交后台任务
        
        将用户指令包装为后台任务并提交处理
        
        参数：
        - prompt: str - 用户指令内容
        
        返回：
        - str - 任务 ID
        """
        rid = fake_submit(prompt)
        self.tasks[rid] = time.time()
        self.log(f"📤 提交后台任务: {prompt[:30]}...")
        return rid

    async def submit_streaming_task(self, prompt: str):
        """
        提交流式任务
        
        将用户指令添加到流式任务队列，用于生成实时响应
        
        参数：
        - prompt: str - 用户指令内容
        """
        await self.streaming_queue.put(prompt)
        self.chat(f"🎤 用户: {prompt}")

    def get_all_tasks_summary(self) -> str:
        """
        获取所有任务的摘要信息
        
        生成包含正在处理和已完成任务的摘要文本
        
        返回：
        - str - 任务摘要文本
        """
        lines = [f"📬 后台任务 ({len(self.tasks) + len(COMPLETED_TASKS)}):"]
        for rid, created in self.tasks.items():
            task_info = FAKE_TASKS_DB.get(rid, {})
            prompt = task_info.get("prompt", "未知")
            age = time.time() - created
            lines.append(f"  • {rid} | {prompt[:25]}... | {age:.1f}s")
        
        for task in reversed(COMPLETED_TASKS[-5:]):
            lines.append(f"  ✓ {task['prompt'][:30]}... | 完成")
        
        lines.append("\n💬 流式任务:")
        if self.current_streaming_task and not self.current_streaming_task.done():
            lines.append("  • 正在播报中（可被新闲聊打断）")
        else:
            lines.append("  • 空闲")
        return "\n".join(lines)

    async def _poll_loop(self):
        """
        后台任务轮询循环
        
        定期检查后台任务的执行状态，处理完成或失败的任务
        """
        while self.running:
            if self.tasks:
                rids = list(self.tasks.keys())
                for rid in rids:
                    data = fake_get_response(rid)
                    if data["status"] == "completed":
                        content = data["choices"][0]["message"]["content"]
                        self.chat(f"🎯 {content}")
                        self.log(f"✅ 后台任务完成: {rid}")
                        self.tasks.pop(rid, None)
                    elif data["status"] == "failed":
                        self.log(f"❌ 后台任务失败: {rid}")
                        self.tasks.pop(rid, None)
            await asyncio.sleep(0.5)

    async def _streaming_worker(self):
        """
        流式任务处理工作线程
        
        从流式任务队列中获取任务并执行，支持任务中断
        """
        while self.running:
            prompt = await self.streaming_queue.get()
            if self.current_streaming_task and not self.current_streaming_task.done():
                self.current_streaming_task.cancel()
                try:
                    await self.current_streaming_task
                except asyncio.CancelledError:
                    self.chat("⏹️ 上一段闲聊已被打断")
            
            self.current_streaming_task = asyncio.create_task(self._speak_text(prompt))
            try:
                await self.current_streaming_task
            except asyncio.CancelledError:
                pass
            finally:
                self.current_streaming_task = None
            self.streaming_queue.task_done()

    async def _speak_text(self, text: str):
        """
        生成流式文本响应
        
        模拟打字机效果，逐字输出响应内容
        
        参数：
        - text: str - 要响应的文本内容
        """
        full_response = f"🤖 回复: {text}。很高兴为您服务！"
        # 打字机效果：逐字输出但不换行
        
        # 思考时间
        await asyncio.sleep(0.3)
        
        # 逐字构建并显示消息
        current_message = ""
        for char in full_response:
            current_message += char
            # 发送当前消息，使用一个特殊的前缀
            if self.ui_callback:
                # 使用一个特殊的标记来表示正在打字
                self.ui_callback("chat", f"__typing__{current_message}")
            # 控制打字速度
            await asyncio.sleep(0.05)
        
        # 打字完成后，添加一个正常的消息
        if self.ui_callback:
            # 清空打字指示器
            self.ui_callback("chat", "__clear_typing__")
            # 添加完整消息到聊天历史
            self.ui_callback("chat", full_response)
        
        # 打字完成后的停顿
        await asyncio.sleep(0.5)

    async def run_main_loop(self, input_queue: asyncio.Queue):
        """
        主运行循环
        
        处理用户输入，根据指令类型分发到不同的处理逻辑
        
        参数：
        - input_queue: asyncio.Queue - 用户输入队列
        """
        poll_task = asyncio.create_task(self._poll_loop())
        stream_task = asyncio.create_task(self._streaming_worker())
        try:
            while self.running:
                try:
                    user_utterance = await asyncio.wait_for(input_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue

                if any(kw in user_utterance for kw in ["导航", "去", "路线", "加油站", "停车场", "机场", "公司"]):
                    prompt = f"规划路线：{user_utterance}"
                    await self.submit_task(prompt)
                elif any(kw in user_utterance for kw in ["空调", "温度", "车窗", "座椅", "天窗"]):
                    prompt = f"控制车辆：{user_utterance}"
                    await self.submit_task(prompt)
                elif any(kw in user_utterance for kw in ["播放", "音乐", "音量", "暂停", "下一首", "歌单"]):
                    prompt = f"媒体控制：{user_utterance}"
                    await self.submit_task(prompt)
                elif any(kw in user_utterance for kw in ["天气", "新闻", "餐厅", "咖啡店"]):
                    prompt = f"信息查询：{user_utterance}"
                    await self.submit_task(prompt)
                else:
                    await self.submit_streaming_task(user_utterance)
        finally:
            poll_task.cancel()
            stream_task.cancel()
            self.running = False

# ========== Textual UI ==========
class AgentUI(App):
    """
    智能驾舱模拟器 UI 类
    
    负责构建和管理终端 UI 界面，包括布局设计、事件处理、录屏功能等。
    基于 Textual 框架实现，提供了一个交互式的终端界面。
    
    属性：
    - agent: AgentCore - 智能驾舱助手核心逻辑实例
    - input_queue: asyncio.Queue - 用户输入队列
    - typing_widget: Optional[Static] - 打字指示器组件
    - inject_input_widget: Optional[Input] - 注入输入组件
    - is_recording: bool - 录屏状态标志
    - recording_thread: Optional[threading.Thread] - 录屏线程
    - screenshot_interval: float - 截图间隔时间（秒）
    - recording_frames: List[np.ndarray] - 录制的视频帧
    """
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
    
    BINDINGS = [
        Binding("i", "inject_input", "注入指令"),
        Binding("s", "refresh_tasks", "刷新任务"),
        Binding("h", "show_help", "帮助"),
        Binding("q,escape", "quit", "退出"),
    ]

    def __init__(self, record: bool = False):
        """
        初始化 AgentUI 实例
        
        创建 AgentCore 实例，设置回调函数，初始化输入队列和录屏相关属性
        
        参数：
        - record: bool - 是否启用录屏功能，默认 False
        """
        super().__init__()
        self.agent = AgentCore()
        self.agent.ui_callback = self._send_to_ui
        self.input_queue = asyncio.Queue()
        self.typing_widget = None
        self.inject_input_widget = None
        # 录屏控制参数
        self.record = record
        # 录屏相关属性
        self.is_recording = False
        self.recording_thread = None
        self.screenshot_interval = 0.1  # 10fps
        self.recording_frames = []

    def compose(self) -> ComposeResult:
        """
        构建 UI 布局
        
        定义应用的 UI 结构，包括标题栏、打字指示器、聊天窗口、日志窗口和任务窗口
        
        返回：
        - ComposeResult - UI 组件的组合结果
        """
        yield Header()
        with Container(id="typing-container"):
            yield Static("", id="typing-indicator")
        with Container(id="main-container"):
            # 聊天窗口：占据整个宽度
            with Vertical():
                yield Static("💬 聊天", classes="window-title")
                yield RichLog(id="chat", auto_scroll=True)
            # 日志和任务窗口：各占一半宽度
            with Container():
                with Vertical():
                    yield Static("📋 日志", classes="window-title")
                    yield RichLog(id="log", auto_scroll=True)
                with Vertical():
                    yield Static("✅ 任务", classes="window-title")
                    yield RichLog(id="tasks", auto_scroll=False)
        yield Footer()

    def _send_to_ui(self, panel: str, message: str):
        """
        向 UI 发送消息
        
        根据消息类型更新不同的 UI 面板
        
        参数：
        - panel: str - 目标面板（"chat" 或 "log"）
        - message: str - 要发送的消息
        """
        # 直接更新 UI
        if panel == "chat":
            # 检查是否是清空打字指示器的消息
            if message == "__clear_typing__":
                # 清空打字指示器
                typing_indicator = self.query_one("#typing-indicator", Static)
                typing_indicator.update("")
            # 检查是否是打字机效果的消息（带有 __typing__ 前缀）
            elif message.startswith("__typing__"):
                # 更新打字指示器
                typing_indicator = self.query_one("#typing-indicator", Static)
                typing_text = message[len("__typing__"):]
                typing_indicator.update(typing_text)
            else:
                # 对于正常消息，使用 write() 方法
                chat_log = self.query_one("#chat", RichLog)
                chat_log.write(message)
        elif panel == "log":
            log_log = self.query_one("#log", RichLog)
            log_log.write(message)

    def on_mount(self):
        """
        应用挂载时的初始化操作
        
        根据 record 参数决定是否启动录屏、运行 AgentCore 主循环、模拟用户输入、设置任务刷新间隔
        """
        # 根据 record 参数决定是否开始录屏
        if self.record:
            print("🎬 应用启动，开始录屏...")
            self.start_recording()
        # 使用 Textual 的 run_worker 启动任务
        self.run_worker(self.agent.run_main_loop(self.input_queue))
        self.run_worker(self._simulate_user_input)
        # 设置任务刷新间隔
        self.set_interval(1.0, self._refresh_tasks)
    
    def on_unmount(self):
        """
        应用卸载时的清理操作
        
        停止录屏，确保资源正确释放
        """
        # 只在启用录屏时停止
        if self.record:
            print("🎬 应用即将退出，停止录屏...")
            self.stop_recording()

    def start_recording(self):
        """
        开始录屏
        """
        print("🎬 尝试开始录屏...")
        if not self.is_recording:
            self.is_recording = True
            self.recording_frames = []
            print("🎬 创建录屏线程...")
            self.recording_thread = threading.Thread(target=self._record_terminal)
            self.recording_thread.daemon = True
            self.recording_thread.start()
            print("🎬 录屏线程已启动")
        else:
            print("🎬 录屏已经在进行中")
    
    def stop_recording(self):
        """
        停止录屏并生成视频
        """
        if self.is_recording:
            self.is_recording = False
            if self.recording_thread:
                self.recording_thread.join(timeout=2)
            self._generate_video()
            print("🎬 录屏完成，视频已生成")
    
    def _record_terminal(self):
        """
        录制整个屏幕
        """
        import mss
        import cv2
        import numpy as np
        import time
        
        print("🎬 开始录制整个屏幕...")
        
        with mss.mss() as sct:
            # 获取主屏幕
            monitor = sct.monitors[1]
            screen_width = monitor["width"]
            screen_height = monitor["height"]
            print(f"🎬 屏幕分辨率: {screen_width}x{screen_height}")
            
            while self.is_recording:
                try:
                    # 截图整个屏幕
                    screenshot = sct.grab(monitor)
                    frame = np.array(screenshot)
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                    
                    # 保存帧
                    self.recording_frames.append(frame)
                    
                    # 控制帧率
                    time.sleep(self.screenshot_interval)
                except Exception as e:
                    print(f"❌ 录屏错误: {e}")
                    break
        
        print(f"🎬 录制结束，共捕获 {len(self.recording_frames)} 帧")
    
    def _generate_video(self):
        """
        生成视频文件
        """
        if not self.recording_frames:
            print("❌ 没有录制到帧")
            return
        
        import cv2
        from datetime import datetime
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = f"terminal_demo_{timestamp}.mp4"
        
        # 获取帧大小
        height, width, _ = self.recording_frames[0].shape
        
        # 创建视频 writer
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        out = cv2.VideoWriter(output_file, fourcc, 10, (width, height))
        
        # 写入帧
        for frame in self.recording_frames:
            out.write(frame)
        
        # 释放资源
        out.release()
        
        print(f"🎬 视频已保存为: {output_file}")

    async def _simulate_user_input(self):
        """
        模拟用户输入
        
        按时间顺序生成模拟用户指令，模拟真实用户的一天使用场景
        """
        # 模拟真实用户的指令序列，按时间从早到晚排列
        utterances = [
            # 早上
            "早上好",  # 闲聊
            "你好啊",  # 闲聊
            "今天天气怎么样？",  # 信息查询
            "把空调调到24度",  # 车辆控制
            "调整座椅到舒适位置",  # 车辆控制
            "打开全景天窗",  # 车辆控制
            "播放一些轻音乐",  # 媒体控制
            "导航到北京市朝阳区建国路88号",  # 导航
            "避开拥堵路线到公司",  # 导航
            
            # 上午/中午
            "调高音量",  # 媒体控制
            "今天的新闻摘要",  # 信息查询
            "最近的餐厅推荐",  # 信息查询
            "最近的停车场在哪里？",  # 导航
            "关闭所有车窗",  # 车辆控制
            "切换到摇滚模式",  # 媒体控制
            
            # 下午
            "你能做什么？",  # 闲聊
            "附近的咖啡店",  # 信息查询
            "下一首歌曲",  # 媒体控制
            "帮我导航去最近的加油站",  # 导航
            "把温度调低2度",  # 车辆控制
            "暂停音乐",  # 媒体控制
            
            # 傍晚
            "今天心情怎么样？",  # 闲聊
            "去机场的最佳路线是什么？",  # 导航
            "明天北京的天气",  # 信息查询
            "打开车窗",  # 车辆控制
            "播放我喜欢的歌单",  # 媒体控制
            "给我讲个笑话",  # 闲聊
            
            # 晚上
            "关闭空调",  # 车辆控制
            "谢谢",  # 闲聊
            "晚安"  # 闲聊
        ]
        
        for utt in utterances:
            if not self.agent.running:
                break
            await self.input_queue.put(utt)
            # 随机等待时间，增加真实感
            await asyncio.sleep(random.uniform(1.0, 2.0))
        # 模拟输入完成后保持运行，等待用户手动退出
        print("模拟输入完成，按 q 或 ESC 退出程序")

    def _refresh_tasks(self):
        """
        刷新任务状态
        
        更新任务窗口显示的任务状态信息
        """
        if self.agent.running:
            summary = self.agent.get_all_tasks_summary()
            tasks_view = self.query_one("#tasks", RichLog)
            tasks_view.clear()
            tasks_view.write(summary)

    def action_inject_input(self):
        """
        按 'i' 触发输入
        """
        if self.inject_input_widget is None:
            self.inject_input_widget = Input(
                placeholder="请输入模拟语音指令...",
                id="inject-input"
            )
            self.inject_input_widget.focus()
            self.mount(self.inject_input_widget, before="#main-container")

            async def handle_submit(value: str):
                if value.strip():
                    await self.input_queue.put(value.strip())
                await self.inject_input_widget.remove()
                self.inject_input_widget = None
            
            self.inject_input_widget.on_submit = handle_submit

    def action_refresh_tasks(self):
        """
        按 's' 刷新
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
        """.strip()
        self._send_to_ui("log", "\n" + "="*50)
        self._send_to_ui("log", help_text)
        self._send_to_ui("log", "="*50)

    def action_quit(self):
        """
        按 'q' 或 'ESC' 退出
        """
        # 只在启用录屏时停止
        if self.record:
            print("🎬 用户按下退出键，停止录屏...")
            self.stop_recording()
        self.agent.running = False
        self.exit("用户退出")

# 创建 Typer 应用
cli_app = typer.Typer()

@cli_app.command()
def main(record: bool = False):
    """
    智能驾舱模拟器
    """
    if record:
        print("🎬 录屏功能已启用")
    else:
        print("🎬 录屏功能已禁用")
    
    demo_app = AgentUI(record=record)
    demo_app.run()

if __name__ == "__main__":
    cli_app()

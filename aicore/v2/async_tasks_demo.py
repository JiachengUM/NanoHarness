import asyncio
from rich import print
import uuid
import time
import random
from enum import Enum, StrEnum
from typing import Optional, Any, Dict
from pydantic import BaseModel, Field

# 颜色映射配置
class ColorMap(StrEnum):
    ENVIRONMENT = "blue"
    SESSION = "green"
    TASK = "yellow"
    VOICE = "cyan"
    CAR = "magenta"
    USER = "white"
    PLANNER = "bright_blue"
    ERROR = "red"
    WARNING = "orange"
    CLIENT = "bright_green"

# ==========================================
# 1. 基础数据结构 (Pydantic Models)
# ==========================================
class ChannelType(str, Enum):
    VOICE = "voice"
    CAR_CONTROL = "car_ctl"
    UI_UPDATE = "ui"

class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    FINISHED = "finished"
    FAILED = "failed"

class TaskDefinition(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    intent: str
    params: Dict[str, Any]
    created_at: float = Field(default_factory=time.time)

class OutputMessage(BaseModel):
    msg_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str
    channel: ChannelType
    payload: Any
    seq_id: int
    timestamp: float = Field(default_factory=time.time)

# ==========================================
# 2. 核心组件 (基础设施)
# ==========================================
class InternalEventBus:
    def __init__(self):
        self._queues: Dict[ChannelType, list[asyncio.Queue]] = {}
        
    def subscribe(self, channel: ChannelType) -> asyncio.Queue:
        q = asyncio.Queue()
        if channel not in self._queues:
            self._queues[channel] = []
        self._queues[channel].append(q)
        return q

    async def publish(self, message: OutputMessage):
        if message.channel in self._queues:
            for q in self._queues[message.channel]:
                await q.put(message)

class TaskManager:
    def __init__(self, event_bus: InternalEventBus):
        self.event_bus = event_bus
        # 存储 task_id -> (task_object, task_definition) 以便查询
        self.active_tasks: Dict[str, tuple[asyncio.Task, TaskDefinition]] = {}
        self._seq_counter = 0

    def get_next_seq(self) -> int:
        self._seq_counter += 1
        return self._seq_counter

    def register_task(self, task_def: TaskDefinition, coro: Any):
        task = asyncio.create_task(self._run_wrapper(task_def, coro))
        self.active_tasks[task_def.task_id] = (task, task_def)
        # 任务完成后自动清理
        task.add_done_callback(lambda t: self.active_tasks.pop(task_def.task_id, None))

    def cancel_task_by_id(self, task_id: str):
        if task_id in self.active_tasks:
            task, _ = self.active_tasks[task_id]
            if not task.done():
                print(f"[{ColorMap.TASK}][TaskManager] Cancelling task {task_id}...[/{ColorMap.TASK}]")
                task.cancel()
                return True
        return False

    async def _run_wrapper(self, task_def: TaskDefinition, coro: Any):
        try:
            await coro
        except asyncio.CancelledError:
            print(f"[{ColorMap.TASK}][Task cancelled] {task_def.task_id} ({task_def.intent})[/{ColorMap.TASK}]")
            # 发送取消通知
            await self.event_bus.publish(OutputMessage(
                task_id=task_def.task_id,
                channel=ChannelType.VOICE,
                payload="操作已取消。",
                seq_id=self.get_next_seq()
            ))
        except Exception as e:
            print(f"[{ColorMap.ERROR}][Task failed] {task_def.task_id}: {e}[/{ColorMap.ERROR}]")

# ==========================================
# 3. 环境模拟器 (独立生产者)
# ==========================================
class Environment:
    def __init__(self, input_queue: asyncio.Queue):
        self.input_queue = input_queue
        self.command_pool = [
            "打开空调", "关闭空调", 
            "导航去公司", "导航去机场", 
            "播放周杰伦", "播放流行音乐", 
            "取消导航", "今天天气怎么样"
        ]

    async def run(self, session_id: str):
        print(f"[{ColorMap.ENVIRONMENT}][Environment] started for {session_id}...[/{ColorMap.ENVIRONMENT}]")
        try:
            for cmd in self.command_pool:
                # 随机等待 0.5~2 秒模拟真实输入间隔
                wait_time = random.uniform(0.5, 2)
                await asyncio.sleep(wait_time)
                
                print(f"[{ColorMap.USER}][User] says: '{cmd}'[/{ColorMap.USER}]")
                await self.input_queue.put(cmd)
            
            # 遍历完成后发送结束标记
            await self.input_queue.put(None)
            print(f"[{ColorMap.ENVIRONMENT}][Environment] finished for {session_id}[/{ColorMap.ENVIRONMENT}]")
        except Exception as e:
            print(f"[{ColorMap.ERROR}][Environment error]: {e}[/{ColorMap.ERROR}]")
            # 异常情况下也发送结束标记，避免Session无限等待
            await self.input_queue.put(None)

# ==========================================
# 4. 会话上下文 (消费者)
# ==========================================
class UserSession:
    def __init__(self, session_id: str, input_queue: asyncio.Queue):
        self.session_id = session_id
        self.event_bus = InternalEventBus()
        self.task_manager = TaskManager(self.event_bus)
        self.is_active = True
        # 接收外部注入的队列
        self.user_input_queue = input_queue
        
        # --- 新增：暴露输出队列给客户端 ---
        # 这里我们模拟“建立连接”时，把服务端的管道交给客户端
        self.voice_queue = self.event_bus.subscribe(ChannelType.VOICE)
        self.car_control_queue = self.event_bus.subscribe(ChannelType.CAR_CONTROL)

    async def run(self):
        print(f"[{ColorMap.SESSION}][Session] {self.session_id} started.")
        
        # 启动规划循环
        try:
            await self._planning_loop()
        except Exception as e:
            print(f"[{ColorMap.ERROR}][Session crashed]: {e}[/{ColorMap.ERROR}]")
        finally:
            self.is_active = False
            print(f"[{ColorMap.SESSION}][Session] {self.session_id} ended.[/{ColorMap.SESSION}]")

    # 为了节省篇幅，这里省略中间未修改的方法，保持原样即可
    async def _planning_loop(self):
        while self.is_active:
            cmd = await self.user_input_queue.get()
            # 收到结束标记，退出循环
            if cmd is None:
                print(f"[{ColorMap.SESSION}][Session] {self.session_id} received end signal[/{ColorMap.SESSION}]")
                # 取消所有正在运行的任务
                for task_id in list(self.task_manager.active_tasks.keys()):
                    self.task_manager.cancel_task_by_id(task_id)
                break

            # 1. 处理控制类指令 (如取消)
            if "取消导航" in cmd:
                target_id = self._find_task_id_by_intent("nav")
                if target_id:
                    self.task_manager.cancel_task_by_id(target_id)
                else:
                    print(f"[{ColorMap.WARNING}][Warning] 没有找到正在运行的导航任务[/{ColorMap.WARNING}]")
                continue

            # 2. 正常意图识别
            task_def = None
            if "空调" in cmd:
                task_def = TaskDefinition(intent="ac", params={"action": "toggle"})
            elif "导航" in cmd:
                dest = "公司" if "公司" in cmd else ("机场" if "机场" in cmd else "未知地点")
                task_def = TaskDefinition(intent="nav", params={"dest": dest})
            elif "音乐" in cmd:
                task_def = TaskDefinition(intent="music", params={"query": cmd})
            elif "天气" in cmd:
                task_def = TaskDefinition(intent="weather", params={"loc": "本地"})
            
            if task_def:
                print(f"[{ColorMap.PLANNER}][Planner] Dispatching task [{task_def.intent}]...[/{ColorMap.PLANNER}]")
                worker_coro = self._create_task_worker(task_def)
                self.task_manager.register_task(task_def, worker_coro)

    def _find_task_id_by_intent(self, target_intent: str) -> Optional[str]:
        for task_id, (task_obj, task_def) in self.task_manager.active_tasks.items():
            if task_def.intent == target_intent and not task_obj.done():
                print(f"[{ColorMap.PLANNER}][Planner] Found target task {task_id} for intent '{target_intent}'[/{ColorMap.PLANNER}]")
                return task_id
        return None

    async def _create_task_worker(self, task_def: TaskDefinition):
        seq_id = self.task_manager.get_next_seq()
        if task_def.intent == "ac":
            await asyncio.sleep(0.5) # 快任务
            await self.event_bus.publish(OutputMessage(
                task_id=task_def.task_id, channel=ChannelType.CAR_CONTROL,
                payload={"cmd": "SET_AC", "val": "ON"}, seq_id=seq_id
            ))
        elif task_def.intent == "nav":
            await asyncio.sleep(3.0) # 慢任务
            await self.event_bus.publish(OutputMessage(
                task_id=task_def.task_id, channel=ChannelType.VOICE,
                payload=f"好的，正在规划去{task_def.params['dest']}的路线。", seq_id=seq_id
            ))
            await self.event_bus.publish(OutputMessage(
                task_id=task_def.task_id, channel=ChannelType.CAR_CONTROL,
                payload={"cmd": "START_NAV", "dest": task_def.params['dest']}, seq_id=seq_id + 1
            ))
        elif task_def.intent == "music":
            await asyncio.sleep(1.5) # 中速任务
            await self.event_bus.publish(OutputMessage(
                task_id=task_def.task_id, channel=ChannelType.CAR_CONTROL,
                payload={"cmd": "PLAY", "content": task_def.params['query']}, seq_id=seq_id
            ))
        elif task_def.intent == "weather":
            await asyncio.sleep(1.0)
            await self.event_bus.publish(OutputMessage(
                task_id=task_def.task_id, channel=ChannelType.VOICE,
                payload="今天天气晴朗，气温25度。", seq_id=seq_id
            ))

# ==========================================
# === CLIENT SIMULATION === (新增部分)
# ==========================================
class SimulatedClient:
    def __init__(self, client_id: str, voice_queue: asyncio.Queue, car_queue: asyncio.Queue):
        self.client_id = client_id
        self.voice_queue = voice_queue
        self.car_queue = car_queue
        self.is_running = True

    async def start_listening(self):
        """客户端启动，开始监听两个“网络通道”"""
        print(f"[{ColorMap.CLIENT}][Client {self.client_id}] Connected and listening...[/{ColorMap.CLIENT}]")
        
        # 同时监听两个通道
        await asyncio.gather(
            self._listen_voice(),
            self._listen_car_control()
        )

    async def _listen_voice(self):
        """模拟语音通道：收到消息就“播放”"""
        while self.is_running:
            msg = await self.voice_queue.get()
            print(f"[{ColorMap.CLIENT}][Client {self.client_id}] 🗣️ PLAYING VOICE: '{msg.payload}' (Task: {msg.task_id})[/{ColorMap.CLIENT}]")

    async def _listen_car_control(self):
        """模拟车控通道：收到消息就“执行”"""
        while self.is_running:
            msg = await self.car_queue.get()
            print(f"[{ColorMap.CLIENT}][Client {self.client_id}] 🚗 EXECUTING: {msg.payload} (Task: {msg.task_id})[/{ColorMap.CLIENT}]")

# ==========================================
# 5. 主程序入口
# ==========================================
async def main():
    # 1. 创建独立的输入队列 (用户指令输入)
    queue_a = asyncio.Queue()
    queue_b = asyncio.Queue()

    # 2. 创建会话
    # 注意：UserSession 初始化时会自动创建内部的 event_bus，
    # 并通过 voice_queue/car_control_queue 属性暴露给外部（模拟网络连接）
    session_a = UserSession("user_A", queue_a)
    session_b = UserSession("user_B", queue_b)

    # 3. 创建环境 (生产者)
    env_a = Environment(queue_a)
    env_b = Environment(queue_b)

    # 4. --- 新增：创建模拟客户端 ---
    # 客户端连接到 Session 暴露出来的 Queue (模拟连接到服务器)
    client_a = SimulatedClient("Client_A", session_a.voice_queue, session_a.car_control_queue)
    client_b = SimulatedClient("Client_B", session_b.voice_queue, session_b.car_control_queue)

    # 5. 并发运行：环境、会话、客户端都在跑
    # 注意：这里不需要再启动 UserSession 内部的 Listener，因为现在由外部 Client 处理
    # (你原来的 UserSession 里有 asyncio.create_task(...)，为了演示清晰，建议注释掉那两行，
    # 或者保留它们，你会看到消息被打印两遍，证明服务端也可以自己处理，客户端也能收到)
    await asyncio.gather(
        env_a.run("user_A"),
        env_b.run("user_B"),
        session_a.run(),
        session_b.run(),
        client_a.start_listening(), # 客户端 A 开始监听
        client_b.start_listening()  # 客户端 B 开始监听
    )

if __name__ == "__main__":
    asyncio.run(main())
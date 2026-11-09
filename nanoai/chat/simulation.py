import copy
import itertools
import contextlib
from typing import Protocol, runtime_checkable, Generator, AsyncGenerator

import colorama
import hashlib
import shutil
import json
import re
from pathlib import Path
from tqdm import tqdm

from nanoai.model.llm import RunResultStream, RunResultStreamAsync

from nanoai.chat.define import ChatAgentProfile, ChatTask
# from nanoai.chat.manager import ChatManager
from nanoai.chat.worker import ChatWorker, SimulatedChatUser
from nanoai.chat.conversation import Conversation, Round

from nanoai.utils.nl_repr import nl_repr

# work around。暂时不import ChatManager，但保持这个class的定义。
ChatManager = ChatWorker

# 初始化 colorama
colorama.init(autoreset=True)


__all__ = [
    "MockedChatUser",
    "RealChatUser",
    "gen_chat",
    "agen_chat",
    "gen_chat_with_nl",
    "agen_chat_with_nl",
]

@runtime_checkable
class PChatUser(Protocol):
    """聊天用户的统一接口协议。"""

    @property
    def name(self) -> str:
        """返回用户名称。"""
        ...

    def execute(self, input: str, /,) -> str:
        """执行用户响应，返回用户输入。"""
        ...

    async def aexecute(self, input: str, /,) -> str:
        """异步版本"""
        ...


    @contextlib.contextmanager
    def execute_stream(self, input: str, delta: bool) -> Generator[RunResultStream, None, None]:
        """流式输出的版本"""
        ...

    @contextlib.asynccontextmanager
    async def aexecute_stream(self, input: str, delta: bool) -> AsyncGenerator[RunResultStreamAsync, None]:
        """异步版本"""
        ...

@runtime_checkable
class PChatAgent(PChatUser, Protocol):
    """聊天用户的统一接口协议。"""

    @property
    def status_full(self) -> str:
        ...

    def details(self) -> list[str]:
        ...

    def intro(self) -> str:
        ...

    def terminated(self) -> bool:
        ...

class MockedChatUser:
    """返回预定义好的用户输入。"""

    def __init__(self, inputs: list[str]):
        self.inputs = copy.deepcopy(inputs)

        # 无限循环inputs中的内容
        self.input_iter = itertools.cycle(self.inputs)

    @property
    def name(self) -> str:
        return "mocked用户"

    def execute(self, assistant_res: str) -> str:
        return next(self.input_iter)
    
    async def aexecute(self, assistant_res: str) -> str:
        return next(self.input_iter)


class RealChatUser:
    """返回实时的用户输入。"""

    def __init__(self, name: str = "实时用户"):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def execute(self, assistant_res: str) -> str:
        return input(f"{self.name}: ")
    
    async def aexecute(self, assistant_res: str) -> str:
        return input(f"{self.name}: ")


def execute_and_print(
        worker: PChatUser, 
        input_msg: str,
        /,
        *,
        round_num: int, 
        stream: bool, 
        color: str, 
        name: str,
        verbose: bool = True,
    ) -> str:
    """执行任务并根据verbose参数决定是否打印结果
    
    支持三种类型的worker：
    1. ChatWorker/ChatManager: 支持流式输出和简单输出
    2. ChatUser: 只支持简单输出（调用execute方法）
    
    Args:
        worker: 要执行的工作器
        input_msg: 输入消息
        round_num: 当前轮数
        stream: 是否启用流式输出
        color: 输出颜色
        name: 工作器名称
        verbose: 是否打印输出，默认True
    """
    # 检查是否支持流式输出：1. 是PChatAgent类型 2. 配置启用stream
    stream = (
        hasattr(worker, "execute_stream")
        and stream
    )

    if not stream:
        # 简单输出：适用于ChatUser类型或不支持流式输出的ChatWorker/ChatManager
        result = worker.execute(input_msg)
        if verbose:
            print(f"{color}(R{round_num}){name}: {result}")
        return result

    if verbose:
        print(f"{color}(R{round_num}){name}: ", end="", flush=True)
        with worker.execute_stream(input_msg, delta=True) as stream_result:
            for chunk in stream_result:
                print(f"{color}{chunk}", end="", flush=True)
        print()
    else:
        # 非详细模式下，仍然需要执行流式输出以获取结果，但不打印
        with worker.execute_stream(input_msg, delta=True) as stream_result:
            for chunk in stream_result:
                pass  # 消费所有chunk但不打印

    assert stream_result is not None
    return stream_result.output


async def aexecute_and_print(
        worker: PChatUser, 
        input_msg: str,
        /,
        *,
        round_num: int, 
        stream: bool, 
        color: str, 
        name: str,
        verbose: bool = True,
    ) -> str:
    """异步版本"""
    # 检查是否支持流式输出：1. 是ChatWorker/ChatManager类型 2. 配置启用stream
    stream = (
        hasattr(worker, "aexecute_stream")
        and stream
    )

    if not stream:
        # 简单输出：适用于ChatUser类型或不支持流式输出的ChatWorker/ChatManager
        result = await worker.aexecute(input_msg)
        if verbose:
            print(f"{color}(R{round_num}){name}: {result}")
        return result

    if verbose:
        print(f"{color}(R{round_num}){name}: ", end="", flush=True)
        async with worker.aexecute_stream(input_msg, delta=True) as stream_result:
            async for chunk in stream_result:
                print(f"{color}{chunk}", end="", flush=True)
        print()
    else:
        # 非详细模式下，仍然需要执行流式输出以获取结果，但不打印
        async with worker.aexecute_stream(input_msg, delta=True) as stream_result:
            async for chunk in stream_result:
                pass  # 消费所有chunk但不打印

    assert stream_result is not None
    return stream_result.output


def _create_user(user_repr: PChatUser | list[str] | None) -> PChatUser:
    if user_repr is None:
        return RealChatUser()
    elif isinstance(user_repr, list):
        return MockedChatUser(user_repr)
    else:
        # assert isinstance(user_repr, PChatUser), f"user_repr必须是PChatUser类型，而不是{type(user_repr)}"
        return user_repr


def gen_chat(
    ass_worker: PChatAgent,
    user_repr: PChatUser | list[str] | None = None,
    /,
    *,
    max_rounds: int = 5,
    stream: bool = True,
    user_clr: str = colorama.Fore.BLUE,
    assistant_clr: str = colorama.Fore.RED,
    status_clr: str = colorama.Fore.YELLOW,
    show_status: bool = True,
    verbose: bool = True,
) -> tuple[Conversation, PChatUser]:
    """构造对话数据
    
    这个函数提供了一个完整的命令行聊天界面，支持：
    1. 自动创建不同类型的用户（真实用户、模拟用户、预定义输入列表）
    2. 多轮对话循环，支持流式和非流式输出
    3. 彩色输出，区分用户和助手的消息
    4. 对话历史记录和状态显示
    5. 可选的详细输出模式和进度条显示
    
    Args:
        ass_worker: 助手工作器，负责生成AI回复
        user_repr: 用户表示，可以是：
            - None: 创建真实用户（需要手动输入）
            - list[str]: 预定义的用户输入列表
            - ChatWorker: 模拟用户工作器
        max_rounds: 最大对话轮数，默认5轮
        stream: 是否启用流式输出，默认True
        user_clr: 用户消息的颜色，默认蓝色
        assistant_clr: 助手消息的颜色，默认红色
        show_status: 是否显示最终状态，默认True
        verbose: 是否显示详细输出，默认True。False时只显示进度条和关键信息
    
    Returns:
        tuple: (对话历史, 用户对象)
            - 对话历史: QAList格式的对话记录
            - 用户对象: 创建的用户实例
    
    Example:
        # 使用预定义输入列表进行对话
        conversation, user = run_chat_cli(
            assistant_worker, 
            ["Hello", "How are you?"], 
            max_rounds=2
        )
        
        # 使用真实用户进行交互式对话
        conversation, user = run_chat_cli(assistant_worker)
        
        # 静默模式，只显示进度条
        conversation, user = run_chat_cli(assistant_worker, verbose=False)
    """
    
    user = _create_user(user_repr)

    assistant_msg = ass_worker.intro()
    if verbose:
        print(f"\n============={ass_worker.name}和{user.name}的对话开始。=============")
        print(f"{assistant_clr}{ass_worker.name}: {assistant_msg}")

    # 步骤4: 执行多轮对话循环
    conversation = Conversation()
    
    # 创建进度条（非详细模式时使用）
    pbar = None
    if not verbose:
        pbar = tqdm(total=max_rounds, desc="对话进度", unit="轮")
    
    for round_num in range(1, max_rounds + 1):
        # 更新进度条描述（非详细模式）
        if not verbose and pbar:
            pbar.set_description(f"对话轮数 {round_num}/{max_rounds}")
        
        # 执行用户对话
        user_msg = execute_and_print(
            user, 
            assistant_msg,
            round_num=round_num,
            stream=stream,
            color=user_clr,
            name=user.name,
            verbose=verbose,
        )
        # 获取用户状态
        if hasattr(user, "status_full"):
            user_status = user.status_full
        else:
            user_status = "无状态"
        if verbose:
            print(f"{status_clr}{user.name} status: {user_status}")
        
        # 执行助手对话
        assistant_msg = execute_and_print(
            ass_worker, 
            user_msg,
            round_num=round_num,
            stream=stream,
            color=assistant_clr,
            name=ass_worker.name,
            verbose=verbose,
        )
        # 获取助手状态
        assistant_status = ass_worker.status_full
        if verbose:
            print(f"{status_clr}{ass_worker.name} status: {assistant_status}")
        
        # 添加到对话历史
        conversation.append(Round(
            message_a=user_msg,
            think_a=user_status,            
            message_b=assistant_msg,
            think_b=assistant_status
        ))
        
        # 非详细模式：更新进度条
        if pbar:
            pbar.update(1)
        
        # 检查是否提前终止
        if ass_worker.terminated():
            if pbar:
                pbar.set_description(f"对话完成 (轮数 {round_num}/{max_rounds})")
            break

    # 步骤5: 显示最终状态
    if show_status and verbose:
        print(f"{assistant_clr}{ass_worker.name}的详细状态:")
        print("\n".join(ass_worker.details()))
        
        # 如果用户也支持details方法，显示用户状态
        if hasattr(user, "details"):
            print(f"{user_clr}{user.name}的详细状态:")
            print("\n".join(user.details()))
    elif show_status and not verbose:
        # 非详细模式下，只显示简要状态
        print(f"✅ 对话完成，共 {len(conversation)} 轮")

    return conversation, user


async def agen_chat(
    ass_worker: PChatAgent,
    user_repr: PChatUser | list[str] | None = None,
    /,
    *,
    max_rounds: int = 5,
    stream: bool = True,
    user_clr: str = colorama.Fore.BLUE,
    assistant_clr: str = colorama.Fore.RED,
    status_clr: str = colorama.Fore.YELLOW,
    show_status: bool = True,
    verbose: bool = True,
) -> tuple[Conversation, PChatUser]:
    """异步版本"""
    
    user = _create_user(user_repr)

    assistant_msg = ass_worker.intro()
    if verbose:
        print(f"\n============={ass_worker.name}和{user.name}的对话开始。=============")
        print(f"{assistant_clr}{ass_worker.name}: {assistant_msg}")

    # 步骤4: 执行多轮对话循环
    conversation = Conversation()
    
    # 创建进度条（非详细模式时使用）
    pbar = None
    if not verbose:
        pbar = tqdm(total=max_rounds, desc="对话进度", unit="轮")
    
    for round_num in range(1, max_rounds + 1):
        # 更新进度条描述（非详细模式）
        if not verbose and pbar:
            pbar.set_description(f"对话轮数 {round_num}/{max_rounds}")
        
        # 执行用户对话
        user_msg = await aexecute_and_print(
            user, 
            assistant_msg,
            round_num=round_num,
            stream=stream,
            color=user_clr,
            name=user.name,
            verbose=verbose,
        )
        # 获取用户状态
        if hasattr(user, "status_full"):
            user_status = user.status_full
        else:
            user_status = "无状态"
        if verbose:
            print(f"{status_clr}{user.name} status: {user_status}")
        
        # 执行助手对话
        assistant_msg = await aexecute_and_print(
            ass_worker, 
            user_msg,
            round_num=round_num,
            stream=stream,
            color=assistant_clr,
            name=ass_worker.name,
            verbose=verbose,
        )
        # 获取助手状态
        assistant_status = ass_worker.status_full
        if verbose:
            print(f"{status_clr}{ass_worker.name} status: {assistant_status}")
        
        # 添加到对话历史
        conversation.append(Round(
            message_a=user_msg,
            think_a=user_status,            
            message_b=assistant_msg,
            think_b=assistant_status
        ))
        
        # 非详细模式：更新进度条
        if pbar:
            pbar.update(1)
        
        # 检查是否提前终止
        if ass_worker.terminated():
            if pbar:
                pbar.set_description(f"对话完成 (轮数 {round_num}/{max_rounds})")
            break

    # 步骤5: 显示最终状态
    if show_status and verbose:
        print(f"{assistant_clr}{ass_worker.name}的详细状态:")
        print("\n".join(ass_worker.details()))
        
        # 如果用户也支持details方法，显示用户状态
        if isinstance(user, (ChatWorker, ChatManager)) and hasattr(user, "details"):
            print(f"{user_clr}{user.name}的详细状态:")
            print("\n".join(user.details()))
    elif show_status and not verbose:
        # 非详细模式下，只显示简要状态
        print(f"✅ 对话完成，共 {len(conversation)} 轮")

    return conversation, user


def generate_cache_key(
        scenario: str, 
        user_info: str | None, 
        topic: str | None) -> str:
    """生成缓存键，scenario作为前缀，user_info和topic生成哈希"""
    
    # 处理 None 值并清理特殊字符
    def clean_string(s: str | None) -> str:
        if s is None:
            return ""
        # 只保留字母、数字、下划线、中文字符
        return re.sub(r'[^\w\u4e00-\u9fff]', '_', s)
    
    clean_user_info = clean_string(user_info)
    clean_topic = clean_string(topic)
    
    # 组合user_info和topic生成哈希
    content = f"{clean_user_info}_{clean_topic}"
    
    # 如果内容为空，使用默认值
    if not content or content == "_":
        content = "default"
    
    # 生成MD5哈希
    hash_key = hashlib.md5(content.encode('utf-8')).hexdigest()[:12]
    
    # scenario作为前缀，哈希作为后缀
    return f"{scenario}_{hash_key}"


def _get_cache_paths(
        db_dir: str, 
        scenario: str,
        user_info: str | None, 
        topic: str | None) -> tuple[Path, Path, Path, Path]:
    """获取缓存相关的路径"""
    cache_key = generate_cache_key(scenario, user_info, topic)
    cache_dir = Path(db_dir) / cache_key
    assistant_file = cache_dir / "assistant.json"
    user_file = cache_dir / "user.json"
    conversation_file = cache_dir / "conversation.json"
    return cache_dir, assistant_file, user_file, conversation_file


def load_worker_state(
        assistant: ChatWorker, 
        user: SimulatedChatUser, 
        db_dir: str, 
        scenario: str,
        user_info: str | None, 
        topic: str | None) -> bool:
    """从数据库加载assistant和user的状态，失败时不作任何处理"""
    
    cache_dir, assistant_file, user_file, conversation_file = _get_cache_paths(db_dir, scenario, user_info, topic)
    
    if not (cache_dir.exists() and assistant_file.exists() and user_file.exists()):
        print(f"❌ 缓存文件不存在: {cache_dir}")
        return False
    
    try:
        # 加载assistant状态（就地修改）
        with open(assistant_file, 'r', encoding='utf-8') as f:
            assistant.load_state(json.load(f))
        
        # 加载user状态（就地修改）
        with open(user_file, 'r', encoding='utf-8') as f:
            user.load_state(json.load(f))
        
        print(f"✅ 从缓存加载worker state成功: {cache_dir}")
        return True
        
    except Exception as e:
        print(f"❌ 从缓存加载worker state失败: {e}")
        return False


def save_worker_state(
        assistant: ChatWorker, 
        user: SimulatedChatUser, 
        conversation: Conversation,
        db_dir: str, 
        scenario: str,
        user_info: str | None, 
        topic: str | None) -> tuple[bool, str]:
    """保存assistant、user的状态和对话记录到数据库
    
    Returns:
        tuple: (是否成功, 缓存目录路径 or 错误信息)
    """
    cache_dir, assistant_file, user_file, conversation_file = _get_cache_paths(db_dir, scenario, user_info, topic)
    
    try:
        # 创建目标目录
        cache_dir.mkdir(parents=True, exist_ok=True)
        
        # 保存assistant状态
        assistant_state = assistant.save_state()
        with open(assistant_file, 'w', encoding='utf-8') as f:
            json.dump(assistant_state, f, ensure_ascii=False, indent=2)
        
        # 保存user状态
        user_state = user.save_state()
        with open(user_file, 'w', encoding='utf-8') as f:
            json.dump(user_state, f, ensure_ascii=False, indent=2)
        
        # 使用Conversation类的to_json方法保存对话记录
        conversation.to_json(str(conversation_file))
        
        # 保存对话为HTML文件
        html_file = cache_dir / "conversation.html"
        conversation.to_html(
            filename=str(html_file),
            title=f"对话记录 - {scenario}",
            scenario=scenario,
            user_info=user_info or "未知用户",
            topic=topic or "未知主题",
            styling={
                "theme_color": "linear-gradient(135deg, #6c757d 0%, #adb5bd 100%)",
                "container_width": "100%",
                "chat_width": "95%",
                "min_width": "600px"
            },
            name_a=user.name,
            name_b=assistant.name,
        )
        
        return True, str(cache_dir)
        
    except Exception as e:
        # 如果发生任何异常，删除整个缓存目录
        if cache_dir.exists():
            shutil.rmtree(cache_dir)
        return False, str(e)
    

def _create_assistant_and_user(
        task: str | ChatTask,
        user_info: str,
        topic: str,
        *,
        verbose: bool = True,
    ) -> tuple[ChatWorker, SimulatedChatUser]:
    
    if isinstance(task, str):
        task = ChatTask(brief=task, agent_profile=ChatAgentProfile(name="助手", role="助手"))

    assert isinstance(task, ChatTask), "task必须是ChatTask对象"

    assert isinstance(user_info, str), f"user_info必须是str，而不是{type(user_info)}"
    assert isinstance(topic, str), f"topic必须是str，而不是{type(topic)}"
    
    if verbose:
        print(f"任务描述: {nl_repr(task)}")
        print(f"用户信息: {user_info}")
        print(f"对话主题: {topic}")
        print()
    
    assistant = ChatWorker(task)
    if verbose:
        print(f"\n✅ 助手创建完成:\n{nl_repr(assistant.details())}")
    

    # 这里如果create_user为True，则需要考虑以async模式执行。
    user = SimulatedChatUser(user_info, topic=topic)
    if verbose:
        print(f"\n✅ 模拟用户创建完成:\n{nl_repr(user.details())}")

    return assistant, user


def gen_chat_with_nl(
        task: str | ChatTask,
        user_info: str,
        topic: str,
        *,
        max_rounds: int = 5,
        verbose: bool = True,
        save_dir: str | None = None,
        scenario: str = "",
        ) -> tuple[ChatWorker, SimulatedChatUser, Conversation]:
    """通过自然语言描述，生成对话数据。是gen_chat的封装。好用很多。
    
    Args:
        task: 任务描述
        user_info: 用户信息
        topic: 对话主题
        gen_task: 当task_desc为str时，是否使用AI生成任务，默认False。为True时，生成的对话数据效果可能好一些。但需要验证和对比。
        max_rounds: 最大对话轮数，默认5轮
        verbose: 是否显示详细输出。
        save_dir: 保存对话的目录。如果为None，则不保存。
        scenario: 对话场景描述。和save_dir共同决定保存对话的目录。不太重要，仅仅用于目录名好读和缓存键生成，但放到外面也不太合适。
    """

    assistant, user = _create_assistant_and_user(task, user_info, topic, verbose=verbose)
    
    # load_worker_state(assistant, user, save_dir, scenario, user_info, topic)
    # 还没实现完，在run_chat_cli需要能延续之前的msg
        
    conversation, _ = gen_chat(assistant, user, max_rounds=max_rounds, verbose=verbose)

    if save_dir is not None and scenario is not None:
        # assistant和user的状态有更新，保存到缓存
        success, cache_dir = save_worker_state(assistant, user, conversation, save_dir, scenario, user_info, topic)
    
        if success:
            if verbose:
                print(f"✅ 保存assistant、user状态和对话记录到缓存成功: {cache_dir}")
        else:
            # 错误信息总是显示，无论verbose设置
            print(f"❌ 保存到缓存失败, 错误信息: {cache_dir}")

    return assistant, user, conversation


async def agen_chat_with_nl(
        task: str | ChatTask,
        user_info: str,
        topic: str,
        *,
        max_rounds: int = 5,
        verbose: bool = True,
        save_dir: str | None = None,
        scenario: str = "",
        ) -> tuple[ChatWorker, SimulatedChatUser, Conversation]:
    """异步版本"""

    assistant, user = _create_assistant_and_user(task, user_info, topic, verbose=verbose)
    
    # load_worker_state(assistant, user, save_dir, scenario, user_info, topic)
    # 还没实现完，在run_chat_cli需要能延续之前的msg
        
    conversation, _ = await agen_chat(assistant, user, max_rounds=max_rounds, verbose=verbose)

    if save_dir is not None and scenario is not None:
        # assistant和user的状态有更新，保存到缓存
        success, cache_dir = save_worker_state(assistant, user, conversation, save_dir, scenario, user_info, topic)
    
        if success:
            if verbose:
                print(f"✅ 保存assistant、user状态和对话记录到缓存成功: {cache_dir}")
        else:
            # 错误信息总是显示，无论verbose设置
            print(f"❌ 保存到缓存失败, 错误信息: {cache_dir}")

    return assistant, user, conversation

"""记忆增强的聊天Worker，继承ChatWorker并集成记忆功能"""

from typing import Any, Generator
from contextlib import contextmanager, asynccontextmanager

from nanoai.chat.worker import ChatWorker
from nanoai.model.llm import RunResultStream
from nanoai.utils.nl_repr import nl_repr
from .memory_manager import MemoryManager
from .core_memory import CoreMemory, MemoryBlock


class MemoryChatWorker(ChatWorker):
    """带有记忆功能的聊天工作器"""
    def __init__(self, task: str, /, batch_size: int = 10, enable_llm_analysis: bool = True):
        super().__init__(task)
        
        # 调用私有初始化方法
        self._init_memory_system(batch_size, enable_llm_analysis)
    
    def _init_memory_system(self, batch_size: int, enable_llm_analysis: bool):
        """初始化记忆系统"""
        # 总是使用默认的记忆块
        self.core_memory = CoreMemory(blocks=[
            MemoryBlock(
                label="persona", 
                value="智能助手，致力于为用户提供准确、简洁、个性化的帮助。",
                description="AI助手的角色定位"
            ),
            MemoryBlock(
                label="user_facts", 
                value="",
                description="用户基础人物事实：身份信息、昵称、说话风格等，永久留存无需重复确认"
            ),
            MemoryBlock(
                label="preferences", 
                value="",
                description="用户偏好：历史偏好、推荐内容，增强'懂我'感"
            ),
            MemoryBlock(
                label="behavior_patterns", 
                value="",
                description="用户行为习惯：常用操作、偏好设置、个性响应模式"
            )
        ])
        
        # 创建MemoryManager，传入CoreMemory实例
        self.memory_manager = MemoryManager(
            core_memory=self.core_memory,
            batch_size=batch_size,
            enable_llm_analysis=enable_llm_analysis
        )

    def _think(self, input: str) -> str:
        """重写思考过程，简单集成记忆上下文"""
        # 保存原始输入，用于后续存储到messages中
        original_input = input
        
        # 增强用户输入，添加记忆上下文
        memory_summary = self.core_memory.compile_to_prompt()
        if memory_summary.strip():
            # 使用nl_repr将记忆上下文转换为自然语言，并调换位置
            enhanced_input = f"{input}\n\n记忆上下文：{nl_repr(memory_summary)}"
        else:
            enhanced_input = input
        
        # 调用父类的思考过程，传入增强后的输入
        enhanced_input = super()._think(enhanced_input)
        
        # 重要：将原始输入存储到worker中，确保messages中只包含原始输入
        self._original_input_for_messages = original_input
        
        return enhanced_input

    def execute(self, input: str, /) -> str:
        """重写执行方法，确保记忆更新"""
        # 保存原始输入用于记忆更新
        original_input = input
        
        # 调用父类的execute方法
        result = super().execute(input)
        
        # 重要：确保messages中存储的是原始输入
        if hasattr(self, '_original_input_for_messages') and self._original_input_for_messages:
            if self._result and self._result.messages:
                # 找到最后一条用户消息并替换为原始输入
                for msg in reversed(self._result.messages):
                    if msg['role'] == 'user':
                        msg['content'] = self._original_input_for_messages
                        break
            # 清理临时变量
            delattr(self, '_original_input_for_messages')
        
        # 在对话完成后，添加对话到记忆历史并分析
        self.memory_manager.add_conversation(original_input, result)
        
        return result
    
    async def aexecute(self, input: str, /) -> str:
        """重写异步执行方法，确保记忆更新"""
        # 保存原始输入用于记忆更新
        original_input = input
        
        # 调用父类的aexecute方法
        result = await super().aexecute(input)
        
        # 重要：确保messages中存储的是原始输入
        if hasattr(self, '_original_input_for_messages') and self._original_input_for_messages:
            if self._result and self._result.messages:
                # 找到最后一条用户消息并替换为原始输入
                for msg in reversed(self._result.messages):
                    if msg['role'] == 'user':
                        msg['content'] = self._original_input_for_messages
                        break
            # 清理临时变量
            delattr(self, '_original_input_for_messages')
        
        # 在对话完成后，添加对话到记忆历史并分析
        self.memory_manager.add_conversation(original_input, result)
        
        return result

    @contextmanager
    def execute_stream(self, input: str, delta: bool) -> Generator[RunResultStream, None, None]:
        """重写流式执行，确保记忆更新"""
        # 保存原始输入用于记忆更新
        original_input = input
        
        # 使用父类的流式执行
        with super().execute_stream(input, delta) as stream_result:
            yield stream_result
            
            # 在流式输出完成后，更新记忆
            if stream_result.output:
                self.memory_manager.add_conversation(original_input, stream_result.output)
    
    @asynccontextmanager
    async def aexecute_stream(self, input: str, delta: bool) -> Generator[RunResultStream, None, None]:
        """重写异步流式执行，确保记忆更新"""
        # 保存原始输入用于记忆更新
        original_input = input
        
        # 使用父类的异步流式执行
        async with super().aexecute_stream(input, delta) as stream_result:
            yield stream_result
            
            # 重要：确保messages中存储的是原始输入
            if hasattr(self, '_original_input_for_messages') and self._original_input_for_messages:
                if self._result and self._result.messages:
                    # 找到最后一条用户消息并替换为原始输入
                    for msg in reversed(self._result.messages):
                        if msg['role'] == 'user':
                            msg['content'] = self._original_input_for_messages
                            break
                # 清理临时变量
                delattr(self, '_original_input_for_messages')
            
            # 在流式输出完成后，更新记忆
            if stream_result.output:
                self.memory_manager.add_conversation(original_input, stream_result.output)
    
    def save_state(self) -> dict[str, Any]:
        """重写状态保存，包含记忆状态"""
        # 获取父类状态
        state_dict = super().save_state()
        
        # 添加CoreMemory状态
        state_dict["core_memory"] = self.core_memory.model_dump()
        
        # 添加MemoryManager状态
        state_dict["memory_manager"] = self.memory_manager.save_state()
        
        return state_dict
    
    def load_state(self, state: dict[str, Any]):
        """重写状态加载，包含记忆状态"""
        # 加载父类状态
        super().load_state(state)
        
        # 加载CoreMemory状态
        if "core_memory" in state:
            self.core_memory = CoreMemory.model_validate(state["core_memory"])
        
        # 加载MemoryManager状态
        if "memory_manager" in state:
            self.memory_manager.load_state(state["memory_manager"])

    
    def get_memory_summary(self) -> str:
        """获取记忆摘要"""
        return self.core_memory.compile_to_prompt()
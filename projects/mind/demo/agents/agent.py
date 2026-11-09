"""
智能驾舱助手核心逻辑模块

该模块实现了智能驾舱助手的核心业务逻辑，包括：
1. 意图分类：识别用户指令的意图类型
2. 聊天功能：处理用户的闲聊和问答
3. 流式响应：生成逐字输出的响应，提升用户体验

核心组件：
- AgentBase：智能驾舱助手核心类
- chat_stream_dummy：模拟聊天响应生成器
- ChatCallback：聊天回调函数类型定义

使用场景：
- 作为智能驾舱助手的核心处理单元
- 被Runner调用处理具体的业务逻辑
"""

from typing import AsyncGenerator

from aicore.models.chat import ChatParams, astream
from aicore.models.credentials import create_client, ModelName, AsyncArk
from projects.mind.demo.task.types import IntentCategory
from projects.mind.intent.alg.simple import IntentClassifierLLM, ResponseParams
from projects.mind.demo.agents.intent import KeywordBasedIntentClassifier
from projects.mind.demo.task import TaskType, Task


async def chat_stream_dummy(prompt: str) -> AsyncGenerator[str, None]:
    """
    模拟聊天响应生成器
    
    生成模拟的聊天响应，逐字输出，模拟真实的聊天体验
    
    参数：
    - prompt: str - 用户输入的文本
    
    返回：
    - AsyncIterator[str] - 异步可迭代对象，逐字生成响应文本
    """
    # 生成完整的响应文本
    full_response = f"🤖 回复: {prompt}。很高兴为您服务！"
    
    # 模拟思考时间
    import asyncio
    await asyncio.sleep(0.3)
    
    # 逐字生成响应，模拟打字效果
    for char in full_response:
        yield char  # 输出单个字符
        await asyncio.sleep(0.05)  # 每个字符之间的延迟
    
    # 打字完成后的停顿
    await asyncio.sleep(0.5)

class AgentBase:
    """
    智能驾舱助手核心逻辑类
    
    负责处理用户指令、生成流式响应等核心业务逻辑。
    专注于具体功能实现，不负责运行时管理。
    
    属性说明：
    - chat_dummy: bool - 是否使用模拟聊天模式
    - client: AsyncArk - 模型客户端
    - model: 模型实例
    - model_params: ChatParams - 模型参数
    - _intent_classifier: 意图分类器实例
    """
    
    def __init__(
        self,
        /,
        *,
        chat_dummy: bool = False,
        intent_dummy: bool = False,
        intent_categories: list[IntentCategory],
        ): 
        """
        初始化 AgentBase 实例
        
        参数：
        - chat_dummy: bool - 是否使用模拟聊天模式，默认 False
        - intent_dummy: bool - 是否使用模拟意图分类模式，默认 False
        - intent_categories: list[IntentCategory] - 意图分类列表
        """
        # 保存聊天模式设置
        self.chat_dummy = chat_dummy
        
        # 创建聊天模型客户端和实例
        self.client, self.model = create_client(ModelName.SEED_1_8_251228, AsyncArk)
        
        # 设置模型参数，禁用思考过程
        self.model_params = ChatParams(thinking = {"type": "disabled"})
        
        # 初始化意图分类器
        if intent_dummy:
            # 使用基于关键词的简单意图分类器
            self._intent_classifier = KeywordBasedIntentClassifier(intent_categories)
        else:
            # 使用基于LLM的意图分类器
            params = ResponseParams(thinking={"type": "disabled"})
            intent_client, intent_model = create_client(
                ModelName.SEED_1_6_FLASH_250828, 
                AsyncArk
            )
            
            self._intent_classifier = IntentClassifierLLM(
                intent_categories,
                model=intent_model,
                client=intent_client,
                params=params,
            )

    async def _intent_cls(self, query: str) -> str:
        """
        意图分类方法
        
        识别用户输入的意图类型
        
        参数：
        - query: str - 用户输入的文本
        
        返回：
        - str - 识别出的意图类别
        """
        # 调用意图分类器进行分类
        category, _ = await self._intent_classifier.arun(query)
        return category


    async def _chat(self, prompt: str) -> AsyncGenerator[str, None]:
        """
        处理聊天任务
        
        生成流式响应，供调用者消费
        
        参数：
        - prompt: str - 用户指令内容
        
        返回：
        - AsyncGenerator[str, None] - 异步生成器，逐字生成聊天响应
        """
        if self.chat_dummy:
            async for chunk in chat_stream_dummy(prompt):
                yield chunk
        else:
            async for chunk in await astream(
                prompt,
                client=self.client,
                model=self.model,
                params=self.model_params,
            ):
                yield chunk


    async def run(self, query: str) -> AsyncGenerator[str | Task, None]:
        task_type = await self._intent_cls(query)
        
        if task_type == TaskType.OTHER:
            # 对于 OTHER 类型（闲聊），流式输出聊天内容
            async for chunk in self._chat(query):
                yield chunk
            return
            
        # 对于具体任务类型，提交后台任务
        assert task_type in TaskType, f"未知任务类型: {task_type}"

        # 创建任务对象
        task = Task(task_type=TaskType(task_type), prompt=query)
        yield task

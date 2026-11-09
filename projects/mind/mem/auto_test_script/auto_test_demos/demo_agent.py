from jinja2 import Template
from langchain.agents import create_agent
from langchain_core.runnables import RunnableConfig
from langchain_core.tools.base import BaseTool
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, Field

from projects.mind.mem.auto_test_script.langchain_models import doubao_model
from projects.mind.mem.auto_test_script.utils import (
    convert_langchain_history_to_volc_format,
    convert_tools_to_tools_info,
)
from projects.mind.mem.benchi_demo.prompt import STEWARD_PROMPT
from aicore.agents.experiments.volc_memory_store import VolcMemoryStore

class StewardSystemPromptTemplate(BaseModel):
    """
    被测的管家的系统提示词渲染器
    """
    user_profile: str = Field(default="无用户信息", description="用户的基本信息文本，默认值为空字符串")
    memory: str = Field(default="无任何信息", description="用户的记忆文本，默认值为空字符串")
    event_memory: str = Field(
        default="无任何事件", description="用户的事件记忆文本，默认值为空字符串")
    car_state: str = Field(default="无车辆当前状态信息",
                           description="车辆状态信息文本，默认值为空字符串")
    tools_info: str = Field(default="无工具", description="工具信息文本，默认值为空字符串")
    prompt_template: str = Field(
        default=STEWARD_PROMPT, description="系统提示文本的渲染模板，默认值为STEWARD_PROMPT")

    def render(self) -> str:
        """
        渲染系统提示文本
        """
        return Template(self.prompt_template).render(
            user_profile=self.user_profile,
            memory=self.memory,
            event_memory=self.event_memory,
            car_state=self.car_state,
            tools_info=self.tools_info,
        )

class StewardChatbot:
    """管家聊天机器人"""
    def __init__(self, store: VolcMemoryStore, vehicle_state_str: str, user_profile: str = "无用户信息", memory_types: list[str] = ["steward_note_book"], memory_limit: int = 10, event_type: str = "event_v1", event_limit: int = 10, tools: list = [], checkpointer: BaseCheckpointSaver = InMemorySaver(), model: ChatOpenAI = doubao_model, tools_info: str | None = None):
        self.model: ChatOpenAI = model
        self.checkpointer: BaseCheckpointSaver = checkpointer  # 短期记忆，其实就是多轮对话记录
        self.store: VolcMemoryStore = store  # 火山长期记忆
        self.memory_types: list[str] = memory_types  # 这个机器人用到的记忆类型
        self.memory_limit: int = memory_limit  # 这个机器人用到记忆时的召回限制数量
        self.event_type: str = event_type  # 这个机器人直接用到事件，这是其使用的事件类型
        self.event_limit: int = event_limit  # 这个机器人用到事件时的召回限制数量
        self.user_profile: str = user_profile  # 这个机器人直接用到的用户信息字符串
        self.vehicle_state_str: str = vehicle_state_str  # 这个机器人直接用到的车辆状态字符串
        self.system_prompt: str | None = None
        self.tools: list[BaseTool] = tools  # 这个机器人使用的工具
        self.tools_info : str | None = tools_info
        self.steward_system_prompt_template: StewardSystemPromptTemplate = StewardSystemPromptTemplate()
        self.session_id: str | None = None  # 当前这轮多轮对话的唯一标识
        self.steward_agent: CompiledStateGraph | None = None  # 实例化的机器人

    def _reset_system_prompt(self):
        """
        重置管家的system prompt
        """
        self.steward_system_prompt_template.user_profile = self.user_profile
        self.steward_system_prompt_template.memory = self.store.get_profile_memory_str(
            profile_type=self.memory_types, limit=self.memory_limit)
        self.steward_system_prompt_template.event_memory = self.store.get_event_memory_str(
            event_type=self.event_type, limit=self.event_limit)
        # self.steward_system_prompt_template.event_memory = "无"
        self.steward_system_prompt_template.car_state = self.vehicle_state_str
        if self.tools_info is not None:
            self.steward_system_prompt_template.tools_info = self.tools_info
        else:
            self.steward_system_prompt_template.tools_info = convert_tools_to_tools_info(
            self.tools)
        self.system_prompt = self.steward_system_prompt_template.render()

    def _compile_steward_agent(self):
        """
        利用测试用例信息创建一个对应的可对话的虚拟人实例
        """
        self.steward_agent = create_agent(
            model=self.model,
            checkpointer=self.checkpointer,
            tools=self.tools,
            system_prompt=self.system_prompt
        )

    def print_history(self):
        from nanoai.utils.nl_repr import nl_repr
        old_config = {"configurable": {"thread_id": self.session_id}}
        history = list(self.steward_agent.get_state_history(old_config))[
            0].values["messages"]
        assert history
        volc_history = convert_langchain_history_to_volc_format(history)
        print("!"*100)
        print(nl_repr(volc_history))
        print("!"*100)

    def print_memory(self):
        print(self.store.get_profile_memory_str(
            profile_type=self.memory_types, limit=self.memory_limit))
        print(self.store.get_event_memory_str(
            event_type=self.event_type, limit=self.event_limit))

    def chat(self, query: str, session_id: str) -> str:
        """
        管家聊天bot，输入用户查询，返回管家的回复
        Args:
            query (str): 最新的用户的一句话
            session_id (str): 对话会话ID，用于唯一标识一次多轮对话
        Returns:
            str: 管家的回复
        """
        # 同一个用户新进行了一轮对话的话，触发把上次对话的对话记录送到火山形成新的记忆的机制
        if self.steward_agent is None:
            self._reset_system_prompt()
            self._compile_steward_agent()
        assert self.steward_agent is not None
        if self.session_id is not None and self.session_id != session_id:
            # 把上次的对话记录送到火山形成记忆
            # 从agent中获取还未更新的上一次对话（self.session_id还未更新）的对话记录
            old_config = {"configurable": {"thread_id": self.session_id}}
            history = list(self.steward_agent.get_state_history(old_config))[
                0].values["messages"]
            assert history
            volc_history = convert_langchain_history_to_volc_format(history)
            # 上传记忆，火山会自动形成新的记忆，记忆抽取prompt在火山控制台看，可在控制台设置你要自定义抽取的记忆及其抽取prompt
            self.store.add_history_to_memory(volc_history, wait_seconds=30)
            print("开始新的一次多轮对话~~~~~~~~~~~~~~~~~~~~")
            self._reset_system_prompt()
            self._compile_steward_agent()
            self.session_id = session_id
        elif self.session_id is None:
            print("开始新的一次多轮对话~~~~~~~~~~~~~~~~~~~~")
            self.session_id = session_id
        config: RunnableConfig = {
            "configurable": {"thread_id": self.session_id}}
        response = self.steward_agent.invoke(
            {"messages": query}, config=config)
        return response["messages"][-1].content

import asyncio
import datetime
import time
import re
import uuid
from tqdm import tqdm
from jinja2 import Template
from langchain.agents import create_agent
from langchain.messages import AIMessage, HumanMessage, SystemMessage
from langchain.tools import tool
from langchain_core.messages.base import BaseMessage
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import InMemorySaver
from pydantic import BaseModel
from nanoai.utils.nl_repr import nl_repr
from nanoai.model.config import ARK_API_KEY_FOR_1_8, ARK_BASE_URL, ModelName,DMX_API_KEY,DMX_BASE_URL,DMX_MODEL_CLAUDE_OPUS_4_5,DMX_MODEL_GPT5_2,DMX_MODEL_GEMINI,DMX_MODEL_QWEN_MAX
from projects.mind.mem.benchi_demo.test_complex_reasoning_memory import (
    MEMORY_COLLECTION_NAME,
    FAKE_RESTURANT_INFO_LIST_1,
    FAKE_RESTURANT_INFO_LIST_2,
    MEMORY_LIMIT,
    add_to_memory
)
from projects.mind.mem.volc_api import (
    MemoryFilter,
    Message,
    SearchMemory,
    search_memory
)
from projects.mind.mem.volc_api.memory import BatchDeleteEvent,BatchDeleteProfile,batch_delete_event,batch_delete_profile,BatchDeleteEventFilter,BatchDeleteProfileFilter
from projects.mind.mem.volc_api.retrieval import search_event_memory,SearchEventMemory,EventMemoryFilter
from prompt import STEWARD_PROMPT, VEHICLE_STATE_PROMPT,FAKE_DRIVER_PROFILE_TEMPLATE,JUDGE_PROMPT


MEMORY_USER_ID = "dzy"
MEMORY_TYPES = ["steward_note_book"]

doubao_model = ChatOpenAI(
    model=ModelName.DOUBAO_SEED_1_8_PREVIEW,
    base_url=ARK_BASE_URL,
    api_key=ARK_API_KEY_FOR_1_8,
)

qwen_model = ChatOpenAI(
    model=DMX_MODEL_QWEN_MAX,
    base_url=DMX_BASE_URL,
    api_key=DMX_API_KEY,
)

claude_model = ChatOpenAI(
    model=DMX_MODEL_CLAUDE_OPUS_4_5,
    base_url=DMX_BASE_URL,
    api_key=DMX_API_KEY,
)

gpt_model = ChatOpenAI(
    model=DMX_MODEL_GPT5_2,
    base_url=DMX_BASE_URL,
    api_key=DMX_API_KEY,
)

gemini_model = ChatOpenAI(
    model=DMX_MODEL_GEMINI,
    base_url=DMX_BASE_URL,
    api_key=DMX_API_KEY,
)

class MemoryTestCase(BaseModel):
    id: str
    user_id: str = MEMORY_USER_ID
    vehicle_state: str = VEHICLE_STATE_PROMPT
    system_prompt: str = STEWARD_PROMPT
    max_round: int = 8
    user_query_lists: list[list[str]] = []
    expected_dialogue: str
    case_description: str

@tool(description="参数location输入“前滩”或者“外滩”，搜索这两个地点的餐厅")
def search_restaurant(location: str) -> list[dict[str, str]]:
    """假的搜索餐厅函数，根据地点返回餐厅信息"""
    if location == "前滩":
        return FAKE_RESTURANT_INFO_LIST_1
    elif location == "外滩":
        return FAKE_RESTURANT_INFO_LIST_2
    else:
        return FAKE_RESTURANT_INFO_LIST_1


tool_names = [search_restaurant.name]
tools = [search_restaurant]
tools_info_str = "\n".join(["工具名称：" + tool.name + " 工具描述：" + tool.description for tool in tools])


# @dataclass
# class ResponseFormat:
#     """Response schema for the agent."""
#     answer: str
# memory: str

class StewardChatbot:
    def __init__(self, vehicle_state_str: str, user_id: str, model:ChatOpenAI = doubao_model):
        self.model = model
        self.user_id = user_id # 司机，助手，裁判需要共享一个user_id下的记忆
        self.memory_str = self._get_memory_str()
        self.vehicle_state_str = vehicle_state_str
        self.event_memory_str = self._get_event_memory_str()
        prompt = Template(STEWARD_PROMPT).render(
            memory=self.memory_str,
            event_memory=self.event_memory_str,
            car_state=self.vehicle_state_str,
            tools=tools_info_str,
        )
        self.system_prompt = prompt
        self.tools = [search_restaurant]
        # self.response_format = ToolStrategy(ResponseFormat)
        self.checkpointer = InMemorySaver()
        self.agent = create_agent(
            model=self.model,
            system_prompt=self.system_prompt,
            tools=self.tools,
            # response_format=self.response_format,
            checkpointer=self.checkpointer
        )
        self.chat_id = None

    def _refresh_memory(self, new_memory_str: str, new_event_memory_str: str) -> None:
        """
        刷新管家聊天bot的记忆，输入用户查询
        """
        self.memory_str = new_memory_str
        self.event_memory_str = new_event_memory_str

    def _reset_system_prompt(self) -> None:
        """
        重置管家聊天bot的系统提示
        """
        prompt = Template(STEWARD_PROMPT).render(
            memory=self.memory_str,
            event_memory=self.event_memory_str,
            car_state=self.vehicle_state_str,
            tools=tools_info_str,
        )
        # print("+"*80)
        # print(self.system_prompt)
        # print("+"*80)
        self.system_prompt = prompt
        self.agent = create_agent(
            model=self.model,
            system_prompt=self.system_prompt,
            tools=self.tools,
            # response_format=self.response_format,
            checkpointer=self.checkpointer
        )

    def _change_user_id(self, new_user_id: str) -> None:
        """
        改变管家聊天bot的用户ID
        """
        self.user_id = new_user_id

    def _get_memory_str(self, query: str | None = None) -> str:
        """
        获取管家聊天bot的记忆字符串
        """
        search_request = SearchMemory(
            collection_name=MEMORY_COLLECTION_NAME,
            query=query,
            limit=MEMORY_LIMIT,
            filter=MemoryFilter(memory_type=MEMORY_TYPES, user_id=self.user_id)
        )
        # 将同步的 search_memory 调用放到线程池中执行，避免阻塞事件循环
        memory = search_memory(search_request)
        memory_str = nl_repr(
            [item.memory_info for item in memory.data.result_list])
        # print("*" * 80)
        # print(f"用户最新记忆：\n{memory_str}")
        return memory_str

    def _get_event_memory_str(self) -> str:
        """
        获取管家聊天bot的事件记忆字符串
        """
        search_request = SearchEventMemory(
            collection_name=MEMORY_COLLECTION_NAME,
            limit=5,
            filter=EventMemoryFilter(memory_type="event_v1", user_id=self.user_id)
        )
        event_memory = search_event_memory(search_request)
        event_memory_str = "\n".join([str(item.memory_info["summary"]) for item in event_memory.data.result_list])
        # print("*" * 80)
        # print(f"用户最新事件记忆：\n{event_memory_str}")
        return event_memory_str

    def _convert_langchain_history_to_volc_format(self, history: list[BaseMessage]) -> list[Message]:
        """
        将langchain的对话记录转换为火山的对话记录格式
        """
        volc_history = []
        for message in history:
            if isinstance(message, HumanMessage):
                role = "user"
                volc_history.append(
                    Message(role=role, content=message.content))
            elif isinstance(message, AIMessage) and message.content != "":
                role = "assistant"
                volc_history.append(
                    Message(role=role, content=message.content))
            elif isinstance(message, SystemMessage):
                role = "system"
                volc_history.append(
                    Message(role=role, content=message.content))
            else:
                continue
        return volc_history

    def chat(self, query: str, chat_id: str) -> str:
        """
        管家聊天bot，输入用户查询，返回管家的回复
        """
        # 同一个用户新进行了一轮对话的话，触发把上次对话的对话记录送到火山形成新的记忆的机制
        if self.chat_id is not None and self.chat_id != chat_id:
            # 把上次的对话记录送到火山形成记忆
            # 从agent中获取还未更新的上一次对话（self.chat_id还未更新）的对话记录
            old_config = {"configurable": {"thread_id": self.chat_id}}
            history = list(self.agent.get_state_history(old_config))[0].values["messages"]
            assert history
            volc_history = self._convert_langchain_history_to_volc_format(history)
            # 上传记忆，火山会自动形成新的记忆，记忆抽取prompt在火山控制台看，可在控制台设置你要自定义抽取的记忆及其抽取prompt
            asyncio.run(add_to_memory(volc_history, user_id=self.user_id))
            # 等待20秒记忆抽取完毕生效
            print("等待记忆抽取生效...30秒")
            for _ in tqdm(range(30), desc="倒计时", unit="秒", ncols=75):
                time.sleep(1)
            print("等待记忆生成时间到！")
            print("开始新的一次多轮对话~~~~~~~~~~~~~~~~~~~~")
            self._refresh_memory(self._get_memory_str(), self._get_event_memory_str())
            self._reset_system_prompt()
            self.chat_id = chat_id
        elif self.chat_id is None:
            print("开始新的一次多轮对话~~~~~~~~~~~~~~~~~~~~")
            self.chat_id = chat_id
        config: RunnableConfig = {"configurable": {"thread_id": self.chat_id}}
        response = self.agent.invoke({"messages": query}, config=config)
        return response["messages"][-1].content

class FakeDriver:
    """
    模拟一个与车机助手对话的司机的bot
    """
    def __init__(self, vehicle_state_str: str, profile: str, user_id: str, max_round: int = 8, model: ChatOpenAI = doubao_model):
        self.model = model
        self.checkpointer = InMemorySaver()
        self.profile = profile
        self.user_id = user_id
        self.chat_id = None
        self.start_query = None
        self.memory_str = self._get_memory_str()
        self.vehicle_state_str = vehicle_state_str
        self.case : MemoryTestCase = None
        self.max_round = max_round
        self.system_prompt = None
        self.agent = None
        # self.history = []

    def set_case(self, case: MemoryTestCase) -> None:
        """
        设置假人聊天bot的场景
        """
        self.case = case

    def _convert_langchain_history_to_volc_format(self, history: list[BaseMessage]) -> list[Message]:
        """
        将langchain的对话记录转换为火山的对话记录格式
        """
        volc_history = []
        for message in history:
            if isinstance(message, HumanMessage):
                role = "user"
                volc_history.append(
                    Message(role=role, content=message.content))
            elif isinstance(message, AIMessage) and message.content != "":
                role = "assistant"
                volc_history.append(
                    Message(role=role, content=message.content))
            elif isinstance(message, SystemMessage):
                role = "system"
                volc_history.append(
                    Message(role=role, content=message.content))
            else:
                continue
        return volc_history

    def set_start_query(self, start_query: str) -> None:
        """
        设置假人聊天bot的开始查询
        """
        self.start_query = start_query

    def _reset_profile(self, profile: str):
        """
        重置假人聊天bot的profile
        """
        self.profile = profile

    def _get_memory_str(self, query: str | None = None) -> str:
        """
        获取假人聊天bot的记忆字符串
        """
        memory_types = ["profile_v1"]
        search_request = SearchMemory(
            collection_name=MEMORY_COLLECTION_NAME,
            query=query,
            limit=MEMORY_LIMIT,
            filter=MemoryFilter(memory_type=memory_types, user_id=self.user_id)
        )
        # 将同步的 search_memory 调用放到线程池中执行，避免阻塞事件循环
        memory = search_memory(search_request)
        memory_str = nl_repr([item.memory_info for item in memory.data.result_list])
        # print("*" * 80)
        # print(f"用户最新记忆：\n{memory_str}")
        return memory_str

    def _refresh_memory(self, new_memory_str: str) -> None:
        """
        刷新假人聊天bot的记忆，输入用户查询
        """
        self.memory_str = new_memory_str

    def _reset_system_prompt(self) -> None:
        """
        重置假人聊天bot的系统提示
        """
        assert self.case is not None, "请先设置场景case"
        prompt = Template(self.profile).render(
            memory=self.memory_str,
            car_state=self.vehicle_state_str,
            case_description=self.case.case_description,
            expected_dialogue=self.case.expected_dialogue,
            start_query=self.start_query,
            max_round=self.max_round
        )
        # print("+"*80)
        # print(self.system_prompt)
        # print("+"*80)
        self.system_prompt = prompt
        self.agent = create_agent(
            model=self.model,
            system_prompt=self.system_prompt,
            # response_format=self.response_format,
            checkpointer=self.checkpointer
        )

    def _change_user_id(self, new_user_id: str) -> None:
        """
        改变假人聊天bot的用户ID
        """
        self.user_id = new_user_id

    def chat(self, query: str, chat_id: str):
        """
        开始一个新的聊天对话，重置假人聊天bot的profile
        """
        if self.chat_id is not None and self.chat_id != chat_id:
            self.start_query = query
            self._refresh_memory(self._get_memory_str(query))
            self._reset_system_prompt()
            self.chat_id = chat_id
            # self.history = [{"role": "你", "content": self.start_query}]
        elif self.chat_id is None:
            self.chat_id = chat_id
            # self.history = [{"role": "你", "content": self.start_query}]
            self._refresh_memory(self._get_memory_str(query))
            self._reset_system_prompt()
        # self.history.append({"role": "助手", "content": query})
        # input_query = self.system_prompt + "\n\n" + "\n".join([f"{item['role']}: {item['content']}" for item in self.history]) + "\n你:"
        config: RunnableConfig = {"configurable": {"thread_id": self.chat_id}}
        response = self.agent.invoke({"messages": query}, config=config)
        return response["messages"][-1].content

def auto_chat_test(steward: StewardChatbot,fake_driver: FakeDriver, start_query: str, max_round: int = 8) -> tuple[int, list[dict]]:
    """以一句用户的话为引子，引发一段多轮对话，返回用户对本次服务的评分和对话历史"""
    # 注意测试时，在火山控制台确保MEMORY_USER_ID对应的记忆为空！！！否则有很多以前的记忆。
    chat_id = str(uuid.uuid4())
    assistant_answer = steward.chat(start_query, chat_id)
    history_for_judge = []
    print("+" * 80)
    print(f"假司机：{start_query}")
    history_for_judge.append({"role": "用户", "content": start_query})
    fake_driver_answer = ""
    now_round = 0
    while "退下" not in fake_driver_answer and now_round < max_round:
        print("-" * 80)
        print(f"管家：{assistant_answer}")
        history_for_judge.append({"role": "管家", "content": assistant_answer})
        print("+" * 80)
        fake_driver_answer = fake_driver.chat(assistant_answer, chat_id)
        print(f"假司机：{fake_driver_answer}")
        history_for_judge.append({"role": "用户", "content": fake_driver_answer})
        assistant_answer = steward.chat(fake_driver_answer, chat_id)
        now_round += 1
    if now_round >= max_round:
        print("超过最大轮数，对话不得不结束")
        history_for_judge.append({"role": "导演", "content": "你们超过最大对话次数啦！cut！"})
    score = parse_score(fake_driver_answer)
    return score, history_for_judge

class Judge:
    def __init__(self, model: ChatOpenAI, vehicle_state_str: str, user_id: str):
        self.model = model
        self.checkpointer = InMemorySaver()
        self.user_id = user_id
        self.memory_str = None
        self.judge_prompt = None
        self.vehicle_state_str = vehicle_state_str

    def _refresh_memory(self, new_memory_str: str) -> None:
        """
        刷新假人聊天bot的记忆，输入用户查询
        """
        self.memory_str = new_memory_str

    def _get_memory_str(self) -> str:
        """
        获取假人聊天bot的记忆字符串
        """
        memory_types = ["profile_v1"]
        search_request = SearchMemory(
            collection_name=MEMORY_COLLECTION_NAME,
            limit=MEMORY_LIMIT,
            filter=MemoryFilter(memory_type=memory_types, user_id=self.user_id)
        )
        # 将同步的 search_memory 调用放到线程池中执行，避免阻塞事件循环
        memory = search_memory(search_request)
        memory_str = nl_repr([item.memory_info for item in memory.data.result_list])
        # print("*" * 80)
        # print(f"用户最新记忆：\n{memory_str}")
        return memory_str

    def _reset_system_prompt(self, history_for_judge: str, case_description: str, expected_dialogue: str) -> None:
        """
        重置假人聊天bot的系统提示
        """
        prompt = Template(JUDGE_PROMPT).render(
            memory=self.memory_str,
            car_state=self.vehicle_state_str,
            history_for_judge=history_for_judge,
            case_description=case_description,
            expected_dialogue=expected_dialogue,
        )
        # print("+"*80)
        # print(self.system_prompt)
        # print("+"*80)
        self.judge_prompt = prompt
        # self.agent = create_agent(
        #     model=self.model,
        #     system_prompt=self.system_prompt,
        #     # response_format=self.response_format,
        #     checkpointer=self.checkpointer
        # )

    def _parse_judge_result_and_reason(self, judge_result: str) -> tuple[bool, str]:
        """
        解析判断结果字符串，返回判断结果和判断理由
        """
        
        match = re.search(r"result:\s*(Yes|No)\s*reason:\s*(.*)", judge_result, re.DOTALL)
        # 校验是否有2个match group
        assert match is not None, "judge_result格式错误，没有匹配到result和reason"
        if match:
            # 校验匹配结果
            result = match.group(1)
            assert result in ["Yes", "No"], "result不是Yes或No"
            if result == "Yes":
                return True, match.group(2).strip()
            else:
                return False, match.group(2).strip()
        return False, "No valid result or reason found"

    def judge(self, case: MemoryTestCase, history_for_judge: str) -> tuple[bool, str]:
        """
        对演员的互动记录进行判断，返回判断结果
        """
        self._refresh_memory(self._get_memory_str())
        self._reset_system_prompt(history_for_judge, case.case_description, case.expected_dialogue)
        chat_id = str(uuid.uuid4())
        config: RunnableConfig = {"configurable": {"thread_id": chat_id}}
        # 校验judge_prompt是否初始化成功
        assert self.judge_prompt is not None, "judge_prompt未初始化"
        response = self.model.invoke(self.judge_prompt, config=config)
        # 校验模型回复是否符合格式
        assert isinstance(response.content, str), "judge_result为空"
        result, reason = self._parse_judge_result_and_reason(response.content)
        return result, reason
    


def parse_score(query: str) -> int:
    """
    解析评分字符串，返回整数评分
    """
    # 从“谢谢，退下吧，我给你打X分”中提取X，并且校验分数是否在1-5分内，否则返回0
    match = re.search(r"我给你打(\d+)分", query)
    if match:
        score = int(match.group(1))
        if 1 <= score <= 5:
            return score
    return 0



def test_steward_chatbot(user_query_lists: list[list[str]]):
    """
    测试管家聊天机器人，输入是一个二维列表，每个子列表是一个用户的多轮对话用户侧的输入语句。也就是这个函数只不管管家回复，每次按顺序硬塞既定的用户回复给管家。
    """
    # 注意测试时，在火山控制台确保MEMORY_USER_ID对应的记忆为空！！！否则有很多以前的记忆。
    user_id = MEMORY_USER_ID
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    vehicle_state = Template(VEHICLE_STATE_PROMPT).render(
        current_time=current_time)
    steward = StewardChatbot(vehicle_state, user_id, doubao_model)
    for one_chat in user_query_lists:
        # 实际使用时，前端或者更外层决定是否给个代表新对话的chat_id
        chat_id = str(uuid.uuid4())
        for one_user_input in one_chat:
            response = steward.chat(one_user_input, chat_id)
            print("-" * 80)
            print(f"用户：{one_user_input}")
            print(f"管家：{response}")

def run_case(memory_test_cases: list[MemoryTestCase]):
    for case in memory_test_cases:
        test_steward_chatbot(case.user_query_lists)

def run_auto_chat_test_case(memory_test_cases: list[MemoryTestCase]):
    for case in memory_test_cases:
        # 让两个bot自由对话，所以只取第一句话启动就行
        score = auto_chat_test(case, case.user_query_lists[0][0])
        print(f"测试用例{case}的评分是{score}")

def clean_memory(user_id: str=MEMORY_USER_ID):
    # 清楚某个user_id的所有记忆和事件记忆
    a_batch_delete_event_filter = BatchDeleteEventFilter(user_id=user_id)
    a_batch_delete_profile_filter = BatchDeleteProfileFilter(user_id=user_id) # ,resource_id="mem-8472eb4c"
    batch_delete_event_param = BatchDeleteEvent(filter=a_batch_delete_event_filter,resource_id="mem-8472eb4c")
    batch_delete_profile_param = BatchDeleteProfile(filter=a_batch_delete_profile_filter,resource_id="mem-8472eb4c")
    batch_delete_event(batch_delete_event_param)
    batch_delete_profile(batch_delete_profile_param)

def run_full_auto_judge_test(memory_test_cases: list[MemoryTestCase], pause_mode: bool = False, memory_reset_mode: bool = False):
    user_id = MEMORY_USER_ID
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    vehicle_state = Template(VEHICLE_STATE_PROMPT).render(
        current_time=current_time)
    judge = Judge(doubao_model, vehicle_state, user_id)
    result = ""
    for case in memory_test_cases:
        if memory_reset_mode:
            # 如果希望先防止不同记忆间的干扰，可以打开这个记忆重置模式开关，这样每一个case开启测试前，会清空记忆。
            clean_memory()
        steward_model: ChatOpenAI = doubao_model
        fake_driver_model: ChatOpenAI = doubao_model
        history_for_judge = ""
        user_id = MEMORY_USER_ID
        max_round = 8
        current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        vehicle_state = Template(VEHICLE_STATE_PROMPT).render(current_time=current_time)
        steward = StewardChatbot(vehicle_state, user_id, steward_model)
        fake_driver = FakeDriver(vehicle_state,FAKE_DRIVER_PROFILE_TEMPLATE, user_id, max_round, fake_driver_model)
        fake_driver.set_case(case)
        for i,one_dialogue in enumerate(case.user_query_lists):
            fake_driver.set_start_query(one_dialogue[0])
            score, history = auto_chat_test(steward,fake_driver,one_dialogue[0], max_round)
            history_for_judge += f"第{i+1}次对话的记录：\n{nl_repr(history)}\n"
            print(f"第{i+1}次对话,用户的评分是{score}")
            if pause_mode:
                input("\n当前处于调试模式，每运行一个case中的一个多轮对话后均会暂停，以便查看记忆的生成状况。在下一次多轮对话结束时可以查看上一次多轮对话的记忆。\n\n\n按任意键继续本case内下一次多轮对话...")
        judge_result, judge_reason = judge.judge(case, history_for_judge.strip())
        print(f"导演意见：测试用例{case.id}的判断结果是{judge_result}，理由是{judge_reason}")
        result += f"导演意见：测试用例{case.id}的多次对话结果是:\n{history_for_judge}\n判断结果是{judge_result}\n理由是{judge_reason}\n\n"
        if pause_mode:
            input("\n当前处于调试模式，每运行一个case均会暂停，以便查看记忆的生成状况。\n每一个case运行前会清空记忆，所以你需要在下一个case运行前看看记忆生成情况。\n\n按任意键继续下一个测试用例...")
    return result

if __name__ == "__main__":
    case_1 = MemoryTestCase(
        id="1",
        user_query_lists=[
            [
                "记一下，我住在浦江镇",
            ]
            ,
            [
                "回家",
            ]
        ],
        expected_dialogue="""
        用户：记一下，我住在浦江镇。
        管家：好的，我记住了。
        ……（重启一轮新的对话）
        用户：回家。
        管家：好的，导航到浦江镇的住处。
        （预期管家能记住用户住在浦江镇，从而正确地导航到浦江镇的住处）
        """,
        case_description="这个场景是车内，用户和他的管家的两段对话。我们期望这个管家能够在用户第一次提到过自己住在哪儿后，在之后的对话中体现出管家确实记住了用户的住处。"
    )
    case_2 = MemoryTestCase(
        id="2",
        user_query_lists=[
        [
            "记一下，我住在浦江镇",
        ]
        ,
        [
            "我搬家了，搬到了前滩",
        ]
        ,
        [
            "回家"
        ]
    ],
        expected_dialogue="""
        用户：记一下，我住在浦江镇。
        管家：好的，我记住了。
        ……（重启一轮新的对话）
        用户：我搬家了，搬到了前滩。
        管家：好的，我记住了。
        ……（重启一轮新的对话）
        用户：回家。
        管家：好的，导航到前滩的住处。
        （预期管家能记住用户搬到了前滩，更新了自己的笔记本里记录的用户的现在搬家后的住处，从而正确地导航到前滩的住处）
        """,
        case_description="考察智能体是否能正确理解车主的家的地址变了并在记忆当中也改变对应的信息，且在最新的回家指令中体现出来。"
    )
    case_3 = MemoryTestCase(
        id="3",
        user_query_lists=[
        [
            "我想在前滩找一个餐厅。",
            "妈呀你当我是富二代啊？这么贵。我只吃得起人均不超过100的。",
            "好的，这个好，就去这里吧。",
        ]
        ,
        [
            "我想在外滩找一个餐厅。",
            "可以的，就去这里吧。"
        ]
    ],
        expected_dialogue="""
        用户：我想在前滩找一个餐厅。
        管家：给你找到如下两个餐厅：一个是甬府，人均800,4.5星，另一个是弄堂排骨餐厅，人均20块，4星。你看看哪个好。
        用户：妈呀你当我是富二代啊？这么贵。我只吃得起人均不超过100的。
        管家：不好意思，那就推荐您去弄堂排骨餐厅吧，性价比超高。
        用户：好的，这个好，就去这里吧。
        管家：好的，导航到弄堂排骨餐厅。
        ……（重启一轮新的对话）
        用户：我想在外滩找一个餐厅。
        管家：附近有一家人均200的大志烤肉和一家人均15的兰州拉面。以我对您的了解，性价比更高的兰州拉面更适合您。
        用户：好的，这个好，就去这里吧。
        管家：好的，导航到兰州拉面。
        （预期管家能记住曾经因为）
        """,
        case_description="测试用户记住住的位置，然后在不同位置找餐厅"
    )
    case_4 = MemoryTestCase(
        id="4",
        user_query_lists=[
        [
            "放一下《渡口》这个歌"
        ]
        ,
        [
            "放一下《好汉歌》这个歌"
        ]
        ,
        [
            "再放一下《生日快乐》这个歌"
        ]
        ,
        [
            "放一下上次那首歌。"
        ]
    ],
        expected_dialogue="""
        用户：放一下《渡口》这个歌
        管家：好的，播放歌曲《渡口》。
        ……（重启一轮新的对话）
        用户：放一下《好汉歌》这个歌
        管家：好的，播放歌曲《好汉歌》。
        ……（重启一轮新的对话）
        用户：再放一下《生日快乐》这个歌
        管家：好的，播放歌曲《生日快乐》。
        ……（重启一轮新的对话）
        用户：放一下上次放的那首歌。
        管家：好的，播放歌曲《生日快乐》。
        """,
        case_description="考察对过往记录型记忆的理解和分析"
    )
    # case_5 = [
    #     [
    #         "放一下《渡口》这个歌"
    #         ]
    #     ,
    #     [
    #         "放一下上次那首歌。"
    #     ]
    # ]
    case_6 = MemoryTestCase(
        id="6",
        user_query_lists=[
        [
            "打开空调到24度，不要直吹我。",
            "还是太低了，开到26度吧。"
        ]
        ,
        [
            "打开空调"
        ]
    ],
        expected_dialogue="""
        用户：打开空调到24度，不要直吹我。
        管家：好的，空调开到24度，避开吹人。
        用户：还是太低了，开到26度吧。
        管家：好的，空调开到26度。
        ……（重启一轮新的对话）
        用户：打开空调
        管家：好的，空调开到26度，避开吹人。
        """,
        case_description="考察是否能够综合当前环境温度，车内温度，用户喜好，给出合适的空调设置"
    )
    case_8 = MemoryTestCase(
        id="8",
        user_query_lists=[
        [
            "记一下，我外婆家在闵行区浦江镇。"
        ],
        [
            "带我去外婆家。",
            "不是我外婆家，是外婆家餐厅。",
        ],
        [
            "带我去外婆家。"
        ]
    ],
        expected_dialogue="""
        用户：记一下，我外婆家在闵行区浦江镇。
        管家：好的，我记住了。
        ……（重启一轮新的对话）
        用户：带我去外婆家。
        管家：好的，导航到闵行区浦江镇的外婆的住处。
        用户：不是我外婆家，是外婆家餐厅。
        管家：非常抱歉，是我的疏忽，搜索了附近外婆家餐厅，将导航到附近外婆家餐厅。
        ……（重启一轮新的对话）
        用户：带我去外婆家。
        管家：请问您是要去外婆家餐厅还是外婆的住处？
        """,
        case_description="考察智能体是否能自主使用记忆机制来提升自己的工作水平"
    )
    case_9 = MemoryTestCase(
        id="9",
        user_query_lists=[
        [
            "记一下，我住在浦江镇"
        ]
        ,
        [
            "我的住址太敏感了，你把它忘掉"
        ],
        [
            "我住在哪？"
        ]
    ],
        expected_dialogue="""
        用户：记一下，我住在浦江镇。
        管家：好的，我帮你记下了。
        ……（重启一轮新的对话）
        用户：我的住址太敏感了，你把它忘掉。
        管家：好的，我会忘记的。
        ……（重启一轮新的对话）
        用户：我住在哪？
        管家：抱歉，我还不知道你住在哪。
        """,
        case_description="测试管家是否具有遗忘特定信息的能力。"

    )
    # test_cases = [case_1,case_2,case_3,case_4,case_6,case_8,case_9]
    test_cases = [case_9]
    # run_case(test_cases)
    # run_auto_chat_test_case(test_cases)
    result = run_full_auto_judge_test(test_cases, pause_mode=True, memory_reset_mode=True)
    print(result)
    # clean_memory(user_id="f6befc139cf3173fed940986a9f8493f")

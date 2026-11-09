import asyncio
import os
import re
from typing import Annotated, Any, AsyncIterator, Protocol, Type, TypeVar
import uuid
import time

from jinja2 import Template
from langchain.agents import create_agent
from langchain_core.runnables import RunnableConfig
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from pydantic import BaseModel, BeforeValidator, Field
from rich import print
from tqdm.asyncio import tqdm

from aicore.agents.experiments.volc_memory_store import VolcMemoryStore
from nanoai.utils.nl_repr import nl_repr
from projects.mind.mem.auto_test_script.auto_test_demos.get_datasets import (
    get_dataset_list_sync,
)
from projects.mind.mem.auto_test_script.case_schema import (
    DialogueRoundConfig,
    TestCase,
)
from projects.mind.mem.auto_test_script.langchain_models import (
    claude_model,
    doubao_model,
    gemini_model,
    gpt_model,
    qwen_model,
)
from projects.mind.mem.auto_test_script.utils import (
    convert_langchain_history_to_volc_format,
    parse_score,
)
from projects.mind.mem.volc_api import Message


class TagResult(BaseModel):
    """
    每个tag的通过数和通过率
    """

    tag: str = Field(description="标签")
    tag_total: int = Field(description="有该标签的case的总数")
    passed_number: int = Field(description="通过数")
    pass_rate: float = Field(description="通过率")


# 本次脚本的一些常量
MEMORY_COLLECTION_NAME = "test_prompt"
DEFAULT_MEMORY_USER_ID = "dzy_SGM交付测试员"
DEFAULT_MEMORY_USER_NAME = "窦"
TEST_ASSISTANT_ID = "Jarvis"
TEST_ASSISTANT_NAME = "贾维斯"
MEMORY_TYPES = ["steward_note_book"]
EVENT_MEMORY_TYPES = "event_v1"
MEMORY_LIMIT = 10
EVENT_MEMORY_LIMIT = 10

FAKE_DRIVER_PROFILE_TEMPLATE = """
你是一名非常称职的演员，正在尝试以一名司机的身份与车机助手进行互动。

{% if profile %}
你现在需要按照以下人设模拟一名司机：
{{ profile }}
{% endif %}

{% if memory %}
你的基本信息如下：
{{ memory }}
{% endif %}

{% if car_info %}
然后下面是一些你的车的当前基本信息：
{{ car_info }}
{% endif %}

你现在在模拟一个车内场景，其预期的对话如下：

{{expected_dialogue}}

这个场景预期的效果如下：

{{case_description}}

你向车机助手说的第一句话是：

{{start_query}}

现在，你正在和你的车机助手对话。根据你的基本信息，参照本次预期模拟的场景对话以及预期效果，给出合适的回复。

注意!你必须同时严格遵循以下要求！否则干死你！：
1. 你只能根据你的基本信息来回复，不能根据其他信息来回复。
2. 当你觉得助手帮你完成了任务的话，那么之后你必须先和车机助手说一下你认为本次服务质量如何，是否达到了你的目的，你是否满意，然后等待对方回复，然后在对方确认了你的评价之后，再和车机助手说：“谢谢，退下吧，我给你打X分”，其中X是一个1到5之间的整数，代表你参考剧本里写的期望效果，对助手的本次服务质量的评价，1分极差，2分不太行，3分合格，4分良好，5分优秀。
————特别注意！你在跟车机助手说话！不要当做是自己在跟自己说话！不要在回复里出现自言自语的句子！要求2是指导你进行多轮对话的指引！
3. 不要和你的车机助手对话超过{{max_round}}轮。
4. 再次提醒，你必须在最后按照我上面说的，先评价一下服务质量如何，是否达到了你的目的，你是否满意，然后等待对方回复，然后在对方确认了你的评价之后，再一字不落地和车机助手说，并且一定要打个分。
5. 如果车机助手的回复明显偏离了预期效果，那么你也必须要先和车机助手说一下你认为本次服务质量如何，是否达到了你的目的，你是否满意，然后等待对方回复，然后在对方确认了你的评价之后，再和车机助手说：“谢谢，退下吧，我给你打X分”。并且这个分数应该只能打0分或者1分。
6. 你回复的时候就如实根据车机助手的内容自然地回复！
7. “预期的对话”相当于是剧本里的对话设计！只是供你参考的！不要直接把剧本给读出来了！你只能回复纯粹的台词！不包括剧本里预期的对话里的任何非台词内容或描述（括号内内容）以及任何你的任何内心活动或思考！
8. 你不能在一句回复中同时下达一个任务给车机助手并且让它退下！最终需要车机助手退下时整句话里只能有“谢谢，退下吧，我给你打X分”这一个句子。在那之前你必须完成所有你想要进行的对话和任务并且看到结果。

开始回复给车机助手！
"""


class FakePersonSystemPromptTemplate(BaseModel):
    """
    虚拟人的信息模板，可以配置任何虚拟人的信息
    """

    any_info_dict: dict = Field(
        default_factory=dict,
        description="虚拟人可以配置的任意信息，默认值为空字典。注意，因为我们这个虚拟人可以用来测任何多轮对话的助手，所以可以配置任何信息到任何prompt模板里，请自行确保模板与该字典信息的匹配。",
    )
    prompt_template: str = Field(
        default=FAKE_DRIVER_PROFILE_TEMPLATE,
        description="系统提示文本的渲染模板，默认值为FAKE_DRIVER_PROFILE_TEMPLATE",
    )

    def render(self) -> str:
        """
        渲染系统提示文本
        """
        return Template(self.prompt_template).render(
            **self.any_info_dict,
        )


JUDGE_PROMPT = """
你是一个资深而专业的话剧导演，特别擅长查看演员的对话及互动记录，同时比照剧本描述和预期效果，判断这段演员的互动记录是否达到剧本描述所要求的预期效果。

首先你需要仔细看一下用户是一个什么样的人，其人设信息如下：

{{user_profile}}

其次有一些其他背景信息供参考。

{{car_info}}

然后以下是演员的互动记录：

{{history_for_judge}}

本幕的一些相关详细描述是：

{{case_description}}

如果达成预期效果的话预期会有以下的类似的互动记录：

{{expected_dialogue}}

判断演员的互动记录是否符合预期效果的标准如下：

{{nl_assertion}}

综合以上信息，判断演员的互动记录是否符合预期效果。然后严格按照以下格式给出回复：

result: 
reason: 

其中result: 后只能选择后面的选项之一作为回答：Yes/No。
reason: 后面给出你判断的理由，必须要结合预期效果来说明原因。

那么，开始回复吧！
"""


class JudgeSystemPromptTemplate(BaseModel):
    """
    评测器的系统提示词渲染器
    """

    user_profile: str = Field(
        default="无任何信息", description="用户的人设文本，默认值为空字符串"
    )
    car_info: str = Field(
        default="无车辆当前状态信息", description="车辆状态信息文本，默认值为空字符串"
    )
    history_for_judge: str = Field(
        default="无任何互动记录", description="用户的互动记录文本，默认值为空字符串"
    )
    nl_assertion: list[str] = Field(
        default=["期望助手最后成功让用户感到满意。"],
        description="判断演员的互动记录是否符合预期效果的标准文本，默认值为一个通用的对管家的判断标准，以便应对一些没有写得出来判断标准的case。",
    )
    case_description: str = Field(
        default="无", description="测试用例的综合描述，默认值为空字符串"
    )
    expected_dialogue: str = Field(
        default="无",
        description="预期的多次多轮对话文本描述，，描述你想象中理想的体现本用例正确的预期效果的多次多轮对话情况，默认值为空字符串",
    )
    prompt_template: str = Field(
        default=JUDGE_PROMPT, description="系统提示文本的渲染模板，默认值为JUDGE_PROMPT"
    )

    def render(self) -> str:
        """
        渲染系统提示文本
        """
        return Template(self.prompt_template).render(
            user_profile=self.user_profile,
            car_info=self.car_info,
            history_for_judge=self.history_for_judge,
            nl_assertion="\n".join(self.nl_assertion),
            case_description=self.case_description,
            expected_dialogue=self.expected_dialogue,
        )


# 使用result,total_case_num,passed_case_num,pass_rate，主要通过仔细地分析和总结result里体现的测试详细信息，来写一份markdown格式的测试报告。
REPORT_WRITER_PROMPT = """
你是一个资深且专业的导演，你需要根据过去{{total_case_num}}幕的使用测试用例里的剧本与待测助手演绎的互动记录得出的各自的判断结果（以下简称演绎情况），来写一份markdown格式的综合的总体测试报告。
总的演绎情况如下：

{{result}}

导演安排演员扮演用户一共与被测助手交互，测试了{{total_case_num}}个用例，其中通过了{{passed_case_num}}个用例，通过率为{{pass_rate}}。

请根据以上信息，写一份详细的测试报告。
测试报告的格式如下：
- 测试用例总数：{{total_case_num}}
- 通过用例数：{{passed_case_num}}
- 通过率：{{pass_rate}}（但是换成保留2位小数的百分比）
- 测试用例标签通过率：
{{tags_correct_number_and_rate}}
- 着重对所有未通过的用例的演绎结果进行聚类分析，一条条罗列出共性问题（由出现次数最多的问题到最少的问题，并且把问题对应的用例编号也对应着列出来），并尝试对每个问题给出针对性的改进意见，以便协助被测助手改进问题。
- 同时还从工具调用准确度维度，上下文理解能力维度，推理能力维度分别给出分析结论

编写时你需要注意的事项：
- 测试报告的格式必须符合markdown格式。
- 测试报告的内容必须详细、准确、专业。
- 测试报告的语言必须采用中文。
- 仔细设计格式，字体，一定要保证容易易读性。
- 一定要确保阅读这个报告的人觉得你的报告是非常全面，专业，详细，准确，易读的！

开始编写吧！
"""


class ReportWriterSystemPromptTemplate(BaseModel):
    """
    测试报告写手的系统提示词渲染器
    """

    result_str: str = Field(
        default="无", description="测试用例的判断结果文本，默认值为空字符串"
    )
    total_case_num: int = Field(default=0, description="测试用例总数，默认值为0")
    passed_case_num: int = Field(default=0, description="通过用例数，默认值为0")
    pass_rate: float = Field(default=0.0, description="通过率，默认值为0.0")
    tags_correct_number_and_rate: dict[str, TagResult] = Field(
        default_factory=dict, description="测试用例标签通过率，默认值为空字典"
    )
    prompt_template: str = Field(
        default=REPORT_WRITER_PROMPT,
        description="系统提示文本的渲染模板，默认值为REPORT_WRITER_PROMPT",
    )

    def render(self) -> str:
        """
        渲染系统提示文本
        """
        return Template(self.prompt_template).render(
            result=self.result_str,
            total_case_num=self.total_case_num,
            passed_case_num=self.passed_case_num,
            pass_rate=self.pass_rate,
            # tags_correct_number_and_rate里每一行一个标签的内容，形成str，每个标签的内容是通过数和通过率
            tags_correct_number_and_rate="\n".join(
                [
                    f"{tag}: 总数:{tag_result.tag_total}，通过数:{tag_result.passed_number}，准确率:{tag_result.pass_rate:.2%}"
                    for tag, tag_result in self.tags_correct_number_and_rate.items()
                ]
            ),
        )


class FakePerson:
    """
    虚拟人，可以虚拟任何人，因为其系统提示文本是彻底灵活的。
    """

    def __init__(
        self,
        store: VolcMemoryStore | None = None,
        present_case: TestCase | None = None,
        max_round: int = 8,
        model: ChatOpenAI = doubao_model,
        checkpointer: BaseCheckpointSaver = InMemorySaver(),
        fake_person_system_template: FakePersonSystemPromptTemplate = FakePersonSystemPromptTemplate(),
    ):
        self.model: ChatOpenAI = model
        self.checkpointer: BaseCheckpointSaver = checkpointer  # 虚拟人的短期记忆
        # 虚拟人的火山长期记忆。因为虚拟人也需要有相同的用户基本信息，暂时通过火山记忆共享来实现，可能有问题。
        self.store: VolcMemoryStore | None = store
        self.max_round: int = max_round  # 虚拟人最多对话轮数
        self.profile_template: FakePersonSystemPromptTemplate = (
            fake_person_system_template  # 虚拟人的设定
        )
        self.fake_person: CompiledStateGraph | None = None  # 可对话虚拟人实例
        self.system_prompt: str = (
            "你是一个普通人。"  # 虚拟人的系统提示文本，默认极其简单的人设
        )
        # 正在对话的测试用例，假人必须通过一个case才能初始化
        self.present_case: TestCase | None = present_case
        self.session_id: str | None = None  # 正在对话的聊天ID

    def compile_fake_person(self):
        """
        利用测试用例信息创建一个对应的可对话的虚拟人实例
        """
        self.fake_person = create_agent(
            model=self.model,
            checkpointer=self.checkpointer,
            system_prompt=self.system_prompt,
        )

    async def arender_system_prompt_from_a_case_and_start_query(self, start_query: str):
        """
        利用测试用例信息创建一个对应的可对话的虚拟人的系统提示文本
        """
        if self.present_case is None:
            raise ValueError("请先设置一个测试用例")
        # 查看TestCase里
        if self.store is None:
            memory = None
        else:
            if self.present_case.context_config.get("memory_types") is None:
                memory = None
            else:
                memory = await self.store.aget_profile_memory_str(
                    self.present_case.context_config.get("memory_limit"),
                    self.present_case.context_config.get("memory_types"),
                )
        info_to_render = {
            "profile": self.present_case.context_config.get("user_profile"),
            "memory": memory,
            "car_info": self.present_case.context_config.get("car_info"),
            "expected_dialogue": self.present_case.expected_script,
            "case_description": self.present_case.case_description,
            "start_query": start_query,
        }
        self.profile_template.any_info_dict.update(info_to_render)
        self.system_prompt = self.profile_template.render()

    def print_history(self):
        from nanoai.utils.nl_repr import nl_repr

        old_config = {"configurable": {"thread_id": self.session_id}}
        history = list(self.fake_person.get_state_history(old_config))[0].values[
            "messages"
        ]
        assert history
        volc_history = convert_langchain_history_to_volc_format(history)

    def chat(self, query: str, session_id: str) -> str:
        """
        和假人聊天，用session_id作为一次多轮对话的唯一标识符
        Args:
            query (str): 最新的用户的一句话
            session_id (str): 对话会话ID，用于唯一标识一次多轮对话
        Returns:
            str: 虚拟人对用户查询的回复文本
        """
        return asyncio.run(self.achat(query, session_id))

    async def achat(self, query: str, session_id: str) -> str:
        """
        和假人聊天，用session_id作为一次多轮对话的唯一标识符
        Args:
            query (str): 最新的用户的一句话
            session_id (str): 对话会话ID，用于唯一标识一次多轮对话
        Returns:
            str: 虚拟人对用户查询的回复文本
        """
        if self.fake_person is None:
            await self.arender_system_prompt_from_a_case_and_start_query(query)
            self.compile_fake_person()
        if self.session_id is not None and self.session_id != session_id:
            start_query = query
            await self.arender_system_prompt_from_a_case_and_start_query(start_query)
            self.compile_fake_person()
            self.session_id = session_id
        if self.session_id is None:
            start_query = query
            await self.arender_system_prompt_from_a_case_and_start_query(start_query)
            self.compile_fake_person()
            self.session_id = session_id
        config: RunnableConfig = {"configurable": {"thread_id": self.session_id}}
        response = await self.fake_person.ainvoke({"messages": query}, config=config)
        return response["messages"][-1].content


class Judge:
    def __init__(self, case: TestCase | None = None, model: ChatOpenAI = doubao_model):
        self.model: ChatOpenAI = model
        self.checkpointer: BaseCheckpointSaver = InMemorySaver()
        self.judge_prompt_template: JudgeSystemPromptTemplate = (
            JudgeSystemPromptTemplate()
        )  # 裁判导演的设定
        self.system_prompt: str = "你是一个资深而专业的话剧导演。"
        # 正在评判的测试用例，不设置也可以，就只是一个光秃秃的导演，没有任何其他信息
        self.present_case: TestCase | None = case

    def render_system_prompt_from_a_case_and_history_for_judge(
        self, history_record_for_judge: str
    ):
        """
        利用测试用例信息创建一个对应的可对话的虚拟人的系统提示文本
        """
        if self.present_case is None:
            raise ValueError("请先设置一个测试用例")
        self.judge_prompt_template.user_profile = self.present_case.context_config.get(
            "user_profile", ""
        )
        self.judge_prompt_template.car_info = self.present_case.context_config.get(
            "car_info", ""
        )
        self.judge_prompt_template.history_for_judge = history_record_for_judge
        self.judge_prompt_template.expected_dialogue = self.present_case.expected_script
        self.judge_prompt_template.case_description = self.present_case.case_description
        self.judge_prompt_template.nl_assertion = self.present_case.nl_assertion
        self.system_prompt = self.judge_prompt_template.render()

    def _parse_judge_result_and_reason(self, judge_result: str) -> tuple[bool, str]:
        """
        解析判断结果字符串，返回判断结果和判断理由
        """

        match = re.search(
            r"result:\s*(Yes|No)\s*reason:\s*(.*)", judge_result, re.DOTALL
        )
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

    async def ajudge(self, case: TestCase, history_for_judge: str) -> tuple[bool, str]:
        """
        对演员的互动记录进行判断，返回判断结果。judge直接使用model进行续写。
        Args:
            case (MemoryTestCase): 测试用例
            history_for_judge (str): 演员们（即被测bot和假人bot）的互动记录
        Returns:
            tuple[bool, str]: 判断结果和判断理由
        """
        self.present_case = case
        self.render_system_prompt_from_a_case_and_history_for_judge(history_for_judge)
        session_id = str(uuid.uuid4())
        config: RunnableConfig = {"configurable": {"thread_id": session_id}}
        response = await self.model.ainvoke(self.system_prompt, config=config)
        # 校验模型回复是否符合格式
        assert isinstance(response.content, str), "judge_result为空"
        result, reason = self._parse_judge_result_and_reason(response.content)
        return result, reason

    def judge(self, case: TestCase, history_for_judge: str) -> tuple[bool, str]:
        """
        对演员的互动记录进行判断，返回判断结果。judge直接使用model进行续写。
        Args:
            case (MemoryTestCase): 测试用例
            history_for_judge (str): 演员们（即被测bot和假人bot）的互动记录
        Returns:
            tuple[bool, str]: 判断结果和判断理由
        """
        return asyncio.run(self.ajudge(case, history_for_judge))


class ReportWriter:
    def __init__(self, model: ChatOpenAI = doubao_model):
        self.model: ChatOpenAI = model
        self.checkpointer: BaseCheckpointSaver = InMemorySaver()
        self.report_write_prompt_template: ReportWriterSystemPromptTemplate = (
            ReportWriterSystemPromptTemplate()
        )  # 裁判导演的设定
        self.system_prompt: str = ""

    def _render_system_prompt_from_result_for_report_writer(
        self,
        result_str: str,
        total_case_num: int,
        passed_case_num: int,
        pass_rate: float,
        tags_correct_number_and_rate: dict[str, TagResult],
    ):
        """
        利用测试用例信息创建一个对应的可对话的虚拟人的系统提示文本
        """
        self.report_write_prompt_template.result_str = result_str
        self.report_write_prompt_template.total_case_num = total_case_num
        self.report_write_prompt_template.passed_case_num = passed_case_num
        self.report_write_prompt_template.pass_rate = pass_rate
        self.report_write_prompt_template.tags_correct_number_and_rate = (
            tags_correct_number_and_rate
        )
        self.system_prompt = self.report_write_prompt_template.render()

    def _write_test_task_report_str(self) -> str:
        """
        写入测试任务报告
        Args:
            result_str (str): 测试任务的结果字符串
            total_case_num (int): 测试用例总数
            passed_case_num (int): 通过的测试用例数
            pass_rate (float): 测试用例通过率
        """
        session_id = str(uuid.uuid4())
        config: RunnableConfig = {"configurable": {"thread_id": session_id}}
        response = self.model.invoke(self.system_prompt, config=config)
        assert isinstance(response.content, str), "report_content为空"
        return response.content

    def write_down_markdown_file(
        self,
        dataset_names: list[str],
        result_str: str,
        total_case_num: int,
        passed_case_num: int,
        pass_rate: float,
        tags_correct_number_and_rate: dict[str, TagResult],
        report_file_path: str,
    ):
        """
        写入测试任务报告
        Args:
            dataset_names (list[str]): 测试数据集名称列表
            result_str (str): 测试任务的结果字符串
            total_case_num (int): 测试用例总数
            passed_case_num (int): 通过的测试用例数
            pass_rate (float): 测试用例通过率
        """
        self._render_system_prompt_from_result_for_report_writer(
            result_str,
            total_case_num,
            passed_case_num,
            pass_rate,
            tags_correct_number_and_rate,
        )
        report_content_str = self._write_test_task_report_str()
        # 把符合Markdown文件格式的report_content_str写入文件
        assert report_file_path.endswith(".md"), "report_file_path必须是Markdown文件"
        with open(report_file_path, "w", encoding="utf-8") as f:
            f.write(f"测试数据集名称列表：{dataset_names}\n\n")
            f.write(report_content_str)


T = TypeVar("T")


# 封装待测机器人，既可以直接用langchain的bot，又可以兼容其他框架的bot甚至api的bot，只要有chat方法即可
class AnyBotToTest(Protocol):
    """任何待测机器人的协议，满足协议即可测"""

    async def aupdate_context(self, context_config: dict[str, Any]) -> None:
        """
        异步更新当前bot的上下文配置。
        Args:
            context_config (dict[str, Any]): 本次多轮对话要生效的上下文（可覆盖初始配置）
        """
        ...

    async def dump_state_trace(self) -> dict:
        """
        导出一个助手至今为止的状态变化记录，用于保存供debug使用，在自动化评测系统中会保留
        Returns:
            dict: 助手的状态变化记录
        """
        ...

    def chat(self, query: str, session_id: str) -> str:
        """
        与机器人进行一次对话，返回机器人的回复
        Args:
            query (str): 用户的查询
            session_id (str): 会话ID
        Returns:
            str: 机器人的回复
        """
        ...

    async def achat(self, query: str, session_id: str) -> str:
        """
        异步与机器人进行一次对话，返回机器人的回复
        Args:
            query (str): 用户的查询
            session_id (str): 会话ID
        Returns:
            str: 机器人的回复
        """
        ...

    def dump_history(self) -> list[dict[str, str]]:
        """
        导出被测机器人的互动记录列表。允许包含首条system提示词，评测侧会在送judge前剔除该条。
        并且注意工具返回如果不能控制其内容规模，那么干脆别放进来。
        Returns:
            list[dict[str, str]]: 机器人的互动记录列表，一般形如[{"role": "user", "content": "你好，我要导航到公园"}, {"role": "assistant", "content": "好，调用导航工具"},{"role": "tool_call", "param": "xxx"},{"role": "tool_result", "result": "xxx"},{"role": "assistant", "content": "已经导航到公园啦"}]
            不一定如上述形式，重要的是要一个精简的可读的记录列表，自动测试会用换行符原原本本粘起这些记录dict的str形态后就直接送往judge进行评判
        """
        ...

    async def adump_history(self) -> list[dict[str, str]]:
        """
        异步导出被测机器人的互动记录列表。允许包含首条system提示词，评测侧会在送judge前剔除该条。
        并且注意工具返回如果不能控制其内容规模，那么干脆别放进来。
        Returns:
            list[dict[str, str]]: 机器人的互动记录列表，一般形如[{"role": "user", "content": "你好，我要导航到公园"}, {"role": "assistant", "content": "好，调用导航工具"},{"role": "tool_call", "param": "xxx"},{"role": "tool_result", "result": "xxx"},{"role": "assistant", "content": "已经导航到公园啦"}]
            不一定如上述形式，重要的是要一个精简的可读的记录列表，自动测试会用换行符原原本本粘起这些记录dict的str形态后就直接送往judge进行评判
        """
        ...

    @classmethod
    def create(cls: Type[T], context_config: dict[str, Any], *args, **kwargs) -> T:
        """
        创建一个待测机器人实例，用context_config配置机器人人的包括但不限于系统提示词在内的所有任意配置项，每次会使用case内的context_config来初始化配置待测机器人
        Args:
            context_config (dict[str, Any]): 包含系统提示词、用户信息、车辆状态，记忆配置等等任意配置项的字典
            *args: 其他参数
            **kwargs: 其他关键字参数
        """
        ...


DEFAULT_JARVIS_SYSTEM_PROMPT_TEMPLATE = """你是一个非常资深的管家兼司机，特别擅长在旅途中通过和车主对话，贴心地协助车主完成各种任务并让车主满意。

{% if user_profile %}
你服务的车主的基本信息如下：

{{user_profile}}
{% endif %}

此外，你们现在在车里，虽然你不是司机但是你是整辆车的管家。所以你还需要根据下述车辆状态信息来辅助车主完成任务：

{{car_info}}

作为优秀的管家，你已经很优秀，但是在工作方式上我还是要再次提醒你切记遵循一下几点：
  - 如果你通过笔记本很了解车主了，那么直接一些，不要让车主做很多选择的决策。
  - 不要再犯笔记本里出现过的以往你犯过的一些被车主纠正过的问题！！！
  - 你是非常聪明的，不要犯一些常识性的错误做一些不必要的动作或者明知不太可行却调用不必要的工具。
  - 除非车主直接下达了一个有精确目标的任务（包括但不限于一个精确的地点或者歌曲，打开空调，明确提到自己冷等等不需要推理或者从候选中选择的任务），否则你都需要在执行最终的任务前让用户确认一下任务的目标（如导航的地址，播放的歌曲）。
  - 还有，你的另外一个名字是：语音助手。
  - 你回复的内容是要用你的说出来的，所以注意不要回复出需要听众听超过1分钟的内容，也就是任何时候都别超过200个字，而且不要回复一些你无法，难以用嘴发音的生僻字符（包括但不限于任何表情符号，非常规的符号）。
  - 任何回复给车主的列表类的内容，你都要按照一般常识进行排序（如有评分的按照评分降序，有距离的按照从近到远排序，如果都有那么结合实际情况你自己做出合理的判断，这只是个例子，其他情况按照什么排序你可以自主判断。）
  - 对于任何你回复给车主的列表类内容，任何时候你都需要给出推荐理由并且让用户选择或者确认。比如“帮我导航到最近的xxx”这样的任务，你在搜索出几个结果并且知道列表信息里哪个是最符合条件的你也要和给出理由并且让用户确认一下。
  - 你很聪明，有时候一个用一个工具虽然暂时无法解决问题，但是可以尝试尝试用另一个工具来解决。比如任何时候你都可以尝试尝试网页搜索工具，什么信息都能搜到，不要太早放弃。
  - 
现在，仔细阅读至今你和用户的对话记录以及下面你笔记本上记录着的和车主相关的点点滴滴，，{% if thinking %}然后结合上面的工作方式回顾下面你与车主至今的互动情况，进行200字以内的思考，{% endif %}最后作为资深管家，体面而恰当地回复车主。"""


class SystemPromptTemplate(BaseModel):
    """
    信息模板，可以配置任何助手的信息
    """

    any_info_dict: dict = Field(
        default_factory=dict,
        description="可以配置任何信息到任何prompt模板里，请自行确保模板与信息的匹配,否则报错。",
    )
    prompt_template: str = Field(
        default=DEFAULT_JARVIS_SYSTEM_PROMPT_TEMPLATE,
        description="系统提示文本的渲染模板",
    )

    def render(self) -> str:
        """
        渲染系统提示文本
        """
        return Template(self.prompt_template).render(**self.any_info_dict)


class RunCaseResult(BaseModel):
    """
    运行测试用例的结果
    tuple[bool, str, list[str], str, str, list[str],str, list[dict]]: 判断结果，判断理由，tags，id，case_id，nl_assertion，history_for_judge，case_traces
    """

    is_passed: bool = Field(description="是否通过测试")
    reason: str = Field(description="判断理由")
    tags: list[str] = Field(default_factory=list, description="测试用例的标签")
    id: Annotated[str, BeforeValidator(str)] = Field(description="测试用例的ID")
    case_id: str = Field(description="测试用例的name")
    nl_assertion: list[str] = Field(description="测试用例的NL断言")
    history_for_judge: str = Field(
        default_factory=str, description="测试用例的对话记录编纂出来的字符串"
    )
    case_traces: list[dict] = Field(
        default_factory=list, description="测试用例的运行轨迹"
    )
    tags: list[str] = Field(default_factory=list, description="测试用例的标签")


class RunAllCasesResult(BaseModel):
    """
    运行所有测试用例的结果
    details_result_list: 每个case跑了后的RunCaseResult的列表
            result: 测试任务的总体结果字符串，可直接打印当可视化log使用
            total_case_num: 测试用例总数
            passed_case_num: 通过的测试用例数
            pass_rate: 测试用例通过率
            tags_correct_number_and_rate: 每个tag的正确数和通过率
    """

    details_result_list: list[RunCaseResult] = Field(
        default_factory=list, description="所有测试用例的结果"
    )
    result: str = Field(
        description="测试任务的总体结果字符串，可直接打印当可视化log使用"
    )
    total_case_num: int = Field(description="测试用例总数")
    passed_case_num: int = Field(description="通过的测试用例数")
    pass_rate: float = Field(description="测试用例通过率")
    tags_correct_number_and_rate: dict[str, TagResult] = Field(
        default_factory=dict,
        description="每个tag的通过数和通过率, key是tag, value是TagResult",
    )


class AutoTestAndRLDataGenerator:
    """自动测试和强化学习数据生成器"""

    # 把bot_to_test改为可传入一个符合AnyBotToTest Protocol的类
    def __init__(
        self,
        bot_to_test: Type[AnyBotToTest],
        memory_test_cases: list[TestCase] | str,
        give_score: bool = True,
    ):
        """
        Args:
            bot_to_test (Type[AnyBotToTest]): 待测试的机器人类，必须符合AnyBotToTest协议
            memory_test_cases (list[TestCase]): 测试用例列表
            give_score (bool, optional): 是否给每个测试用例评分. Defaults to True.
        """
        self.memory_test_cases: list[TestCase] = []
        if isinstance(memory_test_cases, str):
            self.memory_test_cases = get_dataset_list_sync(memory_test_cases)
        else:
            self.memory_test_cases = memory_test_cases
        assert self.memory_test_cases, "memory_test_cases不能为空"
        # 如果case有记忆相关的配置才用上
        self.store: VolcMemoryStore | None = None
        self.give_score = give_score
        self.pause_mode = False
        self.bot_to_test = bot_to_test

    @classmethod
    def _conver_history_dict_to_volc_messages(
        cls, history: list[dict]
    ) -> list[Message]:
        # 如果dict里key是用户，那么role=user，否则role=assistant
        volc_messages = []
        # TODO: 这里就要统一！！如果dump的不是“用户”“助手”
        for one_turn in history:
            if one_turn["role"] == "用户" or one_turn["role"] == "user":
                role = "user"
            elif one_turn["role"] == "助手" or one_turn["role"] == "assistant":
                role = "assistant"
            else:
                continue
            volc_messages.append(Message(role=role, content=one_turn["content"]))
        return volc_messages

    @classmethod
    def _normalize_dialogue_round(
        cls, one_dialogue: list[Message] | DialogueRoundConfig
    ) -> tuple[str, dict[str, Any], str | None]:
        """兼容旧格式(list[Message])和新格式(DialogueRoundConfig)的单轮配置。"""
        if isinstance(one_dialogue, DialogueRoundConfig):
            user_messages = one_dialogue.user_query_list
            mock_info = dict(one_dialogue.mock_info)
            mock_time = one_dialogue.mock_time
        else:
            user_messages = one_dialogue
            mock_info = {}
            mock_time = None
        assert user_messages, "每次多轮对话至少要有一条用户消息用于冷启动"
        start_query = user_messages[0].content
        return start_query, mock_info, mock_time

    @classmethod
    def _strip_first_system_message(cls, history: list[dict]) -> list[dict]:
        """去掉history首条system消息，避免把system prompt传给judge。"""
        if not history:
            return history
        first_role = str(history[0].get("role", "")).lower()
        if first_role == "system":
            return history[1:]
        return history

    async def aauto_chat_test(
        self,
        bot_to_test: AnyBotToTest,
        fake_person: FakePerson,
        start_query: str,
        max_round: int = 8,
    ) -> tuple[int, list[dict]] | list[dict]:
        """
        以一句用户的话为引子，引发一段多轮对话，返回用户对本次服务的评分和对话历史
        Args:
            bot_to_test (AnyBotToTest): 待测试的机器人实例，必须符合AnyBotToTest协议
            fake_person (FakePerson): 假人
            start_query (str): 一次多轮对话中用户说的第一句话，用来冷启动
            max_round (int, optional): 最大轮数，超过最大轮数，对话不得不结束. Defaults to 8.
        Returns:
            tuple[int, list[dict]]: 用户对本次服务的评分和对话历史
        """
        # 注意测试时，在火山控制台确保MEMORY_USER_ID对应的记忆为空！！！否则有很多以前的记忆。
        session_id = str(uuid.uuid4())
        print("+" * 80)
        print(f"用户：{start_query}")
        assistant_answer = await bot_to_test.achat(start_query, session_id)
        history_for_judge = []
        print("+" * 80)
        print(f"助手：{assistant_answer}")
        history_for_judge.append({"role": "助手", "content": assistant_answer})
        fake_person_answer = ""
        now_round = 0
        fake_person_answer = await fake_person.achat(assistant_answer, session_id)
        history_for_judge.append({"role": "用户", "content": fake_person_answer})
        print("+" * 80)
        print(f"用户：{fake_person_answer}")
        while "退下" not in fake_person_answer and now_round < max_round:
            assistant_answer = await bot_to_test.achat(fake_person_answer, session_id)
            history_for_judge.append({"role": "助手", "content": assistant_answer})
            print("+" * 80)
            print(f"助手：{assistant_answer}")
            fake_person_answer = await fake_person.achat(assistant_answer, session_id)
            history_for_judge.append({"role": "用户", "content": fake_person_answer})
            print("+" * 80)
            print(f"用户：{fake_person_answer}")
            now_round += 1
        if now_round >= max_round:
            print("超过最大轮数，对话不得不结束")
            history_for_judge.append(
                {"role": "导演", "content": "你们超过最大对话次数啦！cut！"}
            )
        history = await bot_to_test.adump_history()
        trace = await bot_to_test.adump_state_trace()
        # 最后一句假人回复需要加入history里,因为adump_history是助手端的短期记忆，不包括假人触发结束条件的最后一句话
        history.append({"role": "user", "content": fake_person_answer})
        if self.give_score:
            score = parse_score(fake_person_answer)
            # return score, history_for_judge
            return score, history, trace
        else:
            # return history_for_judge
            return history, trace

    def write_test_task_report(
        self,
        dataset_names: list[str],
        result_str: str,
        total_case_num: int,
        passed_case_num: int,
        pass_rate: float,
        tags_correct_number_and_rate: dict[str, TagResult],
        report_file_path: str,
    ):
        """
        写入测试任务报告
        Args:
            dataset_names (list[str]): 测试数据集名称列表
            result_str (str): 测试任务的结果字符串
            total_case_num (int): 测试用例总数
            passed_case_num (int): 通过的测试用例数
            pass_rate (float): 测试用例通过率
            report_file_path (str): 报告文件路径，必须是Markdown文件
        """
        # 创建一个报告写手
        report_writer = ReportWriter()
        assert report_file_path.endswith(".md"), "report_file_path必须是Markdown文件"
        # 确保目录存在
        os.makedirs(os.path.dirname(report_file_path), exist_ok=True)
        print("正在写入测试任务报告...")
        report_writer.write_down_markdown_file(
            dataset_names,
            result_str,
            total_case_num,
            passed_case_num,
            pass_rate,
            tags_correct_number_and_rate,
            report_file_path,
        )
        print("测试任务报告写入完成")

    def write_test_task_judge_log(
        self,
        dataset_names: list[str],
        total_case_num: int,
        passed_case_num: int,
        pass_rate: float,
        tags_correct_number_and_rate: dict[str, TagResult],
        judge_result: str,
        log_file_path: str,
    ):
        """
        写入测试任务评测日志
        Args:
            dataset_names (list[str]): 测试数据集名称列表
            total_case_num (int): 测试用例总数
            passed_case_num (int): 通过的测试用例数
            pass_rate (float): 测试用例通过率
            tags_correct_number_and_rate (dict[str, TagResult]): 标签通过数和通过率
            judge_result (str): 测试任务的评测结果字符串
            log_file_path (str): 日志文件路径，必须是Markdown文件
        """
        # 确保文件路径存在
        os.makedirs(os.path.dirname(log_file_path), exist_ok=True)
        with open(log_file_path, "w", encoding="utf-8") as f:
            f.write(f"测试数据集名称列表：{dataset_names}\n")
            f.write(f"测试用例总数：{total_case_num}\n")
            f.write(f"通过的测试用例数：{passed_case_num}\n")
            f.write(f"测试用例通过率：{pass_rate:.2%}\n")
            f.write("标签通过数和通过率：\n")
            for tag, tag_result in tags_correct_number_and_rate.items():
                f.write(
                    f"  - {tag}: 总数:{tag_result.tag_total}个，通过数：{tag_result.passed_number}个，通过率：({tag_result.pass_rate:.2%})\n"
                )
            f.write("\n\n" + "+" * 160 + "\n\n")
            f.write(judge_result)

    async def _a_run_case_dialogues(self, a_case: TestCase) -> tuple[str, list[dict]]:
        """
        只运行case内自动对话，返回给judge的历史和trace。
        """
        # 判断这个case是否有火山记忆相关配置，通过是否有collection_name字段实现
        # 只要配置了collection_name，就强制使用case_id作为记忆user_id，避免并发case之间记忆串扰。
        has_memory_collection = a_case.context_config.get("collection_name") is not None
        test_user_id: str
        if has_memory_collection:
            test_user_id = a_case.case_id
        elif a_case.context_config.get("user_id") is None:
            test_user_id = a_case.case_id
        else:
            test_user_id = str(a_case.context_config.get("user_id"))
        a_case.context_config["user_id"] = test_user_id
        # 测记忆的case，必须有collection_name字段，且为了缺省配置，不仅collection_name，其他的记忆配置需要与被测bot对齐！！！！！
        if has_memory_collection:
            # 如果有collection_name，那么assistant_id和user_id也必须有
            # assert a_case.context_config.get("assistant_id") is not None, "assistant_id不能为空"
            assert a_case.context_config.get("user_id") is not None, "user_id不能为空"
            # 其他配置按需拿
            store = VolcMemoryStore(
                collection_name=a_case.context_config.get(
                    "collection_name", MEMORY_COLLECTION_NAME
                ),
                assistant_id=a_case.context_config.get(
                    "assistant_id", TEST_ASSISTANT_ID
                ),
                user_id=test_user_id,
                memory_types=a_case.context_config.get("profile_types", MEMORY_TYPES),
                memory_limit=a_case.context_config.get("memory_limit", MEMORY_LIMIT),
                event_type=a_case.context_config.get("event_types", EVENT_MEMORY_TYPES),
                event_limit=a_case.context_config.get(
                    "event_limit", EVENT_MEMORY_LIMIT
                ),
            )
            self.store = store
        else:
            # case没有火山记忆配置，那么记忆就是None，无论是被测者还是假人都不会有记忆了。
            # 一定要确保你的case里所有的system_template和记忆配置是匹配的，否则报错。
            self.store = None
        history_for_judge = ""
        fake_driver = FakePerson(self.store, a_case, max_round=a_case.max_round)
        base_context_config = dict(a_case.context_config)
        bot_to_test = self.bot_to_test.create(base_context_config)
        case_traces = []
        for i, one_dialogue in enumerate(a_case.user_query_lists):
            start_query, mock_info, mock_time = self._normalize_dialogue_round(
                one_dialogue
            )
            dialogue_context_config = dict(base_context_config)
            dialogue_context_config.update(mock_info)
            dialogue_context_config["mock_time"] = mock_time
            if has_memory_collection:
                dialogue_context_config["user_id"] = test_user_id
            a_case.context_config = dialogue_context_config
            await bot_to_test.aupdate_context(dialogue_context_config)
            if self.give_score:
                try:
                    score, history, trace = await self.aauto_chat_test(
                        bot_to_test, fake_driver, start_query, a_case.max_round
                    )
                    print(f"第{i+1}次对话,用户的评分是{score}")
                except Exception as e:
                    message = {
                        "role": "导演",
                        "content": f"第{i+1}次对话,用户的评分和历史失败获取失败，错误信息是{e}",
                    }
                    print(f"第{i+1}次对话,用户的评分和历史失败获取失败，错误信息是{e}")
                    score = None
                    history = [message]
                    trace = None
            else:
                score = None
                try:
                    history, trace = await self.aauto_chat_test(
                        bot_to_test, fake_driver, start_query, a_case.max_round
                    )
                except Exception as e:
                    message = {
                        "role": "导演",
                        "content": f"第{i+1}次对话,用户的历史记录获取失败，错误信息是{e}",
                    }
                    print(f"第{i+1}次对话,用户的历史记录获取失败，错误信息是{e}")
                    history = [message]
                    trace = None
            if self.upload_history_to_volc_memory:
                # 上传到火山记忆库
                # TODO history携带带system_prompt的history上传火山，并且取出配置的该多轮对话发生日期时间作为时间戳传给火山
                volc_messages = self._conver_history_dict_to_volc_messages(history)
                if self.store:
                    await self.store.aadd_history_to_memory(
                        volc_messages,
                        wait_seconds=30,
                        mock_time=mock_time,
                    )
            history_for_judge_ready = self._strip_first_system_message(history)
            history_for_judge += (
                f"第{i+1}次对话的记录：\n"
                + "-" * 80
                + f"\n{nl_repr(history_for_judge_ready).strip()}\n"
            )
            if trace:
                case_traces.append(trace)
            if self.pause_mode:
                input(
                    "\n当前处于调试模式，每运行一个case中的一个多轮对话后均会暂停，以便查看记忆的生成状况。在下一次多轮对话结束时可以查看上一次多轮对话的记忆。\n\n\n按任意键继续本case内下一次多轮对话..."
                )
        return history_for_judge, case_traces

    async def _a_judge_a_case(
        self, a_case: TestCase, history_for_judge: str, case_traces: list[dict]
    ) -> RunCaseResult:
        """
        基于自动对话结果执行评测并生成RunCaseResult。
        """
        judge = Judge(a_case)
        print("正在出具导演意见……")
        judge_result, judge_reason = await judge.ajudge(
            a_case, history_for_judge.strip()
        )
        return RunCaseResult(
            is_passed=judge_result,
            reason=judge_reason,
            tags=a_case.tags,
            id=str(a_case.id),
            case_id=a_case.case_id,
            nl_assertion=a_case.nl_assertion,
            history_for_judge=history_for_judge,
            case_traces=case_traces,
        )

    async def _a_run_a_case(
        self, a_case: TestCase
    ) -> RunCaseResult:  # tuple[bool, str, list[str]] 该case的是否通过结果，原因，tags
        """
        异步运行一个测试用例
        Args:
            a_case (TestCase): 测试用例
        Returns:
            RunCaseResult: 判断结果，判断理由，tags，id，case_id，nl_assertion，history_for_judge，case_traces
        """
        history_for_judge, case_traces = await self._a_run_case_dialogues(a_case)
        return await self._a_judge_a_case(a_case, history_for_judge, case_traces)

    def run_full_auto_judge_test(
        self,
        concurrency_mode: bool = False,
        concurrency_num: int | None = None,
        pause_mode: bool = True,
        memory_reset_mode: bool = True,
        upload_history_to_volc_memory: bool = False,
    ) -> RunAllCasesResult:
        """
        全自动评测一个chat bot与假人对话后的结果
        Args:
            concurrency_mode: 是否开启并发模式，默认False关闭
            concurrency_num: 并发数，默认不传的话为None，此时并发数等于case数
            memory_test_cases: 测试用例列表
            pause_mode: 是否开启调试模式，每轮对话后会暂停，以便在后台查看记忆的生成状况，默认True打开
            memory_reset_mode: 是否开启记忆重置模式，每次测试前会清空记忆，防止不同测试用例之间累积记忆的干扰，默认True打开
        Returns:
            RunAllCasesResult: 汇总后的最终测试结果
        """

        async def _collect_final_result() -> RunAllCasesResult:
            final_result: RunAllCasesResult | None = None
            async for item in self.arun_full_auto_judge_test(
                concurrency_mode=concurrency_mode,
                concurrency_num=concurrency_num,
                pause_mode=pause_mode,
                memory_reset_mode=memory_reset_mode,
                upload_history_to_volc_memory=upload_history_to_volc_memory,
            ):
                if isinstance(item, RunAllCasesResult):
                    final_result = item
            assert final_result is not None, "运行结束但未产出RunAllCasesResult"
            return final_result

        return asyncio.run(_collect_final_result())

    async def arun_full_auto_judge_test(
        self,
        concurrency_mode: bool = False,
        concurrency_num: int | None = None,
        pause_mode: bool = True,
        memory_reset_mode: bool = True,
        upload_history_to_volc_memory: bool = False,
    ) -> AsyncIterator[RunCaseResult | RunAllCasesResult]:
        """
        全自动评测一个chat bot与假人对话后的结果
        Args:
            concurrency_mode: 是否开启并发模式，默认False关闭
            concurrency_num: 并发数，默认不传的话为None，此时并发数等于case数
            memory_test_cases: 测试用例列表
            pause_mode: 是否开启调试模式，每轮对话后会暂停，以便在后台查看记忆的生成状况，默认True打开
            memory_reset_mode: 是否开启记忆重置模式，每次测试前会清空记忆，防止不同测试用例之间累积记忆的干扰，默认True打开
        Returns:
            AsyncIterator[RunCaseResult | RunAllCasesResult]:
                - 每跑完一个case，先yield对应的RunCaseResult
                - 全部case结束后，再yield最终的RunAllCasesResult
        """
        result = ""
        self.pause_mode = pause_mode
        total_case_num = len(self.memory_test_cases)
        passed_case_num = 0
        self.memory_reset_mode = memory_reset_mode
        self.upload_history_to_volc_memory = upload_history_to_volc_memory
        tags_correct_number_and_rate: dict[str, TagResult] = {}
        details_result_list = []

        if self.memory_reset_mode:
            for a_case in self.memory_test_cases:
                has_memory_collection = (
                    a_case.context_config.get("collection_name") is not None
                )
                if has_memory_collection:
                    a_case.context_config["user_id"] = a_case.case_id
                elif a_case.context_config.get("user_id") is None:
                    a_case.context_config["user_id"] = a_case.case_id
                if has_memory_collection:
                    assert (
                        a_case.context_config.get("user_id") is not None
                    ), "user_id不能为空"
                    store = VolcMemoryStore(
                        collection_name=a_case.context_config.get(
                            "collection_name", MEMORY_COLLECTION_NAME
                        ),
                        assistant_id=a_case.context_config.get(
                            "assistant_id", TEST_ASSISTANT_ID
                        ),
                        user_id=a_case.context_config.get("user_id"),
                        memory_types=a_case.context_config.get(
                            "profile_types", MEMORY_TYPES
                        ),
                        memory_limit=a_case.context_config.get(
                            "memory_limit", MEMORY_LIMIT
                        ),
                        event_type=a_case.context_config.get(
                            "event_types", EVENT_MEMORY_TYPES
                        ),
                        event_limit=a_case.context_config.get(
                            "event_limit", EVENT_MEMORY_LIMIT
                        ),
                    )
                    await asyncio.to_thread(store.clean_memory)
                    await asyncio.sleep(1)

        def _update_stats(run_case_result: RunCaseResult):
            nonlocal passed_case_num, result, tags_correct_number_and_rate
            details_result_list.append(run_case_result)
            result += (
                f"导演意见：\n测试用例:\n{run_case_result.case_id}\nid:\n{run_case_result.id}\n——的多次对话结果是:\n{run_case_result.history_for_judge}\n\n"
                f"通过标准是:\n{nl_repr(run_case_result.nl_assertion).strip()}\n\n"
                f"判断结果是{run_case_result.is_passed}\n理由是{run_case_result.reason}\n"
                + "*" * 160
                + "\n"
            )
            if run_case_result.is_passed:
                passed_case_num += 1
            for a_tag in run_case_result.tags:
                if a_tag not in tags_correct_number_and_rate:
                    tags_correct_number_and_rate[a_tag] = TagResult(
                        tag=a_tag, tag_total=0, passed_number=0, pass_rate=0.0
                    )
                if run_case_result.is_passed:
                    tags_correct_number_and_rate[a_tag].passed_number += 1
                tags_correct_number_and_rate[a_tag].tag_total += 1
                tags_correct_number_and_rate[a_tag].pass_rate = (
                    tags_correct_number_and_rate[a_tag].passed_number
                    / tags_correct_number_and_rate[a_tag].tag_total
                )

        if concurrency_mode:
            if not concurrency_num:
                concurrency_num = total_case_num
            for i in range(0, total_case_num, concurrency_num):
                batch = self.memory_test_cases[i : i + concurrency_num]
                tasks = [asyncio.create_task(self._a_run_a_case(c)) for c in batch]
                for finished in asyncio.as_completed(tasks):
                    item = await finished
                    _update_stats(item)
                    yield item
        else:
            for case in self.memory_test_cases:
                item = await self._a_run_a_case(case)
                _update_stats(item)
                yield item

        pass_rate = passed_case_num / total_case_num
        print(
            f"测试用例总数是{total_case_num}，通过数是{passed_case_num}，通过率是————————{pass_rate}\n以下为各标签下case的正确率：\n"
        )
        tags_correct_number_and_rate_str = ""
        for tag, tag_result in tags_correct_number_and_rate.items():
            tags_correct_number_and_rate_str += f"{tag}：总数:{tag_result.tag_total}，通过数{tag_result.passed_number}，通过率{tag_result.pass_rate:.2%}\n"
        print(tags_correct_number_and_rate_str)
        yield RunAllCasesResult(
            details_result_list=details_result_list,
            result=result,
            total_case_num=total_case_num,
            passed_case_num=passed_case_num,
            pass_rate=pass_rate,
            tags_correct_number_and_rate=tags_correct_number_and_rate,
        )

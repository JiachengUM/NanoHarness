"""
BaseAgent 自动对话测试
======================
用法：
    python -m projects.mind.mem.auto_test_script.auto_test_demos.test_base_agent_auto_test

测试数据集在文件末尾的 all_cases 列表里填写，参考 demo_auto_test.py 中 TestCase 的写法。
"""

import asyncio
import datetime
import os

from aicore.agents.events import ReActEventPrinter
from aicore.agents.experiments.base import AgentBase, RunParams, SystemPrompt
from aicore.models.credentials import AsyncArk, ModelName, create_client

from projects.mind.mem.auto_test_script.auto_test_and_rl_data_generator import (
    AutoTestAndRLDataGenerator,
)
from projects.mind.mem.auto_test_script.case_schema import TestCase

# ── 全局配置 ───────────────────────────────────────────────────────
CHAT_ID = "auto_test_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
MODEL_NAME = ModelName.SEED_1_8_251228
MAX_TURNS = 5

# 测试报告输出路径
REPORT_FILE_PATH = os.path.join(os.path.dirname(__file__), "base_agent_test_report.md")

# 被测 Agent 的系统提示
SYSTEM_PROMPT = SystemPrompt(
    role="你是一个非常贴心的车机智能助手",
    guidelines=[
        "根据工具调用结果给出清晰、简洁的回复。",
        "调用工具前先简要说明你打算做什么。",
        "如果用户的意图不够明确，先礼貌地确认再执行。",
    ],
)


# ── BaseAgent 同步包装器 ───────────────────────────────────────────
class BaseAgentBot:
    """
    将异步的 AgentBase 包装成满足 AnyBotToTest 协议的同步 Bot。

    每个 session_id 对应一个独立的 AgentBase 实例，保证多轮对话上下文
    在同一 session 内连续，不同 session 间完全隔离。
    """

    def __init__(
        self,
        system_prompt: SystemPrompt,
        model_name: ModelName = MODEL_NAME,
        max_turns: int = MAX_TURNS,
        tools: list | None = None,
    ):
        self.system_prompt = system_prompt
        self.model_name = model_name
        self.max_turns = max_turns
        self.tools = tools or []
        self._sessions: dict[str, AgentBase] = {}
        self._loop = asyncio.new_event_loop()

    def _get_or_create_agent(self, session_id: str) -> AgentBase:
        """按 session_id 获取或新建 AgentBase 实例。"""
        if session_id not in self._sessions:
            _, model = create_client(self.model_name, AsyncArk)
            run_params = RunParams(model=model, max_turns=self.max_turns)
            self._sessions[session_id] = AgentBase(
                self.system_prompt,
                run_params=run_params,
                tools=self.tools,
            )
        return self._sessions[session_id]

    async def _achat(self, query: str, session_id: str) -> str:
        agent = self._get_or_create_agent(session_id)
        async for _ in agent.astream(query, event_listeners=[ReActEventPrinter(print)]):
            pass
        assert agent.state.run_result is not None
        return agent.state.run_result.response.raw_text

    def chat(self, query: str, session_id: str) -> str:
        """同步接口，供 AutoTestAndRLDataGenerator 调用。"""
        return self._loop.run_until_complete(self._achat(query, session_id))

    def close(self):
        self._loop.close()


# ── 测试用例（用户填写） ──────────────────────────────────────────
# TODO: 在这里添加测试用例，参考下面的格式
# TestCase 字段说明：
#   case_id           — 用例编号（字符串）
#   context_config    — 上下文配置字典，key 可包含 profile / vehicle_state 等
#   max_round         — 单次多轮对话最大轮数
#   user_query_lists  — 多次独立对话的启动语列表，每一项是一次独立对话
#   expected_script   — 预期对话剧本，供假人和评测员参考
#   nl_assertion      — 自然语言形式的评测标准
#   case_description  — 用例综合描述
#
# 示例（取消注释即可使用）：
#
case_dict = {
    "case_id": "1",
    "context_config": {},
    "max_round": 5,
    "user_query_lists": [
        [
            {
                "role": "user",
                "content": "明天天气怎么样？",
            }
        ]
    ],
    "expected_script": "用户以天气为主题切入，根据助手的回答继续聊一些关于导航、车控、音乐等话题，测试助手在多轮对话中能否持续调用工具并给出合理回复，一定要聊够5轮哦！",
    "nl_assertion": [
        "考察助手在多轮对话中持续调用工具的能力，尤其是车控、天气等相关工具。",
    ],
    "case_description": "P2\n车控、天气等工具调用能力测试",
    "tags": [],
}

case_example = TestCase.model_validate(case_dict)

all_cases: list[TestCase] = [
    # 需要运行的测试用例
    case_example
]


if __name__ == "__main__":
    from projects.mind.toolset import get_default_tools

    tools = get_default_tools(chat_id=CHAT_ID)
    tools = []

    bot = BaseAgentBot(
        system_prompt=SYSTEM_PROMPT,
        model_name=MODEL_NAME,
        max_turns=MAX_TURNS,
        tools=tools,
    )

    tester = AutoTestAndRLDataGenerator(
        bot_to_test=bot,
        memory_test_cases=all_cases
    )

    run_result = tester.run_full_auto_judge_test(
        pause_mode=False,
        memory_reset_mode=False,
        upload_history_to_volc_memory=False,
    )

    tester.write_test_task_report(
        dataset_names=[],
        result_str=run_result.result,
        total_case_num=run_result.total_case_num,
        passed_case_num=run_result.passed_case_num,
        pass_rate=run_result.pass_rate,
        execution_success_num=run_result.execution_success_num,
        execution_success_rate=run_result.execution_success_rate,
        tags_correct_number_and_rate=run_result.tags_correct_number_and_rate,
        report_file_path=REPORT_FILE_PATH,
    )

    bot.close()
    print(f"\n测试报告已写入：{REPORT_FILE_PATH}")

import pytest
import asyncio

from projects.mind.mem.auto_test_script.auto_tagger import auto_tag_case_with_llm
from projects.mind.mem.auto_test_script.case_schema import TestCase as CaseSchema
from projects.mind.mem.auto_test_script.langchain_models import doubao_model
from projects.mind.mem.auto_test_script.auto_tagger.tag_tree_schema import TagTree, TagTreeNode
from projects.mind.mem.volc_api import Message


class FakeLLM:
    def __init__(self, output: str) -> None:
        self.output = output

    async def ainvoke(self, _: str) -> str:
        return self.output


class SequenceFakeLLM:
    """按顺序返回预设输出，便于测试重试链路。"""

    def __init__(self, outputs: list[str]) -> None:
        self.outputs = outputs
        self.calls = 0

    async def ainvoke(self, _: str) -> str:
        idx = min(self.calls, len(self.outputs) - 1)
        self.calls += 1
        return self.outputs[idx]


def build_demo_case() -> CaseSchema:
    return CaseSchema(
        id="case-001",
        case_id="导航单轮查询",
        context_config={"scene": "驾驶中"},
        user_query_lists=[
            [Message(role="user", content="导航去最近的加油站")],
        ],
        expected_script="助手应调用导航能力并给出路线建议",
        nl_assertion=["应该理解导航意图", "应返回导航相关结果"],
        case_description="用户在驾驶中发起导航请求",
    )


def build_demo_tree() -> TagTree:
    return TagTree(
        root=TagTreeNode(
            name="测试用例标签",
            children=[
                TagTreeNode(name="能力维度", children=[TagTreeNode(name="导航"), TagTreeNode(name="车控")]),
                TagTreeNode(name="对话维度", children=[TagTreeNode(name="单轮对话"), TagTreeNode(name="多轮对话")]),
            ],
        )
    )


def build_complex_tree() -> TagTree:
    """构造一个覆盖能力/结构/记忆/skill四维度的测试树。"""
    return TagTree(
        tagging_guideline="按能力、对话结构、记忆机制、skill机制综合打标。",
        root=TagTreeNode(
            name="测试用例标签",
            children=[
                TagTreeNode(
                    name="能力维度",
                    children=[
                        TagTreeNode(name="导航"),
                        TagTreeNode(name="多媒体控制"),
                        TagTreeNode(name="车控"),
                        TagTreeNode(name="工具编排"),
                    ],
                ),
                TagTreeNode(
                    name="对话结构",
                    children=[
                        TagTreeNode(name="单轮对话"),
                        TagTreeNode(name="多轮对话"),
                        TagTreeNode(name="跨多轮对话"),
                    ],
                ),
                TagTreeNode(
                    name="记忆机制",
                    children=[
                        TagTreeNode(name="长期记忆"),
                        TagTreeNode(name="音乐偏好"),
                    ],
                ),
                TagTreeNode(
                    name="Skill机制",
                    children=[
                        TagTreeNode(name="skill创建"),
                        TagTreeNode(name="skill复用"),
                    ],
                ),
            ],
        ),
    )


def test_auto_tag_case_with_llm_success() -> None:
    test_case = build_demo_case()
    tree = build_demo_tree()
    llm = FakeLLM('{"tags": ["导航", "单轮对话"]}')

    tags = asyncio.run(auto_tag_case_with_llm(test_case=test_case, tag_tree=tree, llm=llm))

    assert tags == ["导航", "单轮对话"]
    assert test_case.tags == ["导航", "单轮对话"]


def test_auto_tag_case_with_llm_invalid_tag() -> None:
    test_case = build_demo_case()
    tree = build_demo_tree()
    llm = FakeLLM('{"tags": ["不存在标签"]}')

    with pytest.raises(ValueError, match="不是叶子节点标签"):
        asyncio.run(auto_tag_case_with_llm(test_case=test_case, tag_tree=tree, llm=llm))


def test_auto_tag_case_with_llm_retry_then_success() -> None:
    test_case = build_demo_case()
    tree = build_demo_tree()
    # 第一次返回非法标签，第二次返回合法标签，应在重试后成功。
    llm = SequenceFakeLLM(['{"tags": ["不存在标签"]}', '{"tags": ["导航", "单轮对话"]}'])

    tags = asyncio.run(auto_tag_case_with_llm(test_case=test_case, tag_tree=tree, llm=llm, max_retries=3))

    assert llm.calls == 2
    assert tags == ["导航", "单轮对话"]
    assert test_case.tags == ["导航", "单轮对话"]


def test_auto_tag_case_with_llm_retry_exhausted() -> None:
    test_case = build_demo_case()
    tree = build_demo_tree()
    llm = SequenceFakeLLM(['{"tags": ["不存在标签"]}'])

    with pytest.raises(ValueError, match="已达到最大重试次数\\(3\\)"):
        asyncio.run(auto_tag_case_with_llm(test_case=test_case, tag_tree=tree, llm=llm, max_retries=3))
    assert llm.calls == 4


def test_auto_tag_four_distinct_cases_with_complex_tree() -> None:
    """
    真实模型回归测试：
    - 用4个语义差异明显的case观察打标质量；
    - 采用“关键标签子集”断言，避免对真实模型做过度脆弱的全量等值校验。
    """
    tree = build_complex_tree()
    llm = doubao_model

    case_nav_memory = CaseSchema(
        id="c-1001",
        case_id="nav-memory-001",
        context_config={"scene": "通勤"},
        user_query_lists=[
            [Message(role="user", content="记一下，我家在嘉定")],
            [Message(role="user", content="回家")],
        ],
        expected_script="助手在后续会话中根据记忆地址完成回家导航。",
        nl_assertion=["应体现跨会话记忆更新后的导航行为"],
        case_description="验证导航与长期记忆联动。",
    )
    case_climate_single = CaseSchema(
        id="c-1002",
        case_id="climate-single-001",
        context_config={"scene": "车内闷热"},
        user_query_lists=[[Message(role="user", content="把空调调到22度并打开座椅通风")]],
        expected_script="助手立即执行车控操作。",
        nl_assertion=["应正确理解并执行车控指令"],
        case_description="验证单轮车控执行。",
    )
    case_music_pref = CaseSchema(
        id="c-1003",
        case_id="music-pref-001",
        context_config={"scene": "周五下班"},
        user_query_lists=[
            [Message(role="user", content="播放周杰伦")],
            [Message(role="user", content="我每周五下班喜欢听谁？")],
        ],
        expected_script="助手能基于多次历史播放形成偏好记忆并回答。",
        nl_assertion=["应体现跨多轮偏好记忆"],
        case_description="验证音乐偏好沉淀与复用。",
    )
    case_skill_reuse = CaseSchema(
        id="c-1004",
        case_id="skill-reuse-001",
        context_config={"scene": "上班前"},
        user_query_lists=[
            [Message(role="user", content="打开空调+导航到公司+播放新闻，记成上班连招")],
            [Message(role="user", content="开启上班连招")],
        ],
        expected_script="首次创建skill，后续通过短触发语复用skill执行组合动作。",
        nl_assertion=["应体现skill创建与复用链路"],
        case_description="验证工具编排和skill复用。",
    )

    must_include_tags = {
        # 每个case的最低合理命中集合：用于评估“是否抓住核心语义”。
        "nav-memory-001": {"导航", "长期记忆"},
        "climate-single-001": {"车控"},
        "music-pref-001": {"多媒体控制", "音乐偏好"},
        "skill-reuse-001": {"skill创建", "skill复用"},
    }

    for case in [case_nav_memory, case_climate_single, case_music_pref, case_skill_reuse]:
        tags = asyncio.run(auto_tag_case_with_llm(test_case=case, tag_tree=tree, llm=llm))
        print(f"{case.case_id} -> {tags}")
        assert len(tags) >= 1
        assert set(must_include_tags[case.case_id]).issubset(set(tags))
        assert case.tags == tags


if __name__ == "__main__":
    # 允许直接运行该文件，直接执行目标测试函数。
    test_auto_tag_four_distinct_cases_with_complex_tree()


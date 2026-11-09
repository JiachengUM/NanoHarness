"""用真实 LLM / Agent 检验 AutoTest 提示词质量。

重点不是 Python 边界条件，而是观察：
1. FakePerson 会不会把 expected_script 中用户本不该知道/主动说出的信息泄漏出来；
2. FakePerson 在 user_profile、car_info、expected_script 冲突时依据什么行动；
3. Judge 会不会把 expected_script 当唯一标准，误判语义等价或更合理的回答；
4. Judge 能否识别部分完成、口头声称完成和真实工具执行之间的差异；
5. Judge 面对含糊或互相拉扯的自然语言断言是否稳定。

运行方式：
    .venv/bin/python \
        projects/mind/mem/auto_test_script/auto_test_demos/demo_framework_edge_cases.py

本脚本会调用真实的 DemoAgentV1Bot、FakePerson LLM 和 Judge LLM，运行前需准备与 demo_auto_test.py 相同的模型和服务配置。
"""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from rich import print

from projects.mind.mem.auto_test_script.auto_test_and_rl_data_generator import (
    AutoTestAndRLDataGenerator,
    RunAllCasesResult,
    RunCaseResult,
)
from projects.mind.mem.auto_test_script.auto_test_demos.demo_auto_test import (
    DemoAgentV1Bot,
    example_input_params,
)
from projects.mind.mem.auto_test_script.auto_test_demos.demo_database_cases import (
    DATABASE_CASES,
)
from projects.mind.mem.auto_test_script.case_schema import TestCase
from projects.mind.mem.volc_api import Message


REPORT_DIR = Path(__file__).resolve().parent.parent / "auto_test_report"
JUDGE_LOG_PATH = REPORT_DIR / "prompt_quality_probe.txt"
DATASET_NAMES = ["AutoTest 提示词质量探针"]


def _context(**overrides):
    """沿用 demo_auto_test.py 的真实 Agent 配置，只覆盖探针需要的上下文。"""
    result = example_input_params.model_dump(exclude_none=True)
    result.update(overrides)
    # 每个 case 的 user_id 后续仍会由 AutoTest 按 case_id 隔离。
    return result


PROMPT_QUALITY_CASES = [
    TestCase(
        id="prompt-fake-person-hidden-detail-leak",
        case_id="假人是否泄漏剧本中的隐藏目的地",
        context_config=_context(
            user_profile="用户准备出门，但尚未决定目的地，也没有固定偏好。",
            car_info="车辆停在上海市中心，导航尚未启动。",
        ),
        max_round=6,
        user_query_lists=[[Message(role="user", content="帮我规划一下出门的路线。")]],
        expected_script="""
用户：帮我规划一下出门的路线。
助手：请问您想去哪里？
用户：去上海博物馆东馆。（注意：该目的地此前没有告诉助手）
助手：为用户规划去上海博物馆东馆的路线。
用户：谢谢，退下吧，我给你打5分。
""",
        nl_assertion=[
            "助手面对缺少目的地的请求，应先澄清目的地，不能擅自导航。",
            "只有在用户明确说出目的地后，助手才能发起相应导航。",
        ],
        case_description=(
            "观察 FakePerson 是否直接从 expected_script 获得并说出隐藏目的地。"
            "如果它能说出，说明测试后续输入由答案剧本强引导，而不是由用户既有信息自然产生。"
        ),
        tags=["FakePerson提示词", "剧本信息泄漏", "澄清能力"],
    ),
    TestCase(
        id="prompt-fake-person-profile-script-conflict",
        case_id="用户人设与预期剧本冲突",
        context_config=_context(
            user_profile=(
                "用户对花生严重过敏，明确要求任何餐厅推荐都必须避开花生相关菜品；"
                "用户非常谨慎，不会接受不确定的过敏风险。"
            ),
            car_info="车辆正在上海行驶。",
        ),
        max_round=6,
        user_query_lists=[[Message(role="user", content="给我推荐一家附近适合吃饭的地方。")]],
        expected_script="""
用户：给我推荐一家附近适合吃饭的地方。
助手：推荐一家以花生酱拌面为招牌的餐厅。
用户：听起来不错，就导航去那里吧。
助手：开始导航。
用户：谢谢，退下吧，我给你打5分。
""",
        nl_assertion=[
            "助手必须尊重用户严重花生过敏的信息，不得推荐存在明显花生风险的餐厅。",
            "FakePerson 也不应违反其明确人设，接受明显危险的推荐。",
        ],
        case_description=(
            "FakePerson prompt 同时要求只能根据基本信息回复、又要求参考预期剧本。"
            "这里用冲突输入观察模型究竟服从人设还是照着剧本演。"
        ),
        tags=["FakePerson提示词", "冲突指令", "用户人设"],
    ),
    TestCase(
        id="prompt-fake-person-unjustified-knowledge",
        case_id="假人是否凭剧本拥有未提供的事实",
        context_config=_context(
            user_profile="用户对自己的车辆配置不熟悉，需要助手基于可用信息谨慎确认。",
            car_info="当前上下文没有提供车辆剩余续航，也没有充电站状态数据。",
        ),
        max_round=6,
        user_query_lists=[[Message(role="user", content="我能直接开到杭州吗？")]],
        expected_script="""
用户：我能直接开到杭州吗？
助手：询问当前续航或说明无法确定。
用户：现在续航还剩420公里。（注意：该数字只存在于参考剧本）
助手：结合路线距离给出谨慎建议。
用户：谢谢，退下吧，我给你打5分。
""",
        nl_assertion=[
            "在上下文没有续航数据时，助手应承认信息不足并澄清。",
            "评测对话不得把仅写在 expected_script 中的420公里当成用户原本已知且必然正确的事实。",
        ],
        case_description=(
            "检查 expected_script 是否事实上充当 FakePerson 的隐藏知识库，"
            "导致评测自动补齐原始 case 未提供的关键事实。"
        ),
        tags=["FakePerson提示词", "知识边界", "剧本信息泄漏"],
    ),
    TestCase(
        id="prompt-judge-semantic-equivalence",
        case_id="Judge能否接受偏离剧本措辞的合理替代方案",
        context_config=_context(
            user_profile="用户希望尽快到达目的地，能接受合理的路线替代方案。",
            car_info="前方主路临时封闭，存在可通行的绕行路线。",
        ),
        max_round=6,
        user_query_lists=[[Message(role="user", content="导航去上海南站，尽量快一点。")]],
        expected_script="""
用户：导航去上海南站，尽量快一点。
助手：选择主路并开始导航。
用户：谢谢，退下吧，我给你打5分。
""",
        nl_assertion=[
            "助手应成功规划一条当前可通行、目标为上海南站且尽量快的路线。",
            "路线不必与参考剧本中的主路一致；在主路封闭时选择绕行路线应视为正确。",
        ],
        case_description=(
            "expected_script 给出主路，但 car_info 明确主路封闭。"
            "观察 Judge 是依据任务效果接受更合理的绕行，还是机械比对参考剧本。"
        ),
        tags=["Judge提示词", "语义等价", "剧本依赖"],
    ),
    TestCase(
        id="prompt-judge-partial-completion",
        case_id="多任务只完成一部分是否会被Judge放过",
        context_config=_context(
            user_profile="用户希望一次完成多个明确操作。",
            car_info="前排车窗关闭，音乐未播放，当前没有导航任务。",
        ),
        max_round=6,
        user_query_lists=[[
            Message(
                role="user",
                content="打开前排车窗，播放周杰伦的歌，再导航去上海虹桥站。",
            )
        ]],
        expected_script="""
用户：打开前排车窗，播放周杰伦的歌，再导航去上海虹桥站。
助手：依次完成车窗、音乐和导航三个任务，并明确反馈各项结果。
用户：请确认三个任务是不是都完成了。
助手：如实确认三个任务的执行结果。
用户：谢谢，退下吧，我给你打5分。
""",
        nl_assertion=[
            "必须完成打开前排车窗、播放周杰伦歌曲、导航到上海虹桥站三个子任务，缺一不可。",
            "不能仅凭助手口头声称完成；互动历史或工具轨迹应能支持三个动作确实执行。",
        ],
        case_description=(
            "检查 Judge 能否逐项核对复合任务，而不是因为回复流畅或完成其中大部分就判通过。"
        ),
        tags=["Judge提示词", "部分完成", "工具调用"],
    ),
    TestCase(
        id="prompt-judge-claim-vs-evidence",
        case_id="Judge是否区分口头承诺与实际执行证据",
        context_config=_context(
            user_profile="用户要求助手真正执行车辆操作，而不是只给操作说明。",
            car_info="空调当前关闭。",
        ),
        max_round=6,
        user_query_lists=[[Message(role="user", content="把空调打开到22度。")]],
        expected_script="""
用户：把空调打开到22度。
助手：调用空调控制工具，把温度设为22度，然后反馈执行结果。
用户：你是真的设置好了，还是只告诉我怎么设置？
助手：基于真实工具结果回答。
用户：谢谢，退下吧，我给你打5分。
""",
        nl_assertion=[
            "必须存在支持空调已开启且温度为22度的工具调用或状态证据。",
            "只有自然语言承诺、没有执行证据时必须判定不通过。",
        ],
        case_description=(
            "Judge prompt 虽会看到 dump_history 的任意字段，但没有明确的工具证据判定规则。"
            "该 case 检查它是否会把助手自述当成事实。"
        ),
        tags=["Judge提示词", "证据判断", "工具调用"],
    ),
    TestCase(
        id="prompt-judge-conservative-clarification",
        case_id="谨慎澄清是否会被剧本中的直接执行压制",
        context_config=_context(
            user_profile="用户重视安全，地点有歧义时希望助手先确认。",
            car_info="附近同时有两个名称相同的‘人民公园’，分别位于不同城区。",
        ),
        max_round=6,
        user_query_lists=[[Message(role="user", content="导航去人民公园。")]],
        expected_script="""
用户：导航去人民公园。
助手：直接选择最近的人民公园并开始导航。
用户：谢谢，退下吧，我给你打5分。
""",
        nl_assertion=[
            "存在两个同名目的地时，助手先澄清具体地点属于正确且更安全的行为。",
            "未经确认直接选择其中一个目的地不应获得更高评价。",
        ],
        case_description=(
            "检查 Judge 是否把 expected_script 的直接执行当成黄金路径，"
            "从而惩罚实际更符合用户人设和安全要求的澄清行为。"
        ),
        tags=["Judge提示词", "澄清能力", "剧本依赖"],
    ),
] + DATABASE_CASES


CASE_OBSERVATIONS = {
    "prompt-fake-person-hidden-detail-leak": "看用户后续是否自然说出只有剧本中才有的‘上海博物馆东馆’。",
    "prompt-fake-person-profile-script-conflict": "看假人是否违反严重过敏人设，接受剧本安排的危险餐厅。",
    "prompt-fake-person-unjustified-knowledge": "看假人是否自动补出剧本中的420公里。",
    "prompt-judge-semantic-equivalence": "若助手合理绕行，Judge是否仍因偏离‘主路’而判失败。",
    "prompt-judge-partial-completion": "核对三个子任务及其工具轨迹，不只看最终措辞。",
    "prompt-judge-claim-vs-evidence": "核对Judge是否要求工具证据，而非相信助手自述。",
    "prompt-judge-conservative-clarification": "看合理澄清是否被直接执行剧本压低评价。",
    "device-v1-create-winter-climate-preference": (
        "与画像状态版对照：自然语言确认正确，不代表 device_v1 中真的创建了完整偏好。"
    ),
    "device-v1-update-winter-climate-preference": (
        "与画像状态版对照：Judge无法仅凭回复确认后台是覆盖旧偏好，还是追加了新旧冲突条目。"
    ),
}


def _select_cases(case_ids: list[str]) -> list[TestCase]:
    if not case_ids:
        return PROMPT_QUALITY_CASES
    wanted = set(case_ids)
    selected = [case for case in PROMPT_QUALITY_CASES if case.id in wanted]
    missing = wanted - {case.id for case in selected}
    if missing:
        raise ValueError(f"未知 case id: {sorted(missing)}")
    return selected


async def _run(cases: list[TestCase], *, epoch: int) -> RunAllCasesResult:
    auto_test = AutoTestAndRLDataGenerator(
        bot_to_test=DemoAgentV1Bot,
        memory_test_cases=cases,
        give_score=True,
        verbose=True,
        log_dialogue=True,
        show_progress=False,
    )

    final_result: RunAllCasesResult | None = None
    async for item in auto_test.arun_full_auto_judge_test(
        # 真实 LLM 的波动本身是本探针要观察的内容；epoch > 1 时仍保持串行，
        # 避免并发限流和共享外部状态污染结论。
        concurrency_mode=False,
        concurrency_num=1,
        pause_mode=False,
        # device_v1 对照 case 必须从空画像开始；其他探针也因此获得可复现初态。
        memory_reset_mode=True,
        upload_history_to_volc_memory=False,
        memory_reset_except_skills=False,
        epoch=epoch,
        long_term_use=False,
    ):
        if isinstance(item, RunCaseResult):
            print(
                f"[case] {item.id}: execution_success={item.execution_success}, "
                f"is_passed={item.is_passed}"
            )
            print(f"观察重点：{CASE_OBSERVATIONS[item.id]}")
            print(f"Judge理由：{item.reason}\n")
        elif isinstance(item, RunAllCasesResult):
            final_result = item

    assert final_result is not None, "未收到最终 RunAllCasesResult"
    auto_test.write_test_task_judge_log(
        dataset_names=DATASET_NAMES,
        total_case_num=final_result.total_case_num,
        passed_case_num=final_result.passed_case_num,
        pass_rate=final_result.pass_rate,
        execution_success_num=final_result.execution_success_num,
        execution_success_rate=final_result.execution_success_rate,
        tags_correct_number_and_rate=final_result.tags_correct_number_and_rate,
        judge_result=final_result.result,
        log_file_path=str(JUDGE_LOG_PATH),
        epoch=epoch,
        details_result_list=final_result.details_result_list,
    )
    return final_result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="运行 AutoTest 真实 LLM 提示词质量探针")
    parser.add_argument(
        "--case",
        action="append",
        default=[],
        help="只运行指定 case id；可重复传入。默认运行全部。",
    )
    parser.add_argument(
        "--epoch",
        type=int,
        default=1,
        help="重复运行次数。建议设为3以观察 FakePerson/Judge 稳定性。",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.epoch < 1:
        raise ValueError("--epoch 必须为正整数")
    selected_cases = _select_cases(args.case)
    print(f"将运行 {len(selected_cases)} 个提示词探针，epoch={args.epoch}")
    result = asyncio.run(_run(selected_cases, epoch=args.epoch))
    print(
        f"完成：执行成功 {result.execution_success_num}/{result.total_case_num}，"
        f"Judge通过 {result.passed_case_num}/{result.execution_success_num}"
    )
    print(f"详细对话与Judge结果：{JUDGE_LOG_PATH}")

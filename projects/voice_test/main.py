"""物理语音链路自动评测入口。

运行方式：
    .venv/bin/python projects/voice_test/main.py
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from rich import print

from projects.mind.mem.auto_test_script.auto_test_and_rl_data_generator import (
    AutoTestAndRLDataGenerator,
    RunAllCasesResult,
    RunCaseResult,
)
from projects.mind.mem.auto_test_script.auto_test_demos.demo_auto_test import example_case
from projects.mind.mem.auto_test_script.auto_test_demos.get_datasets import (
    get_dataset_list,
)
from projects.mind.mem.auto_test_script.case_schema import TestCase
from projects.mind.mem.volc_api import Message

from projects.voice_test.bots.physical_voice_bot import PhysicalVoiceBot

DATASET_NAMES = ["奔驰项目多轮对话测试集"]
REPORT_DIR = Path(__file__).resolve().parent / "output"
JUDGE_LOG_PATH = REPORT_DIR / "benz_demo_judge_log.txt"
REPORT_MD_PATH = REPORT_DIR / "benz_demo_report.md"


example_case  = TestCase(
    id = "example_case",
    case_id="example_case",
    context_config={},
    max_round=5,
    user_query_lists=[[Message(role="user", content="打开前排车窗，并播放音乐")]],
    expected_script="""
    用户：打开前排的车窗，并播放音乐
    助手：好的，正在打开前排车窗，并播放音乐。
    用户：后排车窗也打开吧。
    助手：好的xxxx。
    """,
    nl_assertion=[
        "考察智能体是否能正确理解车主的需求解决问题。",
    ],
    case_description="这是一个考察智能体是否能正确理解车主的需求解决问题的case。"
)

async def main() -> None:
    cases = await get_dataset_list(DATASET_NAMES)
    cases = [example_case]

    auto_test = AutoTestAndRLDataGenerator(
        bot_to_test=PhysicalVoiceBot,
        memory_test_cases=cases,
        show_progress=False,
        log_dialogue=True,
        verbose=True,
    )

    run_result: RunAllCasesResult | None = None
    try:
        async for item in auto_test.arun_full_auto_judge_test(
            concurrency_mode=False,
            concurrency_num=1,
            pause_mode=False,
            memory_reset_mode=False,
            upload_history_to_volc_memory=False,
        ):
            if isinstance(item, RunCaseResult):
                print(
                    f"[完成] case_id={item.case_id}, "
                    f"execution_success={item.execution_success}, "
                    f"is_passed={item.is_passed}"
                )
            elif isinstance(item, RunAllCasesResult):
                run_result = item
    except KeyboardInterrupt:
        print("\n评测已由用户中断")
    finally:
        await PhysicalVoiceBot.close_adapter()

    if run_result is None:
        return

    auto_test.write_test_task_judge_log(
        dataset_names=DATASET_NAMES,
        total_case_num=run_result.total_case_num,
        passed_case_num=run_result.passed_case_num,
        pass_rate=run_result.pass_rate,
        execution_success_num=run_result.execution_success_num,
        execution_success_rate=run_result.execution_success_rate,
        tags_correct_number_and_rate=run_result.tags_correct_number_and_rate,
        judge_result=run_result.result,
        log_file_path=str(JUDGE_LOG_PATH),
        details_result_list=run_result.details_result_list,
    )
    auto_test.write_test_task_report(
        dataset_names=DATASET_NAMES,
        result_str=run_result.result,
        total_case_num=run_result.total_case_num,
        passed_case_num=run_result.passed_case_num,
        pass_rate=run_result.pass_rate,
        execution_success_num=run_result.execution_success_num,
        execution_success_rate=run_result.execution_success_rate,
        tags_correct_number_and_rate=run_result.tags_correct_number_and_rate,
        report_file_path=str(REPORT_MD_PATH),
    )

    print(f"评测完成: {run_result.passed_case_num}/{run_result.total_case_num}")
    print(f"日志: {JUDGE_LOG_PATH}")
    print(f"报告: {REPORT_MD_PATH}")


if __name__ == "__main__":
    asyncio.run(main())

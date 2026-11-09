"""
S2S 语音服务自动化评测 demo。

数据与 ``benz_auto_test_demo.py`` 对齐，使用「奔驰项目多轮对话测试集」；
``bot_to_test`` 为 ``S2SVoiceBot``（WebSocket 文本注入 + 流式回复合并）。

评测约定：
- ``user_query_lists`` 每条子列表只放第一句用户台词；
- 后续台词由 ``FakePerson`` 按 ``expected_script`` 生成；
- 同一段多轮共享 ``session_id``，在同一 WebSocket 上连续 ``achat``。
"""

import asyncio
from pathlib import Path

from rich import print

from projects.mind.mem.auto_test_script.auto_test_and_rl_data_generator import (
    AutoTestAndRLDataGenerator,
    RunAllCasesResult,
    RunCaseResult,
)
from projects.mind.mem.auto_test_script.auto_tagger.tag_tree_schema import TagTree
from projects.mind.mem.auto_test_script.auto_test_demos.get_datasets import (
    get_dataset_list_sync,
)
from projects.mind.mem.auto_test_script.auto_test_demos.benz_demo.s2s_voice_bot import S2SVoiceBot

from projects.mind.mem.auto_test_script.case_schema import TestCase
from projects.mind.mem.volc_api import Message

example_case  = TestCase(
    id = "example_case",
    case_id="example_case",
    context_config={},
    max_round=5,
    user_query_lists=[[Message(role="user", content="打开前排车窗，并播放音乐")]],
    expected_script="""
    用户：打开前排和后排的车窗，并播放音乐
    助手：好的，正在打开前排车窗，并播放音乐。可能包含指令信息。
    用户：后排车窗也打开吧。
    助手：好的xxxx。
    """,
    nl_assertion=[
        "考察智能体是否能正确理解车主的需求解决问题。",
        "对应的指令信息要包含在回复中。"
    ],
    case_description="这是一个考察智能体是否能正确理解车主的需求解决问题的case。"
)

if __name__ == "__main__":
    dataset_names = ["奔驰项目多轮对话测试集"]

    # cases_to_run = get_dataset_list_sync(dataset_names)
    cases_to_run = [example_case]
    # print(cases_to_run)
    auto_test = AutoTestAndRLDataGenerator(
        bot_to_test=S2SVoiceBot,
        memory_test_cases=cases_to_run,
        verbose=True,
        log_dialogue=True,
        show_progress=False,
    )

    RUN_EPOCH = 1

    async def _run_stream_and_collect_final() -> RunAllCasesResult:
        final_result: RunAllCasesResult | None = None
        async for item in auto_test.arun_full_auto_judge_test(
            concurrency_mode=False, # 必须设置为False
            concurrency_num=1,
            pause_mode=False,
            memory_reset_mode=False,
            upload_history_to_volc_memory=False,
            memory_reset_except_skills=False,
            epoch=RUN_EPOCH,
            long_term_use=False,
        ):
            if isinstance(item, RunCaseResult):
                pass
            elif isinstance(item, RunAllCasesResult):
                final_result = item
        assert final_result is not None, "未收到最终 RunAllCasesResult"
        return final_result

    run_all_cases_result = asyncio.run(_run_stream_and_collect_final())

    detail_results_list = run_all_cases_result.details_result_list
    result = run_all_cases_result.result
    total_case_num = run_all_cases_result.total_case_num
    passed_case_num = run_all_cases_result.passed_case_num
    pass_rate = run_all_cases_result.pass_rate
    tags_correct_number_and_rate = run_all_cases_result.tags_correct_number_and_rate

    judge_log_file_path = (
        r"projects\mind\mem\auto_test_script\auto_test_demos\benz_demo\s2s_auto_test_report.txt"
    )
    auto_test.write_test_task_judge_log(
        dataset_names=dataset_names,
        total_case_num=total_case_num,
        passed_case_num=passed_case_num,
        pass_rate=pass_rate,
        execution_success_num=run_all_cases_result.execution_success_num,
        execution_success_rate=run_all_cases_result.execution_success_rate,
        tags_correct_number_and_rate=tags_correct_number_and_rate,
        judge_result=result,
        log_file_path=judge_log_file_path,
        epoch=RUN_EPOCH,
        details_result_list=detail_results_list,
    )

    print(
        f"S2S 评测完成: 通过 {passed_case_num}/{total_case_num}, "
        f"通过率 {pass_rate:.1%}, 日志 {judge_log_file_path}"
    )

from io import BytesIO
from types import SimpleNamespace

from openpyxl import load_workbook

from projects.mind.test_backend.service.task.task_run_export_service import (
    build_task_run_export_workbook,
)


def test_build_task_run_export_workbook_includes_summary_and_case_detail():
    task = SimpleNamespace(id="task_1", name="意图路由回归")
    task_run = SimpleNamespace(
        id="run_1",
        status="completed",
        progress=SimpleNamespace(total=1, completed=1, success=1, failed=0),
        metadata={"pass_rate": 1.0, "time_avg": 88.7},
    )
    run_item = SimpleNamespace(
        id="item_1",
        dataset_item_id="case_doc_1",
        status="completed",
        metadata={"time": 88.7, "result": "simple"},
        created_time="2026-05-29 10:00:00",
    )
    case = SimpleNamespace(
        id="case_doc_1",
        case_id="case-001",
        user_query_lists=[[SimpleNamespace(role="user", content="打开空调")]],
        tags=["车控", "simple"],
        nl_assertion=["应识别为简单车控"],
        code_assertion={"intent_type": "simple"},
        case_description="车控简单指令",
    )
    eval_doc = SimpleNamespace(
        llm_evaluation=SimpleNamespace(is_pass=True, comment="模型通过"),
        human_evaluation=SimpleNamespace(score=1.0, is_pass=True, comment="人工通过"),
    )
    messages = [
        SimpleNamespace(role="user", content="打开空调"),
        SimpleNamespace(role="assistant", content="已为你打开空调"),
    ]

    excel_bytes = build_task_run_export_workbook(
        task=task,
        task_run=task_run,
        run_items=[run_item],
        case_map={"case_doc_1": case},
        eval_map={"item_1": eval_doc},
        message_map={"item_1": messages},
    )

    workbook = load_workbook(BytesIO(excel_bytes))

    assert workbook.sheetnames == ["运行汇总", "运行明细"]
    summary_sheet = workbook["运行汇总"]
    assert summary_sheet["A1"].value == "任务名称"
    assert summary_sheet["B1"].value == "意图路由回归"
    assert summary_sheet["A4"].value == "通过率"
    assert summary_sheet["B4"].value == "100.00%"

    detail_sheet = workbook["运行明细"]
    headers = [cell.value for cell in detail_sheet[1]]
    assert headers == [
        "任务运行项ID",
        "Case ID",
        "测试用例ID",
        "用户输入",
        "标签",
        "运行状态",
        "模型是否通过",
        "模型评价",
        "人工是否通过",
        "人工得分",
        "人工评价",
        "耗时(ms)",
        "执行结果",
        "自然语言断言",
        "代码断言",
        "用例描述",
        "对话记录",
        "创建时间",
    ]
    assert detail_sheet["B2"].value == "case-001"
    assert detail_sheet["D2"].value == "打开空调"
    assert detail_sheet["E2"].value == "车控, simple"
    assert detail_sheet["G2"].value == "通过"
    assert detail_sheet["L2"].value == 88.7
    assert "assistant: 已为你打开空调" in detail_sheet["Q2"].value

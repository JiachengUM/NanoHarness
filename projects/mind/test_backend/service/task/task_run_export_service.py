from __future__ import annotations

import json
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.worksheet.worksheet import Worksheet


DETAIL_HEADERS = [
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


def build_task_run_export_filename(task_run: Any) -> str:
    return f"task_run_{_get_id(task_run)}.xlsx"


def build_task_run_export_workbook(
    *,
    task: Any | None,
    task_run: Any,
    run_items: list[Any],
    case_map: dict[str, Any],
    eval_map: dict[str, Any],
    message_map: dict[str, list[Any]],
) -> bytes:
    workbook = Workbook()
    summary_sheet = workbook.active
    summary_sheet.title = "运行汇总"
    detail_sheet = workbook.create_sheet("运行明细")

    _write_summary_sheet(summary_sheet, task, task_run, len(run_items))
    _write_detail_sheet(
        detail_sheet,
        task_run,
        run_items,
        case_map,
        eval_map,
        message_map,
    )
    _autosize_columns(summary_sheet)
    _autosize_columns(detail_sheet)

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _write_summary_sheet(
    sheet: Worksheet, task: Any | None, task_run: Any, run_item_count: int
) -> None:
    progress = _get_attr(task_run, "progress")
    metadata = _get_metadata(task_run)
    rows = [
        ("任务名称", _get_attr(task, "name") if task else ""),
        ("任务ID", _get_id(task) if task else ""),
        ("任务运行ID", _get_id(task_run)),
        ("通过率", _format_percent(metadata.get("pass_rate"))),
        ("运行状态", _get_attr(task_run, "status", "")),
        ("总用例数", _get_attr(progress, "total", run_item_count)),
        ("已完成", _get_attr(progress, "completed", "")),
        ("成功", _get_attr(progress, "success", "")),
        ("失败", _get_attr(progress, "failed", "")),
        ("平均耗时(ms)", metadata.get("time_avg", "")),
        ("P50耗时(ms)", metadata.get("time_p50", "")),
        ("P90耗时(ms)", metadata.get("time_p90", "")),
        ("P99耗时(ms)", metadata.get("time_p99", "")),
    ]
    for row in rows:
        sheet.append(row)
    _style_header_row(sheet, row_number=1)


def _write_detail_sheet(
    sheet: Worksheet,
    task_run: Any,
    run_items: list[Any],
    case_map: dict[str, Any],
    eval_map: dict[str, Any],
    message_map: dict[str, list[Any]],
) -> None:
    sheet.append(DETAIL_HEADERS)
    _style_header_row(sheet, row_number=1)
    sheet.freeze_panes = "A2"

    for run_item in run_items:
        run_item_id = _get_id(run_item)
        dataset_item_id = _stringify(_get_attr(run_item, "dataset_item_id", ""))
        case = case_map.get(dataset_item_id)
        eval_doc = eval_map.get(run_item_id)
        llm_eval = _get_attr(eval_doc, "llm_evaluation")
        human_eval = _get_attr(eval_doc, "human_evaluation")
        metadata = _get_metadata(run_item)

        sheet.append(
            [
                run_item_id,
                _get_attr(case, "case_id", ""),
                dataset_item_id,
                _extract_user_inputs(case),
                _format_tags(_get_attr(case, "tags", [])),
                _get_attr(run_item, "status", ""),
                _format_pass(_get_attr(llm_eval, "is_pass")),
                _get_attr(llm_eval, "comment", ""),
                _format_pass(_get_attr(human_eval, "is_pass")),
                _get_attr(human_eval, "score", ""),
                _get_attr(human_eval, "comment", ""),
                metadata.get("time", ""),
                _stringify(metadata.get("result", "")),
                _stringify(_get_attr(case, "nl_assertion", "")),
                _stringify(_get_attr(case, "code_assertion", "")),
                _get_attr(case, "case_description", ""),
                _format_messages(message_map.get(run_item_id, [])),
                _stringify(_get_attr(run_item, "created_time", "")),
            ]
        )


def _style_header_row(sheet: Worksheet, row_number: int) -> None:
    fill = PatternFill("solid", fgColor="D9EAF7")
    for cell in sheet[row_number]:
        cell.font = Font(bold=True)
        cell.fill = fill


def _autosize_columns(sheet: Worksheet) -> None:
    for column_cells in sheet.columns:
        column_letter = column_cells[0].column_letter
        max_length = max(len(_stringify(cell.value)) for cell in column_cells)
        sheet.column_dimensions[column_letter].width = min(
            max(max_length + 2, 10), 60
        )


def _get_attr(obj: Any, name: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _get_id(obj: Any) -> str:
    return _stringify(_get_attr(obj, "id", ""))


def _get_metadata(obj: Any) -> dict[str, Any]:
    metadata = _get_attr(obj, "metadata", {})
    return metadata if isinstance(metadata, dict) else {}


def _format_percent(value: Any) -> str:
    if value is None or value == "":
        return ""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return _stringify(value)
    if number <= 1:
        number *= 100
    return f"{number:.2f}%"


def _format_pass(value: Any) -> str:
    if value is True:
        return "通过"
    if value is False:
        return "未通过"
    return ""


def _format_tags(tags: Any) -> str:
    if isinstance(tags, list):
        return ", ".join(_stringify(tag) for tag in tags)
    return _stringify(tags)


def _extract_user_inputs(case: Any) -> str:
    sessions = _get_attr(case, "user_query_lists", []) or []
    user_inputs: list[str] = []
    for session in sessions:
        messages = _get_attr(session, "user_query_list", session)
        if not isinstance(messages, list):
            continue
        for message in messages:
            role = (_get_attr(message, "role", "") or "").lower()
            if role and role != "user":
                continue
            content = _get_attr(message, "content", "")
            if content:
                user_inputs.append(_stringify(content))
    return "\n".join(user_inputs)


def _format_messages(messages: list[Any]) -> str:
    lines = []
    for message in messages:
        role = _get_attr(message, "role", "")
        content = _get_attr(message, "content", "")
        if role or content:
            lines.append(f"{role}: {content}".strip())
    return "\n".join(lines)


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, default=str)
    return str(value)

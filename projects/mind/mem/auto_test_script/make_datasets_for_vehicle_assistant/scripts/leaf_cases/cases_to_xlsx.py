"""把100条case的JSON转成 xlsx 样式（参考 selected_20_user_lines.xlsx）

样式说明：
- 表头：蓝底白字加粗居中，自动换行
- 数据行：顶对齐，自动换行
- 同一case的多轮台词在同一序号下，序号/case_id/通过标准/标签/所属case编号 合并单元格
- 列：序号(A,6) | case_id(B,28) | 轮次(C,8) | 台词列(D,55) | 人工评价(E,25) | 通过标准(F,50) | 标签(G,30) | 所属case编号(H,20)
"""
import json
import re
from pathlib import Path
from copy import copy

import openpyxl
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

SRC = Path(r"d:\yitu_projects\nanoai\projects\mind\mem\auto_test_script\make_datasets_for_vehicle_assistant\artifacts\projects\benz_project\cases\vehicle_assistant_cases.json")
REF = Path(r"d:\yitu_projects\nanoai\projects\mind\mem\auto_test_script\make_datasets_for_vehicle_assistant\artifacts\projects\benz_project\cases\selected_20_user_lines.xlsx")
DST = Path(r"d:\yitu_projects\nanoai\projects\mind\mem\auto_test_script\make_datasets_for_vehicle_assistant\artifacts\projects\benz_project\cases\vehicle_assistant_cases_100.xlsx")


def extract_user_lines(case: dict) -> list[str]:
    """从 expected_script 提取用户台词（按轮次顺序），去掉前导段"""
    es = case.get("expected_script", "")
    if not isinstance(es, str):
        return []

    # 找到正文起点：第一个"用户："开头行
    lines = es.split("\n")
    user_lines = []
    in_body = False
    for line in lines:
        stripped = line.strip()
        # 跳过空行
        if not stripped:
            continue
        # 跳过前导段（重试先导段、盲选规则、简洁承接规则等）
        # 这些段不是"用户："或"管家："开头
        if not in_body:
            if stripped.startswith("用户：") or stripped.startswith("用户:"):
                in_body = True
            else:
                continue
        # 只取用户行
        if stripped.startswith("用户：") or stripped.startswith("用户:"):
            # 去掉"用户："前缀
            content = re.sub(r"^用户[：:]\s*", "", stripped)
            # 去掉行内序号 [1] [2] 等
            content = re.sub(r"^\[\d+\]\s*", "", content)
            user_lines.append(content)
    return user_lines


def make_nl_assertion_text(case: dict) -> str:
    """把 nl_assertion 列表转成编号文本"""
    assertions = case.get("nl_assertion", [])
    if not assertions:
        return ""
    if isinstance(assertions, str):
        return assertions
    return "\n".join(f"{i+1}. {a}" for i, a in enumerate(assertions))


def make_tags_text(case: dict) -> str:
    """把 tags 列表转成顿号分隔文本"""
    tags = case.get("tags", [])
    return "、".join(tags) if tags else ""


def main():
    data = json.loads(SRC.read_text(encoding="utf-8"))

    # 加载参考文件取样式
    ref_wb = openpyxl.load_workbook(REF)
    ref_ws = ref_wb.active

    # 创建新workbook
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "用户台词逐轮"

    # 表头
    headers = ["序号", "case_id", "轮次", "台词列", "人工评价", "通过标准", "标签", "所属case编号"]
    header_font = Font(bold=True, size=11, color="FFFFFF")
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    header_align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    thin_border = Border(
        left=Side(style="thin", color="B4B4B4"),
        right=Side(style="thin", color="B4B4B4"),
        top=Side(style="thin", color="B4B4B4"),
        bottom=Side(style="thin", color="B4B4B4"),
    )

    for c, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=c, value=h)
        cell.font = header_font
        cell.fill = header_fill
        cell.alignment = header_align
        cell.border = thin_border

    # 列宽
    col_widths = {"A": 6, "B": 28, "C": 8, "D": 55, "E": 25, "F": 50, "G": 30, "H": 20}
    for col, w in col_widths.items():
        ws.column_dimensions[col].width = w

    # 数据行样式
    data_font = Font(size=10)
    data_align = Alignment(vertical="top", wrap_text=True)
    center_align = Alignment(horizontal="center", vertical="top", wrap_text=True)

    # 写数据
    row_idx = 2
    for seq, case in enumerate(data, 1):
        case_id = case.get("case_id", "")
        case_num = case.get("id", "")
        user_lines = extract_user_lines(case)
        nl_text = make_nl_assertion_text(case)
        tags_text = make_tags_text(case)

        if not user_lines:
            # 没提取到台词，写一行占位
            ws.cell(row=row_idx, column=1, value=seq)
            ws.cell(row=row_idx, column=2, value=case_id)
            ws.cell(row=row_idx, column=3, value="第1轮")
            ws.cell(row=row_idx, column=4, value="(未提取到台词)")
            ws.cell(row=row_idx, column=6, value=nl_text)
            ws.cell(row=row_idx, column=7, value=tags_text)
            ws.cell(row=row_idx, column=8, value=case_num)
            for c in range(1, 9):
                cell = ws.cell(row=row_idx, column=c)
                cell.font = data_font
                cell.border = thin_border
                cell.alignment = center_align if c in (1, 3) else data_align
            row_idx += 1
            continue

        start_row = row_idx
        for i, line in enumerate(user_lines, 1):
            # 轮次
            ws.cell(row=row_idx, column=3, value=f"第{i}轮")
            # 台词
            ws.cell(row=row_idx, column=4, value=line)
            # 第1行填完整信息
            if i == 1:
                ws.cell(row=row_idx, column=1, value=seq)
                ws.cell(row=row_idx, column=2, value=case_id)
                ws.cell(row=row_idx, column=6, value=nl_text)
                ws.cell(row=row_idx, column=7, value=tags_text)
                ws.cell(row=row_idx, column=8, value=case_num)
            # 样式
            for c in range(1, 9):
                cell = ws.cell(row=row_idx, column=c)
                cell.font = data_font
                cell.border = thin_border
                cell.alignment = center_align if c in (1, 3) else data_align
            row_idx += 1

        end_row = row_idx - 1
        # 合并单元格（多轮才合并）
        if end_row > start_row:
            for col in [1, 2, 6, 7, 8]:
                ws.merge_cells(start_row=start_row, start_column=col, end_row=end_row, end_column=col)

    # 冻结首行
    ws.freeze_panes = "A2"

    # 保存
    wb.save(DST)
    print(f"已生成: {DST}")
    print(f"总case数: {len(data)}")
    print(f"总行数(含表头): {row_idx}")


if __name__ == "__main__":
    main()

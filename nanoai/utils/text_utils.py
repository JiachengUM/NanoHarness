import re
from enum import Enum
from typing import Any, Callable

import pandas as pd


# 主题和样式枚举定义
class Theme(Enum):
    """
    表格主题枚举

    提供预设的主题颜色方案，用于设置表格的整体外观。
    每个主题对应不同的CSS渐变背景色。

    Attributes:
        BLUE: 蓝色渐变主题（默认）
        GREEN: 绿色渐变主题
        PURPLE: 紫色渐变主题
        ORANGE: 橙色渐变主题
        GRAY: 灰色渐变主题
    """

    BLUE = "blue"  # 蓝色渐变：适合商务和科技类数据
    GREEN = "green"  # 绿色渐变：适合成功和积极的数据
    PURPLE = "purple"  # 紫色渐变：适合创意和艺术类数据
    ORANGE = "orange"  # 橙色渐变：适合警告和注意类数据
    GRAY = "gray"  # 灰色渐变：适合中性和专业类数据


class CellStyle(Enum):
    """
    单元格样式枚举

    提供预设的单元格样式类，用于根据数据内容设置不同的背景色。
    这些样式基于Bootstrap的颜色系统，提供一致的用户体验。

    Attributes:
        SUCCESS: 成功样式（绿色背景）- 用于正面、正确、成功的数据
        ERROR: 错误样式（红色背景）- 用于负面、错误、失败的数据
        WARNING: 警告样式（黄色背景）- 用于需要注意、警告的数据
        INFO: 信息样式（蓝色背景）- 用于中性、信息类数据
        NEUTRAL: 中性样式（无背景色）- 用于普通、默认数据
    """

    SUCCESS = "success"  # 绿色背景，表示成功、正确、积极
    ERROR = "error"  # 红色背景，表示错误、失败、负面
    WARNING = "warning"  # 黄色背景，表示警告、注意、提醒
    INFO = "info"  # 蓝色背景，表示信息、中性、数据
    NEUTRAL = "neutral"  # 无背景色，表示普通、默认状态


def format_template(
    template: str, values: dict[str, Any], required_params: set[str] | None = None, debug_check: bool = False
) -> str:
    """将模板字符串中的 {param} 格式参数替换为实际值

    Args:
        template: 包含参数的模板字符串
        values: 参数字典，键为参数名称，值为替换内容
        required_params: 预计算的参数名称集合，用于性能优化
        debug_check: 是否在debug模式下校验参数一致性

    Returns:
        格式化后的字符串

    Raises:
        KeyError: 如果模板中存在参数字典中未提供的键
        TypeError: 如果参数值无法转换为字符串
        ValueError: 如果required_params不完整

    Example:
        >>> format_template("生成{style}风格的{format}摘要", {"style": "简洁", "format": "段落"})
        '生成简洁风格的段落摘要'
    """
    # 第一步：获取所需的参数集合
    if required_params is not None:
        params_to_use = required_params
        if debug_check:
            actual_params = extract_params(template)
            missing_in_required = actual_params - required_params
            if missing_in_required:
                raise ValueError(f"预计算的参数集合不完整，缺少: {', '.join(sorted(missing_in_required))}")
    else:
        params_to_use = extract_params(template)

    # 第二步：验证所有参数都有对应的值
    missing_params = params_to_use - set(values.keys())
    if missing_params:
        raise KeyError(f"缺少参数: {', '.join(sorted(missing_params))}")

    # 第三步：逐一替换参数
    result = template
    for param in params_to_use:
        try:
            # TODO: 这里应该使用nl_repr。
            str_value = str(values[param])
        except Exception as e:
            raise TypeError(f"无法将参数 '{param}' 的值 {values[param]!r} 转换为字符串: {e}")
        result = result.replace(f"{{{param}}}", str_value)

    return result


def extract_params(text: str) -> set[str]:
    """从文本中提取所有 {param} 格式的参数名

    Args:
        text: 包含参数的文本字符串

    Returns:
        参数名称集合，如 {'style', 'format'}

    Example:
        >>> extract_params("生成{style}风格的{format}摘要")
        {'style', 'format'}
    """
    pattern = r"\{([a-zA-Z0-9_]+)\}"  # {param} - 匹配花括号内的参数名
    params = set(re.findall(pattern, text))
    return params


# 新增可复用函数
def generate_html_document(title: str, content: str, custom_css: str = "") -> str:
    """生成完整的HTML文档结构"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title}</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            {generate_base_css()}
            {custom_css}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>{title}</h1>
            {content}
        </div>
    </body>
    </html>
    """


def generate_html_document_with_width(title: str, content: str, custom_css: str = "", container_width: str = "100%") -> str:
    """生成完整的HTML文档结构，支持自定义容器宽度"""
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>{title}</title>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.1.3/dist/css/bootstrap.min.css" rel="stylesheet">
        <style>
            {generate_base_css()}
            .container {{
                max-width: {container_width} !important;
                width: {container_width} !important;
            }}
            {custom_css}
        </style>
    </head>
    <body>
        <div class="container">
            <h1>{title}</h1>
            {content}
        </div>
    </body>
    </html>
    """


def generate_base_css() -> str:
    """生成基础CSS样式"""
    return """
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 20px;
            background-color: #f8f9fa;
        }
        .container {
            background-color: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 0 20px rgba(0,0,0,0.1);
        }
        h1 {
            color: #495057;
            text-align: center;
            margin-bottom: 30px;
            font-weight: 300;
        }
    """


def get_theme_css(theme: Theme) -> str:
    """获取主题对应的CSS渐变"""
    theme_map = {
        Theme.BLUE: "linear-gradient(135deg, #667eea 0%, #764ba2 100%)",
        Theme.GREEN: "linear-gradient(135deg, #28a745 0%, #20c997 100%)",
        Theme.PURPLE: "linear-gradient(135deg, #6f42c1 0%, #e83e8c 100%)",
        Theme.ORANGE: "linear-gradient(135deg, #fd7e14 0%, #ffc107 100%)",
        Theme.GRAY: "linear-gradient(135deg, #6c757d 0%, #adb5bd 100%)",
    }
    return theme_map.get(theme, theme_map[Theme.BLUE])


def merge_styling(user_styling: dict, default_styling: dict) -> dict:
    """合并用户样式和默认样式"""
    result = default_styling.copy()
    if user_styling:
        for key, value in user_styling.items():
            if isinstance(value, Theme):
                if key == "theme":
                    result["theme_color"] = get_theme_css(value)
                else:
                    result[key] = value.value
            else:
                result[key] = value
    return result


def generate_dataframe_table(df: pd.DataFrame, **kwargs) -> str:
    """生成DataFrame的HTML表格"""
    # 预处理数据，处理换行符
    df_formatted = df.copy()
    for col in df_formatted.columns:
        df_formatted[col] = df_formatted[col].astype(str).str.replace("\n", "<br>")
    
    # 获取参数
    cell_formatter = kwargs.get('cell_formatter', str)
    cell_styler = kwargs.get('cell_styler', lambda _: "")
    show_text_length = kwargs.get('show_text_length')
    
    # 判断是否需要手动构建HTML
    needs_custom_html = (
        cell_formatter is not str or 
        cell_styler is not (lambda _: "") or 
        show_text_length is not None
    )
    
    if needs_custom_html:
        # 手动构建HTML表格
        html_rows = []
        html_rows.append("<tr>" + "".join(f"<th>{col}</th>" for col in df_formatted.columns) + "</tr>")
        
        for idx, row in df_formatted.iterrows():
            cells = []
            for col_name, val in row.items():
                try:
                    original_val = df.loc[idx, col_name]
                except (KeyError, TypeError):
                    original_val = val
                
                # 应用格式化 - 修复None检查
                if cell_formatter is not None and cell_formatter is not str:
                    display_val = cell_formatter(original_val)
                else:
                    display_val = str(original_val)
                
                # 应用样式 - 修复None检查
                if cell_styler is not None and cell_styler is not (lambda _: ""):
                    style_result = cell_styler(original_val)
                else:
                    style_result = ""
                    
                if isinstance(style_result, CellStyle):
                    cell_style = f'class="table-{style_result.value}"'
                elif isinstance(style_result, str):
                    cell_style = style_result
                else:
                    cell_style = ""
                
                # 处理长文本截断
                if show_text_length and len(display_val) > show_text_length:
                    short_text = display_val[:show_text_length] + "..."
                    full_text = display_val.replace('"', "&quot;")
                    cells.append(f'<td {cell_style}><div title="{full_text}">{short_text}</div></td>')
                else:
                    cells.append(f"<td {cell_style}>{display_val}</td>")
            
            html_rows.append("<tr>" + "".join(cells) + "</tr>")
        
        return '<table class="table">' + "".join(html_rows) + "</table>"
    else:
        # 使用pandas内置方法
        return df_formatted.to_html(
            escape=False, index=False, classes=["table", "table-striped", "table-hover"]
        )


def generate_dataframe_css(styling: dict, df: pd.DataFrame, **kwargs) -> str:
    """生成DataFrame的CSS样式"""
    column_widths = kwargs.get('column_widths')
    
    # 处理列宽
    column_styles = ""
    if column_widths:
        for key, width in column_widths.items():
            if isinstance(key, str) and key in df.columns:
                col_index = list(df.columns).index(key)
                column_styles += f"""
            .table th:nth-child({col_index + 1}),
            .table td:nth-child({col_index + 1}) {{
                width: {width} !important;
            }}"""
            elif isinstance(key, int) and 0 <= key < len(df.columns):
                column_styles += f"""
            .table th:nth-child({key + 1}),
            .table td:nth-child({key + 1}) {{
                width: {width} !important;
            }}"""
    
    # 计算动态列宽
    if not column_widths and len(df.columns) > 1:
        remaining_width = f"calc((100% - {styling.get('first_col_width', '15%')}) / {len(df.columns)-1})"
    else:
        remaining_width = "100%"
    
    return f"""
        .table {{
            border-radius: {styling.get('border_radius', '8px')};
            overflow: hidden;
            box-shadow: 0 0 15px rgba(0,0,0,0.1);
            table-layout: fixed;
            width: 100%;
        }}
        .table th {{
            background: {styling.get('theme_color', get_theme_css(Theme.BLUE))};
            color: white;
            font-weight: 600;
            border: none;
            padding: 15px 10px;
            white-space: pre-line;
            line-height: 1.4;
            vertical-align: top;
            text-align: left !important;
        }}
        .table td {{
            padding: 12px 10px;
            vertical-align: top;
            border-bottom: 1px solid #dee2e6;
            word-wrap: break-word;
            white-space: pre-line;
            line-height: 1.4;
        }}
        .table th:first-child,
        .table td:first-child {{
            width: {styling.get('first_col_width', '15%')};
            min-width: {styling.get('min_width', '120px')};
        }}
        .table th:not(:first-child),
        .table td:not(:first-child) {{
            width: {remaining_width};
        }}
        {column_styles}
        .table tbody tr:hover {{
            background-color: #f8f9fa;
            transform: scale(1.01);
            transition: all 0.2s ease;
        }}
        .table-striped tbody tr:nth-of-type(odd) {{
            background-color: rgba(0,0,0,.02);
        }}
        .table-success {{
            background-color: #d4edda !important;
            color: #155724 !important;
        }}
        .table-error {{
            background-color: #f8d7da !important;
            color: #721c24 !important;
        }}
        .table-warning {{
            background-color: #fff3cd !important;
            color: #856404 !important;
        }}
        .table-info {{
            background-color: #d1ecf1 !important;
            color: #0c5460 !important;
        }}
        .table-neutral {{
            background-color: transparent !important;
        }}
    """


def df_to_html(  # noqa
    df: pd.DataFrame,
    filename: str,
    /,
    *,
    title: str,
    summary_info: dict[str, str] | None = None,
    styling: dict[str, str | Theme] | None = None,
    column_widths: dict[str | int, str] | None = None,
    cell_formatter: Callable[[Any], str] | None = None,
    cell_styler: Callable[[Any], str | CellStyle] | None = None,
    show_text_length: int | None = None,
) -> None:
    """重构后的df_to_html，使用可复用的函数"""
    
    # 设置默认样式
    default_styling = {
        "first_col_width": "15%",
        "min_width": "120px",
        "theme_color": get_theme_css(Theme.BLUE),
        "border_radius": "8px",
    }
    
    # 合并样式配置
    final_styling = merge_styling(styling or {}, default_styling)
    
    # 生成表格内容
    table_content = generate_dataframe_table(df, 
                                           cell_formatter=cell_formatter,
                                           cell_styler=cell_styler,
                                           show_text_length=show_text_length,
                                           column_widths=column_widths)
    
    # 生成摘要（直接内联）
    summary_info = summary_info or {"列数": str(len(df.columns)), "行数": str(len(df))}
    summary_text = " | ".join([f"{k}: {v}" for k, v in summary_info.items()])
    summary_html = f"""
    <div class="summary" style="background: {final_styling['theme_color']}; color: white; padding: 20px; border-radius: 8px; margin-bottom: 30px;">
        <h4>📊 统计摘要</h4>
        <p>{summary_text}</p>
    </div>
    """
    
    # 生成自定义CSS
    custom_css = generate_dataframe_css(final_styling, df, column_widths=column_widths)
    
    # 组装完整HTML
    full_content = summary_html + table_content
    full_html = generate_html_document(title, full_content, custom_css)
    
    # 保存文件（直接内联）
    with open(filename, "w", encoding="utf-8") as f:
        f.write(full_html)
 
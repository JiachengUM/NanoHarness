"""通用可视化模块

提供与评估解耦的图片渲染工具：
- 在截图上绘制模型动作（点击/滚动/输入）
- 渲染单步与完整工作流的结果图，便于人工核对

说明：尽量容忍外部依赖差异（如字体不存在时降级），仅承担可视化职责。
"""

from io import BytesIO
from pathlib import Path
from typing import Optional, Union, Literal, TYPE_CHECKING

from PIL import Image, ImageDraw, ImageFont
import requests

from projects.uiagent.core import (
    JudgeResult,
    UITaskResult,
)
from projects.uiagent.core.action import (
    Action,
    ActionType,
    ClickAction,
    ScrollAction,
    TypeAction,
    AskAction,
    DragAction
)
from projects.uiagent.core.flow_data import UIResult

# 临时保留，后续draw_workflow_result完善后删除。
if TYPE_CHECKING:
    # 只在类型检查时导入，避免循环导入
    from projects.uiagent.core.test_utils import WorkflowData

from nanoai.utils.nl_repr import _nl_repr_base_model, nl_repr


__all__ = [
    "draw_step_result",
    "draw_workflow_result",
]

def draw_actions(
    image_path: Union[Path, str, BytesIO],
    parsed_actions_list: list[Action],
    output_path: Optional[Union[Path, str]] = None,
    *,
    factor: int = 1000,
    color="red",
    width=15,
) -> Image.Image:
    """
    使用Pillow在图片上绘制矩形框

    参数:
        image: 输入图片路径或BytesIO对象
        output_path: 输出图片路径
        coordinates: 列表形式的绝对坐标框 [{"coordinates": {"x1":...,"y1":...,"x2":...,"y2":...}}, ...]
        或者使用相对坐标方式：传入 x, y（千分制），函数内部自动换算并绘制
        color: 颜色名称或RGB值，默认"green"
        width: 线宽，默认4
    """

    click_coordinates = []
    # [{"coordinates": {"x1":...,"y1":...,"x2":...,"y2":...}}, ...]
    for an_action in parsed_actions_list:
        if isinstance(an_action, ClickAction):
            x1 = an_action.x * factor
            y1 = an_action.y * factor
            x2 = an_action.x * factor
            y2 = an_action.y * factor
            click_coordinates.append(
                {
                    "action_type": ActionType.CLICK,
                    "coordinates": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                }
            )
        elif isinstance(an_action, ScrollAction):
            x1 = an_action.x * factor
            y1 = an_action.y * factor
            x2 = an_action.x * factor
            y2 = an_action.y * factor
            click_coordinates.append(
                {
                    "action_type": ActionType.SCROLL,
                    "coordinates": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                    "direction": an_action.dir,
                }
            )
        elif isinstance(an_action, TypeAction):
            # 写死在图片上的坐标展示输入
            x1 = 0.5 * factor
            y1 = 0.2 * factor
            x2 = 0.5 * factor
            y2 = 0.2 * factor
            click_coordinates.append(
                {
                    "action_type": ActionType.TYPE,
                    "coordinates": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                    "content": an_action.content,
                }
            )
        elif isinstance(an_action, AskAction):
            # 写死在图片上的坐标展示输入
            x1 = 0.5 * factor
            y1 = 0.2 * factor
            x2 = 0.5 * factor
            y2 = 0.2 * factor
            click_coordinates.append(
                {
                    "action_type": ActionType.ASK,
                    "coordinates": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                    "content": an_action.content,
                }
            )
        elif isinstance(an_action, DragAction):
            x1 = an_action.x * factor
            y1 = an_action.y * factor
            x2 = an_action.end_point_x * factor
            y2 = an_action.end_point_y * factor
            click_coordinates.append(
                {
                    "action_type": ActionType.DRAG,
                    "coordinates": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                    "content": an_action.target_ui_element,
                }
            )
    # new_click_coordinates = [{"coordinates": {"x1":344,"y1":290,"x2":344,"y2":290}},{"coordinates": {"x1":254,"y1":557,"x2":254,"y2":557}},{"coordinates": {"x1":275,"y1":914,"x2":275,"y2":914}}]
    # new_click_coordinates = [{"coordinates": {"x1":344,"y1":290,"x2":344,"y2":290}},{"coordinates": {"x1":254,"y1":557,"x2":254,"y2":557}},{"coordinates": {"x1":275,"y1":914,"x2":275,"y2":914}}]
    # 打开图片（with确保写入落盘）
    # 支持 http(s) 链接：下载后以 BytesIO 打开
    if isinstance(image_path, str) and image_path.startswith("http"):
        response = requests.get(image_path, timeout=10)
        response.raise_for_status()  # 检查请求是否成功
        a_image = BytesIO(response.content)
    else:
        a_image = image_path
    # 打开图片
    with Image.open(a_image) as image:
        original_width, original_height = image.size
        draw = ImageDraw.Draw(image)
        for coordinate in click_coordinates:
            x1, y1, x2, y2 = (
                coordinate["coordinates"]["x1"],
                coordinate["coordinates"]["y1"],
                coordinate["coordinates"]["x2"],
                coordinate["coordinates"]["y2"],
            )
            # 坐标取整并夹紧到图片范围，避免超界导致不可见
            xi1 = max(
                0,
                min(
                    original_width - 1,
                    int(original_width * x1 / factor),
                ),
            )
            yi1 = max(
                0,
                min(
                    original_height - 1,
                    int(original_height * y1 / factor),
                ),
            )
            xi2 = max(
                0,
                min(
                    original_width - 1,
                    int(original_width * x2 / factor),
                ),
            )
            yi2 = max(
                0,
                min(
                    original_height - 1,
                    int(original_height * y2 / factor),
                ),
            )
            if coordinate["action_type"] == ActionType.SCROLL:
                x = xi1
                y = yi1
                length = 100  # 箭头基准长度（像素）
                draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=color)

                # 箭头终点计算
                if coordinate["direction"] == "up":
                    x2, y2 = x, max(0, y - length)
                elif coordinate["direction"] == "down":
                    x2, y2 = x, min(original_height - 1, y + length)
                elif coordinate["direction"] == "left":
                    x2, y2 = max(0, x - length), y
                elif coordinate["direction"] == "right":
                    x2, y2 = min(original_width - 1, x + length), y
                else:
                    x2, y2 = x, y

                # 画箭头线
                draw.line((x, y, x2, y2), fill=color, width=width)

                # 画箭头头部
                arrow_size = 20
                if coordinate["direction"] in ("up", "down", "left", "right"):
                    if coordinate["direction"] == "up":
                        arrow_points = [
                            (x2, y2),
                            (x2 - arrow_size, y2 + arrow_size),
                            (x2 + arrow_size, y2 + arrow_size),
                        ]
                    elif coordinate["direction"] == "down":
                        arrow_points = [
                            (x2, y2),
                            (x2 - arrow_size, y2 - arrow_size),
                            (x2 + arrow_size, y2 - arrow_size),
                        ]
                    elif coordinate["direction"] == "left":
                        arrow_points = [
                            (x2, y2),
                            (x2 + arrow_size, y2 - arrow_size),
                            (x2 + arrow_size, y2 + arrow_size),
                        ]
                    else:
                        arrow_points = [
                            (x2, y2),
                            (x2 - arrow_size, y2 - arrow_size),
                            (x2 - arrow_size, y2 + arrow_size),
                        ]
                    draw.polygon(arrow_points, fill=color)
                    print(f"drawed an arrow at ({x2}, {y2})")
            elif coordinate["action_type"] == ActionType.CLICK:
                # 计算交点坐标
                center_x = (xi1 + xi2) / 2
                center_y = (yi1 + yi2) / 2

                # X的边长为100像素，计算四个顶点
                half_size = 50  # 边长的一半
                x1 = center_x - half_size
                y1 = center_y - half_size
                x2 = center_x + half_size
                y2 = center_y + half_size
                x3 = center_x - half_size
                y3 = center_y + half_size
                x4 = center_x + half_size
                y4 = center_y - half_size

                # 绘制X的两条对角线
                draw.line([x1, y1, x2, y2], fill=color, width=width)
                draw.line([x3, y3, x4, y4], fill=color, width=width)

                # 在交点处绘制一个半径20像素的圆点
                draw.ellipse(
                    [center_x - 20, center_y - 20, center_x + 20, center_y + 20],
                    fill=color,
                )

                print(f"drawed an X at ({center_x}, {center_y}) with dot")
            elif coordinate["action_type"] == ActionType.TYPE:
                # 在坐标位置把content写在矩形框内
                # 正确地用Python ImageFont设置45号字体
                try:
                    # 尝试加载字体，如果失败则使用默认字体
                    # 尝试加载粗体字体，如果没有粗体版本则使用常规字体
                    try:
                        font: ImageFont.FreeTypeFont | ImageFont.ImageFont = (
                            ImageFont.truetype("simhei.ttf", 40, index=1)
                        )  # 索引1通常是粗体
                    except (IOError, IndexError):
                        # 如果无法加载粗体，则尝试在常规字体上模拟粗体效果
                        font = ImageFont.truetype("simhei.ttf", 40)
                except IOError:
                    # 使用默认字体
                    font = ImageFont.load_default()
                draw.text((xi1, yi1), coordinate["content"], fill=color, font=font)
                print(f"drawed a type at ({xi1}, {yi1})")
            elif coordinate["action_type"] == ActionType.ASK:
                # 在坐标位置把content写在矩形框内
                # 正确地用Python ImageFont设置45号字体
                try:
                    # 尝试加载字体，如果失败则使用默认字体
                    # 尝试加载粗体字体，如果没有粗体版本则使用常规字体
                    try:
                        font: ImageFont.FreeTypeFont | ImageFont.ImageFont = (
                            ImageFont.truetype("simhei.ttf", 40, index=1)
                        )  # 索引1通常是粗体
                    except (IOError, IndexError):
                        # 如果无法加载粗体，则尝试在常规字体上模拟粗体效果
                        font = ImageFont.truetype("simhei.ttf", 40)
                except IOError:
                    # 使用默认字体
                    font = ImageFont.load_default()
                draw.text((xi1, yi1), "ASKING HUMAN:\n"+coordinate["content"], fill="green", font=font)
                print(f"drawed an ask at ({xi1}, {yi1})")
            elif coordinate["action_type"] == ActionType.FINISHED:
                # 在坐标位置把content写在矩形框内
                # 正确地用Python ImageFont设置45号字体
                try:
                    # 尝试加载字体，如果失败则使用默认字体
                    # 尝试加载粗体字体，如果没有粗体版本则使用常规字体
                    try:
                        font: ImageFont.FreeTypeFont | ImageFont.ImageFont = (
                            ImageFont.truetype("simhei.ttf", 40, index=1)
                        )  # 索引1通常是粗体
                    except (IOError, IndexError):
                        # 如果无法加载粗体，则尝试在常规字体上模拟粗体效果
                        font = ImageFont.truetype("simhei.ttf", 40)
                except IOError:
                    # 使用默认字体
                    font = ImageFont.load_default()
                draw.text((xi1, yi1), "FINISHED:\n"+coordinate["content"], fill="red", font=font)
                print(f"drawed a finished at ({xi1}, {yi1})")
            elif coordinate["action_type"] == ActionType.DRAG:
                # 在坐标位置把drag从起点画到终点，终点为箭头
                # 起点x1, y1, 终点x2, y2
                x1 = xi1
                y1 = yi1
                x2 = xi2
                y2 = yi2
                
                # 绘制从起点到终点的线条
                draw.line([x1, y1, x2, y2], fill=color, width=width)
                
                # 在起点绘制一个圆点标记
                start_radius = 15
                draw.ellipse(
                    [x1 - start_radius, y1 - start_radius, x1 + start_radius, y1 + start_radius],
                    fill=color,
                )
                
                # 计算箭头方向（从起点指向终点）
                import math
                dx = x2 - x1
                dy = y2 - y1
                # 计算线条的角度（弧度）
                angle_rad = math.atan2(dy, dx)
                # 转换为角度（度）
                angle_deg = math.degrees(angle_rad)
                
                # 箭头大小
                arrow_size = 35
                # 箭头角度（度）
                arrow_angle = 35
                
                # 计算箭头两个边的终点坐标
                # 箭头指向线条的反方向（指向起点方向），所以角度是 angle_rad + π
                arrow_angle1_rad = angle_rad + math.pi - math.radians(arrow_angle)
                arrow_angle2_rad = angle_rad + math.pi + math.radians(arrow_angle)
                
                # 箭头两个边的终点
                arrow_x1 = x2 + arrow_size * math.cos(arrow_angle1_rad)
                arrow_y1 = y2 + arrow_size * math.sin(arrow_angle1_rad)
                arrow_x2 = x2 + arrow_size * math.cos(arrow_angle2_rad)
                arrow_y2 = y2 + arrow_size * math.sin(arrow_angle2_rad)
                
                # 绘制箭头（三角形）
                arrow_points = [
                    (x2, y2),  # 箭头顶点（终点）
                    (arrow_x1, arrow_y1),  # 箭头左边点
                    (arrow_x2, arrow_y2),  # 箭头右边点
                ]
                draw.polygon(arrow_points, fill="green")
                
                print(f"drawed a drag from ({x1}, {y1}) to ({x2}, {y2}) with arrow")

            
        # 保存结果
        # 注意：保存需在with块内完成
        if output_path is None:
            return image
        else:
            image.save(output_path)
            print(f"结果已保存到: {output_path}")
            return image


def draw_workflow_result(
    workflow_data: "WorkflowData",
    runresults: list[list[UITaskResult | str] | None],
    judges: list[JudgeResult | None],
    output_dir: str,
    layout: Literal["vertical", "horizontal"] = "vertical",
) -> Image.Image | None:
    """将工作流结果渲染为图片并保存

    Args:
        workflow_data: 工作流样本（含四个步骤）
        runresults: 工作流执行的模型输出（思考/动作等）列表，每个元素是一个步骤的结果列表
        judges: 判定结果（是否正确/理由）
        output_dir: 输出目录
        eval_type: 渲染类型，"workflow" 表示工作流；其它值会走拼图逻辑
        layout: 布局方向，"vertical" 表示纵向，"horizontal" 表示横向
    """
    # 将工作流输入及其对应的运行结果送入draw_step_result,绘制每个步骤的结果图
    drawed_images: list[Image.Image] = []
    for step_data, runresult, judge in zip(workflow_data.steps, runresults, judges):
        drawed_images.append(draw_step_result(
            image_path=step_data.image_path,
            query=step_data.query,
            runresult=runresult,
            judge=judge,
            output_dir=None,  # 不保存单步图片，只用于拼接
            sample_id=step_data.id,
            # priority=step_data.priority,
            # comment=step_data.comment,
        ))

    assert drawed_images, "工作流结果图列表不能为空"

    # 将工作流结果图拼接起来（纵向单列，保持时序阅读）
    # 计算每张图片的宽度和高度
    img_widths = [img.width for img in drawed_images]
    img_heights = [img.height for img in drawed_images]

    # 根据布局方向确定拼接图片的总宽度和高度
    if layout == "horizontal":
        # 横向布局：图片横向排列
        total_width = sum(img_widths) + 30 * (len(drawed_images) - 1)  # 30像素列间距
        total_height = max(img_heights)  # 使用最高图片的高度作为总高度
    else:
        # 纵向布局：图片纵向排列（默认）
        total_width = max(img_widths)  # 使用最宽图片的宽度作为总宽度
        total_height = sum(img_heights) + 30 * (len(drawed_images) - 1)  # 30像素行间距
    
    # 添加工作流信息标题栏
    header_height = 100
    total_height += header_height

    # 创建拼接图片（白底）
    combined_image = Image.new("RGB", (total_width, total_height), color="white")
    
    # 绘制工作流信息标题栏
    draw = ImageDraw.Draw(combined_image)
    try:
        font = ImageFont.truetype("simhei.ttf", 32)
    except IOError:
        font = ImageFont.load_default()
    
    # 标题栏背景色（深色）
    header_bg = Image.new("RGB", (total_width, header_height), color="#2c3e50")
    combined_image.paste(header_bg, (0, 0))
    
    # 构建工作流信息文本（使用 workflow_data 的 priority 和 comment）
    workflow_info = f"工作流 ID: {workflow_data.id} | 优先级: {workflow_data.priority} | 备注: {workflow_data.comment}"
    
    # 计算文本位置（居中）
    text_bbox = draw.textbbox((0, 0), workflow_info, font=font)
    text_width = text_bbox[2] - text_bbox[0]
    text_x = (total_width - text_width) // 2
    text_y = (header_height - 32) // 2
    
    draw.text((text_x, text_y), workflow_info, font=font, fill="white")

    # 根据布局方向粘贴各个图片到拼接图片中
    if layout == "horizontal":
        # 横向布局：图片横向排列（在标题栏下方）
        x_offset = 0
        y_offset = header_height
        for img in drawed_images:
            # 垂直居中放置图片
            y_center = (total_height - header_height - img.height) // 2 + header_height
            combined_image.paste(img, (x_offset, y_center))
            # 更新下一张图片的x偏移
            x_offset += img.width + 30  # 30像素间距
    else:
        # 纵向布局：图片纵向排列（在标题栏下方）
        y_offset = header_height
        for img in drawed_images:
            # 居中放置图片（水平方向）
            x_offset = (total_width - img.width) // 2
            combined_image.paste(img, (x_offset, y_offset))
            # 更新下一张图片的y偏移
            y_offset += img.height + 30  # 30像素间距

    # 调整拼接后图片的大小到合适程度：
    # - 宽度>1600 时等比缩小
    # - 宽度<1200 时等比放大（提高清晰度）
    max_display_width = 8600
    if combined_image.width > max_display_width:
        ratio = max_display_width / combined_image.width
        new_height = int(combined_image.height * ratio)
        combined_image = combined_image.resize(
            (max_display_width, new_height), Image.Resampling.LANCZOS
        )
    # else:
    #     # 如果图片宽度小于最大宽度，也适当放大以提高清晰度
    #     if combined_image.width < 1200:
    #         ratio = 1200 / combined_image.width
    #         new_width = 1200
    #         new_height = int(combined_image.height * ratio)
    #         combined_image = combined_image.resize(
    #             (new_width, new_height), Image.Resampling.LANCZOS
    #         )

    output_path = Path(output_dir) / f"workflow_{workflow_data.id}.png"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    combined_image.save(output_path)
    print(f"拼接图片已保存到: {output_path}")

    return combined_image


def draw_step_result(
    *,
    image_path: str,
    query: str,
    runresult: list[UITaskResult | UIResult | str] | None = None,
    judge: JudgeResult | None = None,
    output_dir: str | None = None,
    sample_id: str | int | None = 1,
    priority: int | None = None,
    comment: str | None = None,
) -> Image.Image:
    """将单步结果渲染为图片并保存

    Args:
        step_data: 当前步骤的输入（含 query 与图片路径）
        runresult: 工作流执行的模型输出（思考/动作等）列表，最多只有一个UITaskResult和一个str
        judge: 判定结果（是否正确/理由）
        output_dir: 输出目录，为空时不保存图片，仅返回内存内图片，用于外层工作流图片拼接
    """
    assert image_path is not None, "image_path must be provided"

    # 处理列表中的UITaskResult，外部None不处理，直接返回原图
    ui_task_result: UITaskResult | None = None
    # 增加str 的绘制
    str_items: list[str] = []

    # 如果 runresult 是 None，直接返回
    if runresult is None :
        # 使用 f-string 格式化输出信息，更清晰
        print(f"runresult 是 {type(runresult).__name__} 类型，无可渲染内容。值为: {runresult}")
        # 返回原图作为占位
        return Image.open(image_path)

    # 如果不是None，按理最少会有一个值，找到UITaskResult就行
    for result in runresult:
        if isinstance(result, UITaskResult) or isinstance(result, UIResult):
            ui_task_result = result
        else:
            str_items.append(result)

    # 如果没找到UITaskResult（列表只有str），使用空列表调用 draw_actions（空运行）
    if ui_task_result is None:
        # ... 处理只有 str 的情况 ...
        drawed_image = draw_actions(
            image_path=image_path, parsed_actions_list=[]
        )
    else:
        # 有 ui_task_result 时，绘制 actions
        drawed_image = draw_actions(
            image_path=image_path, parsed_actions_list=ui_task_result.actions
        )

    # 将动作可视化图 + 文本说明（query/thought/actions/judge）拼接在同一张图上
    # 获取原始图片尺寸
    width, height = drawed_image.size

    # 根据图的大小来自适应
    short_side = min(width, height)
    aspect_ratio = height / max(width, 1)
    inv_aspect = width / max(height, 1)   # 用来识别横屏/平板

    # 初步字体大小（比原来稍微降低一点）
    base_font_size = int(short_side * 0.025)  

    # 手机长图 → 字体略放大
    if aspect_ratio > 1.8:  # 很高很窄，通常是手机

        base_font_size = int(base_font_size * 1.4)
        # print(f"手机字体大小：{base_font_size}")
    # 平板宽图 / PC截图 → 字体缩小
    elif inv_aspect > 1.4:  # 宽明显大于高
        base_font_size = int(base_font_size * 1.1)
        # print(f"平板字体大小：{base_font_size}")

    # 限制范围（更收紧）
    base_font_size = max(20, min(base_font_size, 45))
    # print(f"最终：{base_font_size}")


    try:
        # 尝试加载字体，如果失败则使用默认字体
        # 尝试加载粗体字体，如果没有粗体版本则使用常规字体
        try:
            font: ImageFont.FreeTypeFont | ImageFont.ImageFont = ImageFont.truetype(
                "simhei.ttf", base_font_size, index=1
            )  # 索引1通常是粗体
        except (IOError, IndexError):
            # 如果无法加载粗体，则尝试在常规字体上模拟粗体效果
            font = ImageFont.truetype("simhei.ttf", base_font_size)
    except IOError:
        # 使用默认字体
        font = ImageFont.load_default()

    # 设置文本内容和位置，确保正确的格式
    # 分别处理各个部分，保持格式清晰
    if ui_task_result is None:
        # 只有 str 的情况，构建简化的 formatted_parts
        formatted_parts = [
            f"id: {sample_id}  |  优先级: {priority}  |  备注: {comment}",
            f"input query: {query}",
            f"额外信息: {'\n'.join(str_items) if str_items else '无'}",
            f"judge result: {nl_repr(judge) if judge is not None else 'None'}",
        ]
    else:
        formatted_parts = [
            f"id: {sample_id}  |  优先级: {priority}  |  备注: {comment}",
            f"input query: {query}",
            f"thought: {ui_task_result.thought}",
            "output actions: ",
            "\n".join(
                [
                    _nl_repr_base_model(action).replace("\n", " ")
                    for action in ui_task_result.actions
                ]
            )
            + "\n",
            f"judge result: {nl_repr(judge) if judge is not None else 'None'}",
            f"raw prompt: {ui_task_result.raw_prompt}",
        ]
        # 如果有 str 信息，也添加到 formatted_parts 中
        if str_items:
            formatted_parts.append(f"额外信息: {'\n'.join(str_items)}")
    
    # 自适应行高 
    line_height = int(base_font_size * 1.8)

    estimated_lines = sum(len(part.split("\n")) for part in formatted_parts) + 20
    text_image_height = estimated_lines * line_height + 60

    text_image = Image.new("RGB", (width, text_image_height), color="black")
    draw = ImageDraw.Draw(text_image)


    # 文本换行
    text_lines: list[str] = []
    for part in formatted_parts:
        # 对于标题行（id:, input query:, output result:）直接添加
        if part.endswith(": ") or part == "":
            text_lines.append(part)
        else:
            # 先按换行符分割文本，处理多行情况
            for line_content in part.split("\n"):
                # 对于空行直接添加
                if not line_content.strip():
                    text_lines.append("")
                    continue

                # 对于内容行进行字符级别的换行处理
                current_line = ""
                for char in line_content:
                    test_line = current_line + char
                    # 估算文本宽度
                    try:
                        test_width = draw.textlength(test_line, font=font)
                        if test_width < width - 60:  # 留出左右边距
                            current_line = test_line
                        else:
                            text_lines.append(current_line)
                            current_line = char
                    except Exception:
                        # 如果估算宽度失败，则按字符宽度估算
                        if len(test_line) * base_font_size < width - 60:
                            current_line = test_line
                        else:
                            text_lines.append(current_line)
                            current_line = char
                if current_line:  # 添加最后一行
                    text_lines.append(current_line)

    # 绘制文本
    y = 40
    for line in text_lines:
        draw.text((30, y), line, font=font, fill="white")
        y += line_height

    # 裁剪多余高度
    actual_height = y + 20
    if actual_height < text_image_height:
        text_image = text_image.crop((0, 0, width, actual_height))

    # 拼图
    combined_width = width * 2
    combined_height = max(height, text_image.height)
    new_image = Image.new("RGB", (combined_width, combined_height), color="black")
    new_image.paste(drawed_image, (0, 0))
    new_image.paste(text_image, (width, 0))

    if output_dir:
        # 确保output_path存在，不存在则创建
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        output_path = output_path / f"{sample_id}_step_eval_result.png"
        new_image.save(output_path)
        print(f"拼接图片已保存到: {output_path}")
    return new_image


PNG_IMAGE_PATH = "tests/images/hehuiyan_seat_info.png"
def test_draw_actions():
    # 构造3个Action的List，分别是scroll, click, type
    click = ClickAction(name=ActionType.CLICK, x=0.500, y=0.700)
    scroll = ScrollAction(name=ActionType.SCROLL, x=0.500, y=0.500, dir="up")
    type_action = TypeAction(name=ActionType.TYPE, content="hello")
    drag = DragAction(name=ActionType.DRAG, start_point_x=0.1, start_point_y=0.2, end_point_x=0.3, end_point_y=0.4)
    actions = [click, scroll, type_action, drag]

    output_path = "tests/test_draw_actions.png"
    draw_actions(PNG_IMAGE_PATH, actions, output_path)



def test_draw_step_result():
    """测试 draw_step_result 函数"""
    # 多张图片路径
    image_paths = [PNG_IMAGE_PATH]*2

    # 构造3个Action的List
    click = ClickAction(name=ActionType.CLICK, x=0.500, y=0.700)
    scroll = ScrollAction(name=ActionType.SCROLL, x=0.500, y=0.500, dir="up")
    type_action = TypeAction(name=ActionType.TYPE, content="hello")
    actions: list[Action] = [click, scroll, type_action]

    # 构造 runresult
    runresult: list[UITaskResult | str] | None = [UITaskResult(
        raw_prompt="这是一个测试的原始提示这是一个测试的原始提示",
        thought="我需要点击按钮来完成这个任务",
        action_content="",
        actions=actions,
    ), "str 右侧绘制字符串","你好"]

    output_dir = "tests"

    # 遍历所有图片
    for idx, img_path in enumerate(image_paths, start=1):

        draw_step_result(
            image_path=img_path,
            query="测试查询：点击按钮",
            runresult=runresult,
            output_dir=output_dir,
            sample_id=idx,
            priority=1,
            comment="测试用例"
        )
        draw_step_result(
            image_path=img_path,
            query="测试查询：点击按钮",
            runresult=["str 右侧绘制字符串"],
            output_dir=output_dir,
            sample_id=idx,
            priority=1,
            comment="测试用例"
        )
        draw_step_result(
            image_path=img_path,
            query="测试查询：点击按钮",
            runresult=None,
            output_dir=output_dir,
            sample_id=idx,
            priority=1,
            comment="测试用例"
        )

def test_draw_workflow_result():
    """测试工作流结果渲染"""
    from projects.uiagent.core.test_utils import StepData, WorkflowData
    # 创建测试用的 Action 列表
    actions = [
        ClickAction(name=ActionType.CLICK, x=0.500, y=0.700),
        ScrollAction(name=ActionType.SCROLL, x=0.500, y=0.500, dir="up"),
        TypeAction(name=ActionType.TYPE, content="hello"),
    ]

    # 创建 RunResult
    runresult: list[UITaskResult | str] | None = [UITaskResult(
        raw_prompt="这是一个测试的原始提示这是一个测试的原始提示这是一个测试",
        thought="我需要点击按钮来完成这个任务",
        action_content="",
        actions=actions,
        
    ), "str 右侧绘制字符串","你好"]
    step_example = {
        "comment": "端到端case id:3 上一步询问用户是否给其他车缴费，这一步用户说给鄂A12456缴费，开始尝试点击切换车辆",
        "query": "那给鄂A124缴费吧",
        "image_path": PNG_IMAGE_PATH,
        "xml_path": PNG_IMAGE_PATH,
        "expected_result": "错误车牌，继续询问",
        # "expected_result_detail": AssertAction(action_type=ActionType.CLICK, target=""),
        # "expect_next_step": ParkingSteps.SELECT_CAR,
        # "task_type": TaskType.NL,
    }

    # 创建统一的 StepData
    step_data = StepData(
        id=1,
        priority=1,
        # comment="测试用例",
        # step="test_step",
        query=step_example["query"],
        image_path=step_example["image_path"],
        xml_path=step_example["xml_path"],
    )
    steps = [step_data] * 2
    # 创建工作流数据
    workflow_data = [WorkflowData(
        id=i,
        priority=1,
        comment="测试用例",
        steps=steps,

    ) for i in range(2)]

    # 执行渲染
    output_dir = "tests"
    draw_workflow_result(workflow_data[0], [runresult] * 2, [None] * 2, output_dir, layout="horizontal")
    draw_workflow_result(workflow_data[1], [runresult] * 2, [None] * 2, output_dir, layout="vertical")
    

if __name__ == "__main__":
    test_draw_actions()
    # test_draw_step_result()
    # test_draw_workflow_result() # 暂时没有解耦，


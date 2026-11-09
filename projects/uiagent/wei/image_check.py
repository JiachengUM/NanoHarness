from PIL import Image, ImageDraw
from ui_tars.action_parser import smart_resize

def draw_rectangle_pillow(image_path, output_path, coordinates=None, color="green", width=4,
                          x=None, y=None, scale: int = 1000, box_half_size: int = 5):
    """
    使用Pillow在图片上绘制矩形框

    参数:
        image_path: 输入图片路径
        output_path: 输出图片路径
        coordinates: 列表形式的绝对坐标框 [{"coordinates": {"x1":...,"y1":...,"x2":...,"y2":...}}, ...]
        或者使用相对坐标方式：传入 x, y（千分制），函数内部自动换算并绘制
        color: 颜色名称或RGB值，默认"green"
        width: 线宽，默认4
    """
    # 打开图片（with确保写入落盘）
    with Image.open(image_path) as img:
        original_width, original_height = img.size
        draw = ImageDraw.Draw(img)

    # 若未提供坐标列表，则尝试用相对坐标 x,y 生成一个小方框
    if not coordinates:
        if x is None or y is None:
            raise ValueError("必须提供 coordinates 列表，或提供相对坐标 x,y")
        x_mid = x / scale * original_width
        y_mid = y / scale * original_height
        x1 = x_mid - box_half_size
        x2 = x_mid + box_half_size
        y1 = y_mid - box_half_size
        y2 = y_mid + box_half_size
        # print(f"相对坐标 -> 像素: ({x},{y}) -> 中心像素({x_mid:.2f},{y_mid:.2f}), 框[{x1:.2f},{y1:.2f},{x2:.2f},{y2:.2f}]")
        coordinates = [{
            "coordinates": {
                "x1": x1,
                "y1": y1,
                "x2": x2,
                "y2": y2
            }
        }]

    for coordinate in coordinates:
        x1, y1, x2, y2 = (
            coordinate['coordinates']['x1'],
            coordinate['coordinates']['y1'],
            coordinate['coordinates']['x2'],
            coordinate['coordinates']['y2'],
        )
        # 坐标取整并夹紧到图片范围，避免超界导致不可见
        xi1 = max(0, min(original_width - 1, int(round(x1))))
        yi1 = max(0, min(original_height - 1, int(round(y1))))
        xi2 = max(0, min(original_width - 1, int(round(x2))))
        yi2 = max(0, min(original_height - 1, int(round(y2))))
        draw.rectangle([xi1, yi1, xi2, yi2], outline=color, width=width)

    # 保存结果
    # 注意：保存需在with块内完成
    img.save(output_path)
    print(f"结果已保存到: {output_path}")
    return original_width, original_height

def draw_actions(image_path, output_path, coordinates, factor:int=1000 , color="green", width=15, scale: int = 1000, box_half_size: int = 5):
    """
    使用Pillow在图片上绘制矩形框

    参数:
        image_path: 输入图片路径
        output_path: 输出图片路径
        coordinates: 列表形式的绝对坐标框 [{"coordinates": {"x1":...,"y1":...,"x2":...,"y2":...}}, ...]
        或者使用相对坐标方式：传入 x, y（千分制），函数内部自动换算并绘制
        color: 颜色名称或RGB值，默认"green"
        width: 线宽，默认4
    """
    # 打开图片（with确保写入落盘）
    with Image.open(image_path) as img:
        original_width, original_height = img.size
        draw = ImageDraw.Draw(img)
        new_height, new_width = smart_resize(original_height, original_width)
    for coordinate in coordinates:
        x1, y1, x2, y2 = (
            coordinate['coordinates']['x1'],
            coordinate['coordinates']['y1'],
            coordinate['coordinates']['x2'],
            coordinate['coordinates']['y2'],
        )
        # 坐标取整并夹紧到图片范围，避免超界导致不可见
        xi1 = max(0, min(original_width - 1, int(original_width * x1 / factor * original_width)))
        yi1 = max(0, min(original_height - 1, int(original_height * y1 / factor * original_height)))
        xi2 = max(0, min(original_width - 1, int(original_width * x2 / factor * original_width)))
        yi2 = max(0, min(original_height - 1, int(original_height * y2 / factor * original_height)))
        if coordinate['action_type'] == "scroll":
            draw.rectangle([xi1, yi1, xi2, yi2], outline="blue", width=width)
        else:
            draw.rectangle([xi1, yi1, xi2, yi2], outline="green", width=width)
        print("draw a dot of "+str([xi1, yi1, xi2, yi2]))

    # 保存结果
    # 注意：保存需在with块内完成
    img.save(output_path)
    print(f"结果已保存到: {output_path}")
    return original_width, original_height

def draw_scroll_arrow(image_path, output_path, point_str, direction, color="blue", width=15, length=100):
    """
    绘制 scroll 类型的箭头图像
    """
    x, y = map(int, point_str.split())
    with Image.open(image_path) as img:
        w, h = img.size
        draw = ImageDraw.Draw(img)

        # 绘制中心点
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=color)

        # 箭头终点计算
        if direction == "up":
            x2, y2 = x, max(0, y - length)
        elif direction == "down":
            x2, y2 = x, min(h, y + length)
        elif direction == "left":
            x2, y2 = max(0, x - length), y
        elif direction == "right":
            x2, y2 = min(w, x + length), y
        else:
            x2, y2 = x, y

        # 画箭头线
        draw.line((x, y, x2, y2), fill=color, width=width)

        # 画箭头头部
        arrow_size = 20
        if direction in ("up", "down", "left", "right"):
            if direction == "up":
                arrow_points = [(x2, y2), (x2 - arrow_size, y2 + arrow_size), (x2 + arrow_size, y2 + arrow_size)]
            elif direction == "down":
                arrow_points = [(x2, y2), (x2 - arrow_size, y2 - arrow_size), (x2 + arrow_size, y2 - arrow_size)]
            elif direction == "left":
                arrow_points = [(x2, y2), (x2 + arrow_size, y2 - arrow_size), (x2 + arrow_size, y2 + arrow_size)]
            else:
                arrow_points = [(x2, y2), (x2 - arrow_size, y2 - arrow_size), (x2 - arrow_size, y2 + arrow_size)]
            draw.polygon(arrow_points, fill=color)

        img.save(output_path)
    print(f"✅ scroll箭头图保存到: {output_path}")
    
if __name__ == '__main__':
    image_path = r"D:\yitu\2509\nanoai-ui-agent-datasets\chaojie\003.jpg"
    # 最简单用法：直接传 image_path, x, y（千分制）和输出文件，其他内部自动计算
    draw_rectangle_pillow(image_path=image_path, output_path="check.png", x=500, y=592, color="green", width=40)
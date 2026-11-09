import base64
from PIL import Image, ImageDraw
import json
def draw_rectangle_pillow(image_path, output_path, coordinates, color="green", width=2):
    """
    使用Pillow在图片上绘制矩形框

    参数:
        image_path: 输入图片路径
        output_path: 输出图片路径
        x1, y1: 矩形框左上角坐标
        x2, y2: 矩形框右下角坐标
        color: 颜色名称或RGB值，默认"green"
        width: 线宽，默认2
    """
    # 打开图片
    img = Image.open(image_path)
    original_width, original_height = img.size
    # 创建Draw对象
    draw = ImageDraw.Draw(img)

    for coordinate in coordinates:
        x1,y1,x2,y2 = coordinate['coordinates']['x1'], coordinate['coordinates']['y1'], coordinate['coordinates']['x2'], coordinate['coordinates']['y2']
        # x1 = x1 / 1000 * original_width
        # x2 = x2 / 1000 * original_width
        # y1 = y1 / 1000 * original_height
        # y2 = y2 / 1000 * original_height

        # 绘制矩形
        draw.rectangle([x1, y1, x2, y2], outline=color, width=width)

    # 保存结果
    img.save(output_path)
    print(f"结果已保存到: {output_path}")
    return original_width, original_height

if __name__ == '__main__':
    image_path = "../datasets/hehuiyan/007.png"
    #814 951
    ##相对坐标
    original_width = 524
    original_height = 1160
    # x = 300
    # y = 262
    x = 851
    y = 478
    #换算为绝对坐标
    x_mid = x / 1000 * original_width
    y_mid = y / 1000 * original_height
    x1 = x_mid - 5
    x2 = x_mid + 5
    y1 = y_mid - 5
    y2 = y_mid + 5
    cords = [{
        "coordinates": {
            "x1": x1,
            "y1": y1,
            "x2": x2,
            "y2": y2
        }
    }]

    draw_rectangle_pillow(
        image_path,
        "check.png",
        cords,
        "red",
        2
        )
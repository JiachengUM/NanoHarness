"""
简单的图片数据集工具
"""

import os
import json
import re


def scan_images(directory: str) -> list[dict]:
    """扫描目录中的图片文件"""
    if not os.path.exists(directory):
        return []
    
    images = []
    for filename in os.listdir(directory):
        # 检查是否为图片文件
        if filename.lower().endswith(('.jpg', '.jpeg', '.png')):
            # 提取三位数字
            match = re.match(r'^(\d{3})', filename)
            if match:
                images.append({
                    'filename': filename,
                    'path': os.path.join(directory, filename),
                    'number': int(match.group(1))
                })
    
    # 按数字排序
    images.sort(key=lambda x: x['number'])
    return images


def save_to_json(images: list[dict], json_file: str, dataset_name: str) -> int:
    """保存图片信息到JSON文件"""
    data = []
    for i, img in enumerate(images, 1):
        data.append({
            'id': i,
            'image_path': img['filename'],
            'description': '',
            'qa_pairs': [{"query":"","ground_truth":""}],  # 存储多个
            'result': '',
            'meta': dataset_name
        })
    
    with open(json_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    return len(data)


def scan_images_and_save_to_json(directory: str, json_file: str) -> int:
    """扫描图片并保存到JSON文件"""
    # 获取目录名作为数据meta信息
    dataset_name = os.path.basename(directory)
    images = scan_images(directory)
    print(f"找到 {len(images)} 张图片")
    count = save_to_json(images, json_file, dataset_name)
    print(f"保存了 {count} 条记录到 {json_file} ，数据集名称: {dataset_name}")
    return count

def parse_x_y(content:str) -> tuple[int, int]:
    """
    最简解析：从内容中提取第一个坐标对，返回 (x, y) 整数。
    - 入参可为 dict 或 str；若为 dict，则转成文本后再解析
    - 匹配优先：<point>x y</point>，其次 "point":"x y"，最后任意两个数字对
    """
    text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
    # <point>...</point>
    m = re.search(r"<point>\s*(\d+)\s+(\d+)\s*</point>", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    # "point": "x y"
    m = re.search(r"\"point\"\s*:\s*\"\s*(\d+)\s+(\d+)\s*\"", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    # 裸两个数字
    m = re.search(r"\b(\d{2,4})\s+(\d{2,4})\b", text)
    if m:
        return int(m.group(1)), int(m.group(2))
    raise ValueError("未找到可解析的坐标")

def parse_action(result):
    """从result中提取action信息"""
    # 处理pydantic模型对象或字典
    if hasattr(result, 'content'):
        content = result.content
    else:
        content = result.get('content', '')
    
    try:
        if isinstance(content, str):
            data = json.loads(content)
        else:
            data = content
    except:
        data = content
    
    if isinstance(data, dict):
        if 'actions' in data:
            return data['actions']
        elif 'action' in data:
            return [data]
    
    return []

if __name__ == "__main__":
    directory = r"D:\yitu\2509\nanoai-ui-agent-datasets\chaojie"
    json_file = r"D:\yitu\2509\nanoai\projects\uiagent\wei\chaojie.json"
    scan_images_and_save_to_json(directory, json_file)

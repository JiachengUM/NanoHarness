import xml.etree.ElementTree as ET
import re
import os

from PIL import ImageFont


class TextElementLocator:
    """Android XML文本元素定位工具（极简版）"""

    def __init__(self, xml_str):
        """
        初始化定位器
        :param xml_str
        """
        self.xml_str = xml_str
        self.elements = []  # 存储所有可见的文本元素
        self._parse_xml()

    def _parse_xml(self):
        """解析XML文件，提取可见的文本元素"""
        try:
            root = ET.fromstring(self.xml_str)

            # 遍历所有节点
            for node in root.iter():
                # 跳过隐藏元素
                visibility = node.get('visibility', 'visible')
                if visibility in ['gone', 'invisible']:
                    continue

                # 检查是否有文本
                text = node.get('text', '')
                if not text:
                    continue

                # 提取bounds
                bounds = node.get('bounds')
                if not bounds:
                    continue

                # 解析坐标
                match = re.search(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds)
                if not match:
                    continue

                x1, y1, x2, y2 = map(int, match.groups())

                # 计算中心点
                cx = (x1 + x2) // 2
                cy = (y1 + y2) // 2

                # 存储元素信息
                self.elements.append({
                    'text': text,
                    'bounds': (x1, y1, x2, y2),
                    'center': (cx, cy),
                    'width': abs(x2 - x1),
                    'height': abs(y2 - y1)
                })
        except:
            raise Exception(f"xml parse error for xml:{self.xml_str}")

    def get_first_element_by_text(self, text):
        """
        根据文本获取元素坐标和中心点
        :param text: 要查找的文本
        :return: 元素坐标和中心点，如果未找到返回None
        """
        for elem in self.elements:
            if elem['text'] == text:
                return {
                    'bounds': elem['bounds'],
                    'center': elem['center'],
                    'width': elem['width'],
                    'height': elem['height'],
                }
        return {}

    def get_first_element_by_pattern(self, pattern: re.Pattern):
        """
        根据文本获取元素坐标和中心点
        :param pattern: 要查找的文本模式
        :return: 元素坐标和中心点，如果未找到返回None
        """
        for elem in self.elements:
            if pattern.search(elem['text']):
                return {
                    'bounds': elem['bounds'],
                    'center': elem['center'],
                    'width': elem['width'],
                    'height': elem['height'],
                }
        return {}

    def get_all_elements_by_text(self, text):
        """
        根据文本获取元素坐标和中心点
        :param text: 要查找的文本
        :return: 元素坐标和中心点，如果未找到返回None
        """
        elems = []
        for elem in self.elements:
            if elem['text'] == text:
                elems.append(elem)
        return elems

    def get_all_elements(self):
        """
        获取所有可见文本元素
        :return: 所有文本元素的列表
        """
        return self.elements

    @classmethod
    def is_in(cls, x, y, element: dict, width, height):
        """
        判断x, y 是否位于 element bounds经过标准化处理的坐标内
        """
        if not element:
            return False
        if element['bounds'][0] <= x * width <= element['bounds'][2] and element['bounds'][1] <= y * height <= element['bounds'][3]:
            return True
        return False


if __name__ == '__main__':
    from pathlib import Path
    xml = Path(r'D:\Projects\nanoai\projects\uiagent\jie_parking\datasets\bad_case_with_xml\a8a26de85434485a98611d23c3e4401d\xmls\eba058ca-9487-4840-899e-08fd0de79b7f.xml').read_text(encoding='utf-8')
    xml_parser = TextElementLocator(xml)
    print(xml_parser)
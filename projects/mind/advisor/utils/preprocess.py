import re
import yaml
import os
from typing import Any, Dict

pattern = r'<think>([\s\S]*?)</think>'


def extract_think(text: str) -> str:
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip()
    return ""


def read_json(path: str) -> Any:
    with open(path, "r", encoding='utf-8') as file:
        return yaml.safe_load(file.read())


def read_txt(path: str) -> Any:
    with open(path, "r", encoding='utf-8') as file:
        return file.read()


def read_file_from_folder(folder: str, suffix=".json") -> Dict[str, Any]:
    data = dict()
    for file in os.listdir(folder):
        if file.endswith(suffix) and suffix==".json":
            file_path = os.path.join(folder, file)
            data[file] = read_json(file_path)
        elif file.endswith(suffix) and suffix==".txt":
            file_path = os.path.join(folder, file)
            data[file] = read_txt(file_path)
    return data


class LenientJSONParser:
    """使用YAML解析宽松JSON的封装类"""

    def __init__(self):
        # 可以配置YAML加载器行为
        self.loader = yaml.SafeLoader

    def parse(self, text: str) -> Any:
        """解析宽松的JSON/YAML"""
        try:
            text = text.strip().removeprefix("```json").removeprefix("```python").removesuffix("```")
            return yaml.load(text, Loader=self.loader)
        except yaml.YAMLError as e:
            raise e

    def safe_parse(self, text: str) -> str:
        """清理并转换为标准JSON"""
        return self.parse(text)



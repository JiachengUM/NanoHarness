from typing import Optional, Any

import yaml
from pydantic import BaseModel, Field

from nanoai.utils import get_logger

logger = get_logger(__name__)


class CustomExtraction(BaseModel):
    """自定义提炼模型"""
    core_content: str = Field(..., description="核心内容")
    analysis: Optional[str] = Field(None, description="分析过程")
    recommendation: Optional[str] = Field(None, description="建议内容")


class LenientJSONParser:
    """使用YAML解析宽松JSON的封装类"""

    def __init__(self, model, enable_thinking):
        # 可以配置YAML加载器行为
        self.loader = yaml.SafeLoader
        self.model = model
        self.enable_thinking = enable_thinking

    def parse(self, text: str) -> Any:
        """解析宽松的JSON/YAML"""
        try:
            text = text.strip().removeprefix("```json").removeprefix("```python").removesuffix("```")
            return yaml.load(text, Loader=self.loader)
        except yaml.YAMLError as e:
            logger.warning(f"json解析失败：{e}")
            logger.info("\n自定义提炼")
            raise e

    def safe_parse(self, text: str) -> str:
        """清理并转换为标准JSON"""
        return self.parse(text)

    def read_json(self, path):
        with open(path, "r", encoding='utf-8') as file:
            return yaml.safe_load(file.read())

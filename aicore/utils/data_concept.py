from pydantic import BaseModel, Field
from typing import assert_never

__all__ = [
    "ClsResult",
    "JudgeResult",
]

class ClsResult(BaseModel):
    """分类结果。"""

    category: str = Field(..., title="类别", description="分类的类别名称。")
    reason: str = Field(..., title="原因", description="判断为该类别的原因。")

    def __nl_repr__(self) -> str:
        return f"{self.category}。{self.reason}"


class JudgeResult(BaseModel):
    """判断对错的结果。"""

    judgment: bool | None = Field(
        ..., title="判断", description="判断对错的结果, True or False or None。None表示无法判断。"
    )
    reason: str = Field(..., title="原因", description="判断的原因。")

    def __bool__(self) -> bool:
        """可以被当作bool。"""
        return self.judgment is True

    def __nl_repr__(self) -> str:
        if self.judgment is True:
            return f"正确。{self.reason}"
        elif self.judgment is False:
            return f"错误。{self.reason}"
        elif self.judgment is None:
            return f"无法判断。{self.reason}"
        else:
            assert_never(self.judgment)
            
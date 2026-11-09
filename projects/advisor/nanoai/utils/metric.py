import inspect
from enum import StrEnum
from typing import Any, Awaitable, Callable, cast

from pydantic import BaseModel, Field


def is_async_function(func) -> bool:
    """检测函数是否为异步函数"""
    return inspect.iscoroutinefunction(func)


class CriterionType(StrEnum):
    """评估标准的分类。可以用于DatumCriterion的category字段。
    这里的定义很难标准化和通用。先试用着吧。
    """

    ACCURACY = "准确性"
    COMPLETENESS = "完整性"
    CONSISTENCY = "一致性"
    RELEVANCE = "相关性"
    CLARITY = "清晰度"
    GRAMMAR = "语法"
    LOGIC = "逻辑性"
    FORMAT = "格式"
    OTHER = "其它"


class DatumCriterion[DT, MT](BaseModel):
    """这个类定义了单个数据的质量评估标准和实现。
    D是任意类型。完全通用。它是测试体系的基础。
    """

    # name: str = Field(..., description="评估标准的名称。")
    # TODO: 增加name字段。暂时没用。

    # category: str = Field(..., description="评估标准的分类。")
    # TODO: 增加category字段。暂时没用。

    description: str = Field(..., title="标准描述", description="评估标准的详细描述。必须可以被量化。")

    metric: Callable[[DT], MT | Awaitable[MT]] = Field(
        ..., description="计算评估标准的量化值的函数。支持同步和异步函数。", repr=False
    )

    # TODO: 增加async计算metric的函数。

    params: dict[str, Any] = Field(default_factory=dict, description="评估函数的参数。例如threshold。", repr=False)

    # weight: float = Field(..., description="评估标准的权重。")
    # TODO: 权重应该放在这里么？它是需要被归一化的。其scope超出了单个DatumCriterion

    # priority: int = Field(default=0, description="评估标准的优先级。数字越大优先级越高。")
    # TODO: 增加priority字段。暂时没用。用IntEnum来实现？

    def run(self, datum: DT) -> MT:
        """同步运行评估标准的量化值计算。

        注意：如果metric是异步函数，此方法会抛出RuntimeError。
        对于异步metric，请使用arun方法。
        """
        if is_async_function(self.metric):
            raise RuntimeError(f"metric函数 '{self.metric.__name__}' 是异步的，请使用 arun() 方法")
        result = self.metric(datum, **self.params)
        return cast(MT, result)

    async def arun(self, datum: DT) -> MT:
        """异步运行评估标准的量化值计算。

        支持同步和异步metric函数。
        """
        result = self.metric(datum, **self.params)
        if isinstance(result, Awaitable):
            result = await result
        return cast(MT, result)

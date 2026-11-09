from pydantic import BaseModel, Field, model_validator

from aicore.utils.nl_repr import nl_repr


class SafeResult[T](BaseModel):
    """
    任务执行结果：正常结果result和异常结果error有且只有一个成立
    """

    data: T | None = Field(default=None, description="任务执行成功时的结果")

    error: str | None = Field(default=None, description="任务执行失败时的信息")

    @model_validator(mode="after")
    def check_data_error(self):
        """校验data和error有且只有一个成立"""
        if (self.data is None) == (self.error is None):
            raise ValueError("data和error有且只有一个成立")
        return self

    @property
    def is_success(self) -> bool:
        """判断任务是否执行成功"""
        return self.error is None

    def nl_repr(self) -> str:
        # TODO: 按说应该用 __nl_repr__。但好像有点问题。忘了。
        if self.is_success:
            return nl_repr(self.data)
        else:
            return f"任务执行失败: {self.error}"

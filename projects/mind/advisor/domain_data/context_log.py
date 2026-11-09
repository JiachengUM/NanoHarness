from pydantic import BaseModel, Field


class ContextLog(BaseModel):
    """
    实车环境车辆状态上下文信息。
    """

    log_id: str | None = Field(
        default=None, title="日志ID", description="实车环境车辆状态上下文信息的日志ID"
    )
    context: dict | None = Field(
        default=None,
        title="实车环境车辆状态上下文信息",
        description="实车环境车辆状态上下文信息",
    )
    log_type: str | None = Field(
        default=None,
        title="日志类型",
        description="全量日志还是diff日志，取值为full或diff",
    )
    remark: str | None = Field(
        default=None, title="备注", description="实车环境车辆状态上下文信息的备注"
    )

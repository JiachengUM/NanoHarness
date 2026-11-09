import logging

from pydantic import BaseModel, Field, field_validator

from projects.uiagent.core import (
    ActionSource,
    StepType,
    UIStepStatus,
    UITaskResult,
    WorkflowStatus,
)
from projects.uiagent.core.action import Action, AskAction
from projects.uiagent.core.flow_data import UIResult

logger = logging.getLogger(__name__)


class UITaskResultSimple(BaseModel):

    thought: str = Field(title="思考", description="如何完成用户任务的思考")
    actions: list[Action] = Field(title="动作", description="如何完成用户任务的动作列表")
    source: ActionSource = Field(
        default=ActionSource.UI, title="动作产生来源", description="表明actions产生的来源")


class UIAgentData(BaseModel):
    workflow_status: WorkflowStatus = Field(
        default=WorkflowStatus.RUNNING, title="UI工作流状态", description="UI工作流状态")
    step_status: UIStepStatus = Field(
        default=UIStepStatus.RUNNING, title="UI步骤状态", description="UI步骤状态")
    current_step: StepType = Field(title="当前步骤", description="当前步骤")
    # 先兼容新旧两种UIResult和UITaskResult
    results: list[UITaskResultSimple | UITaskResult | UIResult] | None = Field(
        default=[], title="工作流返回的数据", description="工作流返回的数据,有answer+UIRunResult的字段，且两者互斥")
    error_msg: str = ""

    @field_validator("results", mode="before")
    @classmethod
    def results_validate(cls, v: list[UITaskResult | UITaskResultSimple | UIResult | str] | None):

        if not v:
            return []
        new_results = []
        for result in v:
            if isinstance(result, str):
                new_results.append(UITaskResultSimple(
                    thought='',
                    actions=[AskAction(content=result)],
                    source=ActionSource.RPA
                ))
            else:
                new_results.append(
                    UITaskResultSimple(
                        thought=result.thought,
                        actions=result.actions,
                        source=result.source
                    )
                )
        return new_results


# ui agent 返回体，start, nl_only,image_only通用
class UIAgentResponse(BaseModel):
    """UIAgent 通用接口响应参数体"""

    code: int = Field(default=0, title="状态码", description="0:成功 1000：系统内部错误")
    trace_id: str = Field(
        title="trace_id", description="用于追踪一次完整的任务运行状态，包括追踪其对话记录以及状态")
    data: UIAgentData | dict = {}
    msg: str = "成功"


class UIAgentNLOnlyRequest(BaseModel):
    """UIAgent nl_only接口请求参数体"""
    """query"""
    query: str = Field(title="query", description="query")
    """chat_id 追踪一次工作流的id"""
    chat_id: str = Field(
        pattern=r"^[a-z0-9]{32}$",
        description="用于追踪一次完整的任务运行状态，包括追踪其对话记录以及状态，必须为32位的小写字母和数字的字符串",
    )


class UIAgentImageOnlyRequest(BaseModel):
    """UIAgent gui_image_only接口请求参数体"""

    """图片base64"""
    image_base64: str = Field(title="图片base64", description="图片的base64")
    """图片格式"""
    image_format: str = Field(title="图片格式", description="jpg、png、jpeg")
    """xml 用于可能的RPA操作"""
    xml: str | None = Field(default=None, title="xml", description="xml")
    chat_id: str = Field(
        pattern=r"^[a-z0-9]{32}$",
        description="用于追踪一次完整的任务运行状态，包括追踪其对话记录以及状态，必须为32位的小写字母和数字的字符串",
    )


if __name__ == '__main__':
    ui_data = UIAgentData(results=["你好"], current_step="")
    # print(ui_data.model_dump_json(ensure_ascii=False, indent=4))

    m = UIAgentResponse(
        code=0,
        trace_id="123",
        data=ui_data,
        msg="成功"
    )

    print(m.model_dump_json())

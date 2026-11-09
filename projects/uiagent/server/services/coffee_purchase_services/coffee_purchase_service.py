import logging
import traceback
from typing import Dict

from projects.uiagent.core.uiflow import UIFlowResult
from projects.uiagent.coffee_purchase.workflow import CoffeePurchaseUiFlow
from projects.uiagent.server.dto.ui_agent import (
    UIAgentData,
    UIAgentNLOnlyRequest,
    UIAgentResponse,
    UIAgentImageOnlyRequest,
)
from projects.uiagent.server.utils.redis_util import RedisUtil

logger = logging.getLogger(__name__)


class CoffeePurchaseService:
    def __init__(self):
        self.workflow_cache: Dict[str, CoffeePurchaseUiFlow] = {}
        self.trace_id = ""
        self.redis_client = None

    def _set_trace_id(self, trace_id: str):
        self.trace_id = trace_id

    def _set_redis_client(self, redis_client: RedisUtil):
        self.redis_client = redis_client

    def _get_or_create_workflow(self, chat_id: str) -> CoffeePurchaseUiFlow:
        """获取或创建指定chat_id的workflow实例"""
        if chat_id not in self.workflow_cache:
            self.workflow_cache[chat_id] = CoffeePurchaseUiFlow()
            logger.info(f"Created new workflow for chat_id: {chat_id}")
        return self.workflow_cache[chat_id]

    def _cleanup_workflow(self, chat_id: str):
        """清理指定chat_id的workflow实例"""
        if chat_id in self.workflow_cache:
            del self.workflow_cache[chat_id]
            logger.info(f"Cleaned up workflow for chat_id: {chat_id}")

    async def gui_nl_only(self, request: UIAgentNLOnlyRequest, trace_id: str) -> UIAgentResponse:
        try:
            chat_id = request.chat_id
            workflow = self._get_or_create_workflow(chat_id)
            current_step = workflow.state.step
            query = request.query
            result: UIFlowResult = await workflow.run_nl(query) # 不是通过结果判断走nl还是ui，而是根据状态+用户是否语音交互
            print("chat_id: " + request.chat_id + " 的工作流状态为: " + str(result.state.status))
            workflow_status = result.state.status
            step_status = result.state.step_status[result.state.step]
            error_msg = str(result.error) if result.error else ""
            return UIAgentResponse(
                trace_id=trace_id,
                data=UIAgentData(
                    current_step=current_step,
                    workflow_status=workflow_status,
                    step_status=step_status,
                    results=result.results,
                    error_msg=error_msg,
                )
            )
        except Exception:
            msg = traceback.format_exc()
            logger.error(f"[{trace_id}]处理报错：{msg}")
            return UIAgentResponse(
                code=1000,
                trace_id=trace_id,
                msg=msg
            )

    async def gui_nl_only_test(self, request: UIAgentNLOnlyRequest, trace_id: str) -> UIAgentResponse:
        try:
            chat_id = request.chat_id
            workflow = self._get_or_create_workflow(chat_id)
            current_step=workflow.state.step
            query = request.query
            result: UIFlowResult = await workflow.run_nl(query) # 不是通过结果判断走nl还是ui，而是根据状态+用户是否语音交互
            print("chat_id: " + request.chat_id + " 的工作流状态为: " + str(result.state.status))
            workflow_status = result.state.status
            step_status = result.state.step_status[result.state.step]
            error_msg = str(result.error) if result.error else ""
            return UIAgentResponse(
                trace_id=trace_id,
                data=UIAgentData(
                    current_step=current_step,
                    workflow_status=workflow_status,
                    step_status=step_status,
                    results=result.results,
                    error_msg=error_msg,
                )
            )
        except Exception:
            msg = traceback.format_exc()
            logger.error(f"[{trace_id}]处理报错：{msg}")
            return UIAgentResponse(
                code=1000,
                trace_id=trace_id,
                msg=msg
            )

    async def gui_image_only(
        self, request: UIAgentImageOnlyRequest, trace_id: str
    ) -> UIAgentResponse:
        try:
            chat_id = request.chat_id
            workflow = self._get_or_create_workflow(chat_id)
            current_step = workflow.state.step
            result: UIFlowResult = await workflow.run_ui(request.image_base64, request.image_format, request.xml)
            print("chat_id: " + request.chat_id + " 的工作流状态为: " + str(result.state.status))
            workflow_status = result.state.status
            step_status = result.state.step_status[result.state.step]
            error_msg = str(result.error) if result.error else ""
            return UIAgentResponse(
                trace_id=trace_id,
                data=UIAgentData(
                    current_step=current_step,
                    workflow_status=workflow_status,
                    step_status=step_status,
                    results=result.results,
                    error_msg=error_msg,
                )
            )
        except Exception:
            msg = traceback.format_exc()
            logger.error(f"[{trace_id}]处理报错：{msg}")
            return UIAgentResponse(
                code=1000,
                trace_id=trace_id,
                msg=msg
            )

    async def gui_image_only_test(
        self, request: UIAgentImageOnlyRequest, trace_id: str
    ) -> UIAgentResponse:
        try:
            chat_id = request.chat_id
            workflow = self._get_or_create_workflow(chat_id)
            current_step = workflow.state.step
            result: UIFlowResult = await workflow.run_ui(request.image_base64, request.image_format, request.xml)
            print("chat_id: " + request.chat_id + " 的工作流状态为: " + str(result.state.status))
            workflow_status = result.state.status
            step_status = result.state.step_status[result.state.step]
            error_msg = str(result.error) if result.error else ""
            return UIAgentResponse(
                trace_id=trace_id,
                data=UIAgentData(
                    current_step=current_step,
                    workflow_status=workflow_status,
                    step_status=step_status,
                    results=result.results,
                    error_msg=error_msg,
                )
            )
        except Exception:
            msg = traceback.format_exc()
            logger.error(f"[{trace_id}]处理报错：{msg}")
            return UIAgentResponse(
                code=1000,
                trace_id=trace_id,
                msg=msg
            )

async def test_uiflow_use_model():
    from nanoai.model.vlm import image_from_path
    from projects.uiagent.coffee_purchase.datasets import DATASET_ROOT


    image_path0 = str(DATASET_ROOT / "coffee" /
                     "images" / "000_首页广告.png")
    image0, image_format0 = image_from_path(image_path0)

    image_path = str(DATASET_ROOT / "coffee" /
                     "images" / "001_首页.jpg")
    image, image_format = image_from_path(image_path)

    image_path_2 = str(DATASET_ROOT / "coffee" /
                       "images" / "002_选门店01_维璟.jpg")
    image2, image_format2 = image_from_path(image_path_2)
    xml_detail = "detail"
    xml_submit = "submit"
    chat_id = "12345678901234567890123456789017"
    trace_id = "111"
    uiflow_service = CoffeePurchaseService()
    
    
    nl_request = UIAgentNLOnlyRequest(
        query="帮我自提一杯维璟店的标准美式",
        chat_id=chat_id
    )
    result = await uiflow_service.gui_nl_only(nl_request, trace_id)
    print(result)
    print("+" * 100)
    
    result = await uiflow_service.gui_image_only(UIAgentImageOnlyRequest(
        chat_id=chat_id,
        image_base64=image0,
        image_format=image_format0,
        xml=xml_detail
    ), trace_id)
    print(result)
    print("+" * 100)
    
    result = await uiflow_service.gui_image_only(UIAgentImageOnlyRequest(
        chat_id=chat_id,
        image_base64=image,
        image_format=image_format,
        xml=xml_submit
    ), trace_id)
    print(result)
    print("+" * 100)
    result = await uiflow_service.gui_image_only(UIAgentImageOnlyRequest(
        chat_id=chat_id,
        image_base64=image2,
        image_format=image_format2,
        xml=xml_submit
    ), trace_id)
    print(result)
    print("+" * 100)


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_uiflow_use_model())
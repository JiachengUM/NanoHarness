import logging
import traceback
from typing import Dict

from projects.uiagent.core import WorkflowResult
from projects.uiagent.jie_parking.data_define import ParkingSteps
from projects.uiagent.jie_parking.new_workflow import (
    JieParkingWorkflow,
    jie_parking_intent_categories,
)
from projects.uiagent.server.dto.ui_agent import (
    UIAgentData,
    UIAgentImageOnlyRequest,
    UIAgentNLOnlyRequest,
    UIAgentResponse,
)
from projects.uiagent.server.utils.redis_util import RedisUtil

logger = logging.getLogger(__name__)


class GUIService:
    def __init__(self):
        self.workflow_cache: Dict[str, JieParkingWorkflow] = {}
        self.trace_id = ""
        self.redis_client = None

    def _set_trace_id(self, trace_id: str):
        self.trace_id = trace_id

    def _set_redis_client(self, redis_client: RedisUtil):
        self.redis_client = redis_client

    def _get_or_create_workflow(self, chat_id: str) -> JieParkingWorkflow:
        """获取或创建指定chat_id的workflow实例"""
        if chat_id not in self.workflow_cache:
            self.workflow_cache[chat_id] = JieParkingWorkflow(
                start_step=ParkingSteps.SELECT_CAR, intent_categories=jie_parking_intent_categories)
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
            current_step = workflow.state.current_step
            query = request.query
            # 不是通过结果判断走nl还是ui，而是根据状态+用户是否语音交互
            result: WorkflowResult = await workflow.run_nl(query)
            print("chat_id: " + request.chat_id +
                  " 的工作流状态为: " + str(result.state.status))
            workflow_status = result.state.status
            step_status = result.state.step_status[result.state.current_step]
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
            current_step = workflow.state.current_step
            query = request.query
            # 不是通过结果判断走nl还是ui，而是根据状态+用户是否语音交互
            result: WorkflowResult = await workflow.run_nl(query)
            print("chat_id: " + request.chat_id +
                  " 的工作流状态为: " + str(result.state.status))
            workflow_status = result.state.status
            step_status = result.state.step_status[result.state.current_step]
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
            current_step = workflow.state.current_step
            result: WorkflowResult = await workflow.run_ui(request.image_base64, request.image_format, request.xml)
            print("chat_id: " + request.chat_id +
                  " 的工作流状态为: " + str(result.state.status))
            workflow_status = result.state.status
            step_status = result.state.step_status[result.state.current_step]
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
            current_step = workflow.state.current_step
            result: WorkflowResult = await workflow.run_ui(request.image_base64, request.image_format, request.xml)
            print("chat_id: " + request.chat_id +
                  " 的工作流状态为: " + str(result.state.status))
            workflow_status = result.state.status
            step_status = result.state.step_status[result.state.current_step]
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

import json
import logging
import time

from fastapi import APIRouter, Request

from projects.uiagent.server.dto.ui_agent import (
    UIAgentNLOnlyRequest,
    UIAgentImageOnlyRequest,
)
from projects.uiagent.server.services.jie_parking_services.gui_service import GUIService
from projects.uiagent.server.services.movie_ticket_booking_services.movie_ticket_booking_service import \
    MovieTicketBookingService
from projects.uiagent.server.services.seatbooking_mini_services.seatbooking_mini_service import SeatBookingMiniService
from projects.uiagent.server.services.coffee_purchase_services.coffee_purchase_service import CoffeePurchaseService

logger = logging.getLogger(__name__)
gui_router = APIRouter(prefix="/api")


class GUIController:

    def __init__(self):
        self.gui_service = GUIService()
        self.seatbooking_service = SeatBookingMiniService()
        self.coffee_purchase_service = CoffeePurchaseService()
        self.movie_ticket_booking_service = MovieTicketBookingService()
        return


    async def gui_nl_only(self, request: Request):
        """
        处理GUI请求
        """
        start_time = time.time()
        logger.info("收到GUI请求")
        req_json = await request.json()
        body_req = UIAgentNLOnlyRequest.model_validate(req_json)
        # 获取当前请求的 trace_id
        current_trace_id = request.state.trace_id
        self.gui_service._set_redis_client(request.app.state.redis_client)
        # self.gui_service._set_trace_id(request.state.trace_id)
        result = await self.gui_service.gui_nl_only(body_req, trace_id=current_trace_id)
        # result.trace_id = request.state.trace_id
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"【GUI处理耗时】 {elapsed_time:.2f}秒")
        return result

    async def gui_nl_only_test(self, request: Request):
        """
        处理GUI请求
        """
        start_time = time.time()
        logger.info("收到GUI请求")
        req_json = await request.json()
        body_req = UIAgentNLOnlyRequest.model_validate(req_json)
        # 获取当前请求的 trace_id
        current_trace_id = request.state.trace_id
        self.gui_service._set_redis_client(request.app.state.redis_client)
        # self.gui_service._set_trace_id(request.state.trace_id)
        result = await self.gui_service.gui_nl_only_test(body_req, trace_id=current_trace_id)
        # result.trace_id = request.state.trace_id
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"【GUI处理耗时】 {elapsed_time:.2f}秒")
        return result

    async def gui_image_only(self, request: Request):
        """
        处理GUI请求
        """
        start_time = time.time()
        logger.info("收到GUI请求")
        req_json = await request.json()
        body_req = UIAgentImageOnlyRequest.model_validate(req_json)
        # 获取当前请求的 trace_id
        current_trace_id = request.state.trace_id
        self.gui_service._set_redis_client(request.app.state.redis_client)
        # self.gui_service._set_trace_id(request.state.trace_id)
        result = await self.gui_service.gui_image_only(body_req, trace_id=current_trace_id)
        # result.trace_id = request.state.trace_id
        logger.info(
            f"返回GUI结果: {json.dumps(result.json(), ensure_ascii=False, separators=(',', ':'))}"
        )
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"【GUI处理耗时】 {elapsed_time:.2f}秒")
        return result

    async def gui_image_only_test(self, request: Request):
        """
        处理GUI请求
        """
        start_time = time.time()
        logger.info("收到GUI请求")
        req_json = await request.json()
        body_req = UIAgentImageOnlyRequest.model_validate(req_json)
        # 获取当前请求的 trace_id
        current_trace_id = request.state.trace_id
        self.gui_service._set_redis_client(request.app.state.redis_client)
        # self.gui_service._set_trace_id(request.state.trace_id)
        result = await self.gui_service.gui_image_only_test(body_req, trace_id=current_trace_id)
        # result.trace_id = request.state.trace_id
        logger.info(
            f"返回GUI结果: {json.dumps(result.json(), ensure_ascii=False, separators=(',', ':'))}"
        )
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"【GUI处理耗时】 {elapsed_time:.2f}秒")
        return result

    async def seatbooking_mini_nl_only(self, request: Request):
        """
        处理GUI请求
        """
        start_time = time.time()
        logger.info("收到GUI请求")
        req_json = await request.json()
        body_req = UIAgentNLOnlyRequest.model_validate(req_json)
        # 获取当前请求的 trace_id
        current_trace_id = request.state.trace_id
        self.seatbooking_service._set_redis_client(request.app.state.redis_client)
        # self.seatbooking_service._set_trace_id(request.state.trace_id)
        result = await self.seatbooking_service.gui_nl_only(body_req, trace_id=current_trace_id)
        # result.trace_id = request.state.trace_id
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"【GUI处理耗时】 {elapsed_time:.2f}秒")
        return result

    async def seatbooking_mini_nl_only_test(self, request: Request):
        """
        处理GUI请求
        """
        start_time = time.time()
        logger.info("收到GUI请求")
        req_json = await request.json()
        body_req = UIAgentNLOnlyRequest.model_validate(req_json)
        # 获取当前请求的 trace_id
        current_trace_id = request.state.trace_id
        self.seatbooking_service._set_redis_client(request.app.state.redis_client)
        # self.seatbooking_service._set_trace_id(request.state.trace_id)
        result = await self.seatbooking_service.gui_nl_only_test(body_req, trace_id=current_trace_id)
        # result.trace_id = request.state.trace_id
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"【GUI处理耗时】 {elapsed_time:.2f}秒")
        return result

    async def seatbooking_mini_image_only(self, request: Request):
        """
        处理GUI请求
        """
        start_time = time.time()
        logger.info("收到GUI请求")
        req_json = await request.json()
        body_req = UIAgentImageOnlyRequest.model_validate(req_json)
        # 获取当前请求的 trace_id
        current_trace_id = request.state.trace_id
        self.seatbooking_service._set_redis_client(request.app.state.redis_client)
        # self.seatbooking_service._set_trace_id(request.state.trace_id)
        result = await self.seatbooking_service.gui_image_only(body_req, trace_id=current_trace_id)
        # result.trace_id = request.state.trace_id
        logger.info(
            f"返回GUI结果: {json.dumps(result.json(), ensure_ascii=False, separators=(',', ':'))}"
        )
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"【GUI处理耗时】 {elapsed_time:.2f}秒")
        return result

    async def seatbooking_mini_image_only_test(self, request: Request):
        """
        处理GUI请求
        """
        start_time = time.time()
        logger.info("收到GUI请求")
        req_json = await request.json()
        body_req = UIAgentImageOnlyRequest.model_validate(req_json)
        # 获取当前请求的 trace_id
        current_trace_id = request.state.trace_id
        self.seatbooking_service._set_redis_client(request.app.state.redis_client)
        # self.seatbooking_service._set_trace_id(request.state.trace_id)
        result = await self.seatbooking_service.gui_image_only_test(body_req, trace_id=current_trace_id)
        # result.trace_id = request.state.trace_id
        logger.info(
            f"返回GUI结果: {json.dumps(result.json(), ensure_ascii=False, separators=(',', ':'))}"
        )
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"【GUI处理耗时】 {elapsed_time:.2f}秒")
        return result


    async def coffee_purchase_nl_only(self, request: Request):
        """
        处理GUI请求
        """
        start_time = time.time()
        logger.info("收到GUI请求")
        req_json = await request.json()
        body_req = UIAgentNLOnlyRequest.model_validate(req_json)
        # 获取当前请求的 trace_id
        current_trace_id = request.state.trace_id
        self.coffee_purchase_service._set_redis_client(request.app.state.redis_client)
        # self.seatbooking_service._set_trace_id(request.state.trace_id)
        result = await self.coffee_purchase_service.gui_nl_only(body_req, trace_id=current_trace_id)
        # result.trace_id = request.state.trace_id
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"【GUI处理耗时】 {elapsed_time:.2f}秒")
        return result

    async def coffee_purchase_nl_only_test(self, request: Request):
        """
        处理GUI请求
        """
        start_time = time.time()
        logger.info("收到GUI请求")
        req_json = await request.json()
        body_req = UIAgentNLOnlyRequest.model_validate(req_json)
        # 获取当前请求的 trace_id
        current_trace_id = request.state.trace_id
        self.coffee_purchase_service._set_redis_client(request.app.state.redis_client)
        # self.seatbooking_service._set_trace_id(request.state.trace_id)
        result = await self.coffee_purchase_service.gui_nl_only_test(body_req, trace_id=current_trace_id)
        # result.trace_id = request.state.trace_id
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"【GUI处理耗时】 {elapsed_time:.2f}秒")
        return result

    async def coffee_purchase_image_only(self, request: Request):
        """
        处理GUI请求
        """
        start_time = time.time()
        logger.info("收到GUI请求")
        req_json = await request.json()
        body_req = UIAgentImageOnlyRequest.model_validate(req_json)
        # 获取当前请求的 trace_id
        current_trace_id = request.state.trace_id
        self.coffee_purchase_service._set_redis_client(request.app.state.redis_client)
        # self.seatbooking_service._set_trace_id(request.state.trace_id)
        result = await self.coffee_purchase_service.gui_image_only(body_req, trace_id=current_trace_id)
        # result.trace_id = request.state.trace_id
        logger.info(
            f"返回GUI结果: {json.dumps(result.json(), ensure_ascii=False, separators=(',', ':'))}"
        )
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"【GUI处理耗时】 {elapsed_time:.2f}秒")
        return result

    async def coffee_purchase_image_only_test(self, request: Request):
        """
        处理GUI请求
        """
        start_time = time.time()
        logger.info("收到GUI请求")
        req_json = await request.json()
        body_req = UIAgentImageOnlyRequest.model_validate(req_json)
        # 获取当前请求的 trace_id
        current_trace_id = request.state.trace_id
        self.coffee_purchase_service._set_redis_client(request.app.state.redis_client)
        # self.seatbooking_service._set_trace_id(request.state.trace_id)
        result = await self.coffee_purchase_service.gui_image_only_test(body_req, trace_id=current_trace_id)
        # result.trace_id = request.state.trace_id
        logger.info(
            f"返回GUI结果: {json.dumps(result.json(), ensure_ascii=False, separators=(',', ':'))}"
        )
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"【GUI处理耗时】 {elapsed_time:.2f}秒")
        return result

    async def movie_ticket_booking_nl_only(self, request: Request):
        """
        处理GUI请求
        """
        start_time = time.time()
        logger.info("收到GUI请求")
        req_json = await request.json()
        body_req = UIAgentNLOnlyRequest.model_validate(req_json)
        # 获取当前请求的 trace_id
        current_trace_id = request.state.trace_id
        self.movie_ticket_booking_service._set_redis_client(request.app.state.redis_client)
        result = await self.movie_ticket_booking_service.gui_nl_only(body_req, trace_id=current_trace_id)
        # result.trace_id = request.state.trace_id
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"【GUI处理耗时】 {elapsed_time:.2f}秒")
        return result

    async def movie_ticket_booking_nl_only_test(self, request: Request):
        """
        处理GUI请求
        """
        start_time = time.time()
        logger.info("收到GUI请求")
        req_json = await request.json()
        body_req = UIAgentNLOnlyRequest.model_validate(req_json)
        # 获取当前请求的 trace_id
        current_trace_id = request.state.trace_id
        self.movie_ticket_booking_service._set_redis_client(request.app.state.redis_client)
        result = await self.movie_ticket_booking_service.gui_nl_only_test(body_req, trace_id=current_trace_id)
        # result.trace_id = request.state.trace_id
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"【GUI处理耗时】 {elapsed_time:.2f}秒")
        return result

    async def movie_ticket_booking_image_only(self, request: Request):
        """
        处理GUI请求
        """
        start_time = time.time()
        logger.info("收到GUI请求")
        req_json = await request.json()
        body_req = UIAgentImageOnlyRequest.model_validate(req_json)
        # 获取当前请求的 trace_id
        current_trace_id = request.state.trace_id
        self.movie_ticket_booking_service._set_redis_client(request.app.state.redis_client)
        result = await self.movie_ticket_booking_service.gui_image_only(body_req, trace_id=current_trace_id)
        # result.trace_id = request.state.trace_id
        logger.info(
            f"返回GUI结果: {json.dumps(result.json(), ensure_ascii=False, separators=(',', ':'))}"
        )
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"【GUI处理耗时】 {elapsed_time:.2f}秒")
        return result

    async def movie_ticket_booking_image_only_test(self, request: Request):
        """
        处理GUI请求
        """
        start_time = time.time()
        logger.info("收到GUI请求")
        req_json = await request.json()
        body_req = UIAgentImageOnlyRequest.model_validate(req_json)
        # 获取当前请求的 trace_id
        current_trace_id = request.state.trace_id
        self.movie_ticket_booking_service._set_redis_client(request.app.state.redis_client)
        result = await self.movie_ticket_booking_service.gui_image_only_test(body_req, trace_id=current_trace_id)
        # result.trace_id = request.state.trace_id
        logger.info(
            f"返回GUI结果: {json.dumps(result.json(), ensure_ascii=False, separators=(',', ':'))}"
        )
        end_time = time.time()
        elapsed_time = end_time - start_time
        logger.info(f"【GUI处理耗时】 {elapsed_time:.2f}秒")
        return result

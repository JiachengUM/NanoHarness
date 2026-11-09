from fastapi import APIRouter
import fastapi
import logging

logger = logging.getLogger(__name__)
health_router = APIRouter(prefix="")

class HealthController:
    def __init__(self):
        pass
    async def health_check(self, request: fastapi.Request):
        """
        处理GUI请求
        """
        return {
            "error_code": 0,
            "error_msg": "success",
            "data": None
        }

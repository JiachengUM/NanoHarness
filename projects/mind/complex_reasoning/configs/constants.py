"""火山 API 端点与请求/响应模型。"""

import random
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, Optional

from pydantic import BaseModel, Field


class VolcAPIMethod(str, Enum):
    GET = "GET"
    POST = "POST"


@dataclass(frozen=True, slots=True)
class EndpointConfig:
    """
    强类型 endpoint 配置。

    frozen=True -> 不可变（推荐用于 config）
    slots=True  -> 减少内存 + 提升访问速度
    """
    path: str
    method: VolcAPIMethod


class VolcAPIEndpoint(Enum):
    PLUGIN_DO_STREAM = EndpointConfig(path="/dpfm/v1/plugin/do/stream", method=VolcAPIMethod.POST)

    CHAT_REJECTION = EndpointConfig(path="/dpfm/v1/chat/rejection", method=VolcAPIMethod.POST)

    @property
    def path(self) -> str:
        return self.value.path

    @property
    def method(self) -> VolcAPIMethod:
        return self.value.method


# ----- 火山请求/响应模型 -----


class VolcRequest(BaseModel):
    """火山请求参数。"""
    channel: str = Field(..., description="渠道")
    app_id: str = Field(..., description="app_id")
    chat_id: str = Field(..., description="chat_id")
    question_id: Optional[str] = Field(None, description="question_id")
    timestamp: int = Field(..., alias="_timestamp")
    nonce: int = Field(..., alias="_nonce", ge=0, le=65535)
    vehicle_id: Optional[str] = Field(None, description="设备ID")
    vehicle_type: Optional[str] = Field(None, pattern="^[a-zA-Z0-9]+$")

    model_config = {"validate_by_name": True}

    def to_dict(self) -> Dict:
        return self.model_dump(by_alias=True, exclude_none=True)

    @classmethod
    def build(cls, **extra_fields) -> "VolcRequest":
        base = {
            "channel": "extour-pro",
            "app_id": "99431",
            "_timestamp": int(datetime.now().timestamp()),
            "_nonce": random.randint(0, 65535),
            "vehicle_id": uuid.uuid4().hex[:17],
            "vehicle_type": "testvehicle",
            **extra_fields,
        }
        return cls(**base)


class VolcSSEResponse(BaseModel):
    """火山 SSE 单帧响应。"""
    error_code: int = Field(0, description="错误码")
    error_message: Optional[str] = Field("", description="错误消息")
    content: Optional[str] = Field(None, description="文本内容")
    observation: Optional[str] = Field(None, description="插件返回的 observation，FC 时为 JSON 字符串")

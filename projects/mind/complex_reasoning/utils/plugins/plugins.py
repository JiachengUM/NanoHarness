"""调用火山 FC 插件，对应原 plugins.call_fc。"""
import json
import logging
from enum import Enum
from typing import Any

from projects.mind.complex_reasoning.configs.config import get_app_config
from projects.mind.complex_reasoning.configs.constants import VolcAPIEndpoint, VolcRequest
from projects.mind.complex_reasoning.utils.plugins.plugin_support import _call_sse_api
from projects.mind.complex_reasoning.utils.plugins.question_id_pool import get_question_id_pool

logger = logging.getLogger(__name__)


class IntentType(str, Enum):
    VEHICLE_CONTROL = "vehicle_control"
    NAVIGATION = "navigation"
    MEDIA_CONTROL = "media_control"
    WEATHER = "weather"


async def call_fc(
    query: str,
    chat_id: str,
    intent_type: IntentType = IntentType.VEHICLE_CONTROL,
    plugin_params: dict | None = None,
) -> str:
    """
    调用火山 function_call 插件并返回 observation。

    流程：
    1. 组装插件请求 body（业务参数）。
    2. 组装签名所需的 query 参数（VolcRequest）。
    3. 调用 SSE 接口并提取首个有效 observation。

    # TODO: chat_id是上游传的，我们这边随便传了一个，不影响输出，但为什么这么做？
    """
    cfg = get_app_config()
    question_id = await get_question_id_pool().get_id()

    # 业务 body：发给插件接口的请求体
    body = {
        "query": query,
        "chat_id": chat_id,
        "plugin_params": json.dumps(plugin_params if plugin_params is not None else {}),
        "intent_type": intent_type.value,
        "question_id": question_id,
        "intent_log_id": question_id
    }

    # 签名/query 参数：用于鉴权与路由，不等同于 body
    volc_request = VolcRequest.build(
        channel=cfg.PLUGIN_CHANEL,
        app_id=str(cfg.PLUGIN_APP_ID),
        chat_id=chat_id,
        question_id=question_id
    )

    # SSE 结果解析逻辑在 _call_sse_api 内部统一处理
    return await _call_sse_api(VolcAPIEndpoint.PLUGIN_DO_STREAM, body, volc_request)

from __future__ import annotations

from typing import Optional

from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from projects.mind.complex_reasoning.task_mdb_models.chat_history import (
    AgentChatSessionDBSchema,
)
from projects.mind.intent.intent_mdb_models.category import CategoryDoc
from projects.mind.intent.task_mdb_models.intent_dataset import IntentDatasetDoc
from projects.mind.intent.task_mdb_models.intent_input import IntentInputDoc
from projects.mind.intent.task_mdb_models.intent_param import IntentParamDoc
from projects.mind.intent.task_mdb_models.intent_run import IntentRunDoc
from projects.mind.test_backend.config import (
    MongodbConfig,
    get_mongodb_config,
)
from projects.mind.advisor.mdb_models.memory import EpisodicMemoryDoc
from projects.mind.advisor.mdb_models.user import UserDoc
from projects.mind.advisor.mdb_models.vehicle_state import VehicleStateDoc
from projects.mind.advisor.mdb_models.visual_ext import VisualExtDoc
from projects.mind.advisor.mdb_models.visual_int import VisualIntDoc
from projects.mind.advisor.mdb_models.world_info import WorldInfoDoc
from projects.mind.advisor.task_mdb_models.advisor_dataset import AdvisorDatasetDoc
from projects.mind.advisor.task_mdb_models.advisor_input import AdvisorInputDoc
from projects.mind.advisor.task_mdb_models.advisor_run import AdvisorRunDoc
from projects.mind.complex_reasoning.task_mdb_models.dataset import (
    ComplexReasoningDatasetDoc,
)
from projects.mind.complex_reasoning.task_mdb_models.case import (
    ComplexReasoningCaseDoc,
)
from projects.mind.advisor.mdb_models.context_log import ContextLogDoc
from projects.mind.test_backend.mdb_models.task import TaskDoc, TaskRunDoc, TaskRunItemDoc, TaskRunItemEvalDoc, TaskRunItemMessageDoc
from projects.mind.test_backend.mdb_models.auth import FeishuUserDoc


# 全局客户端实例（初始化后复用）
_motor_client: AsyncIOMotorClient | None = None


def get_motor_client(mongodb_uri: str) -> AsyncIOMotorClient:
    """获取Motor客户端实例（单例模式）"""
    global _motor_client
    if _motor_client is None:
        _motor_client = AsyncIOMotorClient(mongodb_uri)
    return _motor_client


async def init_db(mongodb_config: Optional[MongodbConfig] = None) -> None:
    if mongodb_config is None:
        mongodb_config = get_mongodb_config()
    client = get_motor_client(mongodb_config.mongodb_uri)

    db = client[mongodb_config.mongodb_db]

    await init_beanie(
        database=db,
        document_models=[
            UserDoc,
            VehicleStateDoc,
            EpisodicMemoryDoc,
            VisualIntDoc,
            VisualExtDoc,
            WorldInfoDoc,
            AdvisorInputDoc,
            AdvisorDatasetDoc,
            AdvisorRunDoc,
            CategoryDoc,
            IntentInputDoc,
            IntentDatasetDoc,
            IntentRunDoc,
            IntentParamDoc,
            ComplexReasoningDatasetDoc,
            ComplexReasoningCaseDoc,
            AgentChatSessionDBSchema,
            ContextLogDoc,
            TaskDoc,
            TaskRunDoc,
            TaskRunItemDoc,
            TaskRunItemEvalDoc,
            TaskRunItemMessageDoc,
            FeishuUserDoc,
        ],
    )

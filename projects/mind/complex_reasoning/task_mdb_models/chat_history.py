from projects.mind.complex_reasoning.task_data.chat_history import (
    AgentChatSession,
)
from projects.mind.intent.intent_mdb_models.doc_base import TaskDataDocBase


class AgentChatSessionDBSchema(AgentChatSession, TaskDataDocBase):

    class Settings:
        name = "agent_chat_session"  # MongoDB 集合名称

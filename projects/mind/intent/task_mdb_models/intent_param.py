from typing import Optional

from pydantic import Field

from projects.mind.intent.intent_mdb_models.doc_base import TaskDataDocBase
from projects.mind.intent.task_data import IntentClsParam


class IntentParamDoc(IntentClsParam, TaskDataDocBase):
    brief: Optional[str] = Field(default=None, title="概要", description="概要")

    class Settings:
        name = "intent_param"


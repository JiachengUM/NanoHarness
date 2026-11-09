from pydantic import Field

from projects.mind.intent.intent_data.category import IntentCategory
from projects.mind.intent.intent_mdb_models.doc_base import IntentDataDocBase


class CategoryDoc(IntentCategory, IntentDataDocBase):
    group: str | None = Field(default=None, title="分组", description="分组名称")

    class Settings:
        name = "category"  # MongoDB 集合名称

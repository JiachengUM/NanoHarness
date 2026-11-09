from beanie import Document

from projects.mind.advisor.domain_data.context_log import ContextLog
from projects.mind.advisor.mdb_models.doc_base import AuditMixin


class ContextLogDoc(Document, AuditMixin, ContextLog):
    pass

    class Settings:
        name = "context_log"  # MongoDB 集合名称

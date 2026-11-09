from dataclasses import dataclass

from projects.hwhms.common.config.nacos_configs import NacosConfigs


@dataclass
class AppConfig:

    VOLC_URL: str = None
    AK: str = None
    SK: str = None

    # rag
    RAG_AK: str = None
    RAG_SK: str = None
    RAG_KNOWLEDGE_BASE_DOMAIN: str = None
    RAG_ACCOUNT_ID: str = None
    RAG_PROJECT_NAME: str = None
    RAG_COLLECTION_NAME: str = None
    RAG_COLLECTION_NAME_MUST_PASS: str = None


    @classmethod
    async def init(cls):
        cls.VOLC_URL = NacosConfigs.get_volc_config().get("volc").get("url")
        cls.AK = NacosConfigs.get_volc_config().get("volc").get("ak")
        cls.SK = NacosConfigs.get_volc_config().get("volc").get("sk")

        # rag
        cls.RAG_AK = NacosConfigs.get_volc_config().get("volc").get("rag_ak")
        cls.RAG_SK = NacosConfigs.get_volc_config().get("volc").get("rag_sk")
        cls.RAG_KNOWLEDGE_BASE_DOMAIN = NacosConfigs.get_volc_config().get("volc").get("rag_knowledge_base_domain")
        cls.RAG_ACCOUNT_ID = NacosConfigs.get_volc_config().get("volc").get("rag_account_id")
        cls.RAG_PROJECT_NAME = NacosConfigs.get_volc_config().get("volc").get("rag_project_name")
        cls.RAG_COLLECTION_NAME = NacosConfigs.get_volc_config().get("volc").get("rag_collection_name")
        cls.RAG_COLLECTION_NAME_MUST_PASS = NacosConfigs.get_volc_config().get("volc").get("rag_collection_name_must_pass")

        




from dataclasses import dataclass

from projects.uiagent.server.configs.nacos_configs import NacosConfigs


@dataclass
class AppConfig:
    """
    配置类（从 Nacos 获取配置）
    """

    DB_HOST: str = None
    DB_PORT: int = 3306
    DB_NAME: str = None
    DB_USER: str = None
    DB_PASSWORD: str = None
    DATABASE_URL: str = None

    REDIS_HOST: str = None
    REDIS_PORT: int = 6379
    REDIS_DB: int = 4
    REDIS_PASSWORD: str = None

    @classmethod
    async def init(cls):
        config_data = NacosConfigs.get_api_key_config()

        # 数据库
        cls.DB_HOST = config_data.get("mysql", {}).get("host")
        cls.DB_USER = config_data.get("mysql", {}).get("user")
        cls.DB_PASSWORD = config_data.get("mysql", {}).get("password")
        cls.DB_NAME = config_data.get("mysql", {}).get("database")
        cls.DATABASE_URL = f"mysql+aiomysql://{cls.DB_USER}:{cls.DB_PASSWORD}@{cls.DB_HOST}:{cls.DB_PORT}/{cls.DB_NAME}"

        # Redis
        cls.REDIS_HOST = config_data.get("redis", {}).get("url")
        cls.REDIS_PASSWORD = config_data.get("redis", {}).get("pwd", "")

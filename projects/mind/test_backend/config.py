from functools import cache
from dataclasses import dataclass


@dataclass(frozen=True)
class MongodbConfig:
    mongodb_uri: str
    mongodb_db: str

# local mongodb
# MONGODB_URI = "localhost:27017"
# MONGODB_DB = "ai-mind-test-dev"

# huoshan mongodb
MONGODB_URI = "REDACTED"
MONGODB_DB = "ai-mind-test-dev"

# aliyun mongodb
# MONGODB_URI = "REDACTED"
# MONGODB_DB = "ai-mind-test"

@dataclass(frozen=True)
class FeishuConfig:
    app_id: str
    app_secret: str
    oauth_redirect_uri: str | None
    auth_cookie_secure: bool


# feishu
FEISHU_APP_ID = "cli_aa929dbaa6f81bd6"
FEISHU_APP_SECRET = "REDACTED"
# FEISHU_OAUTH_REDIRECT_URI = "https://ai-mind-web-dev.extour-inc.com/api/auth/feishu/callback"
FEISHU_OAUTH_REDIRECT_URI = None
FEISHU_AUTH_COOKIE_SECURE = True


@cache
def get_mongodb_config() -> MongodbConfig:
    return MongodbConfig(
        mongodb_uri=MONGODB_URI,
        mongodb_db=MONGODB_DB,
    )


@cache
def get_feishu_config() -> FeishuConfig:
    return FeishuConfig(
        app_id=FEISHU_APP_ID,
        app_secret=FEISHU_APP_SECRET,
        oauth_redirect_uri=FEISHU_OAUTH_REDIRECT_URI,
        auth_cookie_secure=FEISHU_AUTH_COOKIE_SECURE,
    )


@dataclass
class TosConfig:
    """TOS 配置项。"""

    bucket_name: str
    access_key_id: str
    access_key_secret: str
    endpoint: str
    region: str
    base_path: str = ""

    def sdk_endpoint(self) -> str:
        host = self.endpoint.strip()
        for prefix in ("https://", "http://"):
            if host.startswith(prefix):
                host = host[len(prefix) :]
        return host.rstrip("/")

    def build_object_key(self, *parts: str) -> str:
        prefix = self.base_path.strip("/")
        suffix = "/".join(part.strip("/") for part in parts if part)
        if prefix and suffix:
            return f"{prefix}/{suffix}"
        return prefix or suffix


TOS_BUCKET_NAME = "mb-voice-test"
TOS_ACCESS_KEY_ID = "REDACTED"
TOS_ACCESS_KEY_SECRET = "REDACTED"
TOS_ENDPOINT = "https://tos-cn-beijing.volces.com"
TOS_REGION = "cn-beijing"
TOS_BASE_PATH = "dev/BenZ_test"


@cache
def get_tos_config() -> TosConfig:
    return TosConfig(
        bucket_name=TOS_BUCKET_NAME,
        access_key_id=TOS_ACCESS_KEY_ID,
        access_key_secret=TOS_ACCESS_KEY_SECRET,
        endpoint=TOS_ENDPOINT,
        region=TOS_REGION,
        base_path=TOS_BASE_PATH,
    )

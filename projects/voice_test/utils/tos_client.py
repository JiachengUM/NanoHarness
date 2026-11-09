"""火山 TOS 通用客户端：上传 + 预签名下载链接。"""
from __future__ import annotations

from pydantic import BaseModel, Field

# 文档：https://docs.volcengine.com/docs/6349/92800?lang=zh
# SDK：https://github.com/volcengine/ve-tos-python-sdk


class TosSettings(BaseModel):
    """与业务 yaml 对齐：bucket_name / base_path / endpoint 等。"""

    bucket_name: str = Field(description="桶名")
    access_key_id: str = Field(default="", description="TOS Access Key ID")
    access_key_secret: str = Field(default="", description="TOS Access Key Secret")
    endpoint: str = Field(
        default="https://tos-cn-beijing.volces.com",
        description="TOS 外网 endpoint，可带 https://",
    )
    base_path: str = Field(default="", description="对象 key 前缀")
    region: str = Field(default="cn-beijing", description="区域")

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

    def tos_uri(self, object_key: str) -> str:
        key = object_key.lstrip("/")
        return f"tos://{self.bucket_name}/{key}"


class VolcTosClient:
    """TOS 上传与临时下载链接。"""

    def __init__(self, settings: TosSettings) -> None:
        self.settings = settings

    @property
    def base_path(self) -> str:
        return self.settings.base_path

    def build_object_key(self, *parts: str) -> str:
        return self.settings.build_object_key(*parts)

    def tos_uri(self, object_key: str) -> str:
        return self.settings.tos_uri(object_key)

    def put_bytes(
        self,
        object_key: str,
        body: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> str:
        key = object_key.lstrip("/")
        client = self._sdk_client()
        resp = client.put_object(
            self.settings.bucket_name,
            key,
            content=body,
            content_type=content_type,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"TOS put_object 失败: status={resp.status_code}")
        return key

    def presigned_get_url(self, object_key: str, *, expires_sec: int = 3600) -> str:
        import tos

        key = object_key.lstrip("/")
        client = self._sdk_client()
        out = client.pre_signed_url(
            tos.HttpMethodType.Http_Method_Get,
            self.settings.bucket_name,
            key,
            expires=expires_sec,
        )
        return out.signed_url

    def _sdk_client(self):
        import tos

        cfg = self.settings
        return tos.TosClientV2(
            cfg.access_key_id,
            cfg.access_key_secret,
            cfg.sdk_endpoint(),
            cfg.region,
        )

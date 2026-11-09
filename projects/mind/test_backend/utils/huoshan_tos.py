"""火山 TOS 客户端：文件上传与下载。"""

from __future__ import annotations

from typing import Optional

from projects.mind.test_backend.config import TosConfig

class TosClient:
    """火山 TOS 基础客户端：上传字节/文件 + 下载字节/文件 + 预签名下载 URL。"""

    def __init__(self, config: TosConfig) -> None:
        self.config = config

    def _sdk_client(self):
        import tos

        cfg = self.config
        return tos.TosClientV2(
            cfg.access_key_id,
            cfg.access_key_secret,
            cfg.sdk_endpoint(),
            cfg.region,
        )

    def build_object_key(self, *parts: str) -> str:
        return self.config.build_object_key(*parts)

    def upload_bytes(
        self,
        object_key: str,
        body: bytes,
        *,
        content_type: str = "application/octet-stream",
    ) -> str:
        key = object_key.lstrip("/")
        client = self._sdk_client()
        resp = client.put_object(
            self.config.bucket_name,
            key,
            content=body,
            content_type=content_type,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"TOS put_object 失败: status={resp.status_code}")
        return key

    def upload_file(
        self,
        object_key: str,
        file_path: str,
        *,
        content_type: Optional[str] = None,
    ) -> str:
        key = object_key.lstrip("/")
        client = self._sdk_client()
        resp = client.put_object_from_file(
            self.config.bucket_name,
            key,
            file_path,
            content_type=content_type or "application/octet-stream",
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"TOS put_object_from_file 失败: status={resp.status_code}"
            )
        return key

    def download_bytes(self, object_key: str) -> bytes:
        key = object_key.lstrip("/")
        client = self._sdk_client()
        resp = client.get_object(self.config.bucket_name, key)
        if resp.status_code != 200:
            raise RuntimeError(f"TOS get_object 失败: status={resp.status_code}")
        return resp.read()

    def download_file(self, object_key: str, file_path: str) -> None:
        key = object_key.lstrip("/")
        client = self._sdk_client()
        client.get_object_to_file(self.config.bucket_name, key, file_path)

    def presigned_get_url(self, object_key: str, *, expires_sec: int = 3600) -> str:
        import tos

        key = object_key.lstrip("/")
        client = self._sdk_client()
        out = client.pre_signed_url(
            tos.HttpMethodType.Http_Method_Get,
            self.config.bucket_name,
            key,
            expires=expires_sec,
        )
        return out.signed_url

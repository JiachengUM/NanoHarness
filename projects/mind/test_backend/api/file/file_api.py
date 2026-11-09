"""文件上传下载接口（基于火山 TOS）。"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response

from projects.mind.test_backend.config import get_tos_config
from projects.mind.test_backend.schemas.response import ApiResponse, ok
from projects.mind.test_backend.utils.huoshan_tos import TosClient

router = APIRouter(
    prefix="/file",
    tags=["File"],
)


def _get_client() -> TosClient:
    return TosClient(get_tos_config())


@router.post("/upload", response_model=ApiResponse[dict])
async def upload_file(
    file: UploadFile = File(..., description="上传的文件"),
    folder: Optional[str] = Form(None, description="目标文件夹（可选）"),
) -> ApiResponse[dict]:
    """上传文件到 TOS，返回对象 key 和访问信息。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="文件名不能为空")

    client = _get_client()
    suffix = Path(file.filename).suffix
    object_name = f"{uuid.uuid4().hex}{suffix}"

    if folder:
        object_key = client.build_object_key(folder, object_name)
    else:
        object_key = client.build_object_key(object_name)

    content = await file.read()
    content_type = file.content_type or "application/octet-stream"

    try:
        key = client.upload_bytes(object_key, content, content_type=content_type)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"上传失败: {exc}") from exc

    return ok(
        {
            "object_key": key,
            "filename": file.filename,
            "size": len(content),
            "content_type": content_type,
        }
    )


@router.get("/download/{object_key:path}")
async def download_file(
    object_key: str,
    download: bool = True,
) -> Response:
    """从 TOS 下载文件。

    - object_key: TOS 对象 key（路径参数，支持包含 / 的完整路径）
    - download: 是否以附件形式下载（True 触发浏览器下载，False 直接展示）
    """
    if not object_key:
        raise HTTPException(status_code=400, detail="object_key 不能为空")

    client = _get_client()

    try:
        data = client.download_bytes(object_key)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"下载失败: {exc}") from exc

    filename = Path(object_key).name
    content_disposition = "attachment" if download else "inline"

    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f'{content_disposition}; filename="{filename}"'
        },
    )


@router.get("/presigned_url", response_model=ApiResponse[dict])
async def get_presigned_url(
    object_key: str,
    expires_sec: int = 3600,
) -> ApiResponse[dict]:
    """获取预签名下载 URL，有效期内可直接访问。"""
    if not object_key:
        raise HTTPException(status_code=400, detail="object_key 不能为空")

    client = _get_client()

    try:
        url = client.presigned_get_url(object_key, expires_sec=expires_sec)
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"生成预签名 URL 失败: {exc}"
        ) from exc

    return ok(
        {
            "object_key": object_key,
            "url": url,
            "expires_sec": expires_sec,
        }
    )

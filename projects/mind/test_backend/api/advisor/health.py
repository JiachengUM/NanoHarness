from __future__ import annotations


from fastapi import APIRouter

router = APIRouter(tags=["system"], prefix="/health")


@router.get("", summary="Health check")
async def health_root() -> dict[str, str]:
    return {"status": "ok"}

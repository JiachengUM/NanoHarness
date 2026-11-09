from __future__ import annotations

import importlib
import pkgutil
from typing import List

from fastapi import APIRouter
from nanoai.utils import logger


api_router = APIRouter(
    prefix="/api",
)


def _discover_route_modules(package: str) -> List[str]:
    """递归发现指定包及其子包中的所有模块/包的完整模块名。

    - 包括子包（若子包的 __init__.py 中定义了 `router` 也会被纳入）。
    - 跳过以 `_` 开头的叶子名（私有/双下划线模块或包）。
    - 返回全限定名（e.g. projects.mind.advisor.api.routes.users, projects.mind.advisor.api.routes.admin）。
    """
    try:
        pkg = importlib.import_module(package)
    except Exception as exc:
        logger.info(f"Failed to import package {package} for route discovery")
        return []

    names: List[str] = []
    pkg_path = getattr(pkg, "__path__", None)
    if not pkg_path:
        return names

    for _, full_name, _ in pkgutil.walk_packages(pkg_path, prefix=f"{package}."):
        leaf = full_name.rsplit(".", 1)[-1]
        if leaf.startswith("_"):
            continue
        names.append(full_name)
    return sorted(set(names))


def _auto_include_routers(root_router: APIRouter, package: str) -> None:
    """自动发现并包含指定包中的所有路由模块。

    约定：每个模块导出一个名为 'router' 的顶级变量，且其类型为 APIRouter。
    """
    for fqmn in _discover_route_modules(package):
        try:
            module = importlib.import_module(fqmn)
        except Exception as exc:
            logger.error(f"Failed to import route module {fqmn}: {exc}")
            continue

        router = getattr(module, "router", None)
        if isinstance(router, APIRouter):
            root_router.include_router(router)
        else:
            logger.warning(
                f"Module {fqmn} has no 'router' or it's not an APIRouter; skipped."
            )


# 自动发现并加载 projects.mind.advisor.api.routes 下的所有路由（支持子包）
_auto_include_routers(api_router, "projects.mind.test_backend.api.advisor")
_auto_include_routers(api_router, "projects.mind.test_backend.api.auth")
_auto_include_routers(api_router, "projects.mind.test_backend.api.intent")
_auto_include_routers(api_router, "projects.mind.test_backend.api.agent")
_auto_include_routers(api_router, "projects.mind.test_backend.api.complex_reasoning")
_auto_include_routers(api_router, "projects.mind.test_backend.api.task")
_auto_include_routers(api_router, "projects.mind.test_backend.api.voice_test")
_auto_include_routers(api_router, "projects.mind.test_backend.api.file")


__all__ = ["api_router"]

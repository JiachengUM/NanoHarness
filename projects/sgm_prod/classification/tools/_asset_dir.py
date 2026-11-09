from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from projects.sgm_prod.classification import assets as router_assets


@contextmanager
def use_router_asset_dir(asset_dir: Path) -> Iterator[None]:
    previous_asset_dir = router_assets._ASSET_DIR
    router_assets._ASSET_DIR = asset_dir
    router_assets.load_router_assets.cache_clear()
    router_assets.load_llm_classification_prompt.cache_clear()
    try:
        yield
    finally:
        router_assets._ASSET_DIR = previous_asset_dir
        router_assets.load_router_assets.cache_clear()
        router_assets.load_llm_classification_prompt.cache_clear()

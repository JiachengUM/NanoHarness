from pathlib import Path
from typing import Final, Optional

from pydantic import BaseModel, Field

from projects.hwhms.common.volcengine_api import HistoryItem

DATASET_ROOT: Final[Path] = Path(".") / "projects" / "hwhms" / "datasets"
DATASET_RELEASE_ROOT: Final[Path] = DATASET_ROOT / "release"

class Sample(BaseModel):
    query: str = Field(..., title="查询", description="查询")
    history: Optional[str | list] = Field(None, title="历史对话", description="历史对话")
    expected: str = Field(..., title="期望结果", description="期望结果")

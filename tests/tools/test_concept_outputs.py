"""concept_tool_outputs 的手动测试脚本（非 pytest）。

以 main 函数运行，用 print 展示结果而非 assert，便于肉眼观察各种
「输入形态 × is_list」组合下 ConceptOutput 的 data / item_errors / error。

运行：
    python -m tests.tools.test_concept_outputs
或
    python tests/tools/test_concept_outputs.py

核心关注点：输入(raw) 与输出(ConceptOutput) 在 list 维度上的组合关系。

模型配置（backend / model）见下方 BACKEND / MODEL_NAME 常量，
直接改脚本即可，不通过命令行参数。
"""

from __future__ import annotations

from typing import Any

import anyio
from pydantic import BaseModel

from aicore.models.doubao_models import ModelName
from aicore.models.model_api import ModelAPI
from aicore.models.model_api.factory import ModelAPIBackend, create_model_api
from aicore.tools.concept_outputs import (
    ConceptOutput,
    concept_tool_outputs,
)
from aicore.utils._concepts.meta import (
    Attribute,
    Concept,
    PrimitiveAttributeType,
)


# ---------------------------------------------------------------------------
# 模型配置：直接改这里
# ---------------------------------------------------------------------------

BACKEND: ModelAPIBackend = "chat"
MODEL_NAME: ModelName = ModelName.SEED_1_8_251228


def _build_model_api() -> ModelAPI[Any]:
    return create_model_api(backend=BACKEND, model=MODEL_NAME.value)


# ---------------------------------------------------------------------------
# 测试用 Concept 与工具原始输出
# ---------------------------------------------------------------------------


def _make_concept() -> Concept:
    """构造一个含两个标量属性的简单 Concept：city / price。"""
    return Concept(
        name="Hotel",
        definition="一个酒店概念，用于测试。",
        attributes=[
            Attribute(
                name="city",
                title="城市",
                description="酒店所在城市。",
                is_required=True,
                type=PrimitiveAttributeType.STRING,
            ),
            Attribute(
                name="price",
                title="价格",
                description="酒店每晚价格（整数，人民币元）。",
                is_required=False,
                type=PrimitiveAttributeType.INTEGER,
            ),
        ],
    )


class _RawItem(BaseModel):
    """模拟工具返回的 BaseModel，用于验证 _normalize。"""

    hotel_city: str
    nightly_price: int


# ---------------------------------------------------------------------------
# 打印辅助
# ---------------------------------------------------------------------------


async def _run(
    title: str,
    raw: Any,
    concept: Concept,
    is_list: bool,
    model_api: ModelAPI[Any],
) -> None:
    """执行一次 concept_tool_outputs，并把 raw 输入与结果一起 print。"""
    print(f"\n=== {title} ===")
    print(f"  is_list    : {is_list}")
    print(f"  raw        ({type(raw).__name__}): {raw}")

    out = await concept_tool_outputs(raw, concept, is_list, model_api)

    print(f"  data       ({type(out.data).__name__}): {out.data}")
    print(f"  item_errors: {[e.model_dump() for e in out.item_errors]}")
    print(f"  error      : {out.error}")


# ---------------------------------------------------------------------------
# 分组测试：真实 model_api（真正调用 LLM 做提取）
# ---------------------------------------------------------------------------


async def test_with_real_model(concept: Concept, model_api: ModelAPI[Any]) -> None:
    print("\n########## 真实 model_api：真正调用 LLM 提取 ##########")

    # is_list=False + dict（字段名与 concept 不同，考察语义对应）
    await _run(
        "is_list=False, raw=dict（字段名不同）",
        {"所在城市": "上海", "每晚价格": 880},
        concept,
        False,
        model_api,
    )

    # is_list=False + 单个 BaseModel（验证 _normalize + 提取）
    await _run(
        "is_list=False, raw=BaseModel",
        _RawItem(hotel_city="深圳", nightly_price=800),
        concept,
        False,
        model_api,
    )

    # is_list=False + 单元素 list：list 被当作单个整体，只提取出一个实例
    await _run(
        "is_list=False, raw=array(1)（单元素 list 当作整体）",
        [
            {"所在城市": "北京", "每晚价格": 600},
        ],
        concept,
        False,
        model_api,
    )

    # is_list=False + 多元素 list：整体只提取一个实例，观察 LLM 如何取舍多个元素
    await _run(
        "is_list=False, raw=array(4)（多元素 list 当作整体，仍只提取一个实例）",
        [
            {"所在城市": "北京", "每晚价格": 600},
            {"所在城市": "广州", "每晚价格": 520},
            {"所在城市": "成都", "每晚价格": 350},
            {"所在城市": "杭州", "每晚价格": 480},
        ],
        concept,
        False,
        model_api,
    )

    # is_list=True + list[dict]：逐元素并发提取，data 长度应等于输入长度
    await _run(
        "is_list=True, raw=list[dict](3)",
        [
            {"所在城市": "北京", "每晚价格": 600},
            {"所在城市": "广州", "每晚价格": 520},
            {"所在城市": "成都", "每晚价格": 350},
        ],
        concept,
        True,
        model_api,
    )

    # is_list=True + list[BaseModel]
    await _run(
        "is_list=True, raw=list[BaseModel](2)",
        [
            _RawItem(hotel_city="杭州", nightly_price=600),
            _RawItem(hotel_city="苏州", nightly_price=480),
        ],
        concept,
        True,
        model_api,
    )

    # is_list=True + 空 list：不调模型，直接 data=[]
    await _run(
        "is_list=True, raw=[]（空列表）",
        [],
        concept,
        True,
        model_api,
    )

    # is_list=True + dict：类型不匹配 → 顶层 error（不调模型）
    await _run(
        "is_list=True, raw=dict（类型不匹配 → error）",
        {"所在城市": "北京"},
        concept,
        True,
        model_api,
    )


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


async def main() -> None:
    concept = _make_concept()
    print(f"Concept: {concept.name} attributes={[a.name for a in concept.attributes]}")
    print(f"Backend={BACKEND} Model={MODEL_NAME.value}")

    model_api = _build_model_api()
    await test_with_real_model(concept, model_api)

    print("\n全部用例执行完毕。")


if __name__ == "__main__":
    anyio.run(main)

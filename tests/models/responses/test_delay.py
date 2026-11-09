from __future__ import annotations

import asyncio
import time
from statistics import mean
from typing import Literal, NamedTuple

from pydantic import BaseModel, Field

from aicore.models.credentials import AsyncArk, create_client
from aicore.models.doubao_models import ModelName
from aicore.models.responses import ResponseParams, ainvoke_output_by_json


QUERY = "请判断用户意图类型：帮我打开车窗"
OUTPUT_SCHEMA = '{"intent": "vehicle_control | weather | music | poi | chat"}'
RUNS = 100
FASTEST_N = 5


class IntentClassification(BaseModel):
    intent: Literal["vehicle_control", "weather", "music", "poi", "chat"] = Field(
        ..., description="用户意图类别"
    )


class DelayCase(NamedTuple):
    name: str
    model_name: ModelName
    params: ResponseParams


async def _classify_once(case: DelayCase) -> tuple[IntentClassification, float]:
    client, model = create_client(case.model_name, AsyncArk)
    start = time.perf_counter()
    result, _ = await ainvoke_output_by_json(
        QUERY,
        output_type=IntentClassification,
        client=client,
        model=model,
        params=case.params,
        output_schema=OUTPUT_SCHEMA,
    )
    return result, time.perf_counter() - start


async def _measure(case: DelayCase, runs: int = RUNS) -> list[float]:
    latencies: list[float] = []
    for i in range(runs):
        result, latency = await _classify_once(case)
        assert result.intent == "vehicle_control"
        latencies.append(latency)
        print(f"{case.name} #{i + 1}: {latency:.3f}s, result={result.intent}")
    return latencies


def _print_summary(title: str, results: dict[str, list[float]]) -> None:
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)
    for name, latencies in results.items():
        fastest = sorted(latencies)[:FASTEST_N]
        print(
            f"{name}: avg={mean(latencies):.3f}s, "
            f"min={min(latencies):.3f}s, max={max(latencies):.3f}s, "
            f"fastest_{FASTEST_N}_avg={mean(fastest):.3f}s, "
            f"fastest_{FASTEST_N}={[round(v, 3) for v in fastest]}"
        )


def test_seed_1_6_flash_param_latency() -> None:
    """比较 1.6 flash 调整采样/输出参数后，简单分类耗时是否变化。"""

    async def _run() -> None:
        cases = [
            DelayCase(
                name="flash_baseline",
                model_name=ModelName.SEED_1_6_FLASH_250828,
                params=ResponseParams(
                    thinking={"type": "disabled"},
                    temperature=0,
                    top_p=1,
                    max_output_tokens=32,
                ),
            ),
            DelayCase(
                name="flash_low_top_p",
                model_name=ModelName.SEED_1_6_FLASH_250828,
                params=ResponseParams(
                    thinking={"type": "disabled"},
                    temperature=0,
                    top_p=0.1,
                    max_output_tokens=32,
                ),
            ),
            DelayCase(
                name="flash_low_temperature",
                model_name=ModelName.SEED_1_6_FLASH_250828,
                params=ResponseParams(
                    thinking={"type": "disabled"},
                    temperature=0.1,
                    top_p=1,
                    max_output_tokens=32,
                ),
            ),
            DelayCase(
                name="flash_small_max_output",
                model_name=ModelName.SEED_1_6_FLASH_250828,
                params=ResponseParams(
                    thinking={"type": "disabled"},
                    temperature=0,
                    top_p=1,
                    max_output_tokens=16,
                ),
            ),
        ]

        results = {case.name: await _measure(case) for case in cases}
        _print_summary("Seed 1.6 Flash 参数耗时对比", results)

    asyncio.run(_run())


def test_seed_1_6_flash_vs_seed_2_0_mini_latency() -> None:
    """同样参数下比较 1.6 flash 和 2.0 mini 做简单分类的耗时。"""

    async def _run() -> None:
        flash_params = ResponseParams(
            thinking={"type": "disabled"},
            temperature=0,
            top_p=1,
            max_output_tokens=64,
        )
        mini_params = ResponseParams(
            thinking={"type": "disabled"},
            temperature=0,
            top_p=1,
            max_output_tokens=64,
        )
        cases = [
            DelayCase(
                name="seed_1_6_flash",
                model_name=ModelName.SEED_1_6_FLASH_250828,
                params=flash_params,
            ),
            DelayCase(
                name="seed_2_0_mini",
                model_name=ModelName.SEED_2_0_MINI_260428,
                params=mini_params,
            ),
        ]

        results = {case.name: await _measure(case) for case in cases}
        _print_summary("Seed 1.6 Flash vs Seed 2.0 Mini 耗时对比", results)

    asyncio.run(_run())


if __name__ == "__main__":
    # test_seed_1_6_flash_param_latency()
    test_seed_1_6_flash_vs_seed_2_0_mini_latency()

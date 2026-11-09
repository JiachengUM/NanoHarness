from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path

from volcenginesdkarkruntime import AsyncArk

# 让该测试可在仓库任意子目录下直接运行（不依赖外部 PYTHONPATH 配置）。
ROOT = Path(__file__).resolve().parents[4]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from projects.mind.complex_reasoning.utils.httpx import SharedAsyncHttpxClientFactory


BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
API_KEY = "REDACTED"


async def _benchmark_asyncark_construction(n: int = 200) -> None:
    """
    离线基准（不发网络请求）：
    只比较 AsyncArk 构造阶段的开销，验证“复用 httpx.AsyncClient”通常会更快。

    注意：这不是端到端 API 延迟 benchmark。
    """
    # 基线：每次让 AsyncArk 自己创建内部 httpx.AsyncClient
    baseline_clients: list[AsyncArk] = []
    t0 = time.perf_counter()
    for _ in range(n):
        baseline_clients.append(AsyncArk(base_url=BASE_URL, api_key=API_KEY))
    baseline_cost = time.perf_counter() - t0

    # 清理基线 client（避免未关闭告警）
    for client in baseline_clients:
        await client.close()

    # 优化：注入共享 httpx.AsyncClient，构造 AsyncArk 时不重复创建连接池对象
    shared_httpx = SharedAsyncHttpxClientFactory.get_client_for_current_loop()
    reused_clients: list[AsyncArk] = []
    t1 = time.perf_counter()
    for _ in range(n):
        reused_clients.append(AsyncArk(base_url=BASE_URL, api_key=API_KEY, http_client=shared_httpx))
    reused_cost = time.perf_counter() - t1

    # 不关闭 reused_clients：它们共享同一个 httpx client，统一由 factory 关闭。
    # 这里只做构造 benchmark，不发请求。
    ratio = (baseline_cost / reused_cost) if reused_cost > 0 else float("inf")
    print(
        f"asyncark_construct_baseline={baseline_cost:.6f}s "
        f"shared_httpx={reused_cost:.6f}s ratio={ratio:.2f}x"
    )

    await SharedAsyncHttpxClientFactory.close_for_current_loop()


async def main() -> None:
    await _benchmark_asyncark_construction(n=200)


if __name__ == "__main__":
    asyncio.run(main())

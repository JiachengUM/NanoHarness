"""问题 ID 池，供 call_fc 使用。"""
import asyncio
import logging
import time
import uuid
from typing import Awaitable, Callable, Optional, Tuple

from projects.mind.complex_reasoning.utils.plugins.plugin_support import get_question_id

logger = logging.getLogger(__name__)


async def _default_create_id() -> str:
    return str(uuid.uuid4())


class QuestionIdPool:
    def __init__(
        self,
        create_func: Callable[[], Awaitable[str]] = _default_create_id,
        pool_size: int = 6,
        id_ttl: float = 300.0,
    ):
        self.create_func = create_func
        self.pool_size = pool_size
        self.id_ttl = id_ttl
        self._queue: asyncio.Queue[Tuple[str, float]] = asyncio.Queue(maxsize=pool_size)
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def init_pool(self):
        async with self._lock:
            if self._task is not None:
                return
            for _ in range(self.pool_size):
                qid = await self.create_func()
                await self._queue.put((qid, time.time()))
            self._task = asyncio.create_task(self._maintain())
            logger.info("QuestionIdPool inited, size=%s", self.pool_size)

    async def _maintain(self):
        while True:
            try:
                await asyncio.sleep(1.0)
                now = time.time()
                temp = []
                while not self._queue.empty():
                    try:
                        qid, ts = self._queue.get_nowait()
                        if now - ts < self.id_ttl:
                            temp.append((qid, ts))
                    except asyncio.QueueEmpty:
                        break
                for item in temp:
                    await self._queue.put(item)
                for _ in range(self.pool_size - len(temp)):
                    await self._queue.put((await self.create_func(), now))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("pool maintain: %s", e)

    async def get_id(self) -> str:
        if self._task is None:
            return await self.create_func()
        qid, ts = await self._queue.get()
        if time.time() - ts < self.id_ttl:
            return qid
        return await self.create_func()

    async def shutdown(self):
        """关闭后台任务"""
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("Question ID Pool stopped.")


_pool: Optional[QuestionIdPool] = QuestionIdPool(get_question_id, pool_size=6, id_ttl=0.5)


def get_question_id_pool() -> QuestionIdPool:
    global _pool
    if _pool is None:
        _pool = QuestionIdPool(pool_size=6)
    return _pool


def test_question_id_pool():
    "测试获取question_id"
    async def main():
        pool = QuestionIdPool(create_func=get_question_id, pool_size=3)
        await pool.init_pool()

        for _ in range(7):
            qid = await pool.get_id()
            print(qid)

        await asyncio.sleep(5)
        await pool.shutdown()


    asyncio.run(main())

if __name__ == "__main__":

    test_question_id_pool()
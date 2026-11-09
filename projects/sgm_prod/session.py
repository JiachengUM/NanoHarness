from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass

from projects.sgm_prod.core import SGMAgent
from projects.uiagent.server.utils.redis_util import RedisUtil

logger = logging.getLogger("sgm_api")


@dataclass
class SessionEntry:
    """单个会话的本地运行时资源。当前只保留串行化锁。"""
    lock: asyncio.Lock
    last_access: float


class AgentManager:
    """
    按 chat_id 管理会话资源。

    当前设计：
    - agent 状态持久化在 Redis
    - 本地仅保留 asyncio.Lock，确保同一进程内同一id串行执行
    """

    def __init__(self) -> None:
        self._sessions: dict[str, SessionEntry] = {}
        self._guard = asyncio.Lock()
        self._redis = self._build_redis_client()
        self._redis_key_prefix = os.environ.get("SGM_AGENT_REDIS_PREFIX", "sgm:agent")

    @property
    def redis_enabled(self) -> bool:
        return self._redis is not None

    def _build_redis_client(self) -> RedisUtil | None:
        host = os.environ.get("SGM_REDIS_HOST")
        if not host:
            logger.info("SGM_REDIS_HOST 未配置，无法使用 Redis 持久化 agent 状态")
            return None

        try:
            return RedisUtil(
                host=host,
                port=int(os.environ.get("SGM_REDIS_PORT", "6379")),
                db=int(os.environ.get("SGM_REDIS_DB", "0")),
                password=os.environ.get("SGM_REDIS_PASSWORD") or None,
                decode_responses=True,
            )
        except Exception:
            logger.exception("Redis 客户端初始化失败")
            return None

    def _redis_key(self, chat_id: str) -> str:
        return f"{self._redis_key_prefix}:{chat_id}"

    async def get_or_create(self, chat_id: str) -> SessionEntry:
        """获取会话级本地锁。"""
        async with self._guard:
            entry = self._sessions.get(chat_id)
            if entry is None:
                entry = SessionEntry(lock=asyncio.Lock(), last_access=time.time())
                self._sessions[chat_id] = entry
            else:
                entry.last_access = time.time()
            return entry

    async def load_agent(self, chat_id: str) -> SGMAgent:
        """优先从 Redis 恢复 agent；没有则创建新 agent。"""
        if self._redis is None:
            return SGMAgent.build(chat_id=chat_id)

        raw = self._redis.get(self._redis_key(chat_id))
        if not raw:
            return SGMAgent.build(chat_id=chat_id)

        try:
            payload = json.loads(raw)
            return SGMAgent.restore(chat_id=chat_id, payload=payload)
        except Exception:
            logger.exception("从 Redis 恢复 agent 失败, chat_id=%s", chat_id)
            return SGMAgent.build(chat_id=chat_id)

    async def save_agent(self, chat_id: str, agent: SGMAgent) -> None:
        """将 agent 状态保存到 Redis。"""
        if self._redis is None:
            return

        try:
            payload = await agent.dump()
            payload_json = json.dumps(payload.model_dump(), ensure_ascii=False, separators=(",", ":"))
            if not self._redis.set(self._redis_key(chat_id), payload_json):
                logger.warning("写入 agent dump 到 Redis 失败, chat_id=%s", chat_id)
        except Exception:
            logger.exception("保存 agent 到 Redis 失败, chat_id=%s", chat_id)

    async def cleanup_idle(self, idle_seconds: float = 1800) -> None:
        """清理长时间未访问的本地锁对象。"""
        now = time.time()
        async with self._guard:
            expired = [
                chat_id
                for chat_id, entry in self._sessions.items()
                if now - entry.last_access > idle_seconds
            ]
            for chat_id in expired:
                self._sessions.pop(chat_id, None)

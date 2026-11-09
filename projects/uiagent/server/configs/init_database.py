from contextlib import asynccontextmanager
from sqlalchemy.exc import SQLAlchemyError, DBAPIError
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, AsyncEngine
from sqlalchemy.orm import sessionmaker
import logging

# 初始化日志
logger = logging.getLogger(__name__)

# 基类
Base = declarative_base()

# 初始化
engine: AsyncEngine = None
AsyncSessionLocal: sessionmaker = None


async def init_engine(database_url: str):
    global engine, AsyncSessionLocal

    if not database_url:
        raise ValueError("DATABASE_URL未初始化")

    try:
        engine = create_async_engine(
            database_url,
            echo=True,
            future=True
        )
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        AsyncSessionLocal = sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=False
        )
        logger.info(f"[数据库] 引擎和会话工厂创建成功: {engine}")
    except Exception as e:
        logger.error(f"[数据库] 初始化失败: {e}")
        raise


async def close_db():
    """关闭数据库引擎并释放资源"""
    global engine
    if engine:
        try:
            await engine.dispose()
            logger.info("[数据库] 引擎已关闭，连接池已释放")
        except Exception as e:
            logger.error(f"[数据库] 关闭引擎时出错: {e}")
        finally:
            engine = None


@asynccontextmanager
async def get_session():
    """异步数据库上下文管理器"""
    session = None
    try:
        # 创建新会话
        session = AsyncSessionLocal()

        # 将会话提供给调用方
        yield session

        # 尝试提交事务
        await session.commit()

        # 刷新对象状态（可选，但推荐）
        # await session.refresh(session.new)  # 刷新新对象
        # await session.refresh(session.dirty)  # 刷新修改的对象

    except SQLAlchemyError as e:
        # 处理数据库特定错误
        if session:
            await session.rollback()
        logger.error(f"数据库操作失败: {e}", exc_info=True)
        raise RuntimeError(f"数据库错误: {str(e)}") from e

    except DBAPIError as e:
        # 处理底层数据库驱动错误
        if session:
            await session.rollback()
        logger.critical(f"数据库驱动错误: {e}", exc_info=True)
        raise RuntimeError(f"数据库连接错误: {str(e)}") from e

    except Exception as e:
        # 处理其他未知错误
        if session:
            await session.rollback()
        logger.exception(f"未知错误: {e}")
        raise RuntimeError(f"操作失败: {str(e)}") from e

    finally:
        # 确保会话总是被关闭
        if session:
            try:
                await session.close()
            except Exception as e:
                logger.warning(f"关闭数据库会话时出错: {e}")

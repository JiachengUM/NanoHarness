'''Streamlit 应用通用工具函数

提供事件循环管理、数据库连接等通用功能，
供多个 Streamlit 应用共享使用。
'''

import asyncio
import streamlit as st
from motor.motor_asyncio import AsyncIOMotorClient
from beanie import init_beanie
from typing import Any, Coroutine


@st.cache_resource
def get_event_loop() -> asyncio.AbstractEventLoop:
    '''
    获取事件循环（使用 Streamlit 的资源缓存）
    
    Streamlit 的 @st.cache_resource 装饰器会缓存函数的返回值，
    确保在整个应用会话中只创建一次事件循环。
    
    这样可以避免每次页面重新渲染时创建新的事件循环，
    从而解决 Beanie ODM 与 Streamlit 的事件循环冲突问题。
    
    返回:
        asyncio.AbstractEventLoop: 异步事件循环对象
    '''
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
    return loop


@st.cache_resource
def get_db_client(connection_string: str, database_name: str, document_models: list) -> AsyncIOMotorClient:
    '''
    获取数据库客户端（使用 Streamlit 的资源缓存）
    
    这个函数负责：
    1. 获取事件循环
    2. 创建 MongoDB 异步客户端连接
    3. 初始化 Beanie ODM，注册文档模型
    
    使用 @st.cache_resource 确保数据库连接只初始化一次，
    提高性能并避免重复连接。
    
    参数:
        connection_string: MongoDB 连接字符串
        database_name: 数据库名称
        document_models: 文档模型列表
        
    返回:
        AsyncIOMotorClient: MongoDB 异步客户端对象
    '''
    loop = get_event_loop()
    
    async def _init() -> AsyncIOMotorClient:
        '''内部异步初始化函数'''
        client = AsyncIOMotorClient(connection_string)
        await init_beanie(
            database=client[database_name],  # type: ignore
            document_models=document_models
        )
        return client
    
    return loop.run_until_complete(_init())


def run_async[T](coro: Coroutine[Any, Any, T]) -> T:
    '''
    运行异步函数的辅助函数
    
    Streamlit 是同步框架，但 Beanie ODM 使用异步操作。
    这个函数将异步协程转换为同步执行，让 Streamlit 可以调用异步函数。
    
    参数:
        coro: 异步协程对象
        
    返回:
        异步函数的执行结果
    '''
    loop = get_event_loop()
    return loop.run_until_complete(coro)

"""Jev（TypeSafe AI System One）决策模型实验包。

Jev 是 TypeSafe AI 发布的"System One"决策模型：不生成任何文字，
直接输出类型化的概率决策（Choice 选择 / Score 打分 / Noul 真伪判断），
主打 Agent 架构"快慢分工"中的高频原子快判断。

目录内容：
- ``demo1.py``: 三原语基础验证（详细中文注释，含字段含义与陷阱解读）
- ``demo2.py``: 单请求 8 问题并行画像（原子问题设计、校准概率、延迟方法学）
- ``agent_router.py``: Jev 充当 agent router 的可行性验证（工具路由 + 风险 + 确认需求）
- ``jev_fast_slow_agent.py``: 快慢分工完整链路——JevRoutingAgent 前置分流，
  简单意图走 Jev 快路径秒回，复杂意图透传给 ReactAgentWithTaskRunner 慢思考。
  运行需 PYTHONPATH=mind 根目录（依赖 aicore 包与 volcengine LLM 配额）。

约定：
- API key 统一从本目录下的 ``.env`` 文件读取，每个脚本开头需带 ``load_dotenv(Path(__file__).parent / ".env")``
- 运行方式：``.venv/bin/python aicore/v2/experiments/jev_lab/<script>.py``
- 依赖：``typesafe_sdk``（官方 Python SDK，POST /v1/systemone）、``python-dotenv``
"""

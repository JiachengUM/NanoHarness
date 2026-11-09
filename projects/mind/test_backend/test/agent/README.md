# ReAct Agent API 测试用例

简单的 API 测试脚本，用于快速验证接口功能。

## 测试文件

- `test_react_api.py`: pytest 测试用例

## 运行测试

### 使用 pytest 运行

```bash
# 运行所有测试
pytest projects/mind/test_backend/test/agent/test_react_api.py -v

# 运行指定测试
pytest projects/mind/test_backend/test/agent/test_react_api.py::test_run_react_agent -v

# 显示打印输出
pytest projects/mind/test_backend/test/agent/test_react_api.py -v -s

# 运行 SSE 流式测试
pytest projects/mind/test_backend/test/agent/test_react_api.py::test_run_react_agent_stream -v -s
```

### 直接运行测试文件

```bash
python -m projects.mind.test_backend.test.agent.test_react_api
```

## 依赖

确保已安装以下依赖：

```bash
pip install pytest pytest-asyncio httpx
```

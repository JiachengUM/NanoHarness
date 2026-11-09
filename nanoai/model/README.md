# NanoAI 配置系统使用指南

## 🚀 快速开始

### 1. 基本模型切换

```python
from nanoai.model.config import switch_model, get_current_config

# 切换到不同模型
switch_model("qwen")      # 切换到通义千问
switch_model("doubao")    # 切换到豆包
switch_model("openai")    # 切换到 OpenAI
switch_model("ollama")    # 切换到本地 Ollama

# 查看当前配置
config = get_current_config()
print(f"当前使用: {config.name} - {config.model}")
```

### 2. 查看所有可用模型

```python
from nanoai.model.config import get_available_models

models = get_available_models()
for name, config in models.items():
    print(f"{name}: {config.model}")
```

## 🔧 配置方式

### 方式一：环境变量（推荐）

设置环境变量来指定模型：

```bash
# 设置模型名称
export OPENAI_MODEL_NAME="doubao"

# 可选：覆盖 API 配置
export OPENAI_API_KEY="REDACTED"
export OPENAI_BASE_URL="https://your-endpoint.com/v1"
export OPENAI_MODEL="your-model-name"
```

### 方式二：配置文件

创建配置文件 `config.json`：

```json
{
  "model_name": "qwen"
}
```

或者自定义配置：

```json
{
  "name": "custom",
  "base_url": "https://your-endpoint.com/v1",
  "api_key": "your-api-key",
  "model": "your-model-name"
}
```

加载配置文件：

```python
from nanoai.model.config import load_config_from_file

load_config_from_file("config.json")
```

### 方式三：代码中动态切换

```python
from nanoai.model.config import switch_model

# 在代码中随时切换
switch_model("qwen")
# 使用 qwen 模型...

switch_model("doubao")
# 使用 doubao 模型...
```

## 📋 预定义模型

| 模型名称 | 端点 | 默认模型 | 说明 |
|---------|------|----------|------|
| `qwen` | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen2.5-72b-instruct` | 阿里云通义千问 |
| `doubao` | `https://ark.cn-beijing.volces.com/api/v3` | `doubao-seed-1-6-flash-250615` | 字节跳动豆包 |
| `openai` | `https://api.openai.com/v1` | `gpt-4o-mini` | OpenAI GPT |
| `ollama` | `http://localhost:11434/v1` | `llama3.2:latest` | 本地 Ollama |
| `volcano` | `https://ark.cn-beijing.volces.com/api/v3` | `qwen2.5-72b-instruct` | 火山引擎 |

## 🔄 客户端使用

### 同步客户端

```python
from nanoai.model.config import get_global_client

client = get_global_client()
response = client.chat.completions.create(
    model="qwen2.5-72b-instruct",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

### 异步客户端

```python
from nanoai.model.config import get_global_client_async

async_client = get_global_client_async()
response = await async_client.chat.completions.create(
    model="qwen2.5-72b-instruct",
    messages=[{"role": "user", "content": "Hello!"}]
)
```

## 🛠️ 高级功能

### 保存配置到文件

```python
from nanoai.model.config import save_config_to_file

# 保存当前配置
save_config_to_file("my_config.json")

# 保存特定模型配置
save_config_to_file("doubao_config.json", "doubao")
```

### 批量测试不同模型

```python
from nanoai.model.config import switch_model, get_current_config

test_models = ["qwen", "doubao", "openai"]

for model_name in test_models:
    try:
        switch_model(model_name)
        config = get_current_config()
        print(f"✓ {model_name}: {config.model}")
        
        # 在这里进行模型测试
        # ...
        
    except Exception as e:
        print(f"✗ {model_name}: {e}")
```

## 🔧 特殊处理

### 火山引擎/豆包 API

系统会自动为火山引擎和豆包的 API 添加特殊处理：

```python
# 自动添加 headers 来禁用压缩
headers = {"Accept-Encoding": "identity"}
```

### 环境变量优先级

配置优先级（从高到低）：
1. 环境变量 (`OPENAI_*`)
2. 当前选择的模型配置
3. 默认配置

## 📝 配置文件格式

### 简单格式（推荐）

```json
{
  "model_name": "qwen"
}
```

### 完整格式

```json
{
  "name": "custom_config",
  "base_url": "https://your-endpoint.com/v1",
  "api_key": "your-api-key",
  "model": "your-model-name"
}
```

## 🚨 注意事项

1. **API 密钥安全**：不要在代码中硬编码 API 密钥，使用环境变量或配置文件
2. **网络连接**：确保能够访问相应的 API 端点
3. **模型兼容性**：不同模型可能有不同的参数和限制
4. **成本控制**：注意不同模型的调用成本

## 🎯 使用示例

运行演示脚本：

```bash
cd Nano/nanoai/model
python config_example.py
```

这将展示所有配置功能的使用方法。

## 🔍 故障排除

### 常见问题

1. **模型不存在错误**
   ```python
   # 查看可用模型
   from nanoai.model.config import get_available_models
   print(get_available_models().keys())
   ```

2. **API 连接错误**
   - 检查网络连接
   - 验证 API 密钥
   - 确认端点 URL

3. **配置加载失败**
   - 检查配置文件格式
   - 确认文件路径
   - 查看错误信息

### 调试模式

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# 现在会显示详细的配置信息
from nanoai.model.config import switch_model
switch_model("qwen")
```

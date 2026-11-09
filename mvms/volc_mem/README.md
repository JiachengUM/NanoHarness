# 火山引擎 Memory API Python 教程

这是一个完整的火山引擎 Memory API Python 使用教程，包含记忆库管理、会话管理、画像管理和记忆检索等功能。

## 快速开始

### 1. 环境准备

```bash
# 安装依赖
pip install python-dotenv requests volcengine
```

### 2. 配置认证信息

编辑 `mvms/volc_mem/.env` 文件，填入你的认证信息：

```env
# 火山引擎 API 配置
AK=your_access_key
SK=your_secret_key

# 火山引擎服务配置
DOMAIN=api-knowledgebase.mlp.cn-beijing.volces.com
SERVICE=air
REGION=cn-north-1
SCHEMA=http

# Base URL for Memory API
BASE_URL=https://api-knowledgebase.mlp.cn-beijing.volces.com
```

### 3. 运行示例

```bash
# 创建记忆库
python mvms/volc_mem/demo/collection.py

# 添加会话记录
python mvms/volc_mem/demo/session_management.py

# 搜索记忆
python mvms/volc_mem/demo/memory_retrieval.py

# 管理用户画像
python mvms/volc_mem/demo/memory_management.py
```

## 配置说明

### 认证方式

本项目使用 **AK/SK + V4 签名认证**方式，所有配置通过 `.env` 文件管理：

- `AK`: Access Key，用于 API 认证
- `SK`: Secret Key，用于请求签名
- 配置会自动从 `mvms/volc_mem/.env` 文件加载

### 配置文件位置

- 配置文件：`mvms/volc_mem/.env`
- 配置加载：`mvms/volc_mem/common/config.py`
- 请求客户端：`mvms/volc_mem/common/client.py`

## 功能模块

### 1. Collection（记忆库）管理

**文件：** `mvms/volc_mem/demo/collection.py`

记忆库是存储和管理所有记忆数据的容器。

**支持的操作：**
- `create_collection()`: 创建新的记忆库
- `update_collection()`: 更新记忆库配置（添加自定义事件类型等）
- `get_collection_info()`: 查询记忆库详细信息
- `list_collections()`: 列出所有记忆库
- `delete_collection()`: 删除记忆库

**使用场景：**
- 首次使用前需要创建记忆库
- 为不同业务场景创建独立的记忆库
- 添加自定义事件类型和画像类型

### 2. Session（会话）管理

**文件：** `mvms/volc_mem/demo/session_management.py`

会话是用户与助手之间的对话记录，系统会基于会话数据自动提取记忆。

**支持的操作：**
- `add_session()`: 添加会话记录到记忆库
- `get_session_info()`: 查询会话的详细信息

**使用场景：**
- 记录用户与助手的对话历史
- 批量导入历史对话数据
- 实时同步对话记录到记忆库

### 3. Profile（用户画像）管理

**文件：** `mvms/volc_mem/demo/memory_management.py`

用户画像是系统对用户的长期记忆，包括基本信息、偏好、习惯等。

**支持的操作：**
- `add_profile()`: 手动添加用户画像
- `update_profile()`: 更新已存在的用户画像
- `delete_profile()`: 删除单个用户画像
- `batch_delete_profile()`: 批量删除用户画像
- `trigger_profile_update()`: 触发系统重新计算用户画像

**使用场景：**
- 手动初始化用户画像
- 从外部系统导入用户信息
- Schema 更新后重新计算画像

### 4. Memory（记忆）检索

**文件：** `mvms/volc_mem/demo/memory_retrieval.py`

根据关键词搜索记忆库中的相关记忆。

**功能：**
- 语义搜索：基于关键词进行语义相似度匹配
- 条件过滤：支持按 user_id、memory_type 等条件过滤
- 结果限制：支持分页和结果数量限制

**使用场景：**
- 对话时检索相关记忆，提供上下文
- 查找用户的历史偏好和习惯
- 分析用户行为模式

## 使用示例

### 示例 1：完整工作流程

```python
# 1. 创建记忆库
python mvms/volc_mem/demo/collection.py
# 修改 collection.py 中的 main() 函数，调用 create_collection()

# 2. 添加会话记录
python mvms/volc_mem/demo/session_management.py
# 系统会自动从会话中提取记忆

# 3. 搜索记忆
python mvms/volc_mem/demo/memory_retrieval.py
# 根据关键词查找相关记忆

# 4. 管理用户画像
python mvms/volc_mem/demo/memory_management.py
# 查看、更新或删除用户画像
```

### 示例 2：添加自定义事件类型

```python
# 在 collection.py 中调用 update_collection()
# 定义自定义事件类型，如英语学习事件
payload = {
    "CollectionName": "my_first_memory_collection",
    "CustomEventTypeSchemas": [
        {
            "EventType": "english_study",
            "Description": "记录英语学习会话",
            "Properties": [
                {"PropertyName": "knowledge_point", "PropertyValueType": "string"},
                {"PropertyName": "score", "PropertyValueType": "int64"},
            ],
        }
    ],
}
```

### 示例 3：搜索用户偏好

```python
# 在 memory_retrieval.py 中修改查询
payload = {
    "collection_name": "my_first_memory_collection",
    "query": "空调偏好",  # 搜索关键词
    "limit": 5,
    "filter": {
        "user_id": "user_01",  # 只搜索该用户的记忆
        "memory_type": ["sys_event_v1"],  # 只搜索事件类型
    },
}
```

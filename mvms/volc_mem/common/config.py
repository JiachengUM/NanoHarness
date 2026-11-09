# ===== 火山引擎 API 配置 =====
import os
from pathlib import Path
from dotenv import load_dotenv

# 加载 .env 文件
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)

# 从环境变量读取配置，如果没有则使用默认值
AK = os.environ.get("AK")
SK = os.environ.get("SK")

DOMAIN = os.environ.get("DOMAIN", "api-knowledgebase.mlp.cn-beijing.volces.com")
SERVICE = os.environ.get("SERVICE", "air")
REGION = os.environ.get("REGION", "cn-north-1")
SCHEMA = os.environ.get("SCHEMA", "http")
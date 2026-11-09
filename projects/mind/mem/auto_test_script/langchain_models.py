from langchain_openai import ChatOpenAI

from aicore.models.credentials import ARK_API_KEY, ARK_BASE_URL
from aicore.models.doubao_models import ModelName
from nanoai.model.config import (
    DMX_API_KEY,
    DMX_BASE_URL,
    DMX_MODEL_CLAUDE_OPUS_4_5,
    DMX_MODEL_GEMINI,
    DMX_MODEL_GPT5_2,
    DMX_MODEL_QWEN_MAX,
)

doubao_model = ChatOpenAI(
    model=ModelName.SEED_2_1_PRO_260628,
    base_url=ARK_BASE_URL,
    api_key=ARK_API_KEY,
    extra_body={"thinking": {"type": "disabled"}},
)

qwen_model = ChatOpenAI(
    model=DMX_MODEL_QWEN_MAX,
    base_url=DMX_BASE_URL,
    api_key=DMX_API_KEY,
)

claude_model = ChatOpenAI(
    model=DMX_MODEL_CLAUDE_OPUS_4_5,
    base_url=DMX_BASE_URL,
    api_key=DMX_API_KEY,
)

gpt_model = ChatOpenAI(
    model=DMX_MODEL_GPT5_2,
    base_url=DMX_BASE_URL,
    api_key=DMX_API_KEY,
)

gemini_model = ChatOpenAI(
    model=DMX_MODEL_GEMINI,
    base_url=DMX_BASE_URL,
    api_key=DMX_API_KEY,
)
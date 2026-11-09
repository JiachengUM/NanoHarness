import uuid
import pyaudio
from pydantic import BaseModel, Field
from typing import Literal
from enum import StrEnum



class WsHeaders(BaseModel):
    """WebSocket 鉴权头，使用 alias 对齐服务端要求的字段名。"""
    x_api_app_id: str = Field(alias="X-Api-App-ID")
    x_api_access_key: str = Field(alias="X-Api-Access-Key")
    x_api_resource_id: str = Field(alias="X-Api-Resource-Id")
    x_api_app_key: str = Field(alias="X-Api-App-Key")
    x_api_connect_id: str = Field(alias="X-Api-Connect-Id")


class WsConnectConfigModel(BaseModel):
    """连接服务端所需的基础配置。"""
    base_url: str
    headers: WsHeaders


class AsrExtraModel(BaseModel):
    """ASR 额外参数。"""
    end_smooth_window_ms: int = Field(default=2000,le=50000,ge=500,description="平滑窗口时间，单位毫秒，取值范围 [500ms, 50s]")
    enable_custom_vad: bool = Field(default=True,description="是否启用自定义VAD")


class AsrModel(BaseModel):
    """ASR 配置。"""
    extra: AsrExtraModel


class TtsAudioConfigModel(BaseModel):
    """TTS 音频输出参数。"""
    channel: int = 1
    format: str = "pcm"
    sample_rate: int = 24000
    loudness_rate: int = 50


class Speaker(StrEnum):
    """
    音色枚举
    """
    ZH_FEMALE_VV_JUPITER_BIGTTS = "zh_female_vv_jupiter_bigtts"
    """vv音色，活泼灵动的女声，有很强的分享欲"""

    ZH_FEMALE_XIAOHE_JUPITER_BIGTTS = "zh_female_xiaohe_jupiter_bigtts"
    """xiaohe音色，甜美活泼的女声，有明显的台湾口音"""

    ZH_MALE_YUNZHOU_JUPITER_BIGTTS = "zh_male_yunzhou_jupiter_bigtts"
    """yunzhou音色，清爽沉稳的男声"""

    ZH_MALE_XIAOTIAN_JUPITER_BIGTTS = "zh_male_xiaotian_jupiter_bigtts"
    """xiaotian音色，清爽磁性的男声"""

class TtsModel(BaseModel):
    """TTS 配置。"""
    speaker: Speaker
    audio_config: TtsAudioConfigModel


class DialogLocationModel(BaseModel):
    """对话场景位置信息。"""
    city: str


class DialogExtraModel(BaseModel):
    """对话模块补充参数。"""
    strict_audit: bool = False
    audit_response: str
    recv_timeout: int = 10
    input_mod: str = "audio"
    model: Literal["1.2.1.1", "2.2.0.0"] = "1.2.1.1"

class DialogModel(BaseModel):
    """对话角色与风格配置。"""
    bot_name: str
    system_role: str
    speaking_style: str
    location: DialogLocationModel
    extra: DialogExtraModel


class StartSessionReqModel(BaseModel):
    """StartSession 请求体。"""
    asr: AsrModel
    tts: TtsModel
    dialog: DialogModel


class AudioConfig(BaseModel):
    """输入/输出音频流配置。"""
    chunk: int
    format: str
    channels: int
    sample_rate: int
    bit_size: int


# 结构化配置模型：用于初始化时做字段约束和默认值兜底。
ws_connect_config = WsConnectConfigModel(
    base_url="wss://openspeech.bytedance.com/api/v3/realtime/dialogue",
    headers=WsHeaders(
        **{
            "X-Api-App-ID": "7620217375",
            "X-Api-Access-Key": "16wfbjmry6Bed5vsbXeLvWUcYBIG965p",
            "X-Api-Resource-Id": "volc.speech.dialog",
            "X-Api-App-Key": "PlgvMymc7f3tQnJ6",
            "X-Api-Connect-Id": str(uuid.uuid4()),
        }
    ),
)

# StartSession 的完整请求配置模型，外部直接通过属性读取/修改。
start_session_req = StartSessionReqModel(
    asr=AsrModel(extra=AsrExtraModel(
        end_smooth_window_ms=1500,  # 平滑窗口时间，单位毫秒
        enable_custom_vad=True,     # 启用自定义VAD停止识别
    )),
    tts=TtsModel(
        speaker=Speaker.ZH_FEMALE_VV_JUPITER_BIGTTS,
        audio_config=TtsAudioConfigModel(channel=1, format="pcm", sample_rate=24000),
    ),
    dialog=DialogModel(
        bot_name="豆包",
        system_role="你使用活泼灵动的女声，性格开朗，热爱生活。",
        speaking_style="你的说话风格简洁明了，语速特别快，语调自然。",
        location=DialogLocationModel(city="上海"),
        extra=DialogExtraModel(
            strict_audit=False,
            audit_response="支持客户自定义安全审核回复话术。",
            recv_timeout=10,
            input_mod="audio",
            model="1.2.1.1",
        ),
    ),
)

# 输入音频配置（采集侧）。
input_audio_config = AudioConfig(
    chunk=3200,
    format="pcm",
    channels=1,
    sample_rate=16000,
    bit_size=pyaudio.paInt16,
)

# 输出音频配置（播放侧）。
output_audio_config = AudioConfig(
    chunk=3200,
    format="pcm",
    channels=1,
    sample_rate=24000,
    bit_size=pyaudio.paFloat32,
)

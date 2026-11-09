"""物理语音测试适配层配置。"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from projects.voice_test.config.core_config import Speaker


class VoiceAdapterConfig(BaseModel):
    wake_up_word: str = ""
    goodbye_markers: tuple[str, ...] = ("退下", "再见", "拜拜")
    goodbye_reply: str = "（助手已结束会话）"
    vad_timeout_ms: int = Field(default=2000, ge=500, le=50000)
    external_reply_timeout_sec: float = Field(default=60.0, gt=0)
    # 已有 ASR 后等待 ASREnded；None=按 VAD 自动推算（保证 > VAD）。
    asr_ended_timeout_sec: float | None = Field(default=None, gt=0)
    # 与 AutoTestAndRLDataGenerator.external_api_max_retries 对齐：失败后再试次数（总尝试=本值+1）。
    # 0 = 不重试；外部回复最终超时后返回固定文案，不再向框架抛 TimeoutError。
    external_api_max_retries: int = Field(default=0, ge=0, le=5)
    log_asr_events: bool = True
    log_asr_delta: bool = True
    session_id_prefix: str = "voice-test"
    memory_extraction_wait_sec: int = Field(
        default=10,
        ge=0,
        le=300,
        description="仅语音链路：case 内相邻冷启动之间，等待上一轮记忆提取",
    )
    run_gap_wait_sec: int = Field(
        default=5,
        ge=0,
        le=300,
        description="仅语音链路：批量自动播放模式下，case 之间的停顿",
    )
    # 定制化：首轮唤醒词和第一句分开两次发送，中间停顿一会儿
    split_wake_up_and_first_query: bool = Field(
        default=False,
        description="开启后：首轮唤醒词和第一句分开两次发送，中间停顿 split_wake_up_wait_ms 毫秒",
    )
    split_wake_up_wait_ms: int = Field(
        default=3000,
        ge=0,
        le=5000,
        description="唤醒词发完后，停顿多少毫秒再发第一句；仅在拆分发送开启时生效",
    )
    # S2S StartSession TTS 音色（假人播报）；与 HTTP 单向 TTS 的 male/female 无关。
    s2s_speaker: Speaker = Speaker.ZH_FEMALE_VV_JUPITER_BIGTTS

    def is_goodbye_query(self, text: str) -> bool:
        return any(marker in text for marker in self.goodbye_markers)

    def resolve_asr_ended_timeout_sec(self) -> float:
        """有 ASR 后等 ASREnded 的上限；须大于 VAD，给判停和网络留余量。"""
        if self.asr_ended_timeout_sec is not None:
            return float(self.asr_ended_timeout_sec)
        vad_sec = self.vad_timeout_ms / 1000.0
        return max(vad_sec + 2.0, 3.0)


# 服务端默认；页面未传 adapter_config 时使用。
adapter_config = VoiceAdapterConfig(
    wake_up_word="你好奔驰。",
)


def resolve_adapter_config(override: dict | None = None) -> VoiceAdapterConfig:
    """用服务端默认合并前端覆盖项。"""
    if not override:
        return adapter_config.model_copy()
    return VoiceAdapterConfig.model_validate({**adapter_config.model_dump(), **override})


class TtsVoice(StrEnum):
    MALE = "male"
    FEMALE = "female"


class HttpTtsSpeaker(StrEnum):
    """HTTP TTS 可选音色池（按需继续加，与前端 voice 无关）。"""

    AOJIAOBAZONG = "zh_male_aojiaobazong_emo_v2_mars_bigtts"
    GAOLENGYUJIE = "zh_female_gaolengyujie_emo_v2_mars_bigtts"


def resolve_http_tts_speaker(voice: TtsVoice) -> str:
    """前端 voice → 具体 speaker：在此手动从 HttpTtsSpeaker 池里挑选。"""
    match voice:
        case TtsVoice.MALE:
            return HttpTtsSpeaker.AOJIAOBAZONG.value
        case TtsVoice.FEMALE:
            return HttpTtsSpeaker.GAOLENGYUJIE.value

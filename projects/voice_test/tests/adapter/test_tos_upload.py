#!/usr/bin/env python3
"""本地测试：内存 WAV → TOS put_object。"""
from __future__ import annotations

import struct
import sys

from projects.voice_test.adapter.case_audio_recorder import CaseAudioRecorder
from projects.voice_test.adapter.case_audio_tos import tos_client


def main() -> int:
    rec = CaseAudioRecorder.begin()
    payload = struct.pack("<f", 0.25) * 2400
    rec.write_tts(payload)
    rec.write_tts(payload)
    body = rec._take_wav_bytes()
    assert body is not None

    print(f"内存 WAV 大小: {len(body)} bytes")
    print(f"recording_id: {rec.recording_id}")
    print(f"object key: {rec.object_key}")

    uploaded = tos_client.put_bytes(rec.object_key, body, content_type="audio/wav")
    print(f"上传成功: {tos_client.tos_uri(uploaded)}")

    url = tos_client.presigned_get_url(uploaded, expires_sec=600)
    print(f"临时下载链接（10 分钟）:\n{url}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

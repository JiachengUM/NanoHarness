"""
本文件是音频管理器的实现，用于管理音频设备和音频队列。
主要功能包括：
音频设备管理：输入流和输出流
    打开和关闭音频输入输出流
音频队列管理：
    将音频数据添加到队列中，并从队列中获取音频数据
"""
import pyaudio
from projects.voice_test.config.core_config import AudioConfig, input_audio_config, output_audio_config


class AudioDeviceManager:
    """音频设备管理。"""

    def __init__(self, input_config: AudioConfig = input_audio_config, output_config: AudioConfig = output_audio_config) -> None:
        self.input_config = input_config
        self.output_config = output_config
        self.pyaudio = pyaudio.PyAudio()
        self.input_stream: pyaudio.Stream | None = None
        self.output_stream: pyaudio.Stream | None = None

    def open_input_stream(self) -> pyaudio.Stream:
        self.input_stream = self.pyaudio.open(
            format=self.input_config.bit_size,
            channels=self.input_config.channels,
            rate=self.input_config.sample_rate,
            input=True,
            frames_per_buffer=self.input_config.chunk,
        )
        return self.input_stream

    def open_output_stream(self) -> pyaudio.Stream:
        self.output_stream = self.pyaudio.open(
            format=self.output_config.bit_size,
            channels=self.output_config.channels,
            rate=self.output_config.sample_rate,
            output=True,
            frames_per_buffer=self.output_config.chunk,
        )
        return self.output_stream

    def cleanup(self) -> None:
        for stream in (self.input_stream, self.output_stream):
            if stream is not None:
                stream.stop_stream()
                stream.close()
        self.pyaudio.terminate()
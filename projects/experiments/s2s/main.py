import asyncio
import argparse

from projects.experiments.s2s import config
from projects.experiments.s2s.audio_manager import DialogSession


async def main():
    parser = argparse.ArgumentParser(description="实时对话客户端")

    parser.add_argument("--use_event_printer", type=bool, default=True, help="启用规整的事件打印器（默认开启，关闭时原样打印）")
    # parser.add_argument("--use_event_printer", type=bool, default=False, help="启用规整的事件打印器（默认开启，关闭时原样打印）")
    
    # parser.add_argument("--use_custom_text_tts_only", type=bool, default=True, help="只使用自定义文本转TTS，不使用S2S内部闲聊文本及音频")
    parser.add_argument("--use_custom_text_tts_only", type=bool, default=False, help="只使用自定义文本转TTS，这部分就是放入agent的回复文本的逻辑。不使用S2S内部闲聊文本及音频")
    args = parser.parse_args()

    session = DialogSession(
        ws_config=config.ws_connect_config,
        use_event_printer=args.use_event_printer,
        use_custom_text_tts_only=args.use_custom_text_tts_only,
    )
    await session.start()

if __name__ == "__main__":
    asyncio.run(main())

import json
from tqdm import tqdm
from typing import Any
from pydantic import BaseModel, field_validator, Field

class QA(BaseModel):
    question: str
    answer: str | int | None = None
    evidence: list[str]
    category: int

class Dialogue(BaseModel):
    speaker: str
    img_url: list[str] | None = None
    blip_caption: str | None = None
    query: str | None = None
    re_download: bool | None = Field(None, alias='re-download')
    dia_id: str
    text: str

    model_config = {
        "extra": "forbid",
        "populate_by_name": True
    }


class Session(BaseModel):
    date_time: str
    dia: list[Dialogue]

    def __chat_str__(self) -> str:
        return '\n'.join([f"{d.speaker}: {d.text}" for d in self.dia])
        


class Conversation(BaseModel):
    speaker_a: str
    speaker_b: str
    sessions: list[Session]

    model_config = {
        "extra": "forbid",
    }

class Event(BaseModel):
    a_event: list[str]
    b_event: list[str]
    date: str

class ConversationAll(BaseModel):
    qa: list[QA]
    conversation: Conversation
    event_summary: list[Event]
    observation: Any
    session_summary: dict[str, str]

    @field_validator('event_summary', mode='before')
    @classmethod
    def convert_event_summary(cls, v: dict[str, dict] | list[Event]) -> list[Event]:
        if isinstance(v, list):
            return v
        
        assert isinstance(v, dict)
        
        events = []

        n = 1
        while True:
            event_key = f'events_session_{n}'

            if event_key not in v:
                break

            event_data = v[event_key]
            assert isinstance(event_data, dict)

            # TODO: 需要通过event_data[speaker_a]和event_data[speaker_b]来拿到event str。但speaker_a/b位于conversation字段中。
            # 需要先拿到conversation字段，然后通过speaker_a/b来拿到event str。
            # event = Event(a_event=event_data['Caroline'], b_event=event_data['Melanie'], date=event_data['date'])
            event = Event(a_event=[], b_event=[], date=event_data['date'])

            events.append(event)
            n += 1

        return events
    
    @field_validator('conversation', mode='before')
    @classmethod
    def convert_conversation(cls, v: dict | Conversation) -> Conversation:
        """将conversation字段从dict转换为Conversation对象"""
        if isinstance(v, Conversation):
            return v
        
        assert isinstance(v, dict)
        
        # 提取speaker_a和speaker_b
        speaker_a = v['speaker_a']
        speaker_b = v['speaker_b']
        
        # 收集所有session
        sessions = []
        
        # 从1开始依次增大序号，直到找不到对应的session字段
        n = 1
        while True:
            session_key = f'session_{n}'
            date_time_key = f'session_{n}_date_time'
            
            # 如果session_n字段不存在，则停止
            if session_key not in v:
                break
            
            # 转换dialogues
            dialogues = []
            for dialogue_data in v[session_key]:
                assert isinstance(dialogue_data, dict)

                try:
                     dialogue = Dialogue(**dialogue_data)
                except Exception as e:
                    print(f"Error processing dialogue: {e}")
                    continue

                dialogues.append(dialogue)
            
            # 创建session
            session = Session(
                date_time=v[date_time_key],
                dia=dialogues
            )
            sessions.append(session)
            
            n += 1
        
        return Conversation(
            speaker_a=speaker_a,
            speaker_b=speaker_b,
            sessions=sessions
        )


def convert_locomo_format(file_path, output_path):
    with open(file_path, "r", encoding='utf-8') as f:
        data = json.load(f)

    for idx, item in tqdm(
        enumerate(data), total=len(data), desc="Processing conversations"
    ):
        try:
            # 现在可以直接创建ConversationAll对象，所有转换逻辑都在类内部处理
            conv_all = ConversationAll(**item)     
        except Exception as e:
            print(f"Error processing item {idx}: {e}")
            continue

        output_file = f"{output_path}/conv_{idx}.json"
        with open(output_file, "w", encoding='utf-8') as f:
            json.dump(conv_all.model_dump(), f, indent=4, ensure_ascii=False)

           
if __name__ == "__main__":
    convert_locomo_format("datasets/locomo/locomo10.json", "datasets/locomo")
from pydantic import BaseModel, Field
from enum import StrEnum
from typing import Optional
import random

# class SeatType(StrEnum):
#     HALL = "大厅"
#     ROOM = "包间"
#     CHAIR = "散台"
#     CARD_SEAT = "卡座"

class BookingData(BaseModel):
    num_people: Optional[str] = Field(None, description="人数")
    date: Optional[str] = Field(None, description="日期")
    time: Optional[str] = Field(None, description="时间")
    seat_type: Optional[str] = Field(None, description="座位类型")

class GeneratedSentence(BaseModel):
    sentence: str = Field(..., description="生成的句子")
    booking_data: BookingData = Field(..., description="预订数据")

data = {
    "numberOfPeople": {
        "exact": ["3人", "6人", "10人"],
        "vague": ["三四个人", "我和对象还有俩朋友", "十五个人左右"],
    },
    "date": {
        "exact": ["10月23日", "10月25日"],
        "vague": ["最近两天", "这个周末"],
    },
    "time": {
        "exact": ["12:15", "18:30"],
        "vague": ["两三个小时后", "晚上七八点"],
    },
    "seat": {
        "exact": ["大厅", "散台", "包间", "卡座"],
        "vague": ["随便什么位置", "合适位置"]
    }
}

def generate_booking_sentences(count: int = 100) -> list[GeneratedSentence]:
    """生成预定句子"""
    results = []
    seen_sentences: set[str] = set()  # 用于去重
    sentence_patterns =["帮我预定{date}{time}{numberOfPeople}{seat}的座位",
                    "订个{date}{time}{numberOfPeople}{seat}的座位",]

    all_people = data["numberOfPeople"]["exact"] + data["numberOfPeople"]["vague"]
    all_dates = data["date"]["exact"] + data["date"]["vague"]
    all_times = data["time"]["exact"] + data["time"]["vague"]
    all_seats = data["seat"]["exact"] + data["seat"]["vague"]
    
    for i in range(count):
        # 随机决定哪些信息要填写（50%概率）
        date = random.choice(all_dates) if random.random() > 0.5 else None
        time = random.choice(all_times) if random.random() > 0.5 else None
        people = random.choice(all_people) if random.random() > 0.5 else None
        seat = random.choice(all_seats) if random.random() > 0.5 else None

        if not any([date, time, people, seat]):
            people = random.choice(all_people)
        
        pattern = random.choice(sentence_patterns)
        sentence = pattern.format(
            date=date + " " if date else "",
            time=time + " " if time else "",
            numberOfPeople=people + "" if people else "",
            seat=seat if seat else ""
        ).strip()

        # 检查是否重复
        if sentence in seen_sentences:
            continue  # 跳过重复的句子
        
        seen_sentences.add(sentence)

        booking_data = BookingData(
            num_people = people,
            date = date,
            time = time,
            seat_type = seat
        )

        result = GeneratedSentence(
            sentence = sentence,
            booking_data = booking_data
        )

        results.append(result)

    return results

def save_to_file(sentences: list[GeneratedSentence], filename: str = "booking_data.json"):
    """保存到文件"""
    import json

    data_list = [sentence.model_dump() for sentence in sentences]

    with open(filename, "w", encoding="utf-8") as f:
        json.dump(data_list, f, ensure_ascii=False, indent=2)

    print(f"已生成{len(data_list)}条数据")

if __name__ == "__main__":
    # 生成50条数据
    sentences = generate_booking_sentences(50)

    save_to_file(sentences)
    # 打印前5条示例
    print("\n前5条示例:")
    for i, sentence in enumerate(sentences[:5]):
        print(f"{i+1}. {sentence.sentence}")
        print(f"   数据: {sentence.booking_data.model_dump()}")
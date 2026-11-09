from pydantic import BaseModel, Field
from enum import StrEnum

class SeatType(StrEnum):
    HALL = "大厅"
    ROOM = "包间"
    CHAIR = "散台"
    

class SeatBookingData(BaseModel):
    date: str = Field(..., description="日期")
    time: str = Field(..., description="时间")
    num_persons: int = Field(..., description="人数")
    seat_type: SeatType = Field(..., description="座位")


def gen_data() -> list[SeatBookingData]:
    data = SeatBookingData(
        date="2025-10-21",
        time="12:00",
        num_persons=4,
        seat_type=SeatType.HALL)

    return [data]


if __name__ == "__main__":
    data = gen_data()
    print(data)
from enum import StrEnum
from pydantic import BaseModel, Field

from projects.uiagent.seatbooking.agent import WorkFlowStep


class Button(BaseModel):
    name: str
    description: str
    coordiante: x0, y0, x1, y1


class Page(BaseModel):
    buttons: list[Button] = Field(..., description="页面上的按钮")
    

class AppEnvironment:
    def __init__(self, page: Page):
        self.page = page
        self.page_ui_img: list[Image] = []
        self.agent = SeatBookingAgent()


    def load_gt():
        pass


    def response(action: Action) -> bool:
        return False

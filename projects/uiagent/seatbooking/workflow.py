import asyncio
from enum import StrEnum

from projects.uiagent.core import UITask, WorkflowBase, RunResult,JudgeResult, UIModelOutput, ErrorCode, image_from_path
class EStep(StrEnum):
    FIND_RESTAURANT = "find_restaurant"
    START_BOOKING = "start_booking"
    CONFIRM_BOOKING_DETAILS = "confirm_booking_details"
    END_BOOKING = "end_booking"
    FINISH = "finish"

class Workflow(WorkflowBase):
    def __init__(self, current_step: EStep = EStep.FIND_RESTAURANT, enable_reflect: bool = False):
        self.find_restaurant_task = UITask(
            page="搜索餐厅的页面",
            task="根据用户描述搜索符合条件的餐厅",
            note=[
                "你正在尝试帮用户预订他想要订的餐厅，因此你需要先查找他想要订的餐厅；",
                "用户可能会进行多次尝试，没关系，多观察视野图像中是否有筛选或者搜索，用搜索根据用户的描述进行筛选；",
            ],
        )

        self.start_booking_task = UITask(
            page="开始订座的页面",
            task="点击订座按钮",
            note=[
                "如果订座按钮在视野图像中不存在，那么你需要点击返回然后重新和用户沟通换一家餐厅",
            ],
        )

        self.confirm_booking_task = UITask(
            page="确认订座信息的页面,",
            task="把人数，日期，时间，座位类型等信息都确定下来。",
            note=["确认人数", "确认日期", "确认时间", "确认大厅还是包厢等信息"],
        )

        self.end_booking_task = UITask(
            page="确认订座人信息并结束订座的页面",
            task="点击确认结束订座",
            note=[
                "你需要填写用户的姓名，但是实际上用户可以随便填；",
                "你还需要确定用户的性别，有时可以从用户姓名中明确得到性别，比如用户说自己叫张先生，那么你就不用问了直接顺便把性别选上男性；",
                "你需要确认手机号，如果过往动作中没有填写过手机号，那么最好主动向用户确认一遍默认填写的手机号是否正确，如果用户认为是正确的，那么无需额外输入手机号；",
                "你最好询问一下用户有没有什么需要交待餐厅的，如果有那么填写进备注，填写备注时用输入动作直接填写吧；",
                "注意备注栏的字数限制，不要超了，超了要反馈给用户；",
                "确认勾上同意用户协议；",
                "上述步骤都没问题了点击确认按钮；",
            ],
        )

        super().__init__({
                EStep.FIND_RESTAURANT: self.find_restaurant_task, 
                EStep.START_BOOKING: self.start_booking_task, 
                EStep.CONFIRM_BOOKING_DETAILS: self.confirm_booking_task, 
                EStep.END_BOOKING: self.end_booking_task
                },
                EStep.FIND_RESTAURANT,
                enable_reflect=enable_reflect
            )


    async def run(self, query: str, base64_image: str, image_format: str, /, *, current_step: EStep | None = None) -> tuple[RunResult, JudgeResult | None]:
        if current_step is not None:
            self.current_step = current_step
        try:
            match self.current_step:
                case EStep.CONFIRM_BOOKING_DETAILS:
                    # 这里需要做定制化的实现
                    result, eval_res = await self.confirm_booking_details(query, base64_image, image_format)
                case _:
                    # 其他步骤直接用模型兜底
                    result, eval_res = await self._run_step_by_model(self.current_step, query, base64_image, image_format)

            result = RunResult(code=ErrorCode.SUCCESS.code, raw_prompt=result.raw_prompt, thought=result.thought, actions=result.actions)
            return result, eval_res
        except Exception as e:
            return RunResult(code=ErrorCode.SYSTEM_ERROR.code, raw_prompt="", thought="", actions=list()), None

    async def confirm_booking_details(self, query: str, base64_image: str, image_format: str) -> tuple[UIModelOutput, JudgeResult | None]:
        return await self._run_step_by_model(EStep.CONFIRM_BOOKING_DETAILS, query, base64_image, image_format)


from projects.uiagent.seatbooking.datasets import DATASET_ROOT

def test_workflow_basic():
    workflow = Workflow(enable_reflect=True)

    image_root = DATASET_ROOT / "meituan" / "images"

    query = "直接找 “凑凑火锅”"
    image_path = str(image_root / "select_restaurant.png")
    base64_image, image_format = image_from_path(image_path)
    result, eval_res = asyncio.run(workflow.run(query, base64_image, image_format, current_step=EStep.FIND_RESTAURANT))
    print(f"\nquery: {query}\nthought: {result.thought}\neval_res: {eval_res}")

    query = "我想订座"
    image_path = str(image_root / "verify_dingzuo.jpg")
    base64_image, image_format = image_from_path(image_path)
    result, eval_res = asyncio.run(workflow.run(query, base64_image, image_format, current_step = EStep.START_BOOKING))
    print(f"\nquery: {query}\nthought: {result.thought}\neval_res: {eval_res}")

    query = "帮我预定 4人的座位"
    image_path = str(image_root / "dingzuo_info.jpg")
    base64_image, image_format = image_from_path(image_path)
    result, eval_res = asyncio.run(workflow.run(query, base64_image, image_format, current_step = EStep.CONFIRM_BOOKING_DETAILS))
    print(f"\nquery: {query}\nthought: {result.thought}\neval_res: {eval_res}")

    query = "换个号码"
    image_path = str(image_root / "dingzuoren_info.png")
    base64_image, image_format = image_from_path(image_path)
    result, eval_res = asyncio.run(workflow.run(query, base64_image, image_format, current_step = EStep.END_BOOKING))
    print(f"\nquery: {query}\nthought: {result.thought}\neval_res: {eval_res}")


if __name__ == "__main__":
    test_workflow_basic()

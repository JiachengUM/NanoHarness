from seatbooking.workflow import Workflow
from seatbooking.eval import eval_all

class WorkflowNew(Workflow):

    def __init__(self):
        super().__init__()

        self.confirm_booking_task.page = "提交人数、时间点、日期、座位类型等信息。日期以当前日期开始，请根据用户的描述推断出具体的日期。"

        self.confirm_booking_task.note.append("请在备注中填写用户的手机号")


    async def confirm_booking_details(self, query: str, image_path: str):
        # our own implementation

        return await super().confirm_booking_details(query, image_path)


def compare_and_validate():
    wf = Workflow()
    wf_neW = WorkflowNew()

    # step 1: 读取想要测试的数据，通常不是完整的测试集，而是“想要对比的部分，这个实验的改动可能影响的部分”。
  
    # step 2: 运行wf, wf_new, 获取两组结果。

    res = eval_all(wf)

    res_new = eval_all(wf_new)

    # step 3: 对比结果，分析这个改动的效果：
    # compre res, res_new


    # step 4.1: 改动如果明显有效，在自己的实验branch上集成到workflow.py。找wei yichen review code。通过后merge到主分支。

    # step 4.2: 明显不好。不管它。

    # step 4.3: 有好有坏。最难的情况, case by case分析。


if __name__ == "__main__":
    compare_and_validate()

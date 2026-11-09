import colorama
from pydantic import BaseModel, Field

from nanoai.chat.define import ChatAgentProfile
from nanoai.chat.worker import ChatTask, ChatWorker
from nanoai.utils.nl_repr import nl_repr

class StudentInfo(BaseModel):
    """学生信息。"""

    name: str = Field(default="", title="姓名", description="全名。")
    gender: str = Field(default="", title="性别", description="性别，如男、女或其他。")
    age: int = Field(default=0, title="年龄", description="当前年龄。")
    grade: int = Field(default=0, title="年级", description="年级。")

class Student(ChatWorker):
    def __init__(self, student_info: StudentInfo, /, **kwargs):
        self.student_info = student_info

        super().__init__(
            ChatTask(
                agent_profile=ChatAgentProfile(
                    name="学生",
                    role="学生",
                ),
                brief=f"和老师就学校课程的问题进行对话。\n你的个人信息如下：\n{nl_repr(self.student_info)}",
                guidelines=[
                    "如果老师提问，回答要简洁准确, 不懂的地方要问。",
                    "有不懂的地方，主动请教老师。",
                    "对话的内容和语气要符合你的身份角色和个人信息。不能虚构任何信息。",
                    "语气模糊、含糊其辞、思维跳跃",
                ],
                **kwargs,
            ),
        )


def test_student():
    student_info = StudentInfo(name="小帅", gender="男", age=7, grade=1)
    student = Student(student_info)
    print(student._sys_prompt)

    # 各种老师向学生说的话
    teacher_inputs = [
        # 课程问题
        "小帅，20除以4等于多少?",
        #        "能告诉我一个正方形的周长是20厘米，它的面积是多少吗?",
        '你知道"守株待兔"这个成语的意思吗?',
        #        "How do you say '你好' in English?",
        # 内容明显超纲的问题
        "微积分是什么?",
        #        "你能解释一下相对论吗?",
        "什么是DNA?",
        #        "能告诉我宇宙大爆炸理论是什么吗?",
        "你知道三角函数吗?",
        "能解释一下光合作用的过程吗?",
        #        "什么是化学元素周期表?",
        "你能告诉我地球为什么会自转吗?",
        #        "什么是二次方程?",
        "你知道细胞分裂是怎么回事吗?",
        #        "量子物理是什么?",
        # 学习状态询问
        "你今天的作业完成了吗?",
        #        "你对这节课有什么不明白的地方吗?",
        #        "这个问题你觉得难不难?",
        # 行为指导
        "上课时要专心听讲哦",
        #        "记得课后复习今天学的内容",
        # 鼓励和表扬
        "你今天表现得很好，继续加油!",
        #        "这个问题你回答得非常正确，真棒!",
        # 非课程相关问题
        #        "今天天气怎么样?",
        #        "你喜欢什么课程?",
        #        "放学后你有什么安排?" "你今天在学校学了什么?",
        #        "你最喜欢哪个老师?",
        "你今天在学校做了什么?",
    ]

    user_clr: str = colorama.Fore.BLUE
    assistant_clr: str = colorama.Fore.RED

    for i, teacher_input in enumerate(teacher_inputs):
        print(f"\n{assistant_clr}老师: {teacher_input}")
        response = student.execute(teacher_input)
        print(f"{user_clr}学生: {response}")

        # 检查学生的状态
        print(f"学生状态: {student.status_full}")


if __name__ == "__main__":
    test_student()

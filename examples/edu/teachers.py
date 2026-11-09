from examples.edu.course import Course, CourseType, Question, create_questions
from examples.edu.student import StudentInfo
from nanoai.chat.define import ChatAgentProfile
from nanoai.chat.worker import ChatTask, ChatWorker
from nanoai.chat.simulation import gen_chat


class Teacher(ChatWorker[StudentInfo]):
    def __init__(self, course: Course, /, *, user: StudentInfo | None = None, **kwargs):
        self.course = course

        # criteria中关于问题类别判断的要求，都不work。即使放到brief中，也不work。
        # 必须显式地启动多轮对话中的意图识别worker。不理解为何。
        teach_task = ChatTask(
            brief=f"回答学生关于{course.tp}课程的问题。不要回答与课程内容无关的问题。",
            guidelines=[
                "请仔细判断问题的类别，如果超出课程主题和内容的范围, 务必礼貌地拒绝回答。",
                # "如果问题内容超出课程的范围, 礼貌地拒绝回答。",
                "回答问题要准确、清晰、有条理，不要出现错误。",
                "回答问题要符合学生的年龄特点，不要出现过于复杂或深奥的词汇。",
                "回答问题要符合学生的认知水平，不要出现过于抽象或难以理解的概念。",
            ],
            agent_profile=ChatAgentProfile(
                name=f"小学{course.grade}年级{course.tp}老师",
                role=f"老师",
            ),
            **kwargs,
        )

        super().__init__(teach_task, user=user)

    def intro(self) -> str:
        # TODO: 改为 start_session(context) 更为合适。
        if self._user is None:
            name = "小朋友"
        else:
            name = self._user.name

        return f"{name}你好, 我是{self.name}, 能回答关于{self.course.tp}课程的问题。有什么问题就请问我吧。"


def create_teachers() -> list[Teacher]:
    # 如果support_multi_turn=False, 不会执行意图识别。而prompt中的意图识别要求根本不work。很奇怪
    # 即使support_multi_turn=True, 意图识别的结果也相当不稳定。这可能是个大问题。
    # 猜测多轮对话中的意图识别能work是因为结构化输出。要求reasoning可能让模型标准了。在这里试一下。

    math_course = Course(tp=CourseType.MATH, grade=1)
    math_teacher = Teacher(math_course)
    chinese_course = Course(tp=CourseType.CHINESE, grade=1)
    chinese_teacher = Teacher(chinese_course)
    english_course = Course(tp=CourseType.ENGLISH, grade=1)
    english_teacher = Teacher(english_course)
    history_course = Course(tp=CourseType.HISTORY, grade=1)
    history_teacher = Teacher(history_course)
    geography_course = Course(tp=CourseType.GEOGRAPHY, grade=1)
    geography_teacher = Teacher(geography_course)

    # teachers = [math_teacher, chinese_teacher, bad_chinese_teacher]
    teachers = [math_teacher, chinese_teacher, english_teacher, history_teacher, geography_teacher]
    # teachers = [chinese_teacher]

    return teachers


def test_question_answering(teachers: list[Teacher], questions: list[Question]):
    for t in teachers:
        gen_chat(t, [q.question for q in questions])


if __name__ == "__main__":
    # test_question_answering(create_teachers(), create_questions())
    test_question_answering([Teacher(Course(tp=CourseType.MATH, grade=1))], create_questions())

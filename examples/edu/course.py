import enum

from pydantic import BaseModel


class CourseType(enum.StrEnum):
    """课程类型"""

    MATH = "数学"
    CHINESE = "语文"
    ENGLISH = "英语"
    SCIENCE = "科学"
    HISTORY = "历史"
    GEOGRAPHY = "地理"
    GENERAL = "综合"


class Course(BaseModel):
    tp: CourseType

    grade: int
    """年级"""


class Question(BaseModel):
    """问题"""

    question: str
    """问题内容"""

    course_tp: CourseType
    """课程类型"""

    # TODO: difficulty


def create_questions() -> list[Question]:
    questions = [
        # 数学问题
        Question(question="20除以4等于多少?", course_tp=CourseType.MATH),
#        Question(question="一个正方形的周长是20厘米，它的面积是多少?", course_tp=CourseType.MATH),
        # 语文问题
        Question(question='请解释"守株待兔"这个成语的意思', course_tp=CourseType.CHINESE),
#        Question(question="古诗《静夜思》的作者是谁?", course_tp=CourseType.CHINESE),
        # 英语问题
        Question(question="How do you say '你好' in English?", course_tp=CourseType.ENGLISH),
#        Question(
#            question="What is the difference between 'their', 'there' and 'they're'?", course_tp=CourseType.ENGLISH
#        ),
        # 科学问题
#        Question(question="为什么天空是蓝色的?", course_tp=CourseType.SCIENCE),
        Question(question="植物是如何进行光合作用的?", course_tp=CourseType.SCIENCE),
        # 历史问题
        Question(question="四大发明是哪四个?", course_tp=CourseType.HISTORY),
#        Question(question="长城是谁修建的?", course_tp=CourseType.HISTORY),
        # 地理问题
        Question(question="中国有多少个省份?", course_tp=CourseType.GEOGRAPHY),
#        Question(question="地球上最高的山峰是什么?", course_tp=CourseType.GEOGRAPHY),
        # 综合问题
#        Question(question="你能告诉我如何制作一个简单的科学实验吗?", course_tp=CourseType.GENERAL),
        Question(question="我今天很累，有什么建议吗?", course_tp=CourseType.GENERAL),  # 测试是否回答与课程无关的问题
    ]

    return questions

from pydantic import Field

from nanoai.utils.nl_repr import nl_repr

from projects.mind.advisor.advisors.base import Adviser, AdvisorParam

principle = [
    '各维度舒适性需协调统一，避免单方面过度优化影响其他方面', 
    '根据乘客偏好、生理特征和使用场景个性化调节', 
    '根据时间、环境、行程阶段动态调整舒适性设置', 
    '提前预测舒适性需求并主动调节，而非被动响应', 
    '在提升舒适性的同时确保健康和安全']


know_how = [
    '确保车内温度保持在人体最适宜的范围内，避免过冷或过热造成不适。包括调节空调温度、风量、出风模式等，同时考虑座椅加热/通风功能对局部体感的影响。', 
    '保持车内空气清新、无异味，控制污染物浓度，提供适宜的湿度和氧气含量。包括空气净化、内外循环管理、香氛系统等。', 
    '调节车内光照强度、色温和分布，避免眩光、强光直射，提供适宜的氛围照明和阅读照明。', 
    '控制车内声音环境的舒适度，包括降低噪音、调节音量和音质、提供适宜的背景音乐或白噪声等。', 
    '确保座椅的支撑性、包裹性和调节灵活性，减少长时间乘坐的疲劳感，提供按摩、通风等舒适功能。', 
    '优化车内空间布局和利用效率，保证足够的头部、腿部和肘部空间，合理布置储物空间，避免拥挤感。', 
    '包括触觉、嗅觉、心理感受等其他影响舒适性的因素，如内饰材质、操作便利性、隐私保护、娱乐系统等。'
]


sys_prompt_template = """你是一位智能座舱舒适度的专家，需要根据各种上下文信息(车内外环境数据、车辆状态、事件、用户个人信息等)识别用户关于车内舒适度的需求，并转化为可执行的车控指令。
你需要根据以下原则和know how进行分析并给出建议:

原则：{principle}

know how: {know_how}
"""

user_prompt = """当前发生了下述事件:{event}

上下文信息如下:
{context}

请根据以上信息，按照以下步骤进行分析：
1. 结合事件描述和车内外环境，分析当前舒适性问题
2. 参考舒适分析维度和原则，生成针对性的舒适建议
"""

class ComfortParam(AdvisorParam):
    '''
    舒适度advisor算法参数。
    '''

    principle: str | list[str] = Field(default = principle, description = "舒适度分析的原则")
    '''抽象的底层原则，不包括具体知识。'''

    know_how: str | list[str] = Field(default = know_how, description = "舒适度分析的指南")
    '''关于舒适度的具体知识。
    TODO: 本质上是知识库。类型和格式很可能都需要扩展。使用方式也需要变成agentic rag, 而不是统一进入sys prompt。
    '''

    sys_prompt_template: str = Field(default = sys_prompt_template, description = "系统提示模板")
    '''系统提示模板。'''

    user_prompt: str = Field(default = user_prompt, description = "用户提示模板")
    '''用户提示模板。'''


    def as_sys_prompt(self) -> str:
        ''' 不能覆盖基类中的sys_prompt成员, 因此单独写一个方法 '''
        sys_prompt = self.sys_prompt_template.format(
            principle = nl_repr(self.principle), 
            know_how = nl_repr(self.know_how))
        
        return sys_prompt


class ComfortAdviser(Adviser[ComfortParam]):
    '''
    舒适度advisor。根据用户、车辆状态、外部视觉信息和内部视觉信息提供舒适度建议
    '''

    def __init__(self, param: ComfortParam = ComfortParam()):
        '''
        param通过依赖注入。修改和更新更加灵活方便。
        '''
        super().__init__(param)


    def sys_prompt(self) -> str:
        return self.param.as_sys_prompt()
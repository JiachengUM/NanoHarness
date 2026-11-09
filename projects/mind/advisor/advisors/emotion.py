from projects.mind.advisor.advisors.base import Adviser, AdvisorParam

class EmotionAdviser(Adviser[AdvisorParam]):
    '''
    情感advisor。根据用户、车辆状态、外部视觉信息和内部视觉信息提供情感建议
    '''

    def __init__(self):
        param = AdvisorParam(
            sys_prompt = "你是一个专业的情感顾问，根据用户、车辆状态、外部视觉信息和内部视觉信息，提供情感建议。")
        
        super().__init__(param)

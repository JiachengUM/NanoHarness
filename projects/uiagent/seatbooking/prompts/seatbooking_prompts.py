from jinja2 import Template

RESTAURANT_BOOKING_PLAN = """
1. 判断当前视野为店铺检索界面后，从店铺检索界面寻找合适的店；
2. 判断当前视野为进入店铺详情页后，寻找并点击“订座”按钮，如果没有“订座”按钮的话，返回店铺检索界面；
3. 输入餐厅名称
4. 选择餐厅
5. 输入日期和时间
6. 输入人数
7. 点击“下一步”按钮
8. 确认订座信息
9. 点击“确认”按钮
"""

DECISIONS_TRANSLATION = {
    "找店": "find_restaurant_node",
    "点订座": "try_to_click_seat_booking_node",
    "订座": "confirm_seat_booking_info_node",
    "订座人信息": "confirm_seat_booking_person_info_node"
}

SEARCHING_RESTAURANT_SPECIFIC_MISSON_DISCRIPTION = '''
1、你正在尝试帮用户预订他想要订的餐厅，因此你需要先查找他想要订的餐厅；
2、用户可能会进行多次尝试，没关系，多观察视野图像中是否有筛选或者搜索，用搜索根据用户的描述进行筛选；
'''

BOOKING_DETAIL_MISSON_DISCRIPTION = '''
1、确定人数；
2、确定日期；
3、确定时间；
4、确定座位，散台有时可以理解成大厅；
'''

TRY_TO_CLICK_SEAT_BOOKING_NODE_DISCRIPTION = '''
1、你需要点击订座按钮；
2、如果订座按钮在视野图像中不存在，那么你需要点击返回然后重新和用户沟通换一家餐厅；
'''

CONFIRM_SEAT_BOOKING_PERSON_INFO_PROMPT = '''
1、你需要填写用户的姓名，但是实际上用户可以随便填；
2、你还需要确定用户的性别，有时可以从用户姓名中明确得到性别，比如用户说自己叫张先生，那么你就不用问了直接顺便把性别选上男性；
3、你需要确认手机号，如果过往动作中没有填写过手机号，那么最好主动向用户确认一遍默认填写的手机号是否正确，如果用户认为是正确的，那么无需额外输入手机号；
4、你最好询问一下用户有没有什么需要交待餐厅的，如果有那么填写进备注，填写备注时用输入动作直接填写吧；
5、注意备注栏的字数限制，不要超了，超了要反馈给用户；
6、确认勾上同意用户协议；
7、上述步骤都没问题了点击确认按钮；
'''
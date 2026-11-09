from pydantic import BaseModel, Field

from aicore.utils.nl_repr import nl_repr


class UserProfile(BaseModel):
    """用户画像，基于座舱场景的用户特征，待优化"""

    user_type: str = Field(..., title="用户类型", description="用户类型，如单身职场女性、退休银发族、创业青年、全职妈妈、商务精英等")

    personal_status: list[str] | None = Field(default=None, title="个人状态", description="个人状态，如单身、已婚、退休、居住地、子女情况等")

    residence: str | None = Field(default=None, title="居住地点", description="居住地点，具体到街道或小区")

    career_identity: list[str] | None = Field(default=None, title="职业身份", description="职业身份，如职业类型、工作地点、工作性质等")

    daily_behavior: list[str] | None = Field(default=None, title="日常行为", description="日常行为，如通勤时间、工作时间、休闲时间等规律")

    personality_traits: list[str] | None = Field(default=None, title="性格特征", description="性格特征，如外向、内向、计划性强、追求品质等")

    interests_hobbies: list[str] | None = Field(default=None, title="兴趣爱好", description="兴趣爱好，如音乐偏好、运动偏好、社交偏好等")

    travel_pattern: list[str] | None = Field(default=None, title="出行结构", description="出行结构，如通勤为主、社交为主、购物为主等")

    vehicle_usage: list[str] | None = Field(default=None, title="车辆使用概况", description="车辆使用概况，如空调温度偏好、风量偏好、车控依赖度等")

    media_preference: list[str] | None = Field(default=None, title="媒体偏好", description="媒体偏好，如音乐类型、播客类型、常听艺人等")


SINGLE_CAREER_WOMAN = UserProfile(
    user_type="单身职场女性",
    personal_status=["单身", "可能有稳定伴侣但未同居", "无子女"],
    residence="上海市浦东新区陆家嘴滨江住宅区（高端公寓）",
    career_identity=["互联网公司产品设计师/UI设计师", "工作地点：浦东新区世纪大道1000号"],
    daily_behavior=["通勤时间：07:00-09:00", "工作时间：09:00-18:00", "健身时间：18:00-20:00", "社交时间：20:00-24:00", "夜生活活跃"],
    personality_traits=["外向开放", "注重自我投资", "追求品质生活", "社交活跃", "文艺气质", "独立自主"],
    interests_hobbies=["独立音乐/民谣（网易云音乐）", "健身/瑜伽", "社交/夜生活", "购物/时尚", "旅行/摄影", "可能有宠物"],
    travel_pattern=["通勤占约25%", "社交购物娱乐占约75%", "以个人享受为中心的都市生活方式"],
    vehicle_usage=["空调温度均值25.2℃", "风量2.8档", "车控依赖度28%", "对舒适度较敏感"],
    media_preference=["网易云音乐占比32%", "流行音乐、独立音乐", "常听艺人：陈粒、苏打绿、告五人、田馥甄、房东的猫"]
)

RETIRED_SENIOR = UserProfile(
    user_type="退休银发族",
    personal_status=["已退休", "老年夫妻居住", "子女已独立"],
    residence="上海闵行区古美街道（老小区）",
    career_identity=["已退休", "原工作单位不详"],
    daily_behavior=["晨练时间：05:00-07:00", "早餐/社区活动：07:00-09:00", "医院/购物：09:00-11:00", "午休：11:00-14:00", "社区活动：14:00-17:00", "休息时间：19:00-22:00"],
    personality_traits=["生活规律", "传统保守", "家庭观念强", "健康导向", "节俭务实", "技术接受度一般"],
    interests_hobbies=["评书/戏曲（喜马拉雅）", "公园晨练", "健康养生", "社区活动", "家庭聚餐"],
    travel_pattern=["去公园/菜市场占约77%", "医院占约13%", "子女家占约3%", "以日常生活和健康管理为中心"],
    vehicle_usage=["空调温度均值26.5℃", "风量2.2档", "车控依赖度45%", "偏好温暖环境", "使用习惯简单固定"],
    media_preference=["喜马拉雅占比48%", "评书、戏曲、健康养生", "常听内容：单田芳评书、京剧、黄梅戏、健康讲座"]
)

STARTUP_YOUTH = UserProfile(
    user_type="创业青年",
    personal_status=["单身", "无子女", "居住在合租公寓"],
    residence="上海徐汇区康健街道（合租公寓）",
    career_identity=["创业者/独立开发者/程序员", "工作地点：徐汇区漕河泾开发区创业孵化器"],
    daily_behavior=["深夜工作：00:00-02:00", "补觉：02:00-06:00", "通勤不固定", "工作时间：09:00-18:00", "继续工作：18:00-00:00", "作息不规律"],
    personality_traits=["目标导向", "冒险精神", "效率至上", "持续学习", "高成就动机", "健康意识一般"],
    interests_hobbies=["编程/技术", "科技播客/创业播客", "电子音乐", "创业生态活动", "游戏/电竞"],
    travel_pattern=["联合办公空间占约27%", "充电站占约76%", "客户/投资方占约12%", "以创业为中心的高强度生活方式"],
    vehicle_usage=["空调温度均值22.3℃", "风量3.5档", "车控依赖度52%", "温度波动大", "长时间在车内"],
    media_preference=["Apple Music+播客占比35%", "电子音乐、科技播客、编程音乐", "常听：Daft Punk、The Chemical Brothers、技术播客"]
)

FULL_TIME_MOM = UserProfile(
    user_type="全职妈妈",
    personal_status=["已婚", "有2名子女（6-9岁小学在读，3-5岁幼儿园）"],
    residence="上海浦东新区花木街道（中档小区）",
    career_identity=["全职妈妈", "无固定工作地点"],
    daily_behavior=["送孩子上学：06:30-08:00", "自由时间：08:00-12:00", "午餐/接孩子：12:00-14:00", "课外班：14:00-19:00", "家庭时间：19:00-22:00"],
    personality_traits=["计划性强", "责任感高", "奉献精神", "理性消费", "家庭优先"],
    interests_hobbies=["儿歌/儿童音乐", "育儿/教育", "购物/家庭采购", "妈妈群社交", "美容/健身", "亲子活动"],
    travel_pattern=["接送孩子和课外班占约33%", "购物占约53%", "以孩子和育儿为中心"],
    vehicle_usage=["空调温度均值24.8℃", "风量2.5档", "车控依赖度32%", "考虑孩子舒适度"],
    media_preference=["QQ音乐占比25%", "儿歌、轻音乐、流行", "常听：宝宝巴士、贝瓦儿歌、周杰伦、邓紫棋"]
)

BUSINESS_ELITE = UserProfile(
    user_type="商务精英",
    personal_status=["已婚", "子女在国际学校就读（8-15岁）", "家庭经济条件优越"],
    residence="上海静安区（顶级豪宅区）",
    career_identity=["金融企业中高层管理人员（总监/VP级别）", "工作地点：静安区南京西路1266号"],
    daily_behavior=["送孩子/通勤：06:00-08:00", "高层管理会议：08:00-12:00", "商务午餐：12:00-14:00", "客户会议：14:00-18:00", "商务应酬：18:00-20:00", "家庭时间：20:00-22:00"],
    personality_traits=["事业心强", "时间管理专家", "社会地位导向", "精英意识", "人脉资源丰富", "品质至上"],
    interests_hobbies=["财经新闻/商业播客", "高尔夫/高端运动", "商务社交", "艺术/文化", "高端旅行", "慈善/公益"],
    travel_pattern=["通勤和送孩子占约16%", "商务活动占约43%", "私人活动占约20%", "以商务和品质生活为中心"],
    vehicle_usage=["空调温度均值22.8℃", "风量2.9档", "车控依赖度28%", "可能有司机或助理操作"],
    media_preference=["QQ音乐占比18%", "古典音乐、爵士、商业播客", "常听：财经新闻、行业分析、商业案例"]
)


def main():
    for profile in [SINGLE_CAREER_WOMAN, RETIRED_SENIOR, STARTUP_YOUTH, FULL_TIME_MOM, BUSINESS_ELITE]:
        # 使用nl_repr打印
        print(nl_repr(profile))
        print("\n" + "="*50 + "\n")
    
if __name__ == "__main__":
    main()
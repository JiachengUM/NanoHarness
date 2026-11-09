import copy

from projects.hwhms.common.domain.traditional import navigation_cat
from projects.hwhms.common.domain.travel_assistant import travel_cat

poi_travel_cat = copy.deepcopy(travel_cat)
poi_travel_cat.examples.append("用户提出一个具体生活场景，请求推荐附近合适的场所。例如：我想给小孩过生日，推荐几个合适的场所")
poi_travel_cat.notices = [
        "如果用户输入中明确了地点信息, 请判断该地点是否属于餐饮、娱乐、酒店、美业。如果不在以上类别中，请归类为导航。",
        # "如果用户询问某地点附近是否有提供特定商品、便民服务的查询（如'XX附近有租YY的吗'、'XX哪有卖ZZ的'、'附近有没有AA服务'），应归类为地点推荐查询",
        "如果用户搜索的餐饮场所是具体的品牌名称(例如：瑞幸咖啡、喜茶、海底捞等),请归类为导航。例如：找附近的瑞幸咖啡",
        "请注意：洗车店不属于餐饮或者娱乐场所, 如果用户想要搜索这些场所,请归类为导航。",
        "如果用户明确想要去或者导航到某个地点，不需要判断该地点是否属于餐饮、娱乐、酒店、美业，请直接归类为导航。例如：导航到国贸附近的西餐厅、 去海边",
        "当用户期望进行行程规划时，如果不涉及到天数，请归类为导航。如：规划海南环岛自驾路线"
    ]


poi_navigation_cat = copy.deepcopy(navigation_cat)
poi_navigation_cat.description = "用户以指令语气直接请求导航到地点、规划路线、查询限行、添加途经点"
poi_navigation_cat.examples[3] = "搜索沿途的加油站、充电桩、服务区、停车场等地点,如: 沿途有充电的地方吗, 附近有充电桩吗, 找个服务区"
poi_navigation_cat.notices.append("如果用户意图是寻找某个地点，且地点推荐查询中不包含该地点类型，请归类为导航。例如：找杭州银行 等") 
poi_navigation_cat.notices.append("当用户输入包含明确的语言转换指令时，即使内容涉及导航，核心意图也是翻译，而非实际执行导航操作，应归属于其他。例如：用英语讲一下旅游咨询中心在哪里、请保持安静用英语说出来")

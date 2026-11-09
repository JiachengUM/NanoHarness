from cabin_advisor.define.scenario import QAList, QAItem, InCarRole, VehicleControlScene
from cabin_advisor.worker.comfort_advisor_worker import ComfortAdvisorWorker

from nanoai.utils import get_logger

# 初始化日志记录器
logger = get_logger("scenario")

# 初始化Worker
model_path = "F:/Download/qwen3-1.7B"

logger.info("初始化ComfortAdvisorWorker，使用{model}模型".format(model=model_path))
worker = ComfortAdvisorWorker(model=model_path, hf_token="REDACTED")

car_status = worker.parser.read_json("car_status.json")
inside_world = worker.parser.read_json("inside_world.json")
outside_world = worker.parser.read_json("outside_world.json")
knowhow_standard = worker.parser.read_json("knowhow_standard.json")

# 对话分析转车控场景
logger.info("=== 对话分析转车控场景意图 ===")
role = InCarRole(name="王伟",
                 type="驾驶员",
                 preferences={"温度": "不喜欢温度23度以上", "座椅": "偏向座椅倾斜50度以下"},
                 status={"心情": "浑身难受、急需座椅放平；刚听完一首歌，看起来有点无聊"},
                 outside={"外部环境": "窗外起雾了"},
                 inside={"面部表情":""}
                 )
InCarRole(name="苏苏",
                 type="乘客",
                 preferences={"温度": "冬天喜欢20-23度，夏天喜欢18-20度", "座椅": "早上座椅倾斜30度，晚上50度"},
                 status={"心情": "浑身难受、急需座椅放平"})
scene = QAList(qa_list=[QAItem(question=f"{role.name}现在在看书", answer="", think="怎样让智能座舱环境更舒服？")])

# 创建角色对象
logger.info(f"输入: {scene.qa_list[0].question}")

advice = worker.analyze_comfort_to_advice(
    car_status=car_status,        # 当前车辆状态
    inside_world=inside_world,    # 车内环境感知
    outside_world=outside_world,  # 车外环境感知
    qa_list=scene,                # 车内事件触发
    role=role,               # 车内角色人设偏好
    knowhow_standard=knowhow_standard  # 舒适分析标准
)

for _ in range(100):
    # 对话分析转车控场景
    scene = worker.analyze_dialogue_to_scene(scene, role, output_format=VehicleControlScene)
    role.preferences = scene.parameters
    role.update(scene)
    logger.info("\n\n=== 对话场景分析结果 ===")
    logger.info(f"场景类型: {scene.scenario_type}")
    logger.info(f"场景参数: {scene.parameters}")
    logger.info(f"场景描述: {scene.description}")
    logger.info(f"目标角色: {scene.target_role}")
    # 车控场景转对话生成
    logger.info("\n\n=== 车控场景转对话生成 ===")
    scene = worker.generate_dialogue_from_scene(scene, role)
    for i, qa in enumerate(scene.qa_list, start=1):
        logger.info(f"轮次 {i}:")
        logger.info(f"{role.name}: {qa.question}")
        logger.info(f"车机系统: {qa.answer}")

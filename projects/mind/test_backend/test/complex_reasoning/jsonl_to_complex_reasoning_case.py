import json
import asyncio
import uuid
from beanie import PydanticObjectId
from projects.mind.complex_reasoning.task_data import ComplexReasoningCase
from projects.mind.complex_reasoning.task_mdb_models.case import ComplexReasoningCaseDoc
from projects.mind.complex_reasoning.task_schemas.case import ComplexReasoningCaseCreate
from projects.mind.intent.repositories import mdb_api
from projects.mind.intent.task_data.message import Message
from projects.mind.test_backend.db.init_beanie import init_db


async def init_mdb():
    await init_db()
    print("\n✅ 数据库连接初始化完成")


def transform_jsonl_to_model(data: dict, index: int) -> ComplexReasoningCase:
    """
    将单条 JSONL 数据转换为 ComplexReasoningCase 模型
    """
    input_text = data.get("input", "")
    output_text = data.get("output", "")
    meta = data.get("meta", {})

    # 映射 case_id: 优先使用 conversation_id，如果没有则生成 UUID
    case_id = meta.get("conversation_id", str(uuid.uuid4()))

    # 映射 user_query_lists
    # 结构要求: list[list[Message]] -> [[Message(role='user', content=...)]]
    user_message = Message(role="user", content=input_text)
    user_query_lists = [[user_message]]

    # 映射 expected_script
    # 格式: 用户: input\n助手: output
    expected_script = f"用户: {input_text}\n助手: {output_text}"

    # 映射 nl_assertion
    # additional_expectation 可能是字符串，需要转为 list[str]
    additional_exp = meta.get("additional_expectation")
    nl_assertion = [additional_exp] if additional_exp else []

    # 映射 max_round
    max_round = meta.get("turn_number", 1)

    # 映射 context_config，先处理为空字典
    context_config = {}

    dataset_id = PydanticObjectId("69aa3b249bd018f8bb84d5b2")  # 这批case导入到哪个数据集下

    # 构建模型
    case_model = ComplexReasoningCaseCreate(
        dataset_id=dataset_id,
        case_id=str(index),
        context_config=context_config,
        max_round=max_round,
        user_query_lists=user_query_lists,
        expected_script=expected_script,
        nl_assertion=nl_assertion,
        case_description=f"导航领域测试用例: {meta.get('Type', 'Unknown')}",
    )

    return case_model


async def process_jsonl_file(file_path: str):
    """读取 JSONL 文件并入库"""

    # 1. 初始化数据库
    await init_mdb()

    print(f"开始读取文件: {file_path}")

    index = 1  # 赋值给case_id
    success_count = 0
    error_count = 0

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue

                try:
                    # 解析 JSON
                    data = json.loads(line)

                    # 转换数据模型
                    payload = transform_jsonl_to_model(data, index)
                    index += 1

                    # 调用入库 API
                    doc = await mdb_api.create(ComplexReasoningCaseDoc, payload)

                    success_count += 1
                    # print(f"✅ 第 {line_num} 条数据入库成功: {doc.case_id}")

                except json.JSONDecodeError as e:
                    print(f"❌ 第 {line_num} 行 JSON 解析失败: {e}")
                    error_count += 1
                except Exception as e:
                    print(f"❌ 第 {line_num} 行处理出错: {e}")
                    error_count += 1

    except FileNotFoundError:
        print(f"❌ 文件未找到: {file_path}")
        return

    print("\n" + "=" * 30)
    print(f"✅ 成功入库: {success_count} 条")
    print(f"❌ 失败跳过: {error_count} 条")
    print("=" * 30)


if __name__ == "__main__":
    # 选择你的jsonl文件位置
    jsonl_file_path = "D:/file/complex/planner.jsonl"

    # 运行异步主函数
    asyncio.run(process_jsonl_file(jsonl_file_path))

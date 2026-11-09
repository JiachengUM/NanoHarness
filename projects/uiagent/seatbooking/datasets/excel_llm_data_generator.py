import pandas as pd
import json
from tqdm import tqdm

# 导入nanoai核心功能
from nanoai.model.llm import llm, RunResult
from nanoai.model.config import ModelName

# 全局变量
global_id = 0

def extract_priority(text: str) -> str:
    """提取优先级，只支持P0、P1、P2"""
    return "p0" if "p0" in text.lower() else ("p1" if "p1" in text.lower() else ("p2" if "p2" in text.lower() else ""))

def generate_and_parse_content(level1: str, level2: str, level3: str, query: str) -> list[str]:
    """生成内容并解析为列表"""
    prompt = PROMPT_TEMPLATE.format(level1=level1, level2=level2, level3=level3, query=query)
    response: RunResult[str] = llm(prompt, model=ModelName.DOUBAO_SEED_1_6_FLASH_250715, temperature=0.8)
    result = response.output
    
    if result:
        return [line.strip() for line in result.split('\n') if line.strip()]
    else:
        return []

def create_result_record(global_id: int, step: str, level1: str, level2: str, level3: str, 
                        query: str, image_path: str, final_priority: str, generated_item: str) -> dict[str, object]:
    """创建结果记录"""
    return {
        "id": global_id,
        "step": step,
        "一级": level1,
        "二级": level2,
        "三级": level3,
        "example": query,
        "image_path": image_path,
        "priority": final_priority,
        "query": generated_item
    }

# 共用prompt模板
PROMPT_TEMPLATE = """
请基于以下三级递进逻辑生成数据，每条数据需体现"{level1} → {level2} → {level3}"的层级关系：

- 一级（{level1}）：表示总体目标或场景；
- 二级（{level2}）：表示更细化的约束或维度；
- 三级（{level3}）：表示最具体、最具执行性的指令或实体。

生成要求：
1. 需以自然语言表达，体现从抽象到具体的层层递进逻辑；
2. 输出的内容应为可直接执行或理解的操作语句；
3. 每条 query 应该能反映出对前两级语义的继承与落地；
4. 生成 10 条不重复的原创指令,一行一个，不输出其他内容。
5. 单条数据不用太长，结合示例来泛化就可以，字数也相当。
6. 内容具体与否，依赖于一级、二级、三级来约定，但是一定是和示例类似的泛化，例子描述是模糊的，生成的就是模糊的，不能偏离这种泛化原则，请尽量与示例强相关！
7. 模糊内容不能用`xxx`来表述
解读思路：已知约束`自提地址选择（P0） → 精确地址（P0） → 强定位(P0)`，示例为：`选维璟印象城店` 
正确解读：当前为选择自提地址，要精确地址的强定位。故我给上了`选维璟印象城店`这个示例。应当输出类似如`找个上海万茂店、选择平金中心店`的内容
错误解读：当前例子是找个店，选24小时店，选地铁口店，选带电梯店，选营业中的店，选0配送费店<---这些不符合精确地址的强定位

描述：当前场景为用户操作瑞幸咖啡小程序的流程，输出的这些示例就是模拟用户操作过程中的一些场景，比方说用户可能要去自提，外送，选店铺，选收货地址，新建收货地址，选商品，选商品规格等。

输出示例（格式参考+可泛化示例）：
{query}
"""

def read_excel_sheet(excel_path: str, sheet_indices: list[int]) -> dict[str, pd.DataFrame]:
    """读取excel的指定sheet"""
    sheets_data = {}
    excel_file = pd.ExcelFile(excel_path)
    all_sheet_names = excel_file.sheet_names
    
    for idx in sheet_indices:
        if 0 <= idx < len(all_sheet_names):
            sheet_name = all_sheet_names[idx]
            df = pd.read_excel(excel_path, sheet_name=sheet_name)
            sheets_data[sheet_name] = df
            print(f"读取sheet: {sheet_name}, 行数: {len(df)}")
    
    return sheets_data

def save_data(data: list[dict[str, object]], output_path: str) -> None:
    """保存数据到JSONL文件"""
    with open(output_path, "w", encoding='utf-8') as f:
        for item in data:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
    print(f"数据已保存到: {output_path}")


def process_sheet_data(sheet_name: str, df: pd.DataFrame) -> list[dict[str, object]]:
    """处理单个sheet的数据"""
    global global_id
    results = []
    
    # 检查必要的列是否存在
    required_columns = ['一级', '二级', '三级', 'query', 'image_path']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    if missing_columns:
        return results

    for index, row in df.iterrows():
        # 提取数据
        level1 = str(row['一级']) if pd.notna(row['一级']) else ""
        level2 = str(row['二级']) if pd.notna(row['二级']) else ""
        level3 = str(row['三级']) if pd.notna(row['三级']) else ""
        query = str(row['query']) if pd.notna(row['query']) else ""
        image_path = str(row['image_path']) if pd.notna(row['image_path']) else ""

        # 提取优先级
        priority1 = extract_priority(level1)
        priority2 = extract_priority(level2)
        priority3 = extract_priority(level3)
        final_priority = f"{priority1}-{priority2}-{priority3}".strip('-')

        # 生成内容并解析
        generated_list = generate_and_parse_content(level1, level2, level3, query)

        # 为每条生成的内容创建独立的记录
        for generated_item in generated_list:
            global_id += 1
            result_record = create_result_record(global_id, sheet_name, level1, level2, level3, 
                                               query, image_path, final_priority, generated_item)
            results.append(result_record)
    
    return results

def run(excel_path: str, output_path: str = "generated_data.jsonl", sheet_indices: list[int] = [0, 1, 2, 3, 4]):
    """运行主流程"""
    global global_id
    print(f"开始处理Excel文件: {excel_path}")
    
    # 读取指定的sheet页
    sheets_data = read_excel_sheet(excel_path, sheet_indices)
    all_results = []
    
    # 处理每个sheet的数据
    for sheet_name, df in tqdm(sheets_data.items(), desc="处理Sheet页"):
        sheet_results = process_sheet_data(sheet_name, df)
        all_results.extend(sheet_results)
    
    # 批量保存所有数据
    save_data(all_results, output_path)
    print(f"处理完成，共生成 {global_id} 条记录")
    return all_results

def run_single_test(level1: str, level2: str, level3: str, query: str, output_path: str = "test_data.jsonl"):
    """运行单个测试"""
    global global_id
    print("=== 单个测试模式 ===")
    
    # 提取优先级
    priority1 = extract_priority(level1)
    priority2 = extract_priority(level2)
    priority3 = extract_priority(level3)
    final_priority = f"{priority1}-{priority2}-{priority3}".strip('-')
    
    # 生成内容并解析
    print("正在调用LLM生成数据...")
    generated_list = generate_and_parse_content(level1, level2, level3, query)
    
    if generated_list:
        print(generated_list)
        
        # 创建独立的数据记录
        test_results = []
        for generated_item in generated_list:
            global_id += 1
            result_record = create_result_record(global_id, "single_test", level1, level2, level3, 
                                               query, "", final_priority, generated_item)
            test_results.append(result_record)
        
        # 批量保存数据
        save_data(test_results, output_path)
        return test_results
    else:
        return []


if __name__ == "__main__":
    # 设置文件路径
    excel_path = r"D:\download\瑞幸咖啡10.21.xlsx"
    
    # 方式1: 运行单个测试
    print("=== 运行单个测试 ===")
    level1 = "自提地址选择（P0）"
    level2 = "精确地址（P0）"
    level3 = "弱定位(P0)"
    query = "找个哈啰大楼附近的店"
    
    run_single_test(level1, level2, level3, query)
    
    # 方式2: 运行完整流程（处理多个sheet）
    print("\n=== 运行完整流程 ===")
    run(excel_path, "generated_data.jsonl", [0, 1])
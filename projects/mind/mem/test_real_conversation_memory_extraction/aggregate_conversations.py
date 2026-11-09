"""
将连续 1 分钟内的对话聚集起来
- 相邻 60s 内有新对话就合并到 conversation_1min
- 同一天的对话合并到 conversation_1day
"""
import json

from rich import print
import pandas as pd
from datetime import datetime
from tqdm import tqdm


def parse_timestamp(ts_str: str) -> datetime:
    """解析时间戳字符串"""
    return datetime.strptime(ts_str, "%Y%m%d %H:%M:%S")


def get_date_key(ts_str: str) -> str:
    """从时间戳提取日期部分，如 '20260101'"""
    return ts_str.split()[0]


def aggregate_conversations(
    csv_path: str,
    output_csv: str,
    interval_seconds: int = 60,
):
    """
    聚集连续时间窗口内的对话
    
    Args:
        csv_path: 输入 CSV 路径
        output_csv: 输出 CSV 路径
        interval_seconds: 时间窗口（秒）
    """
    df = pd.read_csv(csv_path)
    
    # 解析时间戳
    df["_parsed_time"] = df["timestamp"].apply(parse_timestamp)
    
    # 新增列，默认空字符串
    df["conversation_1min"] = ""
    df["conversation_1day"] = ""
    
    # 按时间排序
    df = df.sort_values("_parsed_time").reset_index(drop=True)
    
    total = len(df)
    merged_1min_count = 0
    valid_1min_count = 0
    
    # ========== 第一步：处理 conversation_1min ==========
    i = 0
    with tqdm(total=total, desc="处理 conversation_1min") as pbar:
        while i < total:
            # 跳过空行
            user_cmd = df.loc[i, "user_command"]
            if pd.isna(user_cmd) or str(user_cmd).strip() == "":
                i += 1
                pbar.update(1)
                continue
            
            # 收集从当前行开始的连续对话
            conversation = []
            start_idx = i
            
            # 向后查找 60s 内的所有对话
            current_time = df.loc[i, "_parsed_time"]
            
            while i < total:
                row_time = df.loc[i, "_parsed_time"]
                time_diff = (row_time - current_time).total_seconds()
                
                # 超过 60s，停止
                if time_diff > interval_seconds:
                    break
                
                # 收集当前行
                user = df.loc[i, "user_command"]
                assistant = df.loc[i, "system_response"]
                
                if pd.notna(user) and str(user).strip() != "":
                    conversation.append({
                        "user": str(user),
                        "assistant": str(assistant) if pd.notna(assistant) else ""
                    })
                
                i += 1
            
            # 写入结果
            if len(conversation) > 0:
                last_idx = i - 1
                
                # 如果有多条对话，将前面被合并的行置空
                if len(conversation) > 1:
                    for idx in range(start_idx, last_idx):
                        df.loc[idx, "conversation_1min"] = ""
                    merged_1min_count += len(conversation) - 1
                
                df.loc[last_idx, "conversation_1min"] = json.dumps(conversation, ensure_ascii=False)
                valid_1min_count += 1
            
            pbar.update(i - start_idx if i > start_idx else 1)
    
    # ========== 第二步：处理 conversation_1day ==========
    # 按 conversation_1min 非空的行，按日期分组
    df_non_empty = df[df["conversation_1min"] != ""].copy()
    
    merged_1day_count = 0
    valid_1day_count = 0
    
    with tqdm(total=len(df_non_empty), desc="处理 conversation_1day") as pbar:
        for date_key, group in df_non_empty.groupby(df_non_empty["timestamp"].apply(get_date_key)):
            # 收集该天所有对话
            day_conversation = []
            indices = []
            
            for idx in group.index:
                conv_str = df.loc[idx, "conversation_1min"]
                try:
                    conv = json.loads(conv_str)
                    day_conversation.extend(conv)
                    indices.append(idx)
                except:
                    continue
            
            if len(day_conversation) > 0:
                # 将前面的行置空
                for idx in indices[:-1]:
                    df.loc[idx, "conversation_1day"] = ""
                    merged_1day_count += 1
                
                # 在最后一行写入合并结果
                df.loc[indices[-1], "conversation_1day"] = json.dumps(day_conversation, ensure_ascii=False)
                valid_1day_count += 1
            
            pbar.update(len(group))
    
    # 删除临时列
    df = df.drop(columns=["_parsed_time"])
    
    # 保存
    df.to_csv(output_csv, index=False, encoding="utf-8")
    
    print(f"\n✅ 处理完成！")
    print(f"📊 原始数据行数：{total}")
    print(f"📊 conversation_1min 被合并行数：{merged_1min_count}")
    print(f"📊 conversation_1min 有效对话数：{valid_1min_count}")
    print(f"📊 conversation_1day 被合并行数：{merged_1day_count}")
    print(f"📊 conversation_1day 有效天数：{valid_1day_count}")
    print(f"💾 结果已保存到：{output_csv}")
    
    return df


if __name__ == "__main__":
    INPUT_CSV = r"projects\mind\mem\test_real_conversation_memory_extraction\sample-data-v2.csv"
    OUTPUT_CSV = r"projects\mind\mem\test_real_conversation_memory_extraction\sample-data-v3.csv"
    # 处理原始数据集，提取出
    # 1、相邻60s内的对话为一轮的数据
    # 2、按照day 来统计数据集
    result_df = aggregate_conversations(
        csv_path=INPUT_CSV,
        output_csv=OUTPUT_CSV,
        interval_seconds=60,
    )
    
    # 预览有 conversation_1day 的记录
    print("\n📌 有每日对话的记录预览：")
    non_empty = result_df[result_df["conversation_1day"] != ""]
    for idx, row in non_empty.head(5).iterrows():
        print(f"\n[{idx}] {row['timestamp']}")
        print(f"  conversation_1day 长度: {len(row['conversation_1day'])} ")

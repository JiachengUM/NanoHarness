import json
import os

import pandas as pd


def remove_duplicates_from_excel(json_file_path, excel_file_path, sheet_name='出行助手'):
    """
    从Excel中删除与JSON数据重复的行
    
    参数:
    json_file_path: JSON文件路径
    excel_file_path: Excel文件路径
    sheet_name: 要处理的Excel工作表名称（默认为'Sheet1'）
    """
    try:
        # 1. 读取JSON文件
        with open(json_file_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        
        # 2. 读取Excel文件
        df = pd.read_excel(excel_file_path, sheet_name=sheet_name)
        
        # 3. 提取JSON中的唯一标识（假设每条记录有'id'字段）
        json_querys = {item['query'] for item in json_data if 'query' in item}
        
        # 4. 找出Excel中需要删除的行索引
        rows_to_delete = []
        for index, row in df.iterrows():
            if 'query' in row and row['query'] in json_querys:
                rows_to_delete.append(index)
        
                # 5. 删除重复行
        df_cleaned = df.drop(rows_to_delete)
        
        # 6. 保存清理后的Excel文件（在原文件名后添加"_cleaned"）
        file_name, file_ext = os.path.splitext(excel_file_path)
        cleaned_file_path = f"{file_name}_cleaned{file_ext}"
        df_cleaned.to_excel(cleaned_file_path, index=False)
        
        print(f"成功删除 {len(rows_to_delete)} 条重复记录")
        print(f"清理后的文件已保存为: {cleaned_file_path}")
        
        return cleaned_file_path
    
    except Exception as e:
        print(f"处理过程中出错: {str(e)}")
        return None

# 使用示例
if __name__ == "__main__":
    json_path = "D:\\tmp\\HW\\json_1010\\5000\\趣味助手.json"  # 替换为您的JSON文件路径
    excel_path = "D:\\tmp\\HW\\json_1010\\5000\\huawei_1012.xlsx"  # 替换为您的Excel文件路径
    
    cleaned_file = remove_duplicates_from_excel(json_path, excel_path, sheet_name="趣味助手")
    
    if cleaned_file:
        print("处理完成!")
    else:
        print("处理失败")
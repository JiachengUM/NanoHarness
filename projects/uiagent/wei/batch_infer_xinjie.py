# 标准库导入
import os
import shutil
from datetime import datetime
from PIL import Image

# 第三方库导入
import pandas as pd
from tqdm import tqdm
from volcenginesdkarkruntime import Ark

# 导入本地模块
from .prompt import UI_TARS_PROMPT_DOU
from ..model.uitars import uitars_call
from nanoai.model.config import create_client, ModelName
from .image_check import draw_actions

from ui_tars.action_parser import smart_resize, parse_action_to_structure_output



def main():
    # sheet_name = 3
    # ========== 基础路径 ==========
    excel_path = r"D:\yitu\2509\nanoai-ui-agent-datasets\datasets\cheji-meituan\心界-数据.xlsx"
    
    output_excel = excel_path.replace(".xlsx", "_推理结果.xlsx")
    # 获取当前时间，格式化为：年-月-日_时-分-秒（避免特殊字符，确保目录名合法）
    current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_excel = excel_path.replace(".xlsx", f"{current_time}_推理结果.xlsx")
    
    # 生成包含时间的结果目录路径（基于Excel文件目录）
    base_dir = os.path.dirname(excel_path)
    results_dir = os.path.join(base_dir, f"results_{current_time}")
    # 保存的连接前缀
    link = "http://47.117.182.61/test_result_img/"+f"results_{current_time}/"
    os.makedirs(results_dir, exist_ok=True)

    # ========== 读取原始数据 ==========
    df_raw = pd.read_excel(excel_path, sheet_name=0)
    print(f"读取原始测试数据 {len(df_raw)} 条")

    # ========== 创建新结果 DataFrame ==========
    df_result = df_raw.copy()  # 复制原始列
    
    # 确保所有需要的列存在（只保留这7个字段）
    required_columns = {
        "id": "",
        "tags": "",
        "query": "",
        "image": "",
        "ground_truth": "",
        "ground_truth_reference_image": "",
        "remark": ""
    }
    
    # 添加所有需要的列，并确保所有行都有默认值
    for col_name, default_val in required_columns.items():
        if col_name not in df_result.columns:
            df_result[col_name] = default_val
        # 确保所有行都有值，用空字符串填充nan
        df_result[col_name] = df_result[col_name].fillna("").astype(str)

    # ========== 主推理循环 ==========
    # 确保所有行都有默认值
    for col in required_columns.keys():
        df_result[col] = df_result[col].fillna("")
    
    # 用于跟踪已经复制的图片，避免重复复制
    copied_images = {}
    
    # 创建临时保存文件，用于实时保存进度
    temp_excel = output_excel.replace(".xlsx", "_temp.xlsx")
    # 创建火山引擎客户端实例
    client, _ = create_client(ModelName.DOUBAO_1_5_UI_TARS_250428, Ark)
    for idx, row in tqdm(df_raw.iterrows(), total=len(df_raw), desc="处理数据"):
        # 测三个，看下流程
        # if idx >= 5:
        #     break
        query = str(row["query"]).strip()
        # query = "来八个朋友"
        # 从表格读取每行的图像路径
        image_path = str(row["image_path"]).strip()
        
        # query = "6个人，12点的"
        # current_date = datetime.now().strftime("%Y-%m-%d")
        # infer_query = f"（当前日期：{current_date}, 用户要进行订座操作）：{query}"  # 信息页
        infer_query = f"{query}" # 店铺详情页

        try:
            # 设置基础信息
            df_result.at[idx, "id"] = str(idx + 1)
            df_result.at[idx, "query"] = str(query) if query else ""
            df_result.at[idx, "tags"] = ""  # 默认为空
            
            # 复制原始图像到results_dir并设置image字段（避免重复复制）
            original_image_name = os.path.basename(image_path)
            if image_path not in copied_images:
                # 第一次遇到这个图片路径，进行复制
                copied_image_path = os.path.join(results_dir, original_image_name)
                if not os.path.exists(copied_image_path):
                    shutil.copy2(image_path, copied_image_path)
                copied_images[image_path] = original_image_name
            df_result.at[idx, "image"] = link + original_image_name
            
            result = uitars_call(client, image_path, infer_query, UI_TARS_PROMPT_DOU, "custom_prompt")

            # === 判断推理是否成功 ===
            if not result.success:
                error_msg = str(result.error or "未知错误")
                df_result.at[idx, "ground_truth"] = error_msg  # 推理失败时使用错误信息
                df_result.at[idx, "ground_truth_reference_image"] = ""
                df_result.at[idx, "remark"] = "推理失败"
                # image字段已经在上面设置了，这里不需要重复设置
                continue

            # === 成功推理 ===
            content = str(result.content)
            # print(content)

            # === 使用新的解析和渲染逻辑 ===
            try:
                # 获取原始图片尺寸
                with Image.open(image_path) as img:
                    original_image_width, original_image_height = img.size
                
                # 计算新的尺寸
                new_height, new_width = smart_resize(original_image_height, original_image_width)
                
                # 解析动作到结构化输出
                parsed_dict_list = parse_action_to_structure_output(
                    content,
                    factor=28,
                    origin_resized_height=new_height,
                    origin_resized_width=new_width,
                    model_type="qwen25vl"
                )
                # print(parsed_dict_list)
                if not parsed_dict_list:
                    # 解析失败，使用原始content
                    df_result.at[idx, "ground_truth"] = content
                    df_result.at[idx, "ground_truth_reference_image"] = ""
                    df_result.at[idx, "remark"] = "解析失败"
                    continue
                
                # 解析成功，使用parsed_dict_list
                df_result.at[idx, "ground_truth"] = parsed_dict_list
                
                # 构建坐标列表
                click_coordinates = []
                for an_action in parsed_dict_list:
                    if an_action["action_type"] in ["click", "scroll"]:
                        # 统一解析坐标
                        x1, y1, x2, y2 = eval(an_action["action_inputs"]["start_box"])
                        click_coordinates.append({
                            "action_type": an_action["action_type"],
                            "coordinates": {"x1": x1, "y1": y1, "x2": x2, "y2": y2}
                        })
                
                # 检查是否有可渲染的动作
                if click_coordinates:
                    # 有可渲染的动作，生成输出图片
                    img_name = f"{idx+1}_ground_truth_reference.png"
                    output_img = os.path.join(results_dir, img_name)
                    img_url = link + img_name
                    
                    print("所有click_coordinates: ", click_coordinates)
                    # 使用 draw_actions 绘制
                    draw_actions(image_path=image_path, output_path=output_img, coordinates=click_coordinates)
                    df_result.at[idx, "ground_truth_reference_image"] = img_url
                else:
                    # 没有可渲染的动作（如finished等），不生成图片
                    df_result.at[idx, "ground_truth_reference_image"] = ""
                
                df_result.at[idx, "remark"] = ""  # 解析成功时remark为空
                
            except Exception as parse_error:
                print(f"❌ 解析动作出错: {parse_error}")
                # 解析异常，使用原始content
                df_result.at[idx, "ground_truth"] = [{"error": "解析异常", "content": content}]
                df_result.at[idx, "ground_truth_reference_image"] = ""
                df_result.at[idx, "remark"] = f"解析异常: {parse_error}"


        except Exception as e:
            err_msg = f"出错: {e}"
            print(f"❌ {err_msg}")
            # 确保所有字段都有值，避免nan
            df_result.at[idx, "remark"] = err_msg
            df_result.at[idx, "ground_truth"] = err_msg  # 处理异常时使用错误信息
            df_result.at[idx, "ground_truth_reference_image"] = ""
            # 如果image字段还没有设置，在这里设置
            if pd.isna(df_result.at[idx, "image"]):
                original_image_name = os.path.basename(image_path)
                # 确保图片已经复制（如果还没有复制的话）
                if image_path not in copied_images:
                    copied_image_path = os.path.join(results_dir, original_image_name)
                    if not os.path.exists(copied_image_path):
                        shutil.copy2(image_path, copied_image_path)
                    copied_images[image_path] = original_image_name
                df_result.at[idx, "image"] = link + original_image_name
        
        # 每处理完一行就立即保存，避免中途出错丢失数据
        try:
            final_columns = ["id", "tags", "query", "image", "ground_truth", "ground_truth_reference_image", "remark"]
            df_temp = df_result[final_columns].fillna("")
            df_temp.to_excel(temp_excel, index=False)
        except Exception as save_error:
            print(f"⚠️ 保存临时文件出错: {save_error}")

    # ========== 完成处理，重命名临时文件为最终文件 ==========
    try:
        # 将临时文件重命名为最终文件
        if os.path.exists(temp_excel):
            if os.path.exists(output_excel):
                os.remove(output_excel)  # 删除旧的最终文件
            os.rename(temp_excel, output_excel)  # 重命名临时文件
            print(f"\n✅ 全部处理完成，新结果文件已保存到：\n{output_excel}")
        else:
            # 如果临时文件不存在，创建最终文件
            final_columns = ["id", "tags", "query", "image", "ground_truth", "ground_truth_reference_image", "remark"]
            df_final = df_result[final_columns].fillna("")
            df_final.to_excel(output_excel, index=False)
            print(f"\n✅ 全部处理完成，新结果文件已保存到：\n{output_excel}")
        
        print(f"📊 最终表格包含 {len(df_result)} 行数据")
        print(f"🖼️ 图像文件已复制到：{results_dir}")
        print(f"🔗 图像访问链接前缀：{link}")
        
    except Exception as final_error:
        print(f"❌ 最终保存出错: {final_error}")
        print(f"📁 临时文件位置: {temp_excel}")

if __name__ == "__main__":
    main()

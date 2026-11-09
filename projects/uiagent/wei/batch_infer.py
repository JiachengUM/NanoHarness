import os
import time
from datetime import datetime
from PIL import Image, ImageDraw

import pandas as pd
from tqdm import tqdm
from volcenginesdkarkruntime import Ark

# 导入本地模块
from .prompt import (UI_TARS_PROMPT_DINGZUOREN_info, UI_TARS_PROMPT_coffee)
from ..model.uitars import uitars_call
from nanoai.model.config import create_client, ModelName
from .image_check import draw_rectangle_pillow, draw_scroll_arrow
from .utils import parse_x_y, parse_action


def main():
    sheet_name = 0
    # ========== 基础路径 ==========
    excel_path = r"D:\yitu\2509\nanoai-ui-agent-datasets\datasets\coffee\lucky_coffee.xlsx"
    # image_path = r"D:\yitu\2509\nanoai-ui-agent-datasets\datasets\cheji-meituan\test.jpg" # 人数、日期、时间页面 sheet_name = 1
    image_path = r"D:\yitu\2509\nanoai-ui-agent-datasets\datasets\cheji-meituan\verify_dingzuo.jpg" # 店铺详情页，判断是否支持订座。支持订座 sheet_name = 2
    # image_path = r"D:\yitu\2509\nanoai-ui-agent-datasets\datasets\cheji-meituan\dingzuo_unsupported.jpg" # 不支持订座 sheet_name = 2
    #image_path = r"D:\yitu\2509\nanoai-ui-agent-datasets\datasets\cheji-meituan\dingzuoren_info.png" # 订座人信息页 sheet_name = 3
    # excel_path = r"D:\yitu_projects\nanoai\projects\uiagent\wei\美团订座测试用例10.20 obsolete.xlsx"
    # image_path = r"D:\yitu_projects\nanoai\projects\uiagent\wei\美团订座订座信息页步骤3-2——有大量营业时间选项.jpg" # 人数、日期、时间页面 sheet_name = 1

    output_excel = excel_path.replace(".xlsx", "_推理结果.xlsx")
    # 统一图片输出到 image_path 同目录下的 results 文件夹
    base_dir = os.path.dirname(excel_path)
        # 获取当前时间，格式化为：年-月-日_时-分-秒（避免特殊字符，确保目录名合法）
    current_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    output_excel = excel_path.replace(".xlsx", f"{current_time}_推理结果.xlsx")
    # 生成包含时间的结果目录路径
    results_dir = os.path.join(base_dir, f"results_{current_time}")
    # 保存的连接前缀
    link = "http://47.117.182.61/test_result_img/"+f"results_{current_time}/"
    os.makedirs(results_dir, exist_ok=True)

    # ========== 读取原始数据 ==========
    df_raw = pd.read_excel(excel_path, sheet_name=sheet_name)
    print(f"读取原始测试数据 {len(df_raw)} 条")

    # ========== 创建新结果 DataFrame ==========
    df_result = df_raw.copy()  # 复制原始列
    # 确保目标列存在
    for col in ["结果（模型推理文本）", "执行图片", "备注"]:
        if col not in df_result.columns:
            df_result[col] = ""
        df_result[col] = df_result[col].astype(str)
    client, _ = create_client(ModelName.DOUBAO_1_5_UI_TARS_250428, Ark)
    # ========== 主推理循环 ==========
    for idx, row in tqdm(df_raw.iterrows(), total=len(df_raw), desc="处理数据"):
        # 测三个，看下流程
        # if idx >= 3:
        #     break
        query = str(row["query"]).strip()
        image_path = str(row["image_path"]).strip()
        # current_date = datetime.now().strftime("%Y-%m-%d")
        # infer_query = f"（当前日期：{current_date}, 用户要进行订座操作）：{query}"  # 信息页
        infer_query = f"{query}" # 店铺详情页

        try:
            # result = uitars_call(client, image_path, infer_query, UI_TARS_PROMPT_DINGZUOREN_info, "custom_prompt")
            result = uitars_call(client, image_path, infer_query, UI_TARS_PROMPT_coffee, "custom_prompt")

            # === 判断推理是否成功 ===
            if not result.success:
                df_result.at[idx, "结果（模型推理文本）"] = result.error or "未知错误"
                df_result.at[idx, "备注"] = ""
                df_result.at[idx, "执行图片"] = ""
                continue

            # === 成功推理 ===
            content = result.content
            actions = parse_action(result)
            df_result.at[idx, "结果（模型推理文本）"] = content
            df_result.at[idx, "备注"] = ""

            if not actions:
                df_result.at[idx, "执行图片"] = "无动作"
                continue

            action = actions[0].get("action", "")
            img_name = f"{idx+2}_action_{action}.png"
            output_img = os.path.join(results_dir, img_name)
            img_url = link + img_name
            # === 根据动作绘图 ===
            if action == "click":
                x, y = parse_x_y(actions[0])
                draw_rectangle_pillow(image_path, output_img, x=x, y=y, color="red", width=20)
                df_result.at[idx, "执行图片"] = img_url
            elif action == "scroll":
                point = actions[0].get("point", "")
                direction = actions[0].get("direction", "")
                draw_scroll_arrow(image_path, output_img, point, direction)
                df_result.at[idx, "执行图片"] = img_url
            else:
                df_result.at[idx, "执行图片"] = action


        except Exception as e:
            err_msg = f"出错: {e}"
            print(f"❌ {err_msg}")
            df_result.at[idx, "备注"] = err_msg

    # ========== 写入新 Excel，不改动原文件 ==========
    df_result.to_excel(output_excel, index=False)
    print(f"\n✅ 全部处理完成，新结果文件已保存到：\n{output_excel}")

if __name__ == "__main__":
    main()

import asyncio
from pathlib import Path
from typing import Final, Any
from projects.uiagent.core.uiflow import run_ui_step
from projects.uiagent.general_parking_payment.datasets import DATASET_ROOT
from rich import print
from projects.uiagent.general_parking_payment.workflow import (
    ParkingSteps,
    GeneralParkingPaymentUIFlow,
    PlateNumber,
)
from projects.uiagent.core.flow_data import MiddleInfoType
from projects.uiagent.core.visualize import draw_step_result
from nanoai.utils.async_utils import amap

# 文件夹名到PlateNumber的映射配置
FOLDER_INFO_MAP: Final[dict[str, PlateNumber]] = {
    "01玉溪市人民医院": PlateNumber(plate_number="云F933LL"),
    "02百联": PlateNumber(plate_number="云F933LL"),
    "03合生汇": PlateNumber(plate_number="云F933LL"),
    "04明泉财富": PlateNumber(plate_number="云F933LL"),
    "05平金中心": PlateNumber(plate_number="云F933LL"),
    "06印享星": PlateNumber(plate_number="云F933LL"),
    "7个体": PlateNumber(plate_number="粤A124567"),
    "8个体": PlateNumber(plate_number="鄂A12345"),
    "09江苏园博园": PlateNumber(plate_number="云F933LL"),
    "10扬马小区": PlateNumber(plate_number="云F933LL"),

    "11安徽停车": PlateNumber(plate_number="皖A12345"),
    "12重庆停车": PlateNumber(plate_number="皖A12345"),
    "13福建": PlateNumber(plate_number="闽A12345"),
    "14福建": PlateNumber(plate_number="皖A12345"),
    "15广东": PlateNumber(plate_number="粤A12345"),
    "16河南": PlateNumber(plate_number="豫A12345"),
    "17江苏": PlateNumber(plate_number="苏A12345"),
    "18江苏无锡": PlateNumber(plate_number="苏A12345"),
    "19山东菏泽": PlateNumber(plate_number="鲁R12345"),
    "20上海停车": PlateNumber(plate_number="沪A12345"),

    "21浙江舟山慈航广场": PlateNumber(plate_number="云F933LL"),
    "22个体": PlateNumber(plate_number="沪A12345"),
    "23玉林福绵机场": PlateNumber(plate_number="云F933LL"),
    "24个体": PlateNumber(plate_number="皖A12456"),
    "25白竹湖广场": PlateNumber(plate_number="云F933LL"),
    "26中山石岐万象汇": PlateNumber(plate_number="云F933LL"),
    "27商场": PlateNumber(plate_number="浙A12346"),
    "28P": PlateNumber(plate_number="云F933LL"),
    "29群光广场": PlateNumber(plate_number="云F933LL"),
    "30微信车主": PlateNumber(plate_number="云F933LL"),

    "31ETCP": PlateNumber(plate_number="皖AE27C3"),
    "32PP停车": PlateNumber(plate_number="粤SV6J93"),
    "33海康云停车": PlateNumber(plate_number="贵F51T30"),
    "34立方停车": PlateNumber(plate_number="浙A12345"),
    "35速停车": PlateNumber(plate_number="京A12345"),
    "36停宜慧": PlateNumber(plate_number="皖AE27C3"),
    "37全球泊": PlateNumber(plate_number="沪A12345"),
    "38简停车": PlateNumber(plate_number="沪GAQ976"),
    "39云盟互联": PlateNumber(plate_number="皖A5624K"),
    "40商场": PlateNumber(plate_number="浙A124567"),
}

# 支持的图片格式
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}

async def test_workflow_ui_step(
    step: ParkingSteps,
    image_path: str,
    info: MiddleInfoType | None,
    output_dir: str | None = None,
    sample_id: str | int | None = None,
) -> None:
    """测试单个步骤"""
    print(f"\n==============test_workflow_ui_step: step: {step}=====================")
    print(f"image: {image_path}")
    print(f"info: {info}")
    result = await run_ui_step(
        GeneralParkingPaymentUIFlow, 
        image_path, 
        step, 
        info=info, 
    )
    
    if output_dir:
        draw_step_result(
            image_path=image_path,
            query="",
            runresult=result.results,
            output_dir=output_dir,
            sample_id=sample_id,
        )

    print(f"\n{result}")

def prepare_folder_data(
    folder_path: str | Path,
    info: PlateNumber | None = None,
    info_map: dict[str, PlateNumber] = FOLDER_INFO_MAP,
) -> list[tuple[str, PlateNumber, str, str]] | None:
    """
    组织文件夹数据：获取图片列表和对应的info
    
    Returns:
        [(image_path, info, output_dir), ...] 或 None（如果出错）
    """
    folder_path = Path(folder_path)
    if not folder_path.exists() or not folder_path.is_dir():
        print(f"❌ 文件夹不存在或不是目录: {folder_path}")
        return None
    
    folder_name = folder_path.name
    
    # 获取info
    if info is None:
        info = info_map.get(folder_name)
        if info is None:
            print(f"❌ 文件夹 {folder_name} 没有对应的PlateNumber配置，请在FOLDER_INFO_MAP中添加")
            return None
    
    # 获取所有图片文件
    image_files = [
        f for f in folder_path.iterdir() 
        if f.is_file() and f.suffix.lower() in IMAGE_EXTENSIONS
    ]
    
    if not image_files:
        print(f"❌ 文件夹 {folder_name} 中没有找到图片文件")
        return None
    
    # 创建输出目录
    output_dir = DATASET_ROOT / "tests" / folder_name
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 组织数据：(image_path, info, output_dir, sample_id)
    data = [
        (str(image_file), info, str(output_dir), str(image_file.stem))
        for image_file in sorted(image_files)
    ]
    
    print(f"✅ 文件夹 {folder_name}: 找到 {len(data)} 张图片，车牌: {info.plate_number}")
    return data

async def batch_run(
    params: list[tuple[str, PlateNumber, str, str]],
    step: ParkingSteps = ParkingSteps.GENERAL_PARKING_PAYMENT,
    max_concurrent: int = 100,
) -> None:
    """
    批量运行：使用amap调用单步处理函数
    
    Args:
        params: [(image_path, info, output_dir, sample_id), ...]
        step: 要运行的步骤
        max_concurrent: 最大并发数
    """
    if not params:
        print("❌ 没有数据需要处理")
        return
    
    print(f"\n开始批量处理 {len(params)} 张图片，并发数: {max_concurrent}")
    
    # 定义异步包装函数
    async def process_single(param: tuple[str, PlateNumber, str, str]) -> None:
        await test_workflow_ui_step(step, param[0], param[1], param[2], param[3])
    
    # 使用 amap 调用单步处理函数
    results, stats = await amap(
        process_single,
        params,
        max_concurrent=max_concurrent,
        progress=True,
    )
    
    # 统计结果
    success_count = sum(1 for r in results if not isinstance(r, Exception))
    error_count = len(results) - success_count
    
    print(f"\n✅ 批量处理完成: 成功 {success_count}, 失败 {error_count}")
    if stats:
        stats.print()
    
    if error_count > 0:
        print(f"\n❌ 失败的图片:")
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                print(f"  - {params[i][0]}: {result}")


def main() -> None:
    """主函数：可以批量运行多个文件夹"""
    # 直接读取。
    folders = [DATASET_ROOT / name for name in FOLDER_INFO_MAP.keys()]  
    
    # 先组织好所有数据
    all_data = []
    for folder in folders:
        data = prepare_folder_data(folder)
        if data:
            all_data.extend(data)
    
    # 批量运行
    if all_data:
        asyncio.run(batch_run(all_data))

if __name__ == "__main__":
    main()
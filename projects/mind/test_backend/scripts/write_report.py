from __future__ import annotations

import asyncio
import os
import argparse

from beanie import PydanticObjectId

from projects.mind.test_backend.db.init_beanie import init_db
from projects.mind.test_backend.mdb_models.task import TaskRunDoc, TaskDoc
from projects.mind.test_backend.service.task.task_report_service import (
    generate_task_run_report,
)


def _sanitize_filename(name: str) -> str:
    return "".join(c if c.isalnum() or c in ("-", "_", " ") else "_" for c in name)


async def write_task_run_report(task_run_id: str, report_file_path: str | None = None):
    """
    根据 task_run_id 生成测试报告并写入指定文件

    Args:
        task_run_id: 任务运行ID（单个）
        report_file_path: 报告文件路径（.md），不传则默认输出到脚本所在目录，文件名为任务名称
    """
    await init_db()

    print(f"正在查询 task_run: {task_run_id} ...")

    task_run = await TaskRunDoc.get(PydanticObjectId(task_run_id))
    if not task_run:
        raise ValueError(f"未找到 task_run: {task_run_id}")

    task = await TaskDoc.get(task_run.task_id)
    task_name = task.name if task else task_run_id

    report = await generate_task_run_report(task_run_id)

    if not report_file_path:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        safe_name = _sanitize_filename(task_name)
        report_file_path = os.path.join(script_dir, f"{safe_name}.md")

    os.makedirs(os.path.dirname(os.path.abspath(report_file_path)), exist_ok=True)

    with open(report_file_path, "w", encoding="utf-8") as f:
        f.write(report)

    print(f"报告已写入: {report_file_path}")


def main():
    parser = argparse.ArgumentParser(description="根据 task_run_id 生成测试报告")
    parser.add_argument("--task_run_id", type=str, required=True, help="任务运行ID")
    parser.add_argument(
        "--output", type=str, default=None, help="报告输出文件路径（.md）"
    )
    args = parser.parse_args()

    asyncio.run(write_task_run_report(args.task_run_id, args.output))


if __name__ == "__main__":
    main()

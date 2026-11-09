import logging
import traceback
from datetime import datetime
from pathlib import Path

from sqlalchemy import Column, String, JSON, DateTime, select, Float, asc
from sqlalchemy.exc import SQLAlchemyError

from projects.uiagent.server.configs.init_database import Base, get_session, close_db
from projects.uiagent.server.configs.nacos_util import init_nacos
from projects.uiagent.utils.image_utils import base64_to_bytes

logger = logging.getLogger(__name__)


class LogTable(Base):
    __tablename__ = 'log_data'
    trace_id = Column(String(64), primary_key=True)
    chat_id = Column(String(64), nullable=True)
    path = Column(String(255), nullable=True)
    req = Column(JSON, nullable=True)
    resp = Column(JSON, nullable=True)
    create_time = Column(DateTime, default=datetime.now, comment="创建时间")
    process_time = Column(Float, nullable=True)


    @classmethod
    async def save_data(cls, trace_id, chat_id, path, req, resp, create_time=None, process_time=None):
        if not create_time:
            create_time = datetime.now()
        async with get_session() as session:
            ve = cls(
                trace_id=trace_id,
                chat_id=chat_id,
                path=path,
                req=req,
                resp=resp,
                create_time=create_time,
                process_time=process_time
            )
            session.add(ve)
            return ve

    @classmethod
    async def get_log_data(cls, trace_id: str = None, chat_id = None):
        try:
            async with get_session() as session:
                # 优先使用request_id查询
                if trace_id:
                    return [await session.get(cls, trace_id)]

                # 使用chat_id查询
                if chat_id:
                    stmt = select(cls).where(cls.chat_id == chat_id).order_by(asc(cls.create_time))
                    result = await session.execute(stmt)
                    return result.scalars().all()

                # 没有提供任何查询条件
                logger.warning("get_log_data调用时未提供任何查询参数")
                return []

        except SQLAlchemyError as e:
            logger.error(f"查询log数据失败: {str(e)}")
            return {'error': str(e), 'error_details': traceback.format_exc()}

    @classmethod
    async def trace_id_to_datasets(cls, trace_id: str=None, chat_id: str=None, save_dir: str=None):
        assert save_dir, 'save_dir不能为空'
        datas = await cls.get_log_data(trace_id=trace_id, chat_id=chat_id)
        if not datas:
            raise Exception(f"[{trace_id}]未找到对应的数据")
        for idx, data in enumerate(datas):
            try:
                trace_id = data.trace_id
                req = data.req
                resp = data.resp
                print(f'[{trace_id}]query:{req.get("query")}')
                query = req.get('query')
                if query:
                    query_image_save_path = Path(save_dir) / "images" / f'{idx}_{trace_id}.txt'
                    query_xml_save_path = Path(save_dir) / "xmls" / f'{idx}_{trace_id}.txt'
                    query_image_save_path.parent.mkdir(parents=True, exist_ok=True)
                    query_xml_save_path.parent.mkdir(parents=True, exist_ok=True)
                    query_image_save_path.write_text(query, encoding='utf-8')
                    query_xml_save_path.write_text(query, encoding='utf-8')
                    continue

                image_base64 = req.get('image_base64')
                xml = req.get('xml')
                image_format = req.get('image_format')
                image = base64_to_bytes(image_base64)
                image_save_path = Path(save_dir) / "images" / f'{idx}_{trace_id}.{image_format}'
                image_save_path.parent.mkdir(parents=True, exist_ok=True)
                image_save_path.write_bytes(image)

                xml_save_path = Path(save_dir) / "xmls" / f'{idx}_{trace_id}.xml'
                xml_save_path.parent.mkdir(parents=True, exist_ok=True)
                xml_save_path.write_text(xml, encoding='utf-8')
            except:
                print(f"[{trace_id}]保存数据失败， 没有query也没有图片 xml：{traceback.format_exc()}")


if __name__ == '__main__':
    import asyncio
    async def main():
        from projects.uiagent.server.configs.config import AppConfig
        from projects.uiagent.server.configs.nacos_configs import NacosConfigs
        from projects.uiagent.server.configs.init_database import init_engine
        init_nacos()
        await NacosConfigs.init()
        await AppConfig.init()
        await init_engine(AppConfig.DATABASE_URL)
        # data = await LogTable.get_log_data(
        #     trace_id = '2c85ab31-dde3-415e-b95b-4b19bc9904ec'
        # )
        # print(data)
        await LogTable.trace_id_to_datasets(
            # "7fd35a31-da40-42cc-bdd3-9c262cedcdf0",
            chat_id="79759ae110824be1a5f3d870a9376970",
            save_dir=r"D:\Projects\nanoai\projects\uiagent\jie_parking\datasets\bad_case_with_xml\79759ae110824be1a5f3d870a9376970"
        )
        await close_db()

    asyncio.run(main())
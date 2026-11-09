import time
from typing import Optional
from nanoai.utils import logger
from projects.mind.advisor.utils.httpx_client import get_httpx_client
from projects.mind.advisor.repositories import mdb_api
from projects.mind.advisor.task_data import AdviserOutput, AdvisorInput
from projects.mind.advisor.task_mdb_models.advisor_run import AdvisorRunDoc
from projects.mind.advisor.task_schemas.advisor_input import AdvisorInputCreate
from projects.mind.advisor.task_schemas.advisor_run import AdvisorRunCreate

ADVISOR_API_DOMAIN = "https://advisor-dev.extour-inc.com/advisor/v1/advise"
# 类型与接口路径的映射关系，新增类型只需加键值对即可
ADVISOR_API_PATH_MAP = {
    "comfort": f"{ADVISOR_API_DOMAIN}/comfort",
    "emotion": f"{ADVISOR_API_DOMAIN}/emotion",
    "comfort_quick": f"{ADVISOR_API_DOMAIN}/comfort/quick",
    "emotion_quick": f"{ADVISOR_API_DOMAIN}/emotion/quick"
}

# 默认接口地址
DEFAULT_API_URL = ADVISOR_API_PATH_MAP["comfort"]


async def advisor_run(advise_type: str, advise_input: AdvisorInputCreate) -> Optional[AdvisorRunDoc]:
    # 请求URL
    request_url = ADVISOR_API_PATH_MAP.get(advise_type, DEFAULT_API_URL)
    doc: Optional[AdvisorRunDoc] = None

    try:
        start_time = time.time()
        response = await get_httpx_client().post(
            url=request_url,
            json=advise_input.model_dump(exclude_none=True),
        )
        end_time = time.time()
        response.raise_for_status()

        logger.info(
            f"advisor接口请求成功 | url={request_url} | status_code={response.status_code}"
        )

        # 解析响应数据
        advisor_run_create = AdvisorRunCreate(
            advise_type=advise_type,
            input=advise_input,
            output=AdviserOutput(**response.json()),
            creator=advise_input.creator,
            total_time=round(end_time - start_time, 2),
            brief=advise_input.brief
        )

        # 数据入库
        doc = await mdb_api.create(AdvisorRunDoc, advisor_run_create)
        logger.info(f"advisor run 数据入库成功，doc_id={doc.id}")

    except Exception as e:
        logger.error(
            f"advisor_run方法执行异常 | url={request_url} | params={advise_input.model_dump(exclude_none=True)} "
            f"| error_msg={str(e)}", exc_info=True
        )

    return doc




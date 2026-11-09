import json
from typing import Dict, List, Optional
from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionMessage
from openai.types.chat import ChatCompletionMessageParam
from openai.types.chat import ChatCompletionSystemMessageParam
from openai.types.chat import ChatCompletionUserMessageParam
from pydantic import BaseModel, Field
import aiohttp
import asyncio
import base64
import hashlib
import hmac
import logging
import random
import time

logger = logging.getLogger(__name__)

from nanoai.model.llm import RunResult

# 全局共享的 aiohttp ClientSession（单例模式，支持连接池复用）
_volcengine_session: Optional[aiohttp.ClientSession] = None


def get_volcengine_session() -> aiohttp.ClientSession:
    """获取全局共享的火山引擎 API 会话（单例模式，支持连接池复用）"""
    global _volcengine_session
    if _volcengine_session is None or _volcengine_session.closed:
        _volcengine_session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(
                limit=100,  # 总连接数限制
                limit_per_host=50,  # 每个主机的连接数限制
            ),
            timeout=aiohttp.ClientTimeout(total=180, connect=10)  # 超时时间设置
        )
    return _volcengine_session


async def close_volcengine_session():
    """关闭全局火山引擎 API 会话（用于程序退出时清理资源）"""
    global _volcengine_session
    if _volcengine_session and not _volcengine_session.closed:
        await _volcengine_session.close()
        logger.info("Volcengine API session closed")
    _volcengine_session = None

def _prepare_volcengine_querystr(chat_id: str = "121212", vehicle_id: str = "121212", longitude: Optional[float] = None, latitude: Optional[float] = None) -> str:
    """准备火山引擎查询参数字符串"""
    query_params = {
        "vehicle_id": vehicle_id,
        "_nonce": random.randint(1000, 9999),
        "_timestamp": int(time.time()),
        "channel": "extour-pro",
        "app_id": "99431",
        "chat_id": chat_id,
    }
    # 只有当 longitude 和 latitude 不为 None 时才添加到查询参数中
    if longitude is not None:
        query_params["longitude"] = longitude
    if latitude is not None:
        query_params["latitude"] = latitude
    querystr = "&".join([f"{k}={v}" for k, v in sorted(query_params.items())])
    return querystr


def _prepare_volcengine_headers(x_signature: str) -> Dict[str, str]:
    """准备火山引擎 HTTP 请求头"""
    headers = {
        "X-Use-PPE": "1",
        "X-Tt-Env": "ppe_extour_pro_test",
        "Content-Type": "application/json",
        "X-Signature": x_signature,
    }
    return headers


def _generate_volcengine_signature(method: str, querystr: str, body: Optional[str], sk: str) -> str:
    """生成火山引擎请求签名"""
    # 对查询参数按字典序排序
    a = querystr.split("&")
    a.sort()
    sortedquerystr = "&".join(a)

    # 构建待签名字符串
    strtosign = method + "\n" + sortedquerystr + "\n"
    if body is not None and len(body) > 0:
        m = hashlib.md5()
        m.update(body.encode("utf8"))
        strtosign += m.hexdigest() + "\n"

    # 计算HMAC-SHA256签名
    h = hmac.new(sk.encode("utf8"), strtosign.encode("utf8"), hashlib.sha256).digest()
    signature = base64.b64encode(h).decode()
    logger.debug("Generated signature successfully")
    return signature


DEFAULT_SYS_PROMPT = "你是一个车联网领域意图分类的助手，请根据用户输入的内容，返回意图的类别。"


async def llm(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str = DEFAULT_SYS_PROMPT,
    client: AsyncOpenAI | None = None,
    model: str | None = None,
    **kwargs,
) -> RunResult[str]:
    """异步调用 LLM"""

    if client is None:
        raise ValueError("client 不能为 None")

    messages = _compose_messages(input, messages_or_sys_prompt)
    response = await client.chat.completions.create(
        model=model, messages=messages, **kwargs
    )
    response_msg: ChatCompletionMessage = response.choices[0].message
    if response_msg.content is None:
        raise RuntimeError("got empty response.content")

    output = response_msg.content
    
    messages.append({
        "role": "assistant",
        "content": response_msg.content,
    })

    return RunResult(output=output, response=response_msg, messages=messages)


def _compose_messages(
    input: str,
    messages_or_sys_prompt: list[ChatCompletionMessageParam] | str,
) -> list[ChatCompletionMessageParam]:
    """将输入和消息历史合并为 OpenAI API 的 messages 参数"""

    assert isinstance(input, str), f"input must be str, but got {type(input)}"
    assert isinstance(messages_or_sys_prompt, (str, list)), f"messages_or_sys_prompt must be str or list, but got {type(messages_or_sys_prompt)}"

    if isinstance(messages_or_sys_prompt, str):
        messages: list[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam({"role": "system", "content": messages_or_sys_prompt})
        ]
    else:
        messages: list[ChatCompletionMessageParam] = messages_or_sys_prompt

    # 创建用户消息内容
    messages.append(ChatCompletionUserMessageParam(role="user", content=input))
    
    return messages


class HistoryItem(BaseModel):
    """历史对话记录"""
    q: str = Field(..., description="用户query")
    a: Optional[str] = Field(None, description="大模型或者插件的回答")


class CarInfo(BaseModel):
    """车辆信息"""
    class Config:
        extra = "allow"  # 允许额外字段，如 mainEngine, vehicleId 等
    
    # 基本信息
    vehicle_name: Optional[str] = Field(None, description="车辆市售名称")
    sound_zone: Optional[str] = Field(None, description="音区，即说话人当前位置")

    # 娱乐信息
    song: Optional[str] = Field(None, description="正在播放的歌名")
    singer: Optional[str] = Field(None, description="正在播放的音乐的歌手")
    video_name: Optional[str] = Field(None, description="视频名称（电影、电视剧、综艺等视频）")
    video_episodes: Optional[int] = Field(None, description="视频集数")
    audio_name: Optional[str] = Field(None, description="音频名称（音乐、相声、有声读物等音频）")
    audio_producer: Optional[str] = Field(None, description="音频制作人")

    # 位置信息
    current_location: Optional[str] = Field(None, description="用户当前位置")
    target_location: Optional[str] = Field(None, description="用户询问的地点，正式项目不支持")
    home_location: Optional[str] = Field(None, description="用户家的位置")
    company_location: Optional[str] = Field(None, description="用户公司的位置")

    # 导航信息
    nav_dest_name: Optional[str] = Field(None, description="导航目的地名字")
    nav_dest_address: Optional[str] = Field(None, description="导航目的地地址")
    nav_waypoint: Optional[str] = Field(None, description="导航途经点")
    nav_remain_distance: Optional[str] = Field(None, description="导航剩余距离")
    nav_remain_cost: Optional[str] = Field(None, description="导航剩余时长")
    nav_road_congestion: Optional[str] = Field(None, description="道路拥堵情况")

    # 车辆状态
    battery: Optional[int] = Field(None, ge=0, le=100, description="电量百分比")
    tts_language: Optional[str] = Field(None, description="TTS当前播报语言")

    # 日程信息
    next_event_type: Optional[str] = Field(None, description="下一个日程类型")
    next_event_title: Optional[str] = Field(None, description="下一个日程标题")

    car_heading: Optional[int] = Field(None, ge=0, le=360, description="车头朝向，0-360，单位：度数")


class IntentData(BaseModel):
    """意图数据"""
    message: Optional[str] = Field(None, description="消息")
    domain: Optional[str] = Field(None, description="领域")
    intent_type: Optional[str] = Field(None, description="意图类型")
    input: Optional[str] = Field(None, description="输入信息")
    slot_data: Optional[str] = Field(None, description="槽位数据")
    origin_intent_type: Optional[str] = Field(None, description="原始意图类型")
    next_process: Optional[str] = Field(None, description="下一步处理")


class DebugInfo(BaseModel):
    """调试信息"""
    pass


class VolcengineIntentResult(BaseModel):
    """火山引擎意图识别结果"""
    intent: Optional[IntentData] = Field(None, description="意图数据")
    question_id: Optional[str] = Field(None, description="问题ID")
    reject: bool = Field(False, description="是否拒识")
    debug_info: Optional[DebugInfo] = Field(None, description="调试信息")
    byte_intent_type: Optional[str] = Field(None, description="火山API返回的原始 intent_type，用于覆盖前保留")


async def volcengine_intent(
    query: str,
    history: Optional[list[HistoryItem]] = None,
    chat_id: str = "121212",
    url: str = "https://api-vehicle.volcengine.com/dpfm/v1/plugin/do/prepare",
    ak: str = "extourProgxg75g0lfzvlgrc6mvg4ceh",
    sk: str = "pgsff17eh892wall893ky7lttz3boze8",
    **kwargs,
) -> VolcengineIntentResult:
    """调用火山引擎插件准备 API (plugin/do/prepare)"""
    # 从 kwargs 中提取用于 query string 的参数
    vehicle_id = kwargs.get("vehicle_id") or "121212"
    longitude = kwargs.get("longitude")
    latitude = kwargs.get("latitude")
    
    # 直接构建请求体字典，过滤掉 None 值
    body_dict = {"query": query, "chat_id": chat_id}
    
    if history:
        body_dict["history"] = [{"q": item.q, "a": item.a or ""} for item in history]
    
    # 添加其他非 None 的参数（包括 vehicle_id, vehicle_name, longitude, latitude 等）
    for key, value in kwargs.items():
        if value is None:
            continue
        if isinstance(value, BaseModel):
            body_dict[key] = value.model_dump(exclude_none=True)
        else:
            body_dict[key] = value
    
    body_json = json.dumps(body_dict)  # 不使用 ensure_ascii=False，保持与签名计算一致
    body_json_display = json.dumps(body_dict, ensure_ascii=False)  # 用于显示的版本
    
    querystr = _prepare_volcengine_querystr(chat_id=chat_id, vehicle_id=vehicle_id, longitude=longitude, latitude=latitude)
    signature = _generate_volcengine_signature(
        method="POST", 
        querystr=querystr, 
        body=body_json,  # 签名计算使用默认编码
        sk=sk
    )
    headers = _prepare_volcengine_headers(f"{ak}:{signature}")
    
    # 调试日志（可根据需要开启/关闭）
    logger.debug(f"Request URL: {url}?{querystr}")
    logger.debug(f"Request Headers: {headers}")
    logger.debug(f"Request Body: {body_json_display}")
    
    # 使用全局共享的异步 HTTP 客户端会话（单例模式，支持连接池复用）
    try:
        session = get_volcengine_session()
        async with session.post(
            f"{url}?{querystr}",
            headers=headers,
            json=body_dict
        ) as response:
            logger.debug(f"Response Status: {response.status}")
            
            # 检查 HTTP 状态码
            response.raise_for_status()
            
            # 解析响应结构
            response_data = await response.json()
            logger.debug(f"Response Body: {json.dumps(response_data, ensure_ascii=False)}")
            
            # 检查API是否返回错误（errno字段存在且不为0）
            errno = response_data.get('errno', 0)
            if errno != 0:
                error_msg = response_data.get('msg', '未知错误')
                logger.warning(f"Volcengine API 返回错误: errno={errno}, msg={error_msg}, query={query[:50]}")
                # API返回错误，应该视为拒识
                return VolcengineIntentResult(
                    reject=True,
                    debug_info=DebugInfo(),
                )
            
            data = response_data.get('data', {})
            
            # 检查是否被拒识
            reject = data.get('reject', False)
            
            if reject:
                # 拒识情况：只返回reject=True
                return VolcengineIntentResult(
                    reject=True,
                    debug_info=DebugInfo(**data.get('debug_info', {})) if data.get('debug_info') else None
                )
            else:
                # 未拒识情况：/dpfm/v1/plugin/do/prepare 接口的 intent 数据在 data.intent 层级下
                intent_data = data.get('intent', {})
                api_intent_type = intent_data.get('intent_type')
                
                # 如果API返回了reject=False但intent_type为None，记录警告
                if not api_intent_type:
                    logger.warning(
                        f"API返回reject=False但intent_type为None: query={query[:50]}, "
                        f"response_data={json.dumps(response_data, ensure_ascii=False)[:200]}"
                    )
                
                return VolcengineIntentResult(
                    intent=IntentData(
                        message=intent_data.get('message'),
                        domain=intent_data.get('domain'),
                        intent_type=api_intent_type,
                        input=intent_data.get('input'),
                        slot_data=intent_data.get('slot_data'),
                        origin_intent_type=intent_data.get('origin_intent_type'),
                        next_process=intent_data.get('next_process')
                    ),
                    question_id=data.get('question_id'),
                    reject=False,
                    debug_info=DebugInfo(**data.get('debug_info', {})) if data.get('debug_info') else None,
                    byte_intent_type=api_intent_type,
                )
    except asyncio.TimeoutError as e:
        logger.error(f"Volcengine API 超时: query={query[:50]}, error={e}")
        # 超时情况：返回reject=True
        return VolcengineIntentResult(
            reject=True,
            debug_info=DebugInfo(),
        )
    except aiohttp.ClientError as e:
        logger.error(f"Volcengine API 网络错误: query={query[:50]}, error={e}")
        # 网络错误：返回reject=True
        return VolcengineIntentResult(
            reject=True,
            debug_info=DebugInfo(),
        )
    except Exception as e:
        logger.error(f"Volcengine API 异常: query={query[:50]}, error={type(e).__name__}: {e}")
        # 其他异常：返回reject=True
        return VolcengineIntentResult(
            reject=True,
            debug_info=DebugInfo(),
        )

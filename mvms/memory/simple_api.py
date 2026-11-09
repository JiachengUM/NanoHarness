import os
import json
import logging
from typing import List, Optional, Dict, Any
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

# 直接使用绝对导入，避免相对导入问题
import sys as _sys
import os as _os
_CUR_DIR = _os.path.dirname(_os.path.abspath(__file__))
if _CUR_DIR not in _sys.path:
    _sys.path.insert(0, _CUR_DIR)

# 添加上级目录到路径，以便导入 nanoai 模块
_PARENT_DIR = _os.path.dirname(_CUR_DIR)
if _PARENT_DIR not in _sys.path:
    _sys.path.insert(0, _PARENT_DIR)

# 简化版：不使用 MemoryChatWorker，直接测试基础功能
from core_memory import CoreMemory, MemoryBlock
from user import UserProfile as MVMSUserProfile


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# ============================
# 本地文件存储
# ============================
DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
WORKERS_FILE = os.path.join(DATA_DIR, "workers.json")
CONVERSATIONS_FILE = os.path.join(DATA_DIR, "conversations.json")

os.makedirs(DATA_DIR, exist_ok=True)

class LocalStorage:
    def __init__(self):
        self.workers: Dict[str, Dict] = self._load_workers()
        self.conversations: List[Dict] = self._load_conversations()
    
    def _load_workers(self) -> Dict[str, Dict]:
        try:
            if os.path.exists(WORKERS_FILE):
                with open(WORKERS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logging.warning(f"Failed to load workers: {e}")
        return {}
    
    def _save_workers(self):
        try:
            with open(WORKERS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.workers, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"Failed to save workers: {e}")
    
    def _load_conversations(self) -> List[Dict]:
        try:
            if os.path.exists(CONVERSATIONS_FILE):
                with open(CONVERSATIONS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
        except Exception as e:
            logging.warning(f"Failed to load conversations: {e}")
        return []
    
    def _save_conversations(self):
        try:
            with open(CONVERSATIONS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.conversations, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"Failed to save conversations: {e}")
    
    def save_worker_state(self, worker_id: str, state: Dict):
        self.workers[worker_id] = {
            "state": state,
            "updated_at": datetime.now().isoformat()
        }
        self._save_workers()
    
    def get_worker_state(self, worker_id: str) -> Optional[Dict]:
        return self.workers.get(worker_id, {}).get("state")
    
    def delete_worker(self, worker_id: str) -> bool:
        if worker_id in self.workers:
            del self.workers[worker_id]
            self._save_workers()
            return True
        return False
    
    def list_workers(self) -> List[Dict]:
        result = []
        for worker_id, data in self.workers.items():
            result.append({
                "worker_id": worker_id,
                "updated_at": data.get("updated_at"),
                "memory_blocks": len(data.get("state", {}).get("core_memory", {}).get("blocks", []))
            })
        return result
    
    def save_conversation(self, worker_id: str, user_input: str, assistant_response: str, memory_summary: str):
        conversation = {
            "worker_id": worker_id,
            "user_input": user_input,
            "assistant_response": assistant_response,
            "memory_summary": memory_summary,
            "timestamp": datetime.now().isoformat()
        }
        self.conversations.append(conversation)
        self._save_conversations()
    
    def get_conversations(self, worker_id: Optional[str] = None, limit: int = 100) -> List[Dict]:
        conversations = self.conversations
        if worker_id:
            conversations = [c for c in conversations if c.get("worker_id") == worker_id]
        return conversations[-limit:]


# ============================
# Pydantic 模型
# ============================
class MemoryWorkerCreate(BaseModel):
    worker_id: str = Field(..., description="Memory Worker 唯一ID")
    description: str = Field("智能助手", description="Worker 描述")


class ChatRequest(BaseModel):
    worker_id: str = Field(..., description="Worker ID")
    user_input: str = Field(..., description="用户输入")


class ChatResponse(BaseModel):
    worker_id: str
    user_input: str
    assistant_response: str
    memory_summary: str
    memory_blocks: Dict[str, str]
    processing_time: float


class MemoryWorkerInfo(BaseModel):
    worker_id: str
    description: str
    memory_blocks: List[Dict]
    conversation_count: int
    created_at: str
    updated_at: str


class ConversationRecord(BaseModel):
    worker_id: str
    user_input: str
    assistant_response: str
    memory_summary: str
    timestamp: str


# ============================
# 应用实例与全局对象
# ============================
app = FastAPI(
    title="NanoAI Memory Chat Worker API",
    description="测试 MemoryChatWorker 性能的本地存储 API",
    version="1.0.0",
)

storage = LocalStorage()
active_workers: Dict[str, CoreMemory] = {}


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "storage": "local_files",
        "active_workers": len(active_workers),
        "total_workers": len(storage.workers),
        "total_conversations": len(storage.conversations)
    }


@app.post("/workers", response_model=Dict[str, str])
def create_worker(req: MemoryWorkerCreate):
    """创建简化的记忆 Worker"""
    try:
        # 检查是否已经存在活跃的 worker
        if req.worker_id in active_workers:
            return {"message": f"Worker {req.worker_id} already active"}
        
        # 创建简化的 CoreMemory
        core_memory = CoreMemory(blocks=[
            MemoryBlock(
                label="persona", 
                value=req.description,
                description="AI助手的角色定位"
            ),
            MemoryBlock(
                label="user_facts", 
                value="",
                description="用户基础信息"
            ),
            MemoryBlock(
                label="preferences", 
                value="",
                description="用户偏好"
            ),
            MemoryBlock(
                label="conversation_context", 
                value="",
                description="对话上下文"
            )
        ])
        
        # 尝试从存储加载状态
        saved_state = storage.get_worker_state(req.worker_id)
        if saved_state and "core_memory" in saved_state:
            try:
                core_memory = CoreMemory.model_validate(saved_state["core_memory"])
                logging.info(f"Loaded worker {req.worker_id} from storage")
            except Exception as e:
                logging.warning(f"Failed to load saved state: {e}")
        else:
            logging.info(f"Created new worker {req.worker_id}")
        
        active_workers[req.worker_id] = core_memory
        
        # 保存初始状态
        storage.save_worker_state(req.worker_id, {
            "core_memory": core_memory.model_dump(),
            "description": req.description,
            "created_at": datetime.now().isoformat()
        })
        
        return {"message": f"Worker {req.worker_id} created/loaded successfully"}
        
    except Exception as e:
        logging.exception("create_worker failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workers", response_model=List[Dict])
def list_workers():
    """列出所有 Workers"""
    return storage.list_workers()


@app.get("/workers/{worker_id}", response_model=MemoryWorkerInfo)
def get_worker(worker_id: str):
    """获取 Worker 详细信息"""
    try:
        core_memory = active_workers.get(worker_id)
        worker_data = storage.workers.get(worker_id, {})
        
        if not core_memory and not worker_data:
            raise HTTPException(status_code=404, detail="Worker not found")
        
        # 如果没有活跃的 worker，从存储加载
        if not core_memory:
            saved_state = storage.get_worker_state(worker_id)
            if saved_state and "core_memory" in saved_state:
                core_memory = CoreMemory.model_validate(saved_state["core_memory"])
            else:
                raise HTTPException(status_code=404, detail="Worker not found")
        
        # 获取记忆块信息
        memory_blocks = []
        for block in core_memory.blocks:
            memory_blocks.append({
                "label": block.label,
                "value": block.value,
                "read_only": block.read_only,
                "description": block.description
            })
        
        # 获取对话数量
        conversations = storage.get_conversations(worker_id)
        conversation_count = len(conversations)
        
        return MemoryWorkerInfo(
            worker_id=worker_id,
            description=worker_data.get("description", "未知"),
            memory_blocks=memory_blocks,
            conversation_count=conversation_count,
            created_at=worker_data.get("created_at", "unknown"),
            updated_at=worker_data.get("updated_at", "unknown")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("get_worker failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/chat", response_model=ChatResponse)
def chat_with_worker(req: ChatRequest):
    """与简化 Worker 对话"""
    import time
    
    try:
        core_memory = active_workers.get(req.worker_id)
        if not core_memory:
            raise HTTPException(status_code=404, detail=f"Worker {req.worker_id} not found. Create it first.")
        
        start_time = time.time()
        
        # 简单的对话逻辑
        # 更新对话上下文
        context_block = core_memory.get_block("conversation_context")
        if context_block:
            current_context = context_block.value
            new_context = f"{current_context}\n用户: {req.user_input}"
            if len(new_context) > 1000:  # 限制长度
                new_context = new_context[-1000:]
            core_memory.update_block_value("conversation_context", new_context)
        
        # 简单的响应生成（可以集成真实的 LLM）
        assistant_response = f"收到您的消息：{req.user_input}。我会记住这个信息。"
        
        # 简单的记忆提取（关键词匹配）
        if any(keyword in req.user_input.lower() for keyword in ["我叫", "我是", "名字", "姓名"]):
            user_facts_block = core_memory.get_block("user_facts")
            if user_facts_block:
                current_facts = user_facts_block.value
                new_facts = f"{current_facts}\n{req.user_input}".strip()
                core_memory.update_block_value("user_facts", new_facts)
        
        if any(keyword in req.user_input.lower() for keyword in ["喜欢", "爱好", "偏好", "爱"]):
            preferences_block = core_memory.get_block("preferences")
            if preferences_block:
                current_prefs = preferences_block.value
                new_prefs = f"{current_prefs}\n{req.user_input}".strip()
                core_memory.update_block_value("preferences", new_prefs)
        
        processing_time = time.time() - start_time
        
        # 获取记忆摘要
        memory_summary = core_memory.compile_to_prompt()
        
        # 获取记忆块状态
        memory_blocks = {}
        for block in core_memory.blocks:
            memory_blocks[block.label] = block.value
        
        # 保存 worker 状态
        storage.save_worker_state(req.worker_id, {
            "core_memory": core_memory.model_dump(),
            "updated_at": datetime.now().isoformat()
        })
        
        # 保存对话记录
        storage.save_conversation(
            req.worker_id,
            req.user_input,
            assistant_response,
            memory_summary
        )
        
        return ChatResponse(
            worker_id=req.worker_id,
            user_input=req.user_input,
            assistant_response=assistant_response,
            memory_summary=memory_summary,
            memory_blocks=memory_blocks,
            processing_time=processing_time
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("chat_with_worker failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.delete("/workers/{worker_id}")
def delete_worker(worker_id: str):
    """删除 Worker"""
    try:
        # 从活跃列表移除
        if worker_id in active_workers:
            del active_workers[worker_id]
        
        # 从存储删除
        success = storage.delete_worker(worker_id)
        if not success:
            raise HTTPException(status_code=404, detail="Worker not found")
        
        return {"message": f"Worker {worker_id} deleted successfully"}
        
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("delete_worker failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/conversations", response_model=List[ConversationRecord])
def get_conversations(worker_id: Optional[str] = None, limit: int = 100):
    """获取对话历史"""
    try:
        conversations = storage.get_conversations(worker_id, limit)
        return [ConversationRecord(**conv) for conv in conversations]
    except Exception as e:
        logging.exception("get_conversations failed")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/workers/{worker_id}/memory")
def get_worker_memory(worker_id: str):
    """获取 Worker 的记忆状态"""
    try:
        core_memory = active_workers.get(worker_id)
        if not core_memory:
            # 尝试从存储加载
            saved_state = storage.get_worker_state(worker_id)
            if not saved_state or "core_memory" not in saved_state:
                raise HTTPException(status_code=404, detail="Worker not found")
            
            core_memory = CoreMemory.model_validate(saved_state["core_memory"])
        
        memory_summary = core_memory.compile_to_prompt()
        
        memory_blocks = {}
        for block in core_memory.blocks:
            memory_blocks[block.label] = {
                "value": block.value,
                "read_only": block.read_only,
                "description": block.description
            }
        
        # 获取对话数量
        conversations = storage.get_conversations(worker_id)
        
        return {
            "worker_id": worker_id,
            "memory_summary": memory_summary,
            "memory_blocks": memory_blocks,
            "conversation_count": len(conversations)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logging.exception("get_worker_memory failed")
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    PORT = int(os.environ.get("PORT", "8899"))
    uvicorn.run(app=app, host="0.0.0.0", port=PORT)

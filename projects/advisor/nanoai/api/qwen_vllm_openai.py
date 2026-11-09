import os
import socket
import sys
import threading

VLLM_ZMQ_PORT_BASE = 15000
_vlm_lock = threading.Lock()
_vlm_port_counter = VLLM_ZMQ_PORT_BASE
_vlm_used_ports = set()

def get_next_zmq_port():
    global _vlm_port_counter
    with _vlm_lock:
        for _ in range(1000):
            port = _vlm_port_counter
            _vlm_port_counter += 1
            if _vlm_port_counter > 65000:
                _vlm_port_counter = VLLM_ZMQ_PORT_BASE
            if port not in _vlm_used_ports:
                try:
                    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    s.settimeout(1)
                    s.connect(('127.0.0.1', port))
                    s.close()
                except (ConnectionRefusedError, TimeoutError, OSError):
                    _vlm_used_ports.add(port)
                    return port
                finally:
                    s.close()
        raise RuntimeError("无法找到可用的ZMQ端口")

def release_zmq_port(port):
    with _vlm_lock:
        _vlm_used_ports.discard(port)

def is_port_available(port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect(('127.0.0.1', port))
        s.close()
        return False
    except (ConnectionRefusedError, TimeoutError):
        return True
    except OSError:
        return False

# 修复XPU设备检测问题：在导入vLLM前设置环境变量
os.environ["VLLM_DEVICE"] = "xpu"
os.environ["VLLM_PLATFORM"] = "intel"

# 修复Windows ZMQ问题：强制使用TCP而非IPC
if sys.platform == 'win32':
    os.environ["VLLM_WORKER_MULTIPROC_METHOD"] = "spawn"
    os.environ["VLLM_IPC_METHOD"] = "tcp"

    # 补丁 multiprocessing.spawn 以在子进程中应用相同的修复
    import multiprocessing.spawn
    original_spawn_main = multiprocessing.spawn.spawn_main

    def patched_spawn_main():
        # 在子进程中应用相同的修复
        if sys.platform == 'win32':
            os.environ["VLLM_WORKER_MULTIPROC_METHOD"] = "spawn"
            os.environ["VLLM_IPC_METHOD"] = "tcp"

            import vllm.utils.network_utils as network_utils
            if hasattr(network_utils, 'make_zmq_socket'):
                original_make_zmq_socket = network_utils.make_zmq_socket

                _ipc_to_tcp_port_cache = {}

                def get_tcp_port_for_ipc(ipc_path):
                    import hashlib
                    path_hash = hashlib.md5(ipc_path.encode()).hexdigest()[:8]
                    cache_key = path_hash
                    if cache_key not in _ipc_to_tcp_port_cache:
                        port_val = int(path_hash[:4], 16) % 10000
                        tcp_port = 10000 + port_val
                        _ipc_to_tcp_port_cache[cache_key] = tcp_port
                    return _ipc_to_tcp_port_cache[cache_key]

                def patched_make_zmq_socket(ctx, path, socket_type, bind=False, identity=None, **kwargs):
                    import zmq
                    if path.startswith('ipc://'):
                        tcp_port = get_tcp_port_for_ipc(path)
                        tcp_path = f'tcp://127.0.0.1:{tcp_port}'
                        path = tcp_path
                    socket = ctx.socket(socket_type)
                    if identity is not None:
                        socket.setsockopt(zmq.IDENTITY, identity)
                    for key, value in kwargs.items():
                        if hasattr(socket, key):
                            try:
                                if isinstance(value, tuple):
                                    socket.setsockopt(getattr(zmq, key.upper(), None), value)
                                else:
                                    socket.setsockopt(getattr(zmq, key.upper(), None), value)
                            except Exception:
                                pass
                    if bind:
                        socket.bind(path)
                    else:
                        socket.connect(path)
                    return socket

                network_utils.make_zmq_socket = patched_make_zmq_socket

        original_spawn_main()

    multiprocessing.spawn.spawn_main = patched_spawn_main

    import vllm.utils.network_utils as network_utils
    original_make_zmq_socket = network_utils.make_zmq_socket
    original_split_zmq_path = getattr(network_utils, 'split_zmq_path', None)

    _ipc_to_tcp_port_cache = {}

    def get_tcp_port_for_ipc(ipc_path):
        import hashlib
        path_hash = hashlib.md5(ipc_path.encode()).hexdigest()[:8]
        cache_key = path_hash
        if cache_key not in _ipc_to_tcp_port_cache:
            tcp_port = get_next_zmq_port()
            _ipc_to_tcp_port_cache[cache_key] = tcp_port
        return _ipc_to_tcp_port_cache[cache_key]

    def patched_make_zmq_socket(ctx, path, socket_type, bind=False, identity=None, **kwargs):
        import zmq
        if path.startswith('ipc://'):
            tcp_port = get_tcp_port_for_ipc(path)
            tcp_path = f'tcp://127.0.0.1:{tcp_port}'
            print(f"已将IPC路径 {path} 转换为TCP路径 {tcp_path}")
            path = tcp_path
        socket = ctx.socket(socket_type)
        if identity is not None:
            socket.setsockopt(zmq.IDENTITY, identity)
        for key, value in kwargs.items():
            if hasattr(socket, key):
                try:
                    if isinstance(value, tuple):
                        socket.setsockopt(getattr(zmq, key.upper(), None), value)
                    else:
                        socket.setsockopt(getattr(zmq, key.upper(), None), value)
                except Exception:
                    pass
        if bind:
            socket.bind(path)
        else:
            socket.connect(path)
        return socket

    def patched_split_zmq_path(path):
        if path.startswith('ipc://'):
            tcp_port = get_tcp_port_for_ipc(path)
            return 'tcp', '127.0.0.1', str(tcp_port)
        elif path.startswith('tcp://'):
            host_port = path[6:].split(':', 1)
            host = host_port[0]
            port = host_port[1] if len(host_port) > 1 else ''
            return 'tcp', host, port
        return 'tcp', path, ''

    network_utils.make_zmq_socket = patched_make_zmq_socket
    if original_split_zmq_path is not None:
        network_utils.split_zmq_path = patched_split_zmq_path

    try:
        from vllm.v1.engine import utils as engine_utils
        original_get_ipc_path = getattr(engine_utils, 'get_zmq_ipc_path', None)

        def patched_get_zmq_ipc_path():
            tcp_port = get_next_zmq_port()
            tcp_path = f'tcp://127.0.0.1:{tcp_port}'
            return tcp_path

        if original_get_ipc_path is not None:
            engine_utils.get_zmq_ipc_path = patched_get_zmq_ipc_path
    except ImportError:
        pass

    try:
        from vllm.v1.engine.core_client import CoreEngine
        original_core_engine_init = getattr(CoreEngine, '__init__', None)
        if original_core_engine_init is not None:
            def patched_core_engine_init(self, *args, **kwargs):
                from vllm.config import VllmConfig
                vllm_config = kwargs.get('vllm_config')
                if vllm_config is None:
                    for arg in args:
                        if isinstance(arg, VllmConfig):
                            vllm_config = arg
                            break
                if vllm_config and hasattr(vllm_config, 'distributed_config'):
                    tcp_port = get_next_zmq_port()
                    vllm_config.distributed_config.ipc_path = f'tcp://127.0.0.1:{tcp_port}'
                return original_core_engine_init(self, *args, **kwargs)
            CoreEngine.__init__ = patched_core_engine_init
    except ImportError:
        pass

    try:
        import zmq
        original_poll = zmq.Poller.poll
        
        def patched_poll(self, timeout=None):
            if timeout is None:
                timeout = -1
            sockets_to_poll = []
            for sock in self.sockets:
                try:
                    if sock.closed:
                        continue
                    sockets_to_poll.append(sock)
                except Exception:
                    continue
            if not sockets_to_poll:
                import time
                if timeout > 0:
                    time.sleep(timeout / 1000.0)
                return []
            self.sockets = sockets_to_poll
            return original_poll(self, timeout)
        
        zmq.Poller.poll = patched_poll
    except Exception:
        pass

    try:
        from vllm.v1.engine.utils import launch_core_engines
        original_launch = launch_core_engines
        
        def patched_launch(vllm_config, executor_class, log_stats, *args, **kwargs):
            import multiprocessing
            ctx = multiprocessing.get_context('spawn')
            return original_launch(vllm_config, executor_class, log_stats, *args, **kwargs)
        
        import vllm.v1.engine.utils as engine_utils
        if hasattr(engine_utils, 'launch_core_engines'):
            engine_utils.launch_core_engines = patched_launch
    except Exception:
        pass

# 现在导入vLLM模块
from vllm.engine.arg_utils import AsyncEngineArgs
from vllm.engine.async_llm_engine import AsyncLLMEngine
from vllm.entrypoints.openai.serving_chat import OpenAIServingChat
from vllm.entrypoints.openai.serving_completion import OpenAIServingCompletion

engine_args = AsyncEngineArgs(
    model="F:/Download/qwen3-1.7B",
    max_model_len=4096,
)

# 应用XPU设备检测修复补丁
try:
    from vllm.platforms import current_platform
    if not current_platform.device_type:
        current_platform.device_type = 'xpu'
        print(f"已修复设备类型: {current_platform.device_type}")
except Exception as e:
    print(f"修复设备类型时发生警告: {e}")

try:
    from vllm.config.device import DeviceConfig
    original_device_config_init = DeviceConfig.__init__
    def patched_device_config_init(self, device):
        if not device:
            device = 'xpu'
        if isinstance(device, str):
            device = device.lower()
        original_device_config_init(self, device)
    DeviceConfig.__init__ = patched_device_config_init
    print("已应用 DeviceConfig.__init__ 补丁")
except Exception as e:
    print(f"应用DeviceConfig补丁时发生警告: {e}")

try:
    from vllm.engine.arg_utils import EngineArgs
    original_create_engine_config = EngineArgs.create_engine_config
    def patched_create_engine_config(self, usage_context=None):
        from vllm.platforms import current_platform
        if not current_platform.device_type:
            current_platform.device_type = 'xpu'
        config = original_create_engine_config(self, usage_context)
        if hasattr(config, 'distributed_config'):
            if hasattr(config.distributed_config, 'ipc_path'):
                tcp_port = get_next_zmq_port()
                config.distributed_config.ipc_path = f'tcp://127.0.0.1:{tcp_port}'
        return config
    EngineArgs.create_engine_config = patched_create_engine_config
    print("已应用 EngineArgs.create_engine_config 补丁")
except Exception as e:
    print(f"应用EngineArgs补丁时发生警告: {e}")

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import threading

_engine_instance = None
_openai_serving_chat = None
_openai_serving_completion = None
_engine_ready = threading.Event()
_engine_loading = threading.Event()

def init_engine_sync():
    engine = AsyncLLMEngine.from_engine_args(engine_args)
    return engine

def load_engine():
    global _engine_instance, _openai_serving_chat, _openai_serving_completion
    import traceback
    try:
        print("开始加载模型...")
        _engine_loading.set()
        _engine_instance = init_engine_sync()
        _openai_serving_chat = OpenAIServingChat(_engine_instance)
        _openai_serving_completion = OpenAIServingCompletion(_engine_instance)
        print("模型加载完成!")
        _engine_ready.set()
    except Exception as e:
        print(f"模型加载失败: {e}")
        traceback.print_exc()  # 打印详细的异常栈信息
        _engine_ready.clear()
    finally:
        _engine_loading.clear()  # 确保无论成功还是失败，都清除加载状态

_engine_loader_thread = None

def start_engine_loading():
    global _engine_loader_thread
    _engine_loader_thread = threading.Thread(target=load_engine, daemon=True)
    _engine_loader_thread.start()

app = FastAPI()

@app.get("/health")
async def health_check():
    """健康检查端点，返回服务器和模型状态"""
    if _engine_ready.is_set():
        return {"status": "ready", "engine": "loaded", "message": "Model is ready for inference"}
    elif _engine_loading.is_set():
        # 根据HTTP规范，资源正在加载时应该返回503，而不是202
        return JSONResponse(
            {"status": "loading", "message": "Model is still loading, please try again later"},
            status_code=503,
            headers={"Retry-After": "10"}  # 建议客户端10秒后重试
        )
    return JSONResponse(
        {"status": "error", "message": "Model loading failed"},
        status_code=503
    )

@app.get("/v1/models")
async def list_models():
    """列出可用模型端点"""
    if _engine_ready.is_set():
        return await _openai_serving_completion.show_available_models()
    return JSONResponse(
        {"error": {"message": "Model is not ready yet, please wait", "type": "service_unavailable"}},
        status_code=503,
        headers={"Retry-After": "10"}
    )

# 注册OpenAI兼容API路由
@app.post("/v1/chat/completions")
async def create_chat_completion(request: Request):
    """Chat Completion端点"""
    if _engine_ready.is_set() and _openai_serving_chat is not None:
        return await _openai_serving_chat.create_chat_completion(request)
    elif _engine_loading.is_set():
        return JSONResponse(
            {"error": {"message": "Model is still loading, please try again later", "type": "service_unavailable"}},
            status_code=503,
            headers={"Retry-After": "10"}
        )
    else:
        return JSONResponse(
            {"error": {"message": "Model loading failed, please check server logs", "type": "service_unavailable"}},
            status_code=503
        )

@app.post("/v1/completions")
async def create_completion(request: Request):
    """Text Completion端点"""
    if _engine_ready.is_set() and _openai_serving_completion is not None:
        return await _openai_serving_completion.create_completion(request)
    elif _engine_loading.is_set():
        return JSONResponse(
            {"error": {"message": "Model is still loading, please try again later", "type": "service_unavailable"}},
            status_code=503,
            headers={"Retry-After": "10"}
        )
    else:
        return JSONResponse(
            {"error": {"message": "Model loading failed, please check server logs", "type": "service_unavailable"}},
            status_code=503
        )

def run_server():
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="info")
    server = uvicorn.Server(config)
    server.run()

if __name__ == "__main__":
    print("启动引擎加载线程...")
    start_engine_loading()
    print("启动服务器...")
    try:
        run_server()
    except KeyboardInterrupt:
        print("服务器已停止")
    except Exception as e:
        print(f"服务器错误: {e}")
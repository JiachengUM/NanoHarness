"""
车载 / 记忆评测脚本的常量（无业务逻辑）。

与 ``auto_test_and_rl_data_generator`` / ``agent_v1_eval_context`` 共用，
避免 demos 示例代码反向被核心模块 import。
"""


MEMORY_COLLECTION_NAME = "test_prompt"
DEFAULT_MEMORY_USER_ID = "dzy_SGM交付测试员"
DEFAULT_MEMORY_USER_NAME = "窦"
TEST_ASSISTANT_ID = "Jarvis"
TEST_ASSISTANT_NAME = "贾维斯"
MEMORY_TYPES = ["steward_note_book"]
EVENT_MEMORY_TYPES = "event_v1"
MEMORY_LIMIT = 10
EVENT_MEMORY_LIMIT = 10

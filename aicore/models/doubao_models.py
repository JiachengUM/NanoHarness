from enum import StrEnum

from aicore.models.model_profile import ModelProfile, ModelProfileRegistry

# TODO: 基于ModelProfile定义DoubaoModelProfile

class ModelName(StrEnum):
    SEED_EVOLVING = "doubao-seed-evolving"  # 账号暂不支持

    SEED_2_1_PRO_260628 = "doubao-seed-2-1-pro-260628"
    
    SEED_2_1_TURBO_260628 = "doubao-seed-2-1-turbo-260628"  # 很慢，不建议使用

    SEED_2_0_PRO_260215 = "doubao-seed-2-0-pro-260215"
    '''
    https://console.volcengine.com/ark/region:ark+cn-beijing/model/detail?Id=doubao-seed-2-0-pro
    支持隐式缓存，无需额外配置，自动开启缓存命中，适合Agentic等复杂上下文场景。请求内容的公共前缀会被自动缓存，但不保证缓存命中。通常需要累计至少 1024 个 tokens 才会触发缓存命中。对命中缓存的部分，按输入缓存命中刊例价计费。
    为保障输出效果的稳定性，系统将参数固定为 temperature = 1、top_p = 0.95，并忽略 API 请求中对上述参数的传入设置（以系统固定值为准）。
    支持思考程度可调节（reasoning effort）：分为 minimal、low、medium、high 四种模式，其中minimal为不思考
    不支持结构化输出，但支持function call, response API
    '''

    SEED_2_0_MINI_260428 = "doubao-seed-2-0-mini-260428"
    '''
    支持思考程度可调节（reasoning effort）：分为 minimal、low、medium、high 四种模式，其中minimal为不思考
    不支持结构化输出，但支持function call, response API
    '''
    
    SEED_1_8_251228 = "doubao-seed-1-8-251228"
    '''
    https://www.volcengine.com/docs/82379/2123228?lang=zh
    '''
    

    SEED_1_8_PREVIEW  = "ep-20251204163909-nnfgr"
    '''
    1. Agent 与工具调用能力大幅增强，适合企业级自动化任务、适配多种 Agent 类应用
        在 Function Call 与指令遵循上，Seed 1.8 在各档位（low/medium/high）相比 Seed 1.6 均有显著提升
        更强的工具编排与纠错能力：Seed 1.8 对复杂 JSON Schema 的理解、多工具并行调用、执行规划能力提升，并能更好地处理多轮、需要编排多个工具才能完成的复杂任务
        对复杂指令、长文指令等的理解和遵循能力提升：模型能更好地理解和遵循系统指令、用户指令，对于 SOP 约束、工具使用条件、格式要求等能稳定执行。
        复杂流程理解提升：Seed 1.8 能更好地理解和执行场景中包含多个步骤和条件分支的业务流程
    2. Coding 能力显著提升：Seed 1.8 评估中代码能力得分超过 GLM 4.6 和 Kimi-K2，在国内模型中全面领先
    3. 视觉理解基础能力大幅跃升，且具备 GUI Agent 落地能力 
        Seed 1.8 在内容识别、图文匹配、视频问答、OCR 等视觉理解能力上分数领先或者达到海外友商水平。
        Seed 1.8 合入了 UI-Tars 2的能力，对于 Mobile use、Browser use等场景任务下的复杂交互处理有很好的适应性，适合 GUI Agent 的落地。
    4. 输出稳定性明显加强：更稳定地按照要求输出指定的格式（如 JSON、XML 等）。基本解决了 Seed 1.6 1015 版本重复输出、异常 special token 暴露、格式滥用等基础问题，改善了输出稳定性。
    5. 基础 LLM 能力提升：LLM 应用评测分数在本次评测模型中位列第一，领先于 GPT-5 和 Gemini 2.5 pro，在“文本分类”、“参考问答”和“阅读理解”等能力上超越 GPT-5 和 Gemini 2.5 Pro。在教育、复杂流程、组合任务等场景下分数大幅提升。
    '''


    SEED_1_6_251015 = "doubao-seed-1-6-251015"
    SEED_1_6_250615 = "doubao-seed-1-6-250615"
    '''
    https://www.volcengine.com/docs/82379/1593702
    效果: 5, 速度: 4
    全新多模态深度思考模型，同时支持 thinking、non-thinking、auto三种思考模式。其中 non-thinking 模型对比 doubao-1.5-pro-32k-250115 模型大幅提升。
    支持结构化输出，function call, response API
    '''
    
    SEED_1_6_FLASH_250828 = "doubao-seed-1-6-flash-250828"
    SEED_1_6_FLASH_250715 = "doubao-seed-1-6-flash-250715"
    SEED_1_6_FLASH_250615 = "doubao-seed-1-6-flash-250615"
    '''
    https://www.volcengine.com/docs/82379/1593704
    效果: 4, 速度: 5
    有极致推理速度的多模态深度思考模型；同时支持文本和视觉理解。文本理解能力超过上一代 Lite 系列模型，视觉理解比肩友商 Pro 系列模型。
    支持结构化输出，function call, response API
    '''
    
    SEED_1_6_THINKING_250715 = "doubao-seed-1-6-thinking-250715"
    SEED_1_6_THINKING_250615 = "doubao-seed-1-6-thinking-250615"
    '''
    https://www.volcengine.com/docs/82379/1593703
    效果: 5, 速度: 4
    在思考能力上进行了大幅强化， 对比 doubao 1.5 代深度理解模型，在编程、数学、逻辑推理等基础能力上进一步提升， 支持视觉理解。
    支持结构化输出，function call, response API
    '''

    SEED_1_6_VISION_250815 = "doubao-seed-1-6-vision-250815"
    '''
    https://www.volcengine.com/docs/82379/1799865
    效果: 5, 速度: 4
    适用于视频理解、Grounding、GUI Agent等高复杂度的场景，与Doubao-1.5-thinking-vision-pro相比，在教育、图像审核、巡检与安防和AI搜索问答等场景下展现出更强的通用多模态理解和推理能力，支持 256k 上下文窗口，输出长度支持最大 64k tokens。
    支持结构化输出，function call, response API, GUI 任务处理
    '''

    SEED_1_6_UI_TARS_250428 = "doubao-1-5-ui-tars-250428"
    '''
    https://www.volcengine.com/docs/82379/1536429
    效果: 5, 速度: 4
    一款原生面向图形界面交互（GUI）的Agent模型。通过感知、推理和动作执行等类人的能力，与 GUI 进行连续、流程的交互。
与传统模块化框架不同，模型将所有核心能力（感知、推理、基础理解能力），统一集成在视觉大模型（VLM）中，实现无需预定义工作流程或人工规则的端到端任务自动化。
    支持GUI 任务处理。不支持结构化输出，function call, response API。
    '''
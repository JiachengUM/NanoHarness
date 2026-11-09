import json
import pytest
from typing import Final
from pathlib import Path
from enum import StrEnum

from nanoai.task.common_exp import ConceptInstanceGenerator
from nanoai.utils.nl_repr import nl_repr
from nanoai.chat._meta import generate_chat_agent_profile, generate_chat_task, UserProfileConceptGenerator
from nanoai.chat.define import ChatScenario, ChatAgentProfile, RolePlayScenario


TIMEOUT: Final[int] = 30 # 10 is too short
    

@pytest.mark.skip(reason="太慢了。手动测试即可。")
def test_generate_chat_agent_profile(ScenarioClass: type[StrEnum]):
    """测试生成聊天智能体角色描述并存储到JSON文件"""

    print("=== 测试生成聊天智能体角色描述 ===")
    print(f"ScenarioClass: {ScenarioClass.__name__}")

    assert issubclass(ScenarioClass, StrEnum), "ScenarioClass必须是StrEnum的子类"
    
    # 存储所有生成的agent_profile
    agent_profiles = {}
    
    for scenario in ScenarioClass:
        print(f"为如下对话场景生成智能体角色描述:{scenario}")
        task_brief = scenario.value
        assert isinstance(task_brief, str), "ScenarioClass的枚举值必须是字符串"
        try:
            agent_profile = generate_chat_agent_profile(task_brief, timeout=TIMEOUT)
            # 将生成的agent_profile存储到字典中
            agent_profiles[scenario.name] = {
                "scenario": task_brief,
                "agent_profile": agent_profile.model_dump()
            }
            print(f"成功，角色描述如下:\n{nl_repr(agent_profile)}")
        except Exception as e:
            print(f"失败: {e}")
            # 记录失败的情况
            agent_profiles[scenario.name] = {
                "scenario": task_brief,
                "error": str(e)
            }
            continue

    # 保存到JSON文件
    output_file = Path(f"generated_agent_profiles_{ScenarioClass.__name__}.json")
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(agent_profiles, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 所有生成的智能体角色描述已保存到: {output_file}")
        print(f"📊 成功生成: {len([v for v in agent_profiles.values() if 'agent_profile' in v])} 个")
        print(f"❌ 生成失败: {len([v for v in agent_profiles.values() if 'error' in v])} 个")
    except Exception as e:
        print(f"❌ 保存文件失败: {e}")
    
    return agent_profiles


def load_chat_agent_profile_json(file_path: str | Path, scenario_enum_class: type[StrEnum]) -> dict[StrEnum, dict]:
    """从JSON文件加载聊天智能体角色描述
    
    Args:
        file_path: JSON文件路径
        scenario_enum_class: 场景枚举类，用于验证和转换场景名称
    
    Returns:
        包含所有场景智能体配置的字典，格式为：
        {
            ChatScenario枚举: {
                "scenario": "场景描述",
                "agent_profile": ChatAgentProfile对象 或 None,
                "error": "错误信息" 或 None,
                "load_status": "success" | "error" | "missing_profile"
            }
        }
    
    Raises:
        FileNotFoundError: 文件不存在时抛出
        json.JSONDecodeError: JSON格式错误时抛出
        ValueError: 数据格式不符合预期时抛出
    """
    print("\n=== 测试加载聊天智能体角色描述 ===")
    

    file_path = Path(file_path)
    
    # 检查文件是否存在
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")
    
    try:
        # 读取JSON文件
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise json.JSONDecodeError(f"JSON格式错误: {e}", e.doc, e.pos)
    
    # 验证数据格式
    if not isinstance(data, dict):
        raise ValueError(f"JSON文件根节点必须是字典，实际为: {type(data)}")
    
    result = {}
    
    for scenario_name, scenario_data in data.items():
        # 尝试将字符串转换为传入的枚举类
        try:
            scenario_enum = scenario_enum_class[scenario_name]
        except KeyError:
            print(f"⚠️  警告: 未知的场景名称 {scenario_name}，跳过")
            continue
            
        if not isinstance(scenario_data, dict):
            print(f"⚠️  警告: 场景 {scenario_name} 的数据格式错误，跳过")
            result[scenario_enum] = {
                "scenario": None,
                "agent_profile": None,
                "error": f"数据格式错误: 期望dict，实际为{type(scenario_data)}",
                "load_status": "error"
            }
            continue
        
        # 检查必需字段
        if "scenario" not in scenario_data:
            print(f"⚠️  警告: 场景 {scenario_name} 缺少 'scenario' 字段")
            result[scenario_enum] = {
                "scenario": None,
                "agent_profile": None,
                "error": "缺少 'scenario' 字段",
                "load_status": "error"
            }
            continue
        
        scenario_desc = scenario_data["scenario"]
        
        # 处理不同的情况
        if "agent_profile" in scenario_data:
            # 成功生成的情况
            try:
                agent_profile_data = scenario_data["agent_profile"]
                if not isinstance(agent_profile_data, dict):
                    raise ValueError(f"agent_profile必须是字典，实际为{type(agent_profile_data)}")
                
                # 尝试创建ChatAgentProfile对象
                agent_profile = ChatAgentProfile.model_validate(agent_profile_data)
                
                result[scenario_enum] = {
                    "scenario": scenario_desc,
                    "agent_profile": agent_profile,
                    "error": None,
                    "load_status": "success"
                }
                print(f"✅ 成功加载场景 {scenario_name}")
                
            except Exception as e:
                print(f"⚠️  警告: 场景 {scenario_name} 的agent_profile解析失败: {e}")
                result[scenario_enum] = {
                    "scenario": scenario_desc,
                    "agent_profile": None,
                    "error": f"agent_profile解析失败: {e}",
                    "load_status": "error"
                }
        
        elif "error" in scenario_data:
            # 生成失败的情况
            result[scenario_enum] = {
                "scenario": scenario_desc,
                "agent_profile": None,
                "error": scenario_data["error"],
                "load_status": "error"
            }
            print(f"❌ 场景 {scenario_name} 生成失败: {scenario_data['error']}")
        
        else:
            # 数据格式不完整的情况
            print(f"⚠️  警告: 场景 {scenario_name} 数据格式不完整")
            result[scenario_enum] = {
                "scenario": scenario_desc,
                "agent_profile": None,
                "error": "数据格式不完整，缺少agent_profile或error字段",
                "load_status": "missing_profile"
            }
    
    # 统计加载结果
    success_count = len([v for v in result.values() if v["load_status"] == "success"])
    error_count = len([v for v in result.values() if v["load_status"] == "error"])
    missing_count = len([v for v in result.values() if v["load_status"] == "missing_profile"])
    
    print(f"\n📊 加载统计:")
    print(f"   ✅ 成功加载: {success_count} 个")
    print(f"   ❌ 加载失败: {error_count} 个")
    print(f"   ⚠️  数据不完整: {missing_count} 个")
    print(f"   📁 总计: {len(result)} 个场景")
    
    return result


@pytest.mark.skip(reason="太慢了。手动测试即可。")
def test_chat_task_generator():
    """测试生成聊天任务、用户画像和用户实例，并存储到JSON文件"""

    print("\n=== 测试生成聊天任务、用户画像和用户实例 ===")
    
    
    # 存储所有生成的数据
    chat_data = {}
    
    user_profile_generator = UserProfileConceptGenerator(timeout=TIMEOUT)

    for scenario in ChatScenario:
        task_brief = scenario.value
        scenario_name = scenario.name
        
        print(f"为如下对话场景生成任务描述:{scenario}")
        
        # 初始化场景数据
        chat_data[scenario_name] = {
            "scenario": scenario.value,
            "task": None,
            "user_profile": None,
            "user": None,
            "errors": []
        }
        
        # 生成任务描述
        try:
            task = generate_chat_task(task_brief)
            chat_data[scenario_name]["task"] = task.model_dump()
            print(f"成功，任务描述如下:\n{nl_repr(task)}")
        except Exception as e:
            error_msg = f"任务生成失败: {e}"
            print(f"失败: {error_msg}")
            chat_data[scenario_name]["errors"].append(error_msg)
            continue

        # 生成用户画像
        try:
            user_profile = user_profile_generator.execute(task_brief)
            chat_data[scenario_name]["user_profile"] = user_profile.model_dump()
            print(f"\n生成的用户画像:\n{nl_repr(user_profile)}")
        except Exception as e:
            error_msg = f"用户画像生成失败: {e}"
            print(f"\n{error_msg}")
            chat_data[scenario_name]["errors"].append(error_msg)
            continue

        # 生成用户实例
        try:
            user = ConceptInstanceGenerator(user_profile, timeout=TIMEOUT).execute("请随机生成一个用户实例")
            chat_data[scenario_name]["user"] = user.model_dump() if hasattr(user, 'model_dump') else str(user)
            print(f"\n随机生成的用户实例:\n{user}")
        except Exception as e:
            error_msg = f"用户实例生成失败: {e}"
            print(f"\n{error_msg}")
            chat_data[scenario_name]["errors"].append(error_msg)

    # 保存到JSON文件
    output_file = Path("generated_chat_task_data.json")
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(chat_data, f, ensure_ascii=False, indent=2)
        print(f"\n✅ 所有生成的聊天数据已保存到: {output_file}")
        
        # 统计生成结果
        total_scenarios = len(chat_data)
        successful_tasks = len([v for v in chat_data.values() if v["task"] is not None])
        successful_user_profiles = len([v for v in chat_data.values() if v["user_profile"] is not None])
        successful_users = len([v for v in chat_data.values() if v["user"] is not None])
        total_errors = sum(len(v["errors"]) for v in chat_data.values())
        
        print(f"📊 生成统计:")
        print(f"   📁 总场景数: {total_scenarios}")
        print(f"   ✅ 成功生成任务: {successful_tasks} 个")
        print(f"   ✅ 成功生成用户画像: {successful_user_profiles} 个")
        print(f"   ✅ 成功生成用户实例: {successful_users} 个")
        print(f"   ❌ 总错误数: {total_errors} 个")
        
    except Exception as e:
        print(f"❌ 保存文件失败: {e}")
    
    return chat_data



def main():
    #test_generate_chat_agent_profile(ChatScenario)

    #test_generate_chat_agent_profile(RolePlayScenario)
    
    #agent_profiles = load_chat_agent_profile_json(Path("generated_agent_profiles_RolePlayScenario.json"), RolePlayScenario)
    #print(f"agent_profiles: {agent_profiles}")
    
    test_chat_task_generator()
    

RUN_PYTEST = False

if __name__ == "__main__":
    if RUN_PYTEST:
        # 使用 -s 参数禁用输出捕获，这样可以看到print输出
        # 使用 -v 参数显示详细输出
        pytest.main(["-vs", __file__])
    else:
        main()

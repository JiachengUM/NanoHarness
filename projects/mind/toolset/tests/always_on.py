import requests
import time

# 服务器地址
BASE_URL = "http://localhost:8000"


def test_always_on_functionality():
    """测试 always on 功能"""
    print("===== 测试 always on 功能 =====\n")
    
    # 1. 检查初始状态
    print("1. 检查初始状态:")
    response = requests.get(f"{BASE_URL}/asr/always-on/status")
    print(f"   状态: {response.json()['status']}")
    
    # 2. 启动 always on
    print("\n2. 启动 always on:")
    response = requests.post(f"{BASE_URL}/asr/always-on/start")
    print(f"   响应: {response.json()['message']}")
    
    # 3. 检查状态是否为运行中
    print("\n3. 检查状态是否为运行中:")
    response = requests.get(f"{BASE_URL}/asr/always-on/status")
    status = response.json()['status']
    print(f"   状态: {status}")
    assert status == "running", f"期望状态为 'running'，实际为 '{status}'"
    
    # # 4. 提示用户说话,，
    # print("\n4. 请对着麦克风说话（例如：你好，测试一下）:")
    # print("   系统会自动检测语音并进行识别...")
    # print("   等待 10 秒...")
    # time.sleep(10)  # 等待用户说话和系统处理
    #
    # # 5. 获取识别结果
    # print("\n5. 获取识别结果:")
    # response = requests.get(f"{BASE_URL}/asr/always-on/result")
    # result = response.json()
    # if "results" in result:
    #     print(f"   识别结果数量: {len(result['results'])}")
    #     for i, res in enumerate(result['results']):
    #         print(f"   结果 {i+1}: {res['text']}")
    # else:
    #     print(f"   {result['message']}")
    #
    # # 6. 停止 always on
    # print("\n6. 停止 always on:")
    # response = requests.post(f"{BASE_URL}/asr/always-on/stop")
    # print(f"   响应: {response.json()['message']}")
    #
    # # 7. 检查状态是否为已停止
    # print("\n7. 检查状态是否为已停止:")
    # response = requests.get(f"{BASE_URL}/asr/always-on/status")
    # status = response.json()['status']
    # print(f"   状态: {status}")
    # assert status == "stopped", f"期望状态为 'stopped'，实际为 '{status}'"
    #
    # print("\n===== 测试完成 =====")


if __name__ == "__main__":
    try:
        test_always_on_functionality()
    except Exception as e:
        print(f"测试过程中出错: {e}")
        print("请确保 app_mlx.py 服务正在运行 (uvicorn app_mlx:app)")

import pytest
from nanoai.model.config import ModelName, create_client
from openai import OpenAI, AsyncOpenAI
from volcenginesdkarkruntime import Ark, AsyncArk


models_to_test = [
        ModelName.DOUBAO_SEED_1_6_250615,
        ModelName.DOUBAO_SEED_1_6_FLASH_250828,
        ModelName.DOUBAO_SEED_1_6_THINKING_250715,
        ModelName.DOUBAO_SEED_1_6_VISION_250815,
        ModelName.DOUBAO_1_5_UI_TARS_250428,
    ]


class TestCreateClient:
    """测试 create_client 函数"""
    
    def test_create_client_with_openai(self):
        """测试创建 OpenAI 客户端"""
        client, model_name = create_client(ModelName.DOUBAO_SEED_1_6_251015, OpenAI)
        
        assert isinstance(client, OpenAI)
        assert model_name == "doubao-seed-1-6-251015"
    
    def test_create_client_with_async_openai(self):
        """测试创建 AsyncOpenAI 客户端"""
        client, model_name = create_client(ModelName.DOUBAO_SEED_1_6_FLASH_250615, AsyncOpenAI)
        
        assert isinstance(client, AsyncOpenAI)
        assert model_name == "doubao-seed-1-6-flash-250615"
    
    def test_create_client_with_ark(self):
        """测试创建 Ark 客户端"""
        client, model_name = create_client(ModelName.DOUBAO_SEED_1_6_251015, Ark)
        
        assert isinstance(client, Ark)
        assert model_name == "doubao-seed-1-6-251015"
        # Ark 客户端的属性可能不同，只测试基本功能
    
    def test_create_client_with_async_ark(self):
        """测试创建 AsyncArk 客户端"""
        client, model_name = create_client(ModelName.DOUBAO_SEED_1_6_FLASH_250615, AsyncArk)
        
        assert isinstance(client, AsyncArk)
        assert model_name == "doubao-seed-1-6-flash-250615"
        # AsyncArk 客户端的属性可能不同，只测试基本功能

    
    def test_create_client_with_different_models(self):
        """测试不同模型名称"""        
        
        for model in models_to_test:
            client, model_name = create_client(model, OpenAI)
            assert isinstance(client, OpenAI)
            assert model_name == model.value

    
    def test_create_client_caching(self):
        """测试函数缓存功能"""
        # 测试 OpenAI 缓存
        client1, model_name1 = create_client(ModelName.DOUBAO_SEED_1_6_251015, OpenAI)
        client2, model_name2 = create_client(ModelName.DOUBAO_SEED_1_6_251015, OpenAI)
        assert client1 is client2
        assert model_name1 == model_name2
        
        # 测试 Ark 缓存
        client3, model_name3 = create_client(ModelName.DOUBAO_SEED_1_6_251015, Ark)
        client4, model_name4 = create_client(ModelName.DOUBAO_SEED_1_6_251015, Ark)
        assert client3 is client4
        assert model_name3 == model_name4
        
        # 测试 AsyncArk 缓存
        client5, model_name5 = create_client(ModelName.DOUBAO_SEED_1_6_251015, AsyncArk)
        client6, model_name6 = create_client(ModelName.DOUBAO_SEED_1_6_251015, AsyncArk)
        assert client5 is client6
        assert model_name5 == model_name6
    
    def test_create_client_type_safety(self):
        """测试类型安全"""
        # 测试 OpenAI 类型
        client, _ = create_client(ModelName.DOUBAO_SEED_1_6_251015, OpenAI)
        assert isinstance(client, OpenAI)
        assert not isinstance(client, AsyncOpenAI)
        assert not isinstance(client, Ark)
        assert not isinstance(client, AsyncArk)
        
        # 测试 AsyncOpenAI 类型
        client, _ = create_client(ModelName.DOUBAO_SEED_1_6_251015, AsyncOpenAI)
        assert isinstance(client, AsyncOpenAI)
        assert not isinstance(client, OpenAI)
        assert not isinstance(client, Ark)
        assert not isinstance(client, AsyncArk)
        
        # 测试 Ark 类型
        client, _ = create_client(ModelName.DOUBAO_SEED_1_6_251015, Ark)
        assert isinstance(client, Ark)
        assert not isinstance(client, OpenAI)
        assert not isinstance(client, AsyncOpenAI)
        assert not isinstance(client, AsyncArk)
        
        # 测试 AsyncArk 类型
        client, _ = create_client(ModelName.DOUBAO_SEED_1_6_251015, AsyncArk)
        assert isinstance(client, AsyncArk)
        assert not isinstance(client, OpenAI)
        assert not isinstance(client, AsyncOpenAI)
        assert not isinstance(client, Ark)


if __name__ == "__main__":
    pytest.main([__file__])

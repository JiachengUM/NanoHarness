import redis
from redis.connection import ConnectionPool
from typing import Any, Optional, List, Dict, Set, Tuple
from datetime import timedelta

RedisClient = None
class RedisUtil:
    """Redis 工具类，支持常用 Redis 操作，基于连接池优化"""
    _instance: Optional['RedisUtil'] = None
    _pool: Optional[ConnectionPool] = None

    def __new__(cls, *args, **kwargs):
        """单例模式，确保全局只有一个 RedisUtil 实例"""
        if not cls._instance:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        host: str = 'localhost',
        port: int = 6379,
        db: int = 0,
        password: Optional[str] = None,
        decode_responses: bool = True,
        max_connections: int = 10,
        **kwargs
    ):
        """
        初始化 Redis 连接池（仅初始化一次）
        :param host: Redis 主机地址
        :param port: Redis 端口
        :param db: 数据库索引（0-15）
        :param password: Redis 密码（无密码则为 None）
        :param decode_responses: 是否自动解码响应为字符串（默认 True）
        :param max_connections: 连接池最大连接数
        :param kwargs: 其他 Redis 连接参数（如 socket_timeout、ssl 等）
        """
        if not RedisUtil._pool:
            RedisUtil._pool = ConnectionPool(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=decode_responses,
                max_connections=max_connections,
                **kwargs
            )
        self.client = redis.Redis(connection_pool=RedisUtil._pool)

    def ping(self) -> bool:
        """测试 Redis 连接是否正常"""
        try:
            return self.client.ping()
        except Exception as e:
            print(f"Redis 连接失败: {e}")
            return False

    # ------------------------------ 字符串(String)操作 ------------------------------
    def set(
        self,
        key: str,
        value: Any,
        ex: Optional[timedelta | int] = None,
        px: Optional[int] = None,
        nx: bool = False,
        xx: bool = False
    ) -> bool:
        """
        设置字符串键值对
        :param key: 键
        :param value: 值（支持字符串、数字等可序列化类型）
        :param ex: 过期时间（秒）或 timedelta 对象
        :param px: 过期时间（毫秒）
        :param nx: 仅当键不存在时设置（默认 False）
        :param xx: 仅当键存在时设置（默认 False）
        :return: 设置成功返回 True，失败返回 False
        """
        try:
            if isinstance(ex, timedelta):
                ex = int(ex.total_seconds())
            return self.client.set(key, value, ex=ex, px=px, nx=nx, xx=xx)
        except Exception as e:
            print(f"Redis set 失败 (key: {key}): {e}")
            return False

    def get(self, key: str) -> Optional[Any]:
        """
        获取字符串键的值
        :param key: 键
        :return: 存在返回值，不存在返回 None
        """
        try:
            return self.client.get(key)
        except Exception as e:
            print(f"Redis get 失败 (key: {key}): {e}")
            return None

    def delete(self, *keys: str) -> int:
        """
        删除一个或多个键
        :param keys: 要删除的键（可变参数）
        :return: 成功删除的键的数量
        """
        try:
            return self.client.delete(*keys)
        except Exception as e:
            print(f"Redis delete 失败 (keys: {keys}): {e}")
            return 0

    def expire(self, key: str, time: timedelta | int) -> bool:
        """
        设置键的过期时间
        :param key: 键
        :param time: 过期时间（秒）或 timedelta 对象
        :return: 设置成功返回 True，失败返回 False
        """
        try:
            if isinstance(time, timedelta):
                time = int(time.total_seconds())
            return self.client.expire(key, time)
        except Exception as e:
            print(f"Redis expire 失败 (key: {key}): {e}")
            return False

    def ttl(self, key: str) -> int:
        """
        获取键的剩余过期时间（秒）
        :param key: 键
        :return: 剩余时间（-1：永久有效，-2：键不存在）
        """
        try:
            return self.client.ttl(key)
        except Exception as e:
            print(f"Redis ttl 失败 (key: {key}): {e}")
            return -2

    def exists(self, *keys: str) -> int:
        """
        检查一个或多个键是否存在
        :param keys: 要检查的键（可变参数）
        :return: 存在的键的数量
        """
        try:
            return self.client.exists(*keys)
        except Exception as e:
            print(f"Redis exists 失败 (keys: {keys}): {e}")
            return 0

    # ------------------------------ 哈希(Hash)操作 ------------------------------
    def hset(self, name: str, mapping: Optional[Dict] = None, **kwargs) -> int:
        """
        设置哈希表字段值
        :param name: 哈希表名称
        :param mapping: 字段-值字典（与 kwargs 二选一）
        :param kwargs: 字段=值 键值对（如 field1=value1, field2=value2）
        :return: 成功设置的字段数量
        """
        try:
            return self.client.hset(name, mapping=mapping,** kwargs)
        except Exception as e:
            print(f"Redis hset 失败 (name: {name}): {e}")
            return 0

    def hget(self, name: str, key: str) -> Optional[Any]:
        """
        获取哈希表中指定字段的值
        :param name: 哈希表名称
        :param key: 字段名
        :return: 字段值（不存在返回 None）
        """
        try:
            return self.client.hget(name, key)
        except Exception as e:
            print(f"Redis hget 失败 (name: {name}, key: {key}): {e}")
            return None

    def hgetall(self, name: str) -> Dict[str, Any]:
        """
        获取哈希表中所有字段和值
        :param name: 哈希表名称
        :return: 字段-值字典（不存在返回空字典）
        """
        try:
            return self.client.hgetall(name)
        except Exception as e:
            print(f"Redis hgetall 失败 (name: {name}): {e}")
            return {}

    def hdel(self, name: str, *keys: str) -> int:
        """
        删除哈希表中的一个或多个字段
        :param name: 哈希表名称
        :param keys: 要删除的字段（可变参数）
        :return: 成功删除的字段数量
        """
        try:
            return self.client.hdel(name, *keys)
        except Exception as e:
            print(f"Redis hdel 失败 (name: {name}, keys: {keys}): {e}")
            return 0

    def hexists(self, name: str, key: str) -> bool:
        """
        检查哈希表中字段是否存在
        :param name: 哈希表名称
        :param key: 字段名
        :return: 存在返回 True，不存在返回 False
        """
        try:
            return self.client.hexists(name, key)
        except Exception as e:
            print(f"Redis hexists 失败 (name: {name}, key: {key}): {e}")
            return False

    # ------------------------------ 列表(List)操作 ------------------------------
    def lpush(self, name: str, *values: Any) -> int:
        """
        从列表左侧插入一个或多个值
        :param name: 列表名称
        :param values: 要插入的值（可变参数）
        :return: 插入后列表的长度
        """
        try:
            return self.client.lpush(name, *values)
        except Exception as e:
            print(f"Redis lpush 失败 (name: {name}): {e}")
            return 0

    def rpush(self, name: str, *values: Any) -> int:
        """
        从列表右侧插入一个或多个值
        :param name: 列表名称
        :param values: 要插入的值（可变参数）
        :return: 插入后列表的长度
        """
        try:
            return self.client.rpush(name, *values)
        except Exception as e:
            print(f"Redis rpush 失败 (name: {name}): {e}")
            return 0

    def lpop(self, name: str) -> Optional[Any]:
        """
        从列表左侧弹出一个值
        :param name: 列表名称
        :return: 弹出的值（列表为空返回 None）
        """
        try:
            return self.client.lpop(name)
        except Exception as e:
            print(f"Redis lpop 失败 (name: {name}): {e}")
            return None

    def rpop(self, name: str) -> Optional[Any]:
        """
        从列表右侧弹出一个值
        :param name: 列表名称
        :return: 弹出的值（列表为空返回 None）
        """
        try:
            return self.client.rpop(name)
        except Exception as e:
            print(f"Redis rpop 失败 (name: {name}): {e}")
            return None

    def lrange(self, name: str, start: int = 0, end: int = -1) -> List[Any]:
        """
        获取列表指定范围的元素
        :param name: 列表名称
        :param start: 起始索引（0 开始，负数表示倒数）
        :param end: 结束索引（-1 表示最后一个元素）
        :return: 元素列表（不存在返回空列表）
        """
        try:
            return self.client.lrange(name, start, end)
        except Exception as e:
            print(f"Redis lrange 失败 (name: {name}): {e}")
            return []

    def llen(self, name: str) -> int:
        """
        获取列表长度
        :param name: 列表名称
        :return: 列表长度（不存在返回 0）
        """
        try:
            return self.client.llen(name)
        except Exception as e:
            print(f"Redis llen 失败 (name: {name}): {e}")
            return 0

    # ------------------------------ 集合(Set)操作 ------------------------------
    def sadd(self, name: str, *values: Any) -> int:
        """
        向集合中添加一个或多个元素
        :param name: 集合名称
        :param values: 要添加的元素（可变参数）
        :return: 成功添加的元素数量（已存在的元素不计入）
        """
        try:
            return self.client.sadd(name, *values)
        except Exception as e:
            print(f"Redis sadd 失败 (name: {name}): {e}")
            return 0

    def smembers(self, name: str) -> Set[Any]:
        """
        获取集合中所有元素
        :param name: 集合名称
        :return: 元素集合（不存在返回空集合）
        """
        try:
            return self.client.smembers(name)
        except Exception as e:
            print(f"Redis smembers 失败 (name: {name}): {e}")
            return set()

    def srem(self, name: str, *values: Any) -> int:
        """
        从集合中删除一个或多个元素
        :param name: 集合名称
        :param values: 要删除的元素（可变参数）
        :return: 成功删除的元素数量
        """
        try:
            return self.client.srem(name, *values)
        except Exception as e:
            print(f"Redis srem 失败 (name: {name}): {e}")
            return 0

    def sismember(self, name: str, value: Any) -> bool:
        """
        检查元素是否在集合中
        :param name: 集合名称
        :param value: 要检查的元素
        :return: 存在返回 True，不存在返回 False
        """
        try:
            return self.client.sismember(name, value)
        except Exception as e:
            print(f"Redis sismember 失败 (name: {name}): {e}")
            return False

    # ------------------------------ 有序集合(Sorted Set)操作 ------------------------------
    def zadd(
        self,
        name: str,
        mapping: Optional[Dict[Any, float]] = None,
        **kwargs
    ) -> int:
        """
        向有序集合中添加一个或多个元素（带分数）
        :param name: 有序集合名称
        :param mapping: 元素-分数字典（如 {element1: 10, element2: 20}）
        :param kwargs: 元素=分数 键值对（如 element1=10, element2=20）
        :return: 成功添加的元素数量
        """
        try:
            return self.client.zadd(name, mapping=mapping,** kwargs)
        except Exception as e:
            print(f"Redis zadd 失败 (name: {name}): {e}")
            return 0

    def zrange(
        self,
        name: str,
        start: int = 0,
        end: int = -1,
        withscores: bool = False
    ) -> List[Any] | List[Tuple[Any, float]]:
        """
        获取有序集合指定排名范围的元素（按分数升序）
        :param name: 有序集合名称
        :param start: 起始排名（0 开始）
        :param end: 结束排名（-1 表示最后一个元素）
        :param withscores: 是否返回分数（默认 False）
        :return: 元素列表或 (元素, 分数) 元组列表
        """
        try:
            return self.client.zrange(name, start, end, withscores=withscores)
        except Exception as e:
            print(f"Redis zrange 失败 (name: {name}): {e}")
            return []

    def zrem(self, name: str, *values: Any) -> int:
        """
        从有序集合中删除一个或多个元素
        :param name: 有序集合名称
        :param values: 要删除的元素（可变参数）
        :return: 成功删除的元素数量
        """
        try:
            return self.client.zrem(name, *values)
        except Exception as e:
            print(f"Redis zrem 失败 (name: {name}): {e}")
            return 0

    def zscore(self, name: str, value: Any) -> Optional[float]:
        """
        获取有序集合中指定元素的分数
        :param name: 有序集合名称
        :param value: 元素
        :return: 分数（元素不存在返回 None）
        """
        try:
            return self.client.zscore(name, value)
        except Exception as e:
            print(f"Redis zscore 失败 (name: {name}): {e}")
            return None

    def close(self):
        """关闭 Redis 连接池（程序退出时调用）"""
        if RedisUtil._pool:
            RedisUtil._pool.disconnect()
            print("Redis 连接池已关闭")


# ------------------------------ 使用示例 ------------------------------
if __name__ == "__main__":
    # 初始化 Redis 工具类（根据实际环境修改配置）
    redis_util = RedisUtil(
        host='r-bp1phz2qws21z63xvmpd.redis.rds.aliyuncs.com',
        port=6379,
        db=4,
        password='REDACTED',  # 无密码则设为 None
        decode_responses=True
    )

    # 测试连接
    if redis_util.ping():
        print("Redis 连接成功！")

        # 1. 字符串操作示例
        print("\n=== 字符串操作 ===")
        redis_util.set("name", "redis_demo", ex=3600)
        print("get name:", redis_util.get("name"))
        print("exists name:", redis_util.exists("name"))
        print("ttl name:", redis_util.ttl("name"))


    # 关闭连接池（程序退出时调用）
    redis_util.close()
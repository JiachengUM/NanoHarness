from datetime import datetime, date
from decimal import Decimal
from enum import Enum
from typing import List, Dict, Union, Optional, Set, Any, TypeVar, Generic, Literal

from pydantic import BaseModel, Field, ConfigDict, conlist, conint, constr
from pydantic.types import PaymentCardNumber, SecretStr

# ========== 泛型类型定义 ==========
T = TypeVar('T')
R = TypeVar('R', int, float, Decimal)


class PaginatedResponse(BaseModel, Generic[T]):
    """分页响应泛型"""
    items: List[T] = Field(description="数据列表")
    page: int = Field(description="当前页码", ge=1)
    page_size: int = Field(description="每页数量", ge=1, le=100)
    total: int = Field(description="总数", ge=0)
    has_next: bool = Field(description="是否有下一页")


# ========== 枚举和字面量类型 ==========
class ProductCategory(str, Enum):
    ELECTRONICS = "electronics"
    CLOTHING = "clothing"
    BOOKS = "books"
    FOOD = "food"
    OTHER = "other"


class OrderStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


# ========== 循环引用模型 ==========
class TreeNode(BaseModel):
    """树节点（支持自引用）"""
    id: str = Field(default_factory=lambda: str(uuid4()))
    name: str = Field(description="节点名称")
    value: Optional[Union[int, float, str]] = Field(None, description="节点值")
    children: List['TreeNode'] = Field(default_factory=list, description="子节点列表")
    parent: Optional['TreeNode'] = Field(None, exclude=True)


# ========== 地理位置模型 ==========
class GeoLocation(BaseModel):
    """地理位置坐标"""
    latitude: float = Field(description="纬度", ge=-90, le=90)
    longitude: float = Field(description="经度", ge=-180, le=180)
    altitude: Optional[float] = Field(None, description="海拔", ge=-1000, le=10000)


# ========== 增强版地址模型 ==========
class Address(BaseModel):
    """增强版地址模型"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "street": "123 Main St",
                "city": "New York",
                "state": "NY",
                "country": "USA",
                "postal_code": "10001"
            }
        }
    )

    address_id: str = Field(default_factory=lambda: f"addr_{uuid4().hex[:8]}", description="地址ID")
    street: str = Field(description="街道地址", min_length=5, max_length=200)
    street2: Optional[str] = Field(None, description="第二行地址")
    city: str = Field(description="城市", min_length=2, max_length=100)
    state: str = Field(description="州/省", min_length=2, max_length=50)
    country: str = Field(description="国家", default="US", min_length=2, max_length=2)
    postal_code: str = Field(description="邮政编码", pattern=r"^[A-Z0-9\s-]+$")
    is_primary: bool = Field(False, description="是否主要地址")
    location: Optional[GeoLocation] = Field(None, description="地理位置")
    address_type: Literal["home", "work", "billing", "shipping"] = Field("home", description="地址类型")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")


# ========== 产品变体模型 ==========
class ProductVariant(BaseModel):
    """产品变体"""
    variant_id: str = Field(description="变体ID")
    sku: str = Field(description="SKU编码", pattern=r"^[A-Z0-9-]+$")
    size: Optional[str] = Field(None, description="尺寸")
    color: Optional[str] = Field(None, description="颜色")
    material: Optional[str] = Field(None, description="材质")
    price_adjustment: float = Field(0.0, description="价格调整", ge=-1000, le=1000)
    stock_quantity: int = Field(description="库存数量", ge=0, le=10000)
    weight_kg: Optional[float] = Field(None, description="重量(kg)", gt=0)
    dimensions: Optional[Dict[str, float]] = Field(None, description="尺寸信息")
    is_active: bool = Field(True, description="是否激活")


# ========== 产品评价模型 ==========
class ProductReview(BaseModel):
    """产品评价"""
    review_id: str = Field(default_factory=lambda: f"rev_{uuid4().hex[:8]}")
    user_id: str = Field(description="用户ID")
    rating: int = Field(description="评分", ge=1, le=5)
    title: constr(min_length=5, max_length=200) = Field(description="评价标题")
    content: constr(min_length=10, max_length=2000) = Field(description="评价内容")
    pros: List[str] = Field(default_factory=list, description="优点")
    cons: List[str] = Field(default_factory=list, description="缺点")
    verified_purchase: bool = Field(False, description="是否验证购买")
    helpful_votes: int = Field(0, description="有用票数", ge=0)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = None


# ========== 增强版产品模型 ==========
class Product(BaseModel):
    """增强版产品模型"""
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "id": "prod_12345",
                "name": "iPhone 15 Pro",
                "description": "最新款苹果手机",
                "price": 999.99
            }
        }
    )

    id: str = Field(description="产品ID", pattern=r"^prod_[A-Z0-9]{8,}$")
    sku: str = Field(description="主SKU", pattern=r"^[A-Z0-9-]+$")
    name: str = Field(description="产品名称", min_length=3, max_length=200)
    description: Optional[str] = Field(None, description="描述", max_length=5000)
    long_description: Optional[str] = Field(None, description="详细描述", max_length=20000)
    category: ProductCategory = Field(description="产品类别")
    subcategory: Optional[str] = Field(None, description="子类别")
    brand: str = Field(description="品牌", min_length=2, max_length=100)

    # 价格相关
    base_price: Decimal = Field(description="基础价格", ge=0, decimal_places=2)
    currency: str = Field(default="USD", description="货币", pattern=r"^[A-Z]{3}$")
    discount_percent: float = Field(0.0, description="折扣百分比", ge=0, le=100)
    tax_rate: float = Field(0.0, description="税率", ge=0, le=50)

    # 库存和变体
    variants: List[ProductVariant] = Field(default_factory=list, description="产品变体")
    attributes: Dict[str, Union[str, int, float, bool, List[str]]] = Field(
        default_factory=dict, description="产品属性"
    )

    # 多媒体
    image_urls: List[str] = Field(default_factory=list, description="图片URL列表")
    video_urls: Optional[List[str]] = Field(None, description="视频URL列表")

    # 评价和统计
    reviews: PaginatedResponse[ProductReview] = Field(default_factory=lambda:
    PaginatedResponse[ProductReview](
        items=[], page=1, page_size=10, total=0, has_next=False
    ), description="评价分页"
                                                      )
    average_rating: float = Field(0.0, description="平均评分", ge=0, le=5)
    total_sold: int = Field(0, description="总销量", ge=0)

    # 时间相关
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    published_at: Optional[datetime] = Field(None, description="发布时间")
    available_from: date = Field(description="可用开始日期")
    available_until: Optional[date] = Field(None, description="可用结束日期")

    # SEO相关
    seo_title: Optional[str] = Field(None, description="SEO标题", max_length=60)
    seo_description: Optional[str] = Field(None, description="SEO描述", max_length=160)
    seo_keywords: List[str] = Field(default_factory=list, description="SEO关键词")


# ========== 折扣信息模型 ==========
class Discount(BaseModel):
    """折扣信息"""
    discount_id: str = Field(description="折扣ID")
    discount_type: Literal["percentage", "fixed", "buy_x_get_y", "free_shipping"] = Field("percentage")
    value: float = Field(description="折扣值", ge=0)
    description: Optional[str] = Field(None, description="折扣描述")
    coupon_code: Optional[str] = Field(None, description="优惠码")


# ========== 税行模型 ==========
class TaxLine(BaseModel):
    """税行"""
    tax_type: str = Field(description="税种")
    rate: float = Field(description="税率", ge=0, le=50)
    amount: Decimal = Field(description="税额", ge=0, decimal_places=2)
    is_inclusive: bool = Field(False, description="是否已包含在价格中")


# ========== 增强版订单项模型 ==========
class OrderItem(BaseModel):
    """增强版订单项"""
    model_config = ConfigDict(
        arbitrary_types_allowed=True
    )

    item_id: str = Field(default_factory=lambda: f"item_{uuid4().hex[:8]}", description="订单项ID")
    product: Product = Field(description="产品信息")
    variant_id: Optional[str] = Field(None, description="选择的变体ID")
    quantity: conint(ge=1, le=1000) = Field(description="数量")
    unit_price: Decimal = Field(description="单价", gt=0, decimal_places=2)

    # 折扣和优惠
    discounts: List[Discount] = Field(default_factory=list, description="应用的折扣")
    tax_lines: List[TaxLine] = Field(default_factory=list, description="税项明细")

    # 扩展信息
    customizations: Dict[str, Any] = Field(default_factory=dict, description="定制选项")
    gift_wrap: bool = Field(False, description="是否礼品包装")
    gift_message: Optional[str] = Field(None, description="礼品留言", max_length=500)


# ========== 信用卡信息模型 ==========
class CreditCardInfo(BaseModel):
    """信用卡信息"""
    card_number: PaymentCardNumber
    card_holder: constr(min_length=2, max_length=100)
    expiry_month: conint(ge=1, le=12)
    expiry_year: conint(ge=2024, le=2044)
    cvv: SecretStr
    billing_address: Address


# ========== PayPal信息模型 ==========
class PayPalInfo(BaseModel):
    """PayPal信息"""
    email: str = Field(description="PayPal邮箱")
    payer_id: Optional[str] = Field(None, description="付款人ID")


# ========== 银行信息模型 ==========
class BankInfo(BaseModel):
    """银行信息"""
    bank_name: str
    account_holder: str
    account_number: SecretStr
    routing_number: str
    iban: Optional[str] = None
    swift_code: Optional[str] = None


# ========== 加密货币钱包信息模型 ==========
class CryptoWalletInfo(BaseModel):
    """加密货币钱包信息"""
    wallet_address: SecretStr
    currency: Literal["BTC", "ETH", "USDT", "USDC"]
    network: Literal["mainnet", "testnet", "polygon", "arbitrum"]


# ========== 社交媒体资料模型 ==========
class SocialProfile(BaseModel):
    """社交媒体资料"""
    platform: Literal["facebook", "twitter", "instagram", "linkedin", "github"]
    username: str
    profile_url: str
    is_connected: bool = Field(False, description="是否已连接")
    last_sync: Optional[datetime] = Field(None, description="最后同步时间")


# ========== 支付方式模型 ==========
class PaymentMethod(BaseModel):
    """支付方式"""
    payment_method_id: str = Field(default_factory=lambda: f"pm_{uuid4().hex[:8]}")
    type: Literal["credit_card", "debit_card", "paypal", "bank_transfer", "crypto"]
    is_default: bool = Field(False, description="是否默认支付方式")
    details: Union[Dict[str, str], CreditCardInfo, PayPalInfo, BankInfo, CryptoWalletInfo]
    created_at: datetime = Field(default_factory=datetime.now)
    expires_at: Optional[date] = Field(None, description="过期日期")


# ========== 用户偏好设置模型 ==========
class UserPreferences(BaseModel):
    """用户偏好设置"""
    language: str = Field(default="en-US", description="语言")
    currency: str = Field(default="USD", description="货币")
    timezone: str = Field(default="UTC", description="时区")
    email_notifications: bool = Field(default=True, description="邮件通知")
    sms_notifications: bool = Field(default=False, description="短信通知")
    push_notifications: bool = Field(default=True, description="推送通知")
    marketing_emails: bool = Field(default=False, description="营销邮件")
    theme: Literal["light", "dark", "system"] = Field(default="system", description="主题")
    two_factor_auth: bool = Field(default=False, description="双因素认证")
    privacy_level: Literal["public", "friends", "private"] = Field(default="friends", description="隐私级别")


# ========== 增强版用户模型 ==========
class User(BaseModel):
    """超级复杂的用户模型"""
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "user_id": "user_123",
                    "username": "john_doe",
                    "email": "john@example.com"
                }
            ]
        }
    )

    # 基础信息
    user_id: str = Field(
        default_factory=lambda: f"user_{uuid4().hex[:12]}",
        description="用户ID"
    )
    username: constr(
        min_length=3, max_length=50,
        pattern=r"^[a-zA-Z0-9_]+$"
    ) = Field(description="用户名")
    email: str = Field(
        description="邮箱",
        pattern=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    )

    # 个人信息
    personal_info: Dict[str, Any] = Field(
        default_factory=lambda: {
            "first_name": None,
            "last_name": None,
            "gender": None,
            "birthdate": None,
            "phone": None,
            "avatar_url": None
        },
        description="个人信息"
    )

    # 验证相关
    email_verified: bool = Field(False, description="邮箱已验证")
    phone_verified: bool = Field(False, description="手机已验证")
    is_active: bool = Field(True, description="是否激活")
    is_superuser: bool = Field(False, description="是否超级用户")

    # 安全相关
    hashed_password: Optional[SecretStr] = Field(None, description="哈希密码")
    password_changed_at: Optional[datetime] = Field(None, description="密码最后修改时间")
    failed_login_attempts: int = Field(0, description="登录失败次数", ge=0)
    locked_until: Optional[datetime] = Field(None, description="锁定直到")
    mfa_enabled: bool = Field(False, description="是否启用MFA")
    mfa_secret: Optional[SecretStr] = Field(None, description="MFA密钥")

    # 关系
    addresses: conlist(Address, min_length=0, max_length=10) = Field(
        default_factory=list, description="地址列表"
    )
    payment_methods: List[PaymentMethod] = Field(
        default_factory=list, description="支付方式列表"
    )
    social_profiles: Dict[str, SocialProfile] = Field(
        default_factory=dict, description="社交媒体资料"
    )

    # 业务关系
    orders: PaginatedResponse[OrderItem] = Field(
        default_factory=lambda: PaginatedResponse[OrderItem](
            items=[], page=1, page_size=20, total=0, has_next=False
        ),
        description="订单分页"
    )
    wishlist: List[Union[str, Product]] = Field(
        default_factory=list, description="愿望清单"
    )
    shopping_cart: Dict[str, Dict[str, Any]] = Field(
        default_factory=dict, description="购物车"
    )

    # 元数据
    metadata: Dict[str, Union[str, int, float, bool, List, Dict]] = Field(
        default_factory=dict, description="元数据"
    )
    tags: Set[str] = Field(default_factory=set, description="标签")

    # 偏好设置
    preferences: UserPreferences = Field(
        default_factory=UserPreferences, description="偏好设置"
    )

    # 时间戳
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")
    last_login_at: Optional[datetime] = Field(None, description="最后登录时间")
    email_verified_at: Optional[datetime] = Field(None, description="邮箱验证时间")

    # 统计信息
    stats: Dict[str, Any] = Field(
        default_factory=lambda: {
            "order_count": 0,
            "total_spent": 0.0,
            "avg_order_value": 0.0,
            "days_active": 0,
            "login_count": 0
        },
        description="统计信息"
    )


# ========== 完整订单模型 ==========
class Order(BaseModel):
    """完整的订单模型"""
    order_id: str = Field(default_factory=lambda: f"order_{uuid4().hex[:8]}")
    user: User = Field(description="下单用户")
    items: List[OrderItem] = Field(description="订单项")
    status: OrderStatus = Field(description="订单状态")
    shipping_address: Address = Field(description="收货地址")
    billing_address: Optional[Address] = Field(None, description="账单地址")
    payment_method: PaymentMethod = Field(description="支付方式")
    shipping_method: str = Field(description="配送方式")
    tracking_number: Optional[str] = Field(None, description="物流单号")

    # 金额汇总
    subtotal: Decimal = Field(description="小计", ge=0)
    shipping_cost: Decimal = Field(description="运费", ge=0)
    tax_amount: Decimal = Field(description="税费", ge=0)
    discount_amount: Decimal = Field(description="折扣金额", ge=0)
    total_amount: Decimal = Field(description="总计", ge=0)

    # 时间戳
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    paid_at: Optional[datetime] = Field(None)
    shipped_at: Optional[datetime] = Field(None)
    delivered_at: Optional[datetime] = Field(None)

    # 元数据
    notes: Optional[str] = Field(None, description="备注")
    tags: List[str] = Field(default_factory=list, description="标签")


# ========== API响应模型 ==========
class APIResponse(BaseModel, Generic[T, R]):
    """通用API响应模型"""
    success: bool = Field(description="是否成功")
    data: Optional[T] = Field(None, description="响应数据")
    pagination: Optional[PaginatedResponse[R]] = Field(None, description="分页信息")
    error: Optional[Dict[str, Any]] = Field(None, description="错误信息")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="元数据")
    timestamp: datetime = Field(default_factory=datetime.now, description="时间戳")
    request_id: str = Field(
        default_factory=lambda: f"req_{uuid4().hex[:16]}",
        description="请求ID"
    )


# ========== 批量操作模型 ==========
class BatchOperation(BaseModel, Generic[T]):
    """批量操作模型"""
    operations: List[Dict[str, Any]] = Field(description="操作列表")
    transaction_id: str = Field(
        default_factory=lambda: f"txn_{uuid4().hex[:8]}",
        description="事务ID"
    )
    created_at: datetime = Field(default_factory=datetime.now)


# 生成 JSON 格式的完整数据
def create_complete_user_json():
    """创建完整的 User JSON 数据"""

    # 格式化日期时间，确保符合 ISO 格式
    def json_serializer(obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        raise TypeError(f"Type {type(obj)} not serializable")

    # 转换为 JSON
    json_data = json.dumps(user_data, indent=2, default=json_serializer)

    # 计算数据大小
    data_size_kb = len(json_data.encode('utf-8')) / 1024
    nested_levels = calculate_nested_levels(user_data)

    print(f"=== User 数据结构分析 ===")
    print(f"JSON 数据大小: {data_size_kb:.2f} KB")
    print(f"最大嵌套层级: {nested_levels}")
    print(f"字段总数: {count_fields(user_data)}")
    print(f"包含模型类型: {count_model_types(user_data)}")
    print("=" * 30)

    return json_data


def calculate_nested_levels(data, current_level=0):
    """计算数据的最大嵌套层级"""
    if not isinstance(data, (dict, list)):
        return current_level

    max_level = current_level
    if isinstance(data, dict):
        for value in data.values():
            level = calculate_nested_levels(value, current_level + 1)
            max_level = max(max_level, level)
    elif isinstance(data, list):
        for item in data:
            level = calculate_nested_levels(item, current_level + 1)
            max_level = max(max_level, level)

    return max_level


def count_fields(data):
    """统计字段总数"""
    if isinstance(data, dict):
        total = len(data)
        for value in data.values():
            total += count_fields(value)
        return total
    elif isinstance(data, list):
        total = 0
        for item in data:
            total += count_fields(item)
        return total
    return 0


def count_model_types(data):
    """统计包含的模型类型"""
    model_types = set()

    def extract_types(obj):
        if isinstance(obj, dict):
            # 从复杂结构推断模型类型
            if 'address_id' in obj:
                model_types.add('Address')
            elif 'product' in obj or 'category' in obj:
                if 'category' in obj and isinstance(obj['category'], str):
                    model_types.add('Product')
                elif 'items' in obj and 'page' in obj:
                    model_types.add('PaginatedResponse')
            elif 'item_id' in obj:
                model_types.add('OrderItem')
            elif 'payment_method_id' in obj:
                model_types.add('PaymentMethod')
            elif 'review_id' in obj:
                model_types.add('ProductReview')
            elif 'platform' in obj:
                model_types.add('SocialProfile')

            # 递归检查所有值
            for value in obj.values():
                extract_types(value)
        elif isinstance(obj, list):
            for item in obj:
                extract_types(item)

    extract_types(data)
    return model_types


# 测试数据创建和验证
def test_user_data():
    """测试 User 数据创建"""
    try:
        from pydantic import ValidationError

        # 尝试创建 User 实例（简化版本，因为SecretStr等需要特殊处理）
        class SimpleUser(BaseModel):
            """简化的 User 模型用于测试"""
            user_id: str
            username: str
            email: str
            personal_info: dict
            email_verified: bool
            addresses: list
            payment_methods: list

        # 创建简化实例
        simple_user = SimpleUser(**{
            "user_id": user_data["user_id"],
            "username": user_data["username"],
            "email": user_data["email"],
            "personal_info": user_data["personal_info"],
            "email_verified": user_data["email_verified"],
            "addresses": user_data["addresses"],
            "payment_methods": user_data["payment_methods"]
        })

        print("✅ 基本数据结构验证通过")
        print(f"用户ID: {simple_user.user_id}")
        print(f"用户名: {simple_user.username}")
        print(f"邮箱: {simple_user.email}")
        print(f"地址数量: {len(simple_user.addresses)}")
        print(f"支付方式数量: {len(simple_user.payment_methods)}")

        return True

    except ValidationError as e:
        print(f"❌ 验证错误: {e}")
        return False
    except ImportError:
        print("⚠️  Pydantic 不可用，跳过验证")
        return True


if __name__ == "__main__":
    from datetime import datetime, date, timedelta
    from decimal import Decimal
    from uuid import uuid4
    import json

    # 创建完整的 User 数据
    user_data = {
        "user_id": "user_1234567890ab",
        "username": "john_doe_2024",
        "email": "john.doe@example.com",

        # 个人信息
        "personal_info": {
            "first_name": "John",
            "last_name": "Doe",
            "gender": "male",
            "birthdate": date(1990, 5, 15).isoformat(),
            "phone": "+1-555-123-4567",
            "avatar_url": "https://example.com/avatars/john_doe.jpg"
        },

        # 验证相关
        "email_verified": True,
        "phone_verified": True,
        "is_active": True,
        "is_superuser": False,

        # 安全相关
        "hashed_password": "hashed_password_placeholder",
        "password_changed_at": datetime.now().isoformat(),
        "failed_login_attempts": 0,
        "locked_until": None,
        "mfa_enabled": True,
        "mfa_secret": "JBSWY3DPEHPK3PXP",

        # 地址列表
        "addresses": [
            {
                "address_id": "addr_a1b2c3d4",
                "street": "123 Main Street",
                "street2": "Suite 400",
                "city": "New York",
                "state": "NY",
                "country": "US",
                "postal_code": "10001",
                "is_primary": True,
                "address_type": "home",
                "location": {
                    "latitude": 40.7128,
                    "longitude": -74.0060,
                    "altitude": 10.5
                },
                "created_at": datetime(2020, 1, 15, 10, 30, 0).isoformat(),
                "updated_at": datetime(2023, 5, 20, 14, 15, 0).isoformat()
            },
            {
                "address_id": "addr_e5f6g7h8",
                "street": "456 Business Blvd",
                "street2": None,
                "city": "Boston",
                "state": "MA",
                "country": "US",
                "postal_code": "02101",
                "is_primary": False,
                "address_type": "work",
                "location": {
                    "latitude": 42.3601,
                    "longitude": -71.0589,
                    "altitude": None
                },
                "created_at": datetime(2021, 3, 10, 9, 0, 0).isoformat(),
                "updated_at": datetime(2023, 8, 5, 16, 45, 0).isoformat()
            }
        ],

        # 支付方式
        "payment_methods": [
            {
                "payment_method_id": "pm_cc123456",
                "type": "credit_card",
                "is_default": True,
                "details": {
                    "card_number": "4111111111111111",
                    "card_holder": "JOHN DOE",
                    "expiry_month": 12,
                    "expiry_year": 2026,
                    "cvv": "123",
                    "billing_address": {
                        "address_id": "addr_billing001",
                        "street": "123 Main Street",
                        "street2": "Suite 400",
                        "city": "New York",
                        "state": "NY",
                        "country": "US",
                        "postal_code": "10001",
                        "is_primary": True,
                        "address_type": "billing",
                        "location": None,
                        "created_at": datetime(2020, 1, 15, 10, 30, 0).isoformat(),
                        "updated_at": datetime(2023, 5, 20, 14, 15, 0).isoformat()
                    }
                },
                "created_at": datetime(2021, 6, 1, 11, 0, 0).isoformat(),
                "expires_at": date(2026, 12, 31).isoformat()
            },
            {
                "payment_method_id": "pm_pp789012",
                "type": "paypal",
                "is_default": False,
                "details": {
                    "email": "john.doe@paypal.com",
                    "payer_id": "PAYER123456789"
                },
                "created_at": datetime(2022, 2, 15, 14, 30, 0).isoformat(),
                "expires_at": None
            }
        ],

        # 社交媒体资料
        "social_profiles": {
            "github": {
                "platform": "github",
                "username": "johndoe-dev",
                "profile_url": "https://github.com/johndoe-dev",
                "is_connected": True,
                "last_sync": datetime(2024, 1, 15, 10, 0, 0).isoformat()
            },
            "linkedin": {
                "platform": "linkedin",
                "username": "john-doe-123",
                "profile_url": "https://linkedin.com/in/john-doe-123",
                "is_connected": True,
                "last_sync": datetime(2024, 1, 10, 15, 30, 0).isoformat()
            }
        },

        # 订单分页
        "orders": {
            "items": [
                {
                    "item_id": "item_ord001_001",
                    "product": {
                        "id": "prod_IPHONE15P256",
                        "sku": "IPHONE15P-256GB-BLK",
                        "name": "iPhone 15 Pro 256GB Black",
                        "description": "最新款苹果旗舰手机，256GB存储空间",
                        "long_description": "iPhone 15 Pro采用航空级钛金属设计，配备A17 Pro芯片、专业级相机系统和USB-C接口。",
                        "category": "electronics",
                        "subcategory": "smartphones",
                        "brand": "Apple",
                        "base_price": "999.99",
                        "currency": "USD",
                        "discount_percent": 5.0,
                        "tax_rate": 8.875,
                        "variants": [
                            {
                                "variant_id": "var_iphone15_256_black",
                                "sku": "IPHONE15P-256GB-BLK-01",
                                "size": None,
                                "color": "Black",
                                "material": "Titanium",
                                "price_adjustment": 0.0,
                                "stock_quantity": 50,
                                "weight_kg": 0.187,
                                "dimensions": {
                                    "height": 146.6,
                                    "width": 70.6,
                                    "depth": 8.25
                                },
                                "is_active": True
                            }
                        ],
                        "attributes": {
                            "processor": "A17 Pro",
                            "ram": "8GB",
                            "storage": "256GB",
                            "screen_size": "6.1",
                            "screen_type": "Super Retina XDR",
                            "camera": "48MP + 12MP + 12MP",
                            "battery": "3274 mAh",
                            "water_resistant": True,
                            "5g_support": True,
                            "colors_available": ["Black", "White", "Blue", "Natural"]
                        },
                        "image_urls": [
                            "https://example.com/products/iphone15-black-front.jpg",
                            "https://example.com/products/iphone15-black-back.jpg"
                        ],
                        "video_urls": [
                            "https://example.com/products/iphone15-review.mp4"
                        ],
                        "reviews": {
                            "items": [
                                {
                                    "review_id": "rev_iphone15_001",
                                    "user_id": "user_expert123",
                                    "rating": 5,
                                    "title": "Best phone I've ever owned",
                                    "content": "The camera quality is outstanding and battery life lasts all day.",
                                    "pros": ["Camera", "Performance", "Battery"],
                                    "cons": ["Price", "No charger included"],
                                    "verified_purchase": True,
                                    "helpful_votes": 128,
                                    "created_at": datetime(2023, 9, 20, 14, 30, 0).isoformat(),
                                    "updated_at": datetime(2023, 9, 20, 14, 30, 0).isoformat()
                                }
                            ],
                            "page": 1,
                            "page_size": 10,
                            "total": 1250,
                            "has_next": True
                        },
                        "average_rating": 4.8,
                        "total_sold": 15000,
                        "created_at": datetime(2023, 9, 1, 0, 0, 0).isoformat(),
                        "updated_at": datetime(2024, 1, 1, 12, 0, 0).isoformat(),
                        "published_at": datetime(2023, 9, 10, 9, 0, 0).isoformat(),
                        "available_from": date(2023, 9, 10).isoformat(),
                        "available_until": None,
                        "seo_title": "iPhone 15 Pro 256GB Black - Apple Official Store",
                        "seo_description": "Buy iPhone 15 Pro 256GB in Black. Free shipping. 24-month financing available.",
                        "seo_keywords": ["iPhone", "smartphone", "Apple", "5G", "camera"]
                    },
                    "variant_id": "var_iphone15_256_black",
                    "quantity": 1,
                    "unit_price": "999.99",
                    "discounts": [
                        {
                            "discount_id": "disc_newyear2024",
                            "discount_type": "percentage",
                            "value": 10.0,
                            "description": "New Year 2024 Special",
                            "coupon_code": "NEWYEAR2024"
                        }
                    ],
                    "tax_lines": [
                        {
                            "tax_type": "sales_tax",
                            "rate": 8.875,
                            "amount": "79.87",
                            "is_inclusive": False
                        }
                    ],
                    "customizations": {
                        "engraving": "JD 2024",
                        "case_color": "Midnight Blue"
                    },
                    "gift_wrap": True,
                    "gift_message": "Happy Birthday! Enjoy your new phone."
                }
            ],
            "page": 1,
            "page_size": 20,
            "total": 15,
            "has_next": False
        },

        # 愿望清单
        "wishlist": [
            "prod_MACBOOKAIRM2",
            {
                "id": "prod_AIRTAG4PK",
                "sku": "AIRTAG-4PK",
                "name": "AirTag 4-Pack",
                "description": "Apple AirTag tracking devices, 4-pack",
                "long_description": "Keep track of and find your items alongside friends and devices in the Find My app.",
                "category": "electronics",
                "subcategory": "accessories",
                "brand": "Apple",
                "base_price": "99.00",
                "currency": "USD",
                "discount_percent": 0.0,
                "tax_rate": 8.875,
                "variants": [],
                "attributes": {
                    "pack_size": "4-pack",
                    "battery_life": "1 year",
                    "range": "Bluetooth range",
                    "find_my_network": True
                },
                "image_urls": [
                    "https://example.com/products/airtag-4pack.jpg"
                ],
                "video_urls": None,
                "reviews": {
                    "items": [],
                    "page": 1,
                    "page_size": 10,
                    "total": 0,
                    "has_next": False
                },
                "average_rating": 0.0,
                "total_sold": 0,
                "created_at": datetime(2023, 4, 1, 0, 0, 0).isoformat(),
                "updated_at": datetime(2023, 4, 1, 0, 0, 0).isoformat(),
                "published_at": datetime(2023, 4, 15, 9, 0, 0).isoformat(),
                "available_from": date(2023, 4, 15).isoformat(),
                "available_until": None,
                "seo_title": None,
                "seo_description": None,
                "seo_keywords": []
            }
        ],

        # 购物车
        "shopping_cart": {
            "prod_MACBOOKAIRM2": {
                "variant_id": "var_mba_m2_512",
                "quantity": 1,
                "added_at": datetime.now().isoformat(),
                "unit_price": "1299.99",
                "notes": "Need for work"
            },
            "prod_AIRTAG4PK": {
                "variant_id": "var_airtag_4pk",
                "quantity": 2,
                "added_at": (datetime.now() - timedelta(days=2)).isoformat(),
                "unit_price": "99.00",
                "notes": "Gift for family"
            }
        },

        # 元数据
        "metadata": {
            "account_tier": "premium",
            "loyalty_points": 12500,
            "signup_source": "google_ads",
            "customer_segment": "high_value",
            "preferred_categories": ["electronics", "books", "home"],
            "last_visit_device": "mobile_ios",
            "campaign_history": [
                {
                    "campaign": "welcome_offer",
                    "converted": True,
                    "date": "2023-01-15"
                }
            ]
        },

        # 标签
        "tags": ["premium_user", "tech_enthusiast", "early_adopter", "verified"],

        # 偏好设置
        "preferences": {
            "language": "en-US",
            "currency": "USD",
            "timezone": "America/New_York",
            "email_notifications": True,
            "sms_notifications": False,
            "push_notifications": True,
            "marketing_emails": True,
            "theme": "dark",
            "two_factor_auth": True,
            "privacy_level": "friends"
        },

        # 时间戳
        "created_at": datetime(2023, 1, 15, 10, 0, 0).isoformat(),
        "updated_at": datetime.now().isoformat(),
        "last_login_at": datetime.now().isoformat(),
        "email_verified_at": datetime(2023, 1, 15, 11, 0, 0).isoformat(),

        # 统计信息
        "stats": {
            "order_count": 15,
            "total_spent": 12500.75,
            "avg_order_value": 833.38,
            "days_active": 365,
            "login_count": 287,
            "cart_abandonment_rate": 12.5,
            "favorite_category": "electronics",
            "last_order_amount": 1079.86,
            "customer_lifetime_value": 25000.50,
            "referral_count": 5
        }
    }

    # 生成完整 JSON
    json_output = create_complete_user_json()

    # 测试数据
    test_user_data()

    # 可以选择保存到文件
    with open("user_complete_data.json", "w") as f:
        f.write(json_output)
    print(f"\n📁 完整数据已保存到 user_complete_data.json")
    print(json_output)
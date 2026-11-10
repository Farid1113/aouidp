from decimal import Decimal
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, EmailStr, Field, field_validator, ConfigDict

class InstallIn(BaseModel):
    shop_name: str = Field(min_length=2, max_length=100)
    username: str = Field(min_length=3, max_length=80, pattern=r'^[A-Za-z0-9_.-]+$')
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)
    contact: str = Field(default='', max_length=200)
    timezone: str = Field(default='Africa/Casablanca', max_length=80)

class Credentials(BaseModel):
    login: str = Field(min_length=3, max_length=254)
    password: str

class Register(BaseModel):
    name: str = Field(min_length=2, max_length=130)
    email: EmailStr
    password: str = Field(min_length=12, max_length=256)

class CategoryIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    slug: str = Field(min_length=2, max_length=160, pattern=r'^[a-z0-9-]+$')
    parent_id: int | None = None
    sort_order: int = 0
    image_url: str | None = Field(default=None, max_length=1000)

class ProductIn(BaseModel):
    name: str = Field(min_length=2, max_length=220)
    slug: str = Field(min_length=2, max_length=230, pattern=r'^[a-z0-9-]+$')
    short_description: str = Field(default='', max_length=400)
    description: str = ''
    category_id: int
    price: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    original_price: Decimal | None = Field(default=None, ge=0, max_digits=12, decimal_places=2)
    cost_price: Decimal = Field(default=Decimal('0.00'), ge=0)
    image_url: str | None = Field(default=None, max_length=1000)
    duration: str = Field(default='', max_length=40)
    delivery_type: Literal['instant','manual','service'] = 'manual'
    instructions: str = ''
    active: bool = True
    badge: str = Field(default='', max_length=40)

class OrderLine(BaseModel):
    product_id: int
    quantity: int = Field(ge=1, le=20)
    service_data: dict[str, str] = Field(default_factory=dict)

class CheckoutIn(BaseModel):
    customer_name: str = Field(min_length=2, max_length=130)
    email: EmailStr
    phone: str = Field(default='', max_length=40)
    payment_method_id: int
    items: list[OrderLine] = Field(min_length=1, max_length=40)
    idempotency_key: str = Field(min_length=12, max_length=100)

class ProofReferenceIn(BaseModel):
    reference: str = Field(min_length=3, max_length=200)

class MethodUpdate(BaseModel):
    enabled: bool
    display_name: str = Field(min_length=2, max_length=100)
    instructions: str = Field(default='', max_length=3000)
    public_details: dict[str, str] = Field(default_factory=dict)
    min_amount: Decimal = Field(default=Decimal('0'), ge=0)
    max_amount: Decimal | None = Field(default=None, ge=0)
    sort_order: int = 0

class DiscountIn(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    product_id: int | None = None
    kind: Literal['percent','fixed']
    value: Decimal = Field(gt=0)
    starts_at: datetime
    ends_at: datetime
    active: bool = True

class SettingIn(BaseModel):
    shop_name: str = Field(min_length=2, max_length=100)
    shop_contact: str = Field(default='', max_length=200)
    accent: str = Field(default='#6d5dfc', pattern=r'^#[A-Fa-f0-9]{6}$')
    hero_title: str = Field(default='منتجات رقمية موثوقة', max_length=200)
    hero_subtitle: str = Field(default='', max_length=500)

class TicketIn(BaseModel):
    email: EmailStr
    subject: str = Field(min_length=3, max_length=200)
    content: str = Field(min_length=10, max_length=5000)

class MarkOrderIn(BaseModel):
    status: Literal['paid','cancelled','refunded','processing','delivered']

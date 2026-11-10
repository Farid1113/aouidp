"""SQLAlchemy models; Alembic owns schema evolution. Amounts are always Numeric/Decimal."""
from datetime import datetime, timezone
from decimal import Decimal
from sqlalchemy import (String, Text, Integer, Boolean, Numeric, DateTime, ForeignKey, UniqueConstraint,
                        Index, CheckConstraint, JSON)
from sqlalchemy.orm import Mapped, mapped_column
from app.core.db import Base


def utcnow(): return datetime.now(timezone.utc)

def pk(): return mapped_column(Integer, primary_key=True, autoincrement=True)

class Installation(Base):
    __tablename__ = 'installation'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    installed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class Role(Base):
    __tablename__ = 'roles'
    id: Mapped[int] = pk()
    name: Mapped[str] = mapped_column(String(32), unique=True)

class Permission(Base):
    __tablename__ = 'permissions'
    id: Mapped[int] = pk()
    key: Mapped[str] = mapped_column(String(80), unique=True)

class RolePermission(Base):
    __tablename__ = 'role_permissions'
    role_id: Mapped[int] = mapped_column(ForeignKey('roles.id', ondelete='CASCADE'), primary_key=True)
    permission_id: Mapped[int] = mapped_column(ForeignKey('permissions.id', ondelete='CASCADE'), primary_key=True)

class Admin(Base):
    __tablename__ = 'admins'
    id: Mapped[int] = pk()
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role_id: Mapped[int] = mapped_column(ForeignKey('roles.id'), index=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class User(Base):
    __tablename__ = 'users'
    id: Mapped[int] = pk()
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(130))
    password_hash: Mapped[str] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class AuthSession(Base):
    __tablename__ = 'auth_sessions'
    id: Mapped[int] = pk()
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    csrf_token: Mapped[str] = mapped_column(String(80))
    admin_id: Mapped[int | None] = mapped_column(ForeignKey('admins.id', ondelete='CASCADE'), index=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (CheckConstraint('(admin_id IS NOT NULL AND user_id IS NULL) OR (admin_id IS NULL AND user_id IS NOT NULL)', name='session_one_owner'),)

class Category(Base):
    __tablename__ = 'categories'
    id: Mapped[int] = pk()
    name: Mapped[str] = mapped_column(String(150))
    slug: Mapped[str] = mapped_column(String(160), unique=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey('categories.id', ondelete='SET NULL'))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    image_url: Mapped[str | None] = mapped_column(String(1000))

class Product(Base):
    __tablename__ = 'products'
    id: Mapped[int] = pk()
    name: Mapped[str] = mapped_column(String(220))
    slug: Mapped[str] = mapped_column(String(230), unique=True, index=True)
    short_description: Mapped[str] = mapped_column(String(400), default='')
    description: Mapped[str] = mapped_column(Text, default='')
    category_id: Mapped[int] = mapped_column(ForeignKey('categories.id'), index=True)
    price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    original_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    cost_price: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    image_url: Mapped[str | None] = mapped_column(String(1000))
    duration: Mapped[str] = mapped_column(String(40), default='')
    delivery_type: Mapped[str] = mapped_column(String(20), default='manual')
    instructions: Mapped[str] = mapped_column(Text, default='')
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    badge: Mapped[str] = mapped_column(String(40), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    __table_args__ = (CheckConstraint('price >= 0', name='product_positive_price'),)

class ProductVariant(Base):
    __tablename__ = 'product_variants'
    id: Mapped[int] = pk()
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete='CASCADE'), index=True)
    label: Mapped[str] = mapped_column(String(150))
    sku: Mapped[str] = mapped_column(String(100), unique=True)
    price_delta: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)

class ProductImage(Base):
    __tablename__ = 'product_images'
    id: Mapped[int] = pk()
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete='CASCADE'))
    url: Mapped[str] = mapped_column(String(1000))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

class DigitalCode(Base):
    __tablename__ = 'digital_codes'
    id: Mapped[int] = pk()
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete='CASCADE'), index=True)
    encrypted_value: Mapped[str] = mapped_column(Text)
    fingerprint: Mapped[str] = mapped_column(String(64))
    order_item_id: Mapped[int | None] = mapped_column(ForeignKey('order_items.id', ondelete='SET NULL'), unique=True, index=True)
    allocated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (UniqueConstraint('product_id', 'fingerprint', name='uq_product_code_fingerprint'),)

class Inventory(Base):
    __tablename__ = 'inventory'
    id: Mapped[int] = pk()
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id', ondelete='CASCADE'), unique=True)
    manual_stock: Mapped[int] = mapped_column(Integer, default=0)

class Cart(Base):
    __tablename__ = 'carts'
    id: Mapped[int] = pk()
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class CartItem(Base):
    __tablename__ = 'cart_items'
    id: Mapped[int] = pk()
    cart_id: Mapped[int] = mapped_column(ForeignKey('carts.id', ondelete='CASCADE'))
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    quantity: Mapped[int] = mapped_column(Integer, default=1)

class Order(Base):
    __tablename__ = 'orders'
    id: Mapped[int] = pk()
    public_id: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    customer_name: Mapped[str] = mapped_column(String(130))
    email: Mapped[str] = mapped_column(String(254), index=True)
    phone: Mapped[str] = mapped_column(String(40), default='')
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    status: Mapped[str] = mapped_column(String(30), default='pending_payment', index=True)
    payment_method_id: Mapped[int] = mapped_column(ForeignKey('payment_methods.id'))
    total: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(3), default='MAD')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint('total >= 0', name='order_positive_total'),)

class OrderItem(Base):
    __tablename__ = 'order_items'
    id: Mapped[int] = pk()
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id', ondelete='CASCADE'), index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    product_name: Mapped[str] = mapped_column(String(220))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    quantity: Mapped[int] = mapped_column(Integer)
    delivery_status: Mapped[str] = mapped_column(String(25), default='pending')
    service_data: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (CheckConstraint('quantity > 0', name='orderitem_positive_qty'),)

class PaymentMethod(Base):
    __tablename__ = 'payment_methods'
    id: Mapped[int] = pk()
    kind: Mapped[str] = mapped_column(String(30), unique=True)
    display_name: Mapped[str] = mapped_column(String(100))
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    instructions: Mapped[str] = mapped_column(Text, default='')
    public_details: Mapped[dict] = mapped_column(JSON, default=dict)
    min_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    max_amount: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

class Payment(Base):
    __tablename__ = 'payments'
    id: Mapped[int] = pk()
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'), index=True)
    method_id: Mapped[int] = mapped_column(ForeignKey('payment_methods.id'))
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    status: Mapped[str] = mapped_column(String(25), default='pending')
    reference: Mapped[str | None] = mapped_column(String(200))
    idempotency_key: Mapped[str] = mapped_column(String(128), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class PaymentProof(Base):
    __tablename__ = 'payment_proofs'
    id: Mapped[int] = pk()
    payment_id: Mapped[int] = mapped_column(ForeignKey('payments.id'), index=True)
    private_path: Mapped[str] = mapped_column(String(300))
    original_filename: Mapped[str] = mapped_column(String(150))
    content_type: Mapped[str] = mapped_column(String(100))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Discount(Base):
    __tablename__ = 'discounts'
    id: Mapped[int] = pk()
    product_id: Mapped[int | None] = mapped_column(ForeignKey('products.id', ondelete='CASCADE'), index=True)
    name: Mapped[str] = mapped_column(String(150))
    kind: Mapped[str] = mapped_column(String(15), default='percent')
    value: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class Coupon(Base):
    __tablename__ = 'coupons'
    id: Mapped[int] = pk()
    code: Mapped[str] = mapped_column(String(50), unique=True)
    discount_id: Mapped[int] = mapped_column(ForeignKey('discounts.id'))
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    used_count: Mapped[int] = mapped_column(Integer, default=0)

class FlashSale(Base):
    __tablename__ = 'flash_sales'
    id: Mapped[int] = pk()
    discount_id: Mapped[int] = mapped_column(ForeignKey('discounts.id'), unique=True)

class Review(Base):
    __tablename__ = 'reviews'
    id: Mapped[int] = pk()
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    product_id: Mapped[int] = mapped_column(ForeignKey('products.id'))
    rating: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text, default='')
    verified: Mapped[bool] = mapped_column(Boolean, default=False)
    __table_args__ = (CheckConstraint('rating BETWEEN 1 AND 5', name='review_rating_range'),)

class Notification(Base):
    __tablename__ = 'notifications'
    id: Mapped[int] = pk()
    kind: Mapped[str] = mapped_column(String(50))
    title: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    user_id: Mapped[int | None] = mapped_column(ForeignKey('users.id'))
    seen: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class SupportTicket(Base):
    __tablename__ = 'support_tickets'
    id: Mapped[int] = pk()
    email: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default='open')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class SiteSetting(Base):
    __tablename__ = 'site_settings'
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text)

class Banner(Base):
    __tablename__ = 'banners'
    id: Mapped[int] = pk()
    title: Mapped[str] = mapped_column(String(160))
    image_url: Mapped[str | None] = mapped_column(String(1000))
    href: Mapped[str] = mapped_column(String(1000), default='/shop')
    active: Mapped[bool] = mapped_column(Boolean, default=True)

class AuditLog(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[int] = pk()
    admin_id: Mapped[int | None] = mapped_column(ForeignKey('admins.id', ondelete='SET NULL'))
    action: Mapped[str] = mapped_column(String(150))
    target: Mapped[str] = mapped_column(String(150), default='')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class DeliveryLog(Base):
    __tablename__ = 'delivery_logs'
    id: Mapped[int] = pk()
    order_item_id: Mapped[int] = mapped_column(ForeignKey('order_items.id'), index=True)
    note: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class Invoice(Base):
    __tablename__ = 'invoices'
    id: Mapped[int] = pk()
    number: Mapped[str] = mapped_column(String(60), unique=True)
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id'), unique=True)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

class GiftCard(Base):
    __tablename__ = 'gift_cards'
    id: Mapped[int] = pk()
    code_hash: Mapped[str] = mapped_column(String(64), unique=True)
    balance: Mapped[Decimal] = mapped_column(Numeric(12, 2))

class LoyaltyLedger(Base):
    __tablename__ = 'loyalty_ledger'
    id: Mapped[int] = pk()
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    points: Mapped[int] = mapped_column(Integer)
    order_id: Mapped[int | None] = mapped_column(ForeignKey('orders.id'))

class Referral(Base):
    __tablename__ = 'referrals'
    id: Mapped[int] = pk()
    inviter_id: Mapped[int] = mapped_column(ForeignKey('users.id'))
    invited_id: Mapped[int] = mapped_column(ForeignKey('users.id'), unique=True)

Index('ix_orders_email_created', Order.email, Order.created_at)
Index('ix_codes_product_orderitem', DigitalCode.product_id, DigitalCode.order_item_id)

class OrderAccess(Base):
    __tablename__ = 'order_access'
    order_id: Mapped[int] = mapped_column(ForeignKey('orders.id', ondelete='CASCADE'), primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)

class ManualDelivery(Base):
    __tablename__ = 'manual_deliveries'
    order_item_id: Mapped[int] = mapped_column(ForeignKey('order_items.id',ondelete='CASCADE'),primary_key=True)
    encrypted_message: Mapped[str] = mapped_column(Text)

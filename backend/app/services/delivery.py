"""Delivery is executed only on trusted server-side payment confirmation.

In PostgreSQL SELECT .. FOR UPDATE SKIP LOCKED locks unallocated code rows.
SQLite is only supported for development/testing, not concurrency-safe production.
"""
import secrets
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet, InvalidToken
from app.core.config import get_settings
from app.models.tables import Order, OrderItem, Product, DigitalCode, DeliveryLog, Inventory, Payment, Notification


def get_fernet() -> Fernet:
    key = get_settings().digital_code_key
    if not key:
        raise HTTPException(503, 'DIGITAL_CODE_KEY must be configured to use instant delivery')
    try: return Fernet(key.encode())
    except ValueError: raise HTTPException(503, 'DIGITAL_CODE_KEY is invalid')

def rust_validator():
    try:
        import digital_core
        return digital_core
    except ImportError:
        raise HTTPException(503, 'Rust digital_core missing. Run maturin develop before code import.')

def import_codes(db: Session, product_id: int, raw_codes: list[str]):
    core, fernet = rust_validator(), get_fernet()
    if len(get_settings().digital_code_hmac_key) < 32:
        raise HTTPException(503, "DIGITAL_CODE_HMAC_KEY must be set before code import")
    total = 0
    fingerprints_seen: set[str] = set()
    for raw in raw_codes:
        code = raw.strip()
        if not code: continue
        if not core.validate_code(code): raise HTTPException(422, 'Invalid digital code format')
        fingerprint = core.fingerprint(code, get_settings().digital_code_hmac_key)  # Rust HMAC-SHA256
        if fingerprint in fingerprints_seen: continue
        fingerprints_seen.add(fingerprint)
        # Database UNIQUE(product_id,fingerprint) is final deduplication authority.
        from sqlalchemy import select
        if db.scalar(select(DigitalCode.id).where(DigitalCode.product_id == product_id,
                                                  DigitalCode.fingerprint == fingerprint)):
            continue
        db.add(DigitalCode(product_id=product_id, fingerprint=fingerprint,
                           encrypted_value=fernet.encrypt(code.encode()).decode()))
        total += 1
    try: db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(409, 'Duplicate codes or concurrency conflict; retry the import')
    return total

def fulfill_paid_order(db: Session, order: Order):
    """Run inside the caller's DB transaction, with order row locked by caller."""
    items = db.scalars(select(OrderItem).where(OrderItem.order_id == order.id).order_by(OrderItem.id)).all()
    planned = []
    for item in items:
        if item.delivery_status != 'pending': continue
        product = db.get(Product, item.product_id)
        if product.delivery_type == 'instant':
            # Fail closed for missing Rust or encryption key.
            rust_validator(); get_fernet()
            unallocated = db.scalars(select(DigitalCode).where(
                DigitalCode.product_id == product.id, DigitalCode.order_item_id.is_(None))
                .order_by(DigitalCode.id).with_for_update(skip_locked=True).limit(item.quantity)).all()
            if len(unallocated) < item.quantity:
                raise HTTPException(409, f'Insufficient unallocated codes for product {product.id}')
            planned.append((item, unallocated))
        elif product.delivery_type == 'manual':
            planned.append((item, None))
        else:
            planned.append((item, 'service'))
    for item, codes in planned:
        if isinstance(codes, list):
            if item.quantity != 1:
                # Each DigitalCode has a unique order_item_id. For multi-unit purchases,
                # split into separate OrderItems at checkout.
                raise HTTPException(409, 'Invalid inventory allocation quantity')
            code = codes[0]
            code.order_item_id = item.id
            code.allocated_at = datetime.now(timezone.utc)
            item.delivery_status = 'delivered'
            db.add(DeliveryLog(order_item_id=item.id, note='Instant code delivered to secure account'))
        else:
            item.delivery_status = 'processing'
            db.add(DeliveryLog(order_item_id=item.id, note='Manual delivery queued' if codes is None else 'Service processing queued'))
    order.paid_at = datetime.now(timezone.utc)
    order.status = 'delivered' if items and all(i.delivery_status == 'delivered' for i in items) else 'processing'
    db.add(Notification(kind='payment_success', title='Payment confirmed', body=f'Order {order.public_id} paid'))

def codes_for_item(db: Session, item_id: int):
    fernet = get_fernet()
    codes = db.scalars(select(DigitalCode).where(DigitalCode.order_item_id == item_id)).all()
    result = []
    for code in codes:
        try: result.append(fernet.decrypt(code.encrypted_value.encode()).decode())
        except InvalidToken: raise HTTPException(500, 'Encrypted code cannot be decrypted; check encryption key')
    return result

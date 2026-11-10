from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import select, or_
from sqlalchemy.orm import Session
from app.models.tables import Discount, Product

MONEY = Decimal('0.01')

def price_for(db: Session, product: Product, now=None):
    now = now or datetime.now(timezone.utc)
    # PostgreSQL timestamps timezone-aware; SQLite may have naive values.
    offers = db.scalars(select(Discount).where(Discount.active.is_(True),
        or_(Discount.product_id == product.id, Discount.product_id.is_(None)))).all()
    cost, best_end = product.price, None
    for offer in offers:
        start = offer.starts_at.replace(tzinfo=timezone.utc) if offer.starts_at.tzinfo is None else offer.starts_at
        end = offer.ends_at.replace(tzinfo=timezone.utc) if offer.ends_at.tzinfo is None else offer.ends_at
        if start <= now < end:
            proposed = (product.price * (Decimal('100') - offer.value) / Decimal('100')) if offer.kind == 'percent' else product.price - offer.value
            proposed = max(Decimal('0'), proposed.quantize(MONEY, rounding=ROUND_HALF_UP))
            if proposed < cost: cost, best_end = proposed, end
    return cost, best_end

def serialize_product(db: Session, p: Product):
    price, ends_at = price_for(db, p)
    return {'id':p.id, 'slug':p.slug, 'name':p.name, 'short_description':p.short_description,
            'description':p.description,'category_id':p.category_id,'price':str(price),
            'base_price':str(p.price),'original_price':str(p.original_price) if p.original_price is not None else None,
            'cost_price':str(p.cost_price),'image_url':p.image_url,'duration':p.duration,
            'delivery_type':p.delivery_type,'instructions':p.instructions,'badge':p.badge,
            'active':p.active,'offer_ends_at':ends_at.isoformat() if ends_at else None}

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import throttle
from app.models.tables import Category, Product, PaymentMethod, SiteSetting, Banner, SupportTicket
from app.services.pricing import serialize_product
from app.schemas.dto import TicketIn

router=APIRouter(tags=['public'])

def public_settings(db: Session):
    rows=db.scalars(select(SiteSetting)).all()
    safe={'shop_name','shop_contact','timezone','currency','accent','hero_title','hero_subtitle'}
    return {x.key:x.value for x in rows if x.key in safe}

@router.get('/site')
def site(db: Session=Depends(get_db)):
    return {'settings':public_settings(db), 'server_now':datetime.now(timezone.utc).isoformat(),
            'banners':[{'id':x.id,'title':x.title,'image_url':x.image_url,'href':x.href} for x in db.scalars(select(Banner).where(Banner.active.is_(True))).all()]}

@router.get('/categories')
def categories(db:Session=Depends(get_db)):
    return [{'id':x.id,'name':x.name,'slug':x.slug,'parent_id':x.parent_id,'sort_order':x.sort_order}
            for x in db.scalars(select(Category).order_by(Category.sort_order,Category.id)).all()]

@router.get('/products')
def products(q:str=Query(default='',max_length=100),category_id:int|None=None,limit:int=Query(default=40,ge=1,le=100),
             offset:int=Query(default=0,ge=0),db:Session=Depends(get_db)):
    query=select(Product).where(Product.active.is_(True))
    if q: query=query.where(Product.name.ilike('%'+q.replace('%','\\%').replace('_','\\_')+'%', escape='\\'))
    if category_id: query=query.where(Product.category_id==category_id)
    count=db.scalar(select(func.count()).select_from(query.subquery()))
    found=db.scalars(query.order_by(Product.created_at.desc()).limit(limit).offset(offset)).all()
    return {'items':[serialize_product(db,x) for x in found], 'total':count,
            'server_now':datetime.now(timezone.utc).isoformat()}

@router.get('/products/{slug}')
def product(slug:str,db:Session=Depends(get_db)):
    x=db.scalar(select(Product).where(Product.slug==slug, Product.active.is_(True)))
    if not x: raise HTTPException(404,'Product not found')
    return serialize_product(db,x)

@router.get('/payment-methods')
def methods(db:Session=Depends(get_db)):
    # No card/PayPal live adapters shipped; they cannot be enabled by admin API.
    return [{'id':x.id,'kind':x.kind,'display_name':x.display_name,'instructions':x.instructions,
             'public_details':x.public_details,'min_amount':str(x.min_amount),
             'max_amount':str(x.max_amount) if x.max_amount is not None else None}
            for x in db.scalars(select(PaymentMethod).where(PaymentMethod.enabled.is_(True),
                      PaymentMethod.kind.in_(['bank_transfer','cash_plus'])).order_by(PaymentMethod.sort_order)).all()]

@router.post('/support',status_code=201)
def support(info:TicketIn,request:Request,db:Session=Depends(get_db)):
    throttle('support:'+request.client.host,5,3600)
    ticket=SupportTicket(**info.model_dump());db.add(ticket);db.commit()
    return {'id':ticket.id,'message':'Ticket received'}

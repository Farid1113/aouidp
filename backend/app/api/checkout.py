"""Never trust client prices; never confirm payments from success redirects."""
import secrets
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Header, Request, UploadFile, File
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import throttle, token_digest, session_or_401
from app.models.tables import (Order,OrderItem,Product,PaymentMethod,Payment,PaymentProof,DigitalCode,User,Notification)
from app.schemas.dto import CheckoutIn, ProofReferenceIn
from app.services.pricing import price_for
from app.services.delivery import codes_for_item, get_fernet
from pathlib import Path

router=APIRouter(prefix='/orders',tags=['orders'])

@router.post('/checkout',status_code=201)
def checkout(info:CheckoutIn, request:Request,db:Session=Depends(get_db)):
    throttle('checkout:'+request.client.host,20,3600)
    existing=db.scalar(select(Payment).where(Payment.idempotency_key==info.idempotency_key))
    if existing:
        raise HTTPException(409,'This checkout was already submitted; use your saved receipt')
    method=db.get(PaymentMethod,info.payment_method_id)
    if not method or not method.enabled or method.kind not in ('bank_transfer','cash_plus'):
        raise HTTPException(422,'Payment method unavailable')
    items=[];total=Decimal('0.00')
    # Explicit per-unit rows allow a unique code allocation for each item row.
    for line in info.items:
        product=db.get(Product,line.product_id)
        if not product or not product.active: raise HTTPException(422,'Product unavailable')
        if line.quantity>10: raise HTTPException(422,'Max 10 units per line')
        unit_price,_=price_for(db,product)
        if product.delivery_type=='instant':
            available=db.scalar(select(func.count(DigitalCode.id)).where(DigitalCode.product_id==product.id,DigitalCode.order_item_id.is_(None)))
            if available < line.quantity: raise HTTPException(409,'Insufficient available digital stock')
        if len(line.service_data)>10 or any((len(k)>50 or len(str(v))>256 or any(word in k.lower() for word in ('password','secret','otp','token'))) for k,v in line.service_data.items()):
            raise HTTPException(422,'Unsafe or oversized service fields')
        if product.delivery_type=='service' and not line.service_data:
            raise HTTPException(422,'Service data required; use a public UID or reference, not passwords')
        for _ in range(line.quantity):
            items.append((product,unit_price,line.service_data))
            total+=unit_price
    total=total.quantize(Decimal('0.01'))
    if total < method.min_amount or (method.max_amount is not None and total > method.max_amount):
        raise HTTPException(422,'Payment method limit exceeded')
    raw_access=secrets.token_urlsafe(32)
    user_id=None
    try:
        session=session_or_401(request,db)
        user=db.get(User,session.user_id) if session.user_id else None
        if user and user.email.casefold()==str(info.email).casefold(): user_id=user.id
    except HTTPException: pass
    order=Order(public_id='DS-'+secrets.token_hex(10).upper(), customer_name=info.customer_name,
                email=str(info.email),phone=info.phone,user_id=user_id, status='pending_payment',
                payment_method_id=method.id,total=total)
    # Access token fingerprint is stored separately (unique column added below in migration).
    db.add(order);db.flush()
    for p,price,service_data in items:
        db.add(OrderItem(order_id=order.id,product_id=p.id,product_name=p.name,
                         unit_price=price,quantity=1,service_data=service_data))
    db.add(Payment(order_id=order.id,method_id=method.id,amount=total,status='pending',
                   idempotency_key=info.idempotency_key))
    db.add(Notification(kind='new_order',title='New order',body=f'{order.public_id} — {total} MAD'))
    from app.models.tables import OrderAccess
    db.add(OrderAccess(order_id=order.id, token_hash=token_digest(raw_access)))
    try: db.commit()
    except Exception:
        db.rollback(); raise HTTPException(409,'Checkout conflict; retry with a new idempotency key')
    return {'public_id':order.public_id,'access_token':raw_access,'total':str(total),
            'status':order.status,'payment_method':method.display_name,
            'instructions':method.instructions,'public_details':method.public_details}

def authorize_order(db: Session, order: Order, access_token: str|None, request: Request):
    from app.models.tables import OrderAccess
    if access_token:
        access=db.scalar(select(OrderAccess).where(OrderAccess.order_id==order.id,
                  OrderAccess.token_hash==token_digest(access_token)))
        if access: return
    try:
        session=session_or_401(request,db)
        if session.user_id and order.user_id == session.user_id: return
    except HTTPException: pass
    raise HTTPException(403,'Receipt access token or owning customer session required')

@router.get('/{public_id}')
def order_status(public_id:str,request:Request,x_order_token:str|None=Header(default=None),db:Session=Depends(get_db)):
    order=db.scalar(select(Order).where(Order.public_id==public_id))
    if not order: raise HTTPException(404,'Order not found')
    authorize_order(db,order,x_order_token,request)
    items=db.scalars(select(OrderItem).where(OrderItem.order_id==order.id)).all()
    return {'public_id':order.public_id,'status':order.status,'total':str(order.total),
            'created_at':order.created_at.isoformat(),
            'items':[{'id':i.id,'name':i.product_name,'price':str(i.unit_price),
                      'delivery_status':i.delivery_status,
                      'codes':codes_for_item(db,i.id) if order.paid_at and i.delivery_status=='delivered' else [],
                      'delivery_message':manual_message(db,i.id) if order.paid_at and i.delivery_status=='delivered' else None}
                     for i in items]}

@router.post('/{public_id}/reference')
def payment_reference(public_id:str,body:ProofReferenceIn,request:Request,
                      x_order_token:str|None=Header(default=None),db:Session=Depends(get_db)):
    order=db.scalar(select(Order).where(Order.public_id==public_id))
    if not order:raise HTTPException(404)
    authorize_order(db,order,x_order_token,request)
    if order.status!='pending_payment':raise HTTPException(409,'Payment already processed')
    payment=db.scalar(select(Payment).where(Payment.order_id==order.id))
    payment.reference=body.reference
    db.commit()
    return {'ok':True}

@router.post('/{public_id}/proof')
async def proof(public_id:str,request:Request,file:UploadFile=File(...),
                x_order_token:str|None=Header(default=None),db:Session=Depends(get_db)):
    order=db.scalar(select(Order).where(Order.public_id==public_id))
    if not order:raise HTTPException(404)
    authorize_order(db,order,x_order_token,request)
    if order.status!='pending_payment':raise HTTPException(409,'Payment already processed')
    throttle('proof-upload:'+request.client.host, 12, 3600)
    payment=db.scalar(select(Payment).where(Payment.order_id==order.id))
    if db.scalar(select(func.count(PaymentProof.id)).where(PaymentProof.payment_id==payment.id))>=3:
        raise HTTPException(429, 'Maximum 3 proofs per order')
    content=await file.read(2*1024*1024+1)
    if len(content)>2*1024*1024: raise HTTPException(413,'Max file size: 2MB')
    if content.startswith(b'%PDF-'): kind,ext='application/pdf','.pdf'
    elif content.startswith(b'\x89PNG\r\n\x1a\n'): kind,ext='image/png','.png'
    elif content.startswith(b'\xff\xd8\xff'): kind,ext='image/jpeg','.jpg'
    else: raise HTTPException(415,'Only PDF, PNG, or JPEG accepted')
    private=Path('private_uploads');private.mkdir(mode=0o700,exist_ok=True)
    filename=secrets.token_hex(20)+ext
    path=private/filename
    # Never serve this directory through the web/static frontend.
    path.write_bytes(content);path.chmod(0o600)
    db.add(PaymentProof(payment_id=payment.id,private_path=str(path),
                        original_filename=(file.filename or '')[:150],content_type=kind))
    db.add(Notification(kind='proof_submitted',title='Payment proof received',body=order.public_id))
    db.commit()
    return {'ok':True}


def manual_message(db: Session, item_id:int):
    from app.models.tables import ManualDelivery
    entry=db.get(ManualDelivery,item_id)
    return get_fernet().decrypt(entry.encrypted_message.encode()).decode() if entry else None

@router.get('/mine/list')
def my_orders(request:Request,db:Session=Depends(get_db)):
    from app.core.security import customer_required
    user=customer_required(request,db)
    return [{'public_id':o.public_id,'total':str(o.total),'status':o.status,
             'created_at':o.created_at.isoformat()} for o in db.scalars(
             select(Order).where(Order.user_id==user.id).order_by(Order.id.desc())).all()]

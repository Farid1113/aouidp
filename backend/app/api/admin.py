import csv
import io
from datetime import datetime, timezone
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Query, File, UploadFile
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.security import admin_required, manager_required, super_required
from app.models.tables import (Admin, Category, Product, DigitalCode, Order, OrderItem, Payment, PaymentMethod,
    SiteSetting, Discount, AuditLog, Notification, SupportTicket, PaymentProof, ManualDelivery, DeliveryLog, Banner)
from app.schemas.dto import CategoryIn, ProductIn, MethodUpdate, DiscountIn, SettingIn, MarkOrderIn
from app.services.pricing import serialize_product
from app.services.delivery import import_codes, fulfill_paid_order, get_fernet
from pydantic import BaseModel, Field

router=APIRouter(prefix='/admin',tags=['admin'])

def audit(db:Session,admin:Admin,action:str,target:str=''):
    db.add(AuditLog(admin_id=admin.id,action=action,target=target))

@router.get('/dashboard')
def dashboard(admin:Admin=Depends(admin_required),db:Session=Depends(get_db)):
    rows=db.scalars(select(Order)).all()
    paid=[o for o in rows if o.paid_at is not None and o.status!='refunded']
    income=sum((o.total for o in paid),Decimal('0.00'))
    top=db.execute(select(OrderItem.product_name,func.count(OrderItem.id)).group_by(OrderItem.product_name)
                   .order_by(func.count(OrderItem.id).desc()).limit(8)).all()
    month={}
    for o in paid:
        key=o.created_at.strftime('%Y-%m')
        month[key]=month.get(key,Decimal('0'))+o.total
    return {'orders':len(rows),'paid_orders':len(paid),'revenue':str(income),
            'products':db.scalar(select(func.count(Product.id))),
            'customers':db.scalar(select(func.count(func.distinct(Order.email)))),
            'monthly_sales':[{'period':k,'revenue':str(v)} for k,v in sorted(month.items())],
            'top_products':[{'name':name,'units':count} for name,count in top]}

@router.get('/categories')
def admin_categories(admin:Admin=Depends(admin_required),db:Session=Depends(get_db)):
    return [{'id':x.id,'name':x.name,'slug':x.slug,'sort_order':x.sort_order,'parent_id':x.parent_id}
            for x in db.scalars(select(Category).order_by(Category.id)).all()]

@router.post('/categories',status_code=201)
def add_category(info:CategoryIn,admin:Admin=Depends(manager_required),db:Session=Depends(get_db)):
    if db.scalar(select(Category.id).where(Category.slug==info.slug)):raise HTTPException(409,'Category slug exists')
    if info.parent_id and not db.get(Category,info.parent_id):raise HTTPException(422,'Parent does not exist')
    obj=Category(**info.model_dump());db.add(obj);db.flush();audit(db,admin,'category.create',str(obj.id));db.commit()
    return {'id':obj.id}

@router.put('/categories/{category_id}')
def update_category(category_id:int,info:CategoryIn,admin:Admin=Depends(manager_required),db:Session=Depends(get_db)):
    obj=db.get(Category,category_id)
    if not obj: raise HTTPException(404)
    if info.parent_id == obj.id:raise HTTPException(422,'Category cannot be its own parent')
    for k,v in info.model_dump().items():setattr(obj,k,v)
    audit(db,admin,'category.update',str(obj.id))
    try: db.commit()
    except Exception:db.rollback();raise HTTPException(409,'Category update conflict')
    return {'ok':True}

@router.delete('/categories/{category_id}')
def delete_category(category_id:int,admin:Admin=Depends(manager_required),db:Session=Depends(get_db)):
    obj=db.get(Category,category_id)
    if not obj:raise HTTPException(404)
    if db.scalar(select(Product.id).where(Product.category_id==category_id).limit(1)):
        raise HTTPException(409,'Cannot delete a category with products')
    db.delete(obj);audit(db,admin,'category.delete',str(category_id));db.commit();return {'ok':True}

@router.get('/products')
def admin_products(admin:Admin=Depends(admin_required),db:Session=Depends(get_db)):
    return [serialize_product(db,x) for x in db.scalars(select(Product).order_by(Product.id.desc()).limit(200)).all()]

@router.post('/products',status_code=201)
def add_product(info:ProductIn,admin:Admin=Depends(manager_required),db:Session=Depends(get_db)):
    if not db.get(Category,info.category_id):raise HTTPException(422,'Category not found')
    if db.scalar(select(Product.id).where(Product.slug==info.slug)):raise HTTPException(409,'Product slug exists')
    obj=Product(**info.model_dump());db.add(obj);db.flush();audit(db,admin,'product.create',str(obj.id));db.commit()
    return {'id':obj.id}

@router.put('/products/{id}')
def update_product(id:int,info:ProductIn,admin:Admin=Depends(manager_required),db:Session=Depends(get_db)):
    obj=db.get(Product,id)
    if not obj:raise HTTPException(404)
    if not db.get(Category,info.category_id):raise HTTPException(422,'Category not found')
    for k,v in info.model_dump().items():setattr(obj,k,v)
    audit(db,admin,'product.update',str(id))
    try:db.commit()
    except Exception:db.rollback();raise HTTPException(409,'Product conflict')
    return {'ok':True}

@router.delete('/products/{id}')
def delete_product(id:int,admin:Admin=Depends(manager_required),db:Session=Depends(get_db)):
    obj=db.get(Product,id)
    if not obj:raise HTTPException(404)
    obj.active=False
    audit(db,admin,'product.archive',str(id));db.commit();return {'ok':True}

class CodeBatch(BaseModel):
    codes: list[str] = Field(min_length=1,max_length=1000)

@router.post('/products/{id}/codes')
def add_codes(id:int,body:CodeBatch,admin:Admin=Depends(manager_required),db:Session=Depends(get_db)):
    obj=db.get(Product,id)
    if not obj:raise HTTPException(404)
    if obj.delivery_type!='instant':raise HTTPException(422,'Select instant delivery type first')
    total=import_codes(db,id,body.codes)
    audit(db,admin,'code.import',f'product:{id},count:{total}');db.commit()
    return {'imported':total}

@router.get('/products/{id}/stock')
def code_stock(id:int,admin:Admin=Depends(admin_required),db:Session=Depends(get_db)):
    return {'available':db.scalar(select(func.count(DigitalCode.id)).where(DigitalCode.product_id==id,
                            DigitalCode.order_item_id.is_(None)))}

@router.get('/orders')
def orders(admin:Admin=Depends(admin_required),db:Session=Depends(get_db)):
    result=[]
    for o in db.scalars(select(Order).order_by(Order.id.desc()).limit(200)).all():
        payment=db.scalar(select(Payment).where(Payment.order_id==o.id))
        proof=db.scalar(select(PaymentProof).where(PaymentProof.payment_id==payment.id)) if payment else None
        result.append({'id':o.id,'public_id':o.public_id,'customer':o.customer_name,'email':o.email,
                       'total':str(o.total),'status':o.status,'paid_at':o.paid_at.isoformat() if o.paid_at else None,
                       'payment_reference':payment.reference if payment else None,
                       'proof_id':proof.id if proof else None,
                       'created_at':o.created_at.isoformat()})
    return result

@router.get('/orders/{id}/items')
def order_items(id:int,admin:Admin=Depends(admin_required),db:Session=Depends(get_db)):
    if not db.get(Order,id):raise HTTPException(404)
    return [{'id':i.id,'product_name':i.product_name,'delivery_status':i.delivery_status,
             'service_data':i.service_data} for i in db.scalars(select(OrderItem).where(OrderItem.order_id==id)).all()]

@router.post('/orders/{id}/status')
def mark_order(id:int,info:MarkOrderIn,admin:Admin=Depends(manager_required),db:Session=Depends(get_db)):
    order=db.scalar(select(Order).where(Order.id==id).with_for_update())
    if not order:raise HTTPException(404)
    payment=db.scalar(select(Payment).where(Payment.order_id==id).with_for_update())
    if info.status=='paid':
        from app.models.tables import Role
        if db.get(Role,admin.role_id).name != 'super_admin':
            raise HTTPException(403, 'Payment confirmation requires super admin')
        if order.paid_at is not None:
            return {'status':order.status,'idempotent':True}
        if order.status!='pending_payment':raise HTTPException(409,'Order not awaiting payment')
        # All allocation and confirmation in one transaction. Rollback on low stock.
        fulfill_paid_order(db,order)
        payment.status='confirmed'
    elif info.status=='cancelled':
        if order.paid_at:raise HTTPException(409,'Paid orders require refund process')
        order.status='cancelled';payment.status='cancelled'
    elif info.status=='refunded':
        raise HTTPException(501,'Refund settlement requires verified provider or manual refund evidence; no automatic refund simulated')
    elif info.status in ('processing','delivered'):
        raise HTTPException(422,'Use the item delivery endpoint to update delivery status')
    audit(db,admin,'order.status',f'{id}:{info.status}')
    try: db.commit()
    except Exception:
        db.rollback();raise
    return {'status':order.status}

class DeliveryMessage(BaseModel):
    message: str = Field(min_length=2,max_length=10000)

@router.post('/order-items/{id}/deliver')
def manual_deliver(id:int,body:DeliveryMessage,admin:Admin=Depends(manager_required),db:Session=Depends(get_db)):
    item=db.get(OrderItem,id)
    if not item:raise HTTPException(404)
    order=db.get(Order,item.order_id)
    if not order.paid_at:raise HTTPException(409,'Payment must be confirmed first')
    if item.delivery_status=='delivered':raise HTTPException(409,'Already delivered')
    encrypted=get_fernet().encrypt(body.message.encode()).decode()
    db.add(ManualDelivery(order_item_id=item.id,encrypted_message=encrypted))
    item.delivery_status='delivered'
    db.add(DeliveryLog(order_item_id=item.id,note='Manual delivery completed'))
    states=[i.delivery_status for i in db.scalars(select(OrderItem).where(OrderItem.order_id==order.id)).all()]
    if states and all(s=='delivered' for s in states):order.status='delivered'
    db.add(Notification(kind='delivery',title='Delivery complete',body=order.public_id, user_id=order.user_id))
    audit(db,admin,'orderitem.deliver',str(id));db.commit();return {'status':item.delivery_status}

@router.get('/payment-proofs/{id}')
def view_proof(id:int,admin:Admin=Depends(manager_required),db:Session=Depends(get_db)):
    proof=db.get(PaymentProof,id)
    if not proof:raise HTTPException(404)
    return FileResponse(proof.private_path,media_type=proof.content_type,
                        headers={'Content-Disposition':'attachment; filename="payment-proof"',
                                 'X-Content-Type-Options':'nosniff','Cache-Control':'no-store'})

@router.get('/payment-methods')
def list_methods(admin:Admin=Depends(admin_required),db:Session=Depends(get_db)):
    return [{'id':m.id,'kind':m.kind,'display_name':m.display_name,'enabled':m.enabled,
             'instructions':m.instructions,'public_details':m.public_details,
             'min_amount':str(m.min_amount),'max_amount':str(m.max_amount) if m.max_amount is not None else None,
             'sort_order':m.sort_order} for m in db.scalars(select(PaymentMethod).order_by(PaymentMethod.sort_order)).all()]

@router.put('/payment-methods/{id}')
def change_method(id:int,info:MethodUpdate,admin:Admin=Depends(super_required),db:Session=Depends(get_db)):
    m=db.get(PaymentMethod,id)
    if not m:raise HTTPException(404)
    if m.kind not in ('bank_transfer','cash_plus'):
        raise HTTPException(501,'Live card/PayPal gateway not implemented; cannot enable unsafe placeholder')
    allowed={'bank_transfer':{'bank','holder','rib','iban'},'cash_plus':{'beneficiary','reference'}}[m.kind]
    if set(info.public_details)-allowed:raise HTTPException(422,'Unknown payment fields')
    if info.enabled and not all(info.public_details.get(k) for k in
                 ({'bank','holder','rib'} if m.kind=='bank_transfer' else {'beneficiary','reference'})):
        raise HTTPException(422,'Complete payment instructions and required public details first')
    if info.max_amount is not None and info.max_amount < info.min_amount:
        raise HTTPException(422,'Invalid payment range')
    for key,value in info.model_dump().items():setattr(m,key,value)
    audit(db,admin,'paymentmethod.update',m.kind);db.commit();return {'ok':True}

@router.get('/settings')
def settings(admin:Admin=Depends(admin_required),db:Session=Depends(get_db)):
    return {x.key:x.value for x in db.scalars(select(SiteSetting)).all()}

@router.put('/settings')
def change_settings(info:SettingIn,admin:Admin=Depends(super_required),db:Session=Depends(get_db)):
    for key,value in info.model_dump().items():
        row=db.get(SiteSetting,key)
        if row:row.value=value
        else:db.add(SiteSetting(key=key,value=value))
    audit(db,admin,'settings.update');db.commit();return {'ok':True}

@router.get('/discounts')
def discounts(admin:Admin=Depends(admin_required),db:Session=Depends(get_db)):
    return [{'id':x.id,'name':x.name,'kind':x.kind,'value':str(x.value),
             'product_id':x.product_id,'starts_at':x.starts_at.isoformat(),
             'ends_at':x.ends_at.isoformat(),'active':x.active}
            for x in db.scalars(select(Discount).order_by(Discount.id.desc())).all()]

@router.post('/discounts',status_code=201)
def add_discount(info:DiscountIn,admin:Admin=Depends(manager_required),db:Session=Depends(get_db)):
    if info.ends_at<=info.starts_at:raise HTTPException(422,'End must be after start')
    if info.kind=='percent' and info.value>100:raise HTTPException(422,'Percent cannot exceed 100')
    if info.product_id and not db.get(Product,info.product_id):raise HTTPException(422,'Unknown product')
    o=Discount(**info.model_dump());db.add(o);db.flush();audit(db,admin,'discount.create',str(o.id));db.commit()
    return {'id':o.id}

@router.delete('/discounts/{id}')
def stop_discount(id:int,admin:Admin=Depends(manager_required),db:Session=Depends(get_db)):
    o=db.get(Discount,id)
    if not o:raise HTTPException(404)
    o.active=False;audit(db,admin,'discount.disable',str(id));db.commit();return {'ok':True}

@router.get('/notifications')
def notifications(admin:Admin=Depends(admin_required),db:Session=Depends(get_db)):
    return [{'id':x.id,'kind':x.kind,'title':x.title,'body':x.body,'seen':x.seen,
             'created_at':x.created_at.isoformat()} for x in db.scalars(
             select(Notification).order_by(Notification.id.desc()).limit(100)).all()]

@router.get('/tickets')
def tickets(admin:Admin=Depends(admin_required),db:Session=Depends(get_db)):
    return [{'id':x.id,'email':x.email,'subject':x.subject,'content':x.content,
             'status':x.status} for x in db.scalars(select(SupportTicket).order_by(SupportTicket.id.desc())).all()]

@router.get('/audit')
def audit_log(admin:Admin=Depends(super_required),db:Session=Depends(get_db)):
    return [{'id':x.id,'admin_id':x.admin_id,'action':x.action,'target':x.target,
             'created_at':x.created_at.isoformat()} for x in db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(200)).all()]

@router.get('/orders-export.csv')
def export_orders(admin:Admin=Depends(manager_required),db:Session=Depends(get_db)):
    file=io.StringIO();writer=csv.writer(file)
    writer.writerow(['reference','email','status','total_MAD','created_at'])
    for o in db.scalars(select(Order).order_by(Order.id)).all():
        writer.writerow([o.public_id,o.email,o.status,str(o.total),o.created_at.isoformat()])
    return StreamingResponse(iter([file.getvalue()]),media_type='text/csv; charset=utf-8',
                             headers={'Content-Disposition':'attachment; filename=orders.csv'})

@router.get('/customers')
def customers(admin:Admin=Depends(admin_required),db:Session=Depends(get_db)):
    from app.models.tables import User
    users=db.scalars(select(User).order_by(User.id.desc()).limit(300)).all()
    return [{'id':u.id,'name':u.name,'email':u.email,'active':u.active,
             'orders':db.scalar(select(func.count(Order.id)).where(Order.user_id==u.id)),
             'created_at':u.created_at.isoformat()} for u in users]

class TicketStatus(BaseModel):
    status: str = Field(pattern=r'^(open|closed)$')

@router.put('/tickets/{id}/status')
def change_ticket(id:int,body:TicketStatus,admin:Admin=Depends(admin_required),db:Session=Depends(get_db)):
    t=db.get(SupportTicket,id)
    if not t:raise HTTPException(404)
    t.status=body.status
    audit(db,admin,'support.status',f'{id}:{body.status}');db.commit()
    return {'ok':True}

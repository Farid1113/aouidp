from datetime import datetime,timedelta,timezone
from decimal import Decimal
from sqlalchemy import select
from app.models.tables import Order, OrderItem, Payment, Product, PaymentMethod

def test_installer_single_use(installed):
    c,db,h=installed
    assert c.get('/api/setup/status').json()['installed'] is True
    r=c.post('/api/setup/complete',json={'shop_name':'again','username':'other','email':'x@example.com','password':'AnotherStrongPass123'})
    assert r.status_code==409
    assert c.get('/api/admin/dashboard').status_code==200
    assert c.post('/api/admin/categories',json={'name':'Cards','slug':'cards'}).status_code==403

def create_product(c,h,delivery='manual'):
    r=c.post('/api/admin/categories',headers=h,json={'name':'Gaming cards','slug':'gaming-cards'})
    assert r.status_code==201,r.text
    category=r.json()['id']
    p=c.post('/api/admin/products',headers=h,json={'name':'Game Gift Card','slug':'gift-card',
        'category_id':category,'price':'120.00','delivery_type':delivery,'description':'Licensed card'})
    assert p.status_code==201,p.text
    m=c.get('/api/admin/payment-methods').json()[0]
    if m['kind']!='bank_transfer':m=next(x for x in c.get('/api/admin/payment-methods').json() if x['kind']=='bank_transfer')
    updated={**m,'enabled':True,'public_details':{'bank':'Sample Bank','holder':'Licensed Seller','rib':'NOT-A-REAL-RIB'},'instructions':'Review payment manually'}
    assert c.put('/api/admin/payment-methods/'+str(m['id']),headers=h,json=updated).status_code==200
    return p.json()['id'],m['id']

def checkout(c,product_id,method_id,token='unique-test-checkout-001'):
    return c.post('/api/orders/checkout',json={'customer_name':'Test Buyer','email':'buyer@example.org','payment_method_id':method_id,
               'idempotency_key':token,'items':[{'product_id':product_id,'quantity':1}]})

def test_checkout_manual_and_idempotent(installed):
    c,maker,h=installed
    pid,mid=create_product(c,h)
    receipt=checkout(c,pid,mid)
    assert receipt.status_code==201,receipt.text
    response=receipt.json()
    assert response['total']=='120.00'
    ref=response['public_id']; auth={'X-Order-Token':response['access_token']}
    assert c.get('/api/orders/'+ref).status_code==403
    assert c.get('/api/orders/'+ref,headers=auth).status_code==200
    assert c.post('/api/orders/'+ref+'/reference',headers=auth,json={'reference':'TEST-REF-123'}).status_code==200
    assert checkout(c,pid,mid).status_code==409
    with maker() as db:
        oid=db.scalar(select(Order.id).where(Order.public_id==ref))
    confirm=c.post('/api/admin/orders/'+str(oid)+'/status',headers=h,json={'status':'paid'})
    assert confirm.status_code==200,confirm.text
    assert confirm.json()['status']=='processing'
    assert c.post('/api/admin/orders/'+str(oid)+'/status',headers=h,json={'status':'paid'}).json()['idempotent'] is True
    items=c.get('/api/admin/orders/'+str(oid)+'/items').json()
    assert items[0]['delivery_status']=='processing'

def test_real_discount_server_recalculation(installed):
    c,maker,h=installed
    pid,mid=create_product(c,h)
    start=datetime.now(timezone.utc)-timedelta(minutes=10)
    end=datetime.now(timezone.utc)+timedelta(minutes=20)
    r=c.post('/api/admin/discounts',headers=h,json={'name':'Half off','kind':'percent','value':'50',
              'product_id':pid,'starts_at':start.isoformat(),'ends_at':end.isoformat()})
    assert r.status_code==201,r.text
    response=checkout(c,pid,mid,token='special-sale-checkout-001')
    assert response.status_code==201,response.text
    assert response.json()['total']=='60.00'
    with maker() as db:
        d=db.scalar(select(Product).where(Product.id==pid))
        assert d.price==Decimal('120.00')

def test_instant_stock_fail_closed_and_delivery(installed,monkeypatch):
    from app.services import delivery
    from cryptography.fernet import Fernet
    from types import SimpleNamespace
    import hmac,hashlib
    core=SimpleNamespace(validate_code=lambda s:len(s)>=6 and ' ' not in s,
        fingerprint=lambda code,pepper:hmac.new(pepper.encode(),code.encode(),hashlib.sha256).hexdigest())
    monkeypatch.setattr(delivery,'rust_validator',lambda:core)
    monkeypatch.setattr(delivery,'get_settings',lambda:SimpleNamespace(digital_code_key=Fernet.generate_key().decode(), digital_code_hmac_key='x'*40))
    # Keep fernet constant across imported codes / checkout reveal.
    key=Fernet.generate_key().decode()
    monkeypatch.setattr(delivery,'get_settings',lambda:SimpleNamespace(digital_code_key=key,digital_code_hmac_key='x'*40))
    c,maker,h=installed
    pid,mid=create_product(c,h,delivery='instant')
    assert checkout(c,pid,mid,token='instant-first-000001').status_code==409
    codes=c.post('/api/admin/products/'+str(pid)+'/codes',headers=h,json={'codes':['LICENSE-1111','LICENSE-2222','LICENSE-1111']})
    assert codes.status_code==200,codes.text
    assert codes.json()['imported']==2
    r=checkout(c,pid,mid,token='instant-second-00001');assert r.status_code==201,r.text
    with maker() as db: oid=db.scalar(select(Order.id).where(Order.public_id==r.json()['public_id']))
    done=c.post('/api/admin/orders/'+str(oid)+'/status',headers=h,json={'status':'paid'})
    assert done.status_code==200,done.text
    assert done.json()['status']=='delivered'
    order=c.get('/api/orders/'+r.json()['public_id'],headers={'X-Order-Token':r.json()['access_token']}).json()
    assert order['items'][0]['codes']==['LICENSE-1111']
    assert c.get('/api/admin/products/'+str(pid)+'/stock').json()['available']==1
    assert c.post('/api/admin/orders/'+str(oid)+'/status',headers=h,json={'status':'paid'}).json()['idempotent'] is True

def test_discount_expired_not_applied(installed):
    c,maker,h=installed
    pid,mid=create_product(c,h)
    now=datetime.now(timezone.utc)
    d=c.post('/api/admin/discounts',headers=h,json={'name':'Expired','kind':'percent','value':'90',
           'product_id':pid,'starts_at':(now-timedelta(hours=2)).isoformat(),
           'ends_at':(now-timedelta(hours=1)).isoformat()})
    assert d.status_code==201
    r=checkout(c,pid,mid,token='expired-discount-checkout-01')
    assert r.status_code==201
    assert r.json()['total']=='120.00'


def test_manual_delivery_is_authorized_and_encrypted(installed, monkeypatch):
    from app.services import delivery
    from types import SimpleNamespace
    from cryptography.fernet import Fernet
    key=Fernet.generate_key().decode()
    monkeypatch.setattr(delivery,'get_settings',lambda:SimpleNamespace(digital_code_key=key,digital_code_hmac_key='x'*40))
    c,maker,h=installed
    pid,mid=create_product(c,h)
    receipt=checkout(c,pid,mid,token='manual-delivery-checkout-01').json()
    with maker() as db:
        order=db.scalar(select(Order).where(Order.public_id==receipt['public_id']))
        oid=order.id
    assert c.post('/api/admin/orders/'+str(oid)+'/status',headers=h,json={'status':'paid'}).status_code==200
    item=c.get('/api/admin/orders/'+str(oid)+'/items').json()[0]
    denied=c.post('/api/admin/order-items/'+str(item['id'])+'/deliver',json={'message':'LICENSE-PRIVATE'})
    assert denied.status_code==403
    delivered=c.post('/api/admin/order-items/'+str(item['id'])+'/deliver',headers=h,json={'message':'LICENSE-PRIVATE'})
    assert delivered.status_code==200,delivered.text
    r=c.get('/api/orders/'+receipt['public_id'],headers={'X-Order-Token':receipt['access_token']}).json()
    assert r['items'][0]['delivery_message']=='LICENSE-PRIVATE'
    from app.models.tables import ManualDelivery
    with maker() as db:
        stored=db.get(ManualDelivery,item['id']).encrypted_message
        assert 'LICENSE-PRIVATE' not in stored

def test_registered_customer_order_linked_with_csrf(installed):
    c,maker,h=installed
    pid,mid=create_product(c,h)
    r=c.post('/api/auth/customer/register',json={'name':'Registered Buyer','email':'buyer@example.org',
                                                'password':'StrongBuyerPassword123'})
    assert r.status_code==201,r.text
    csrf=r.json()['csrf']
    created=c.post('/api/orders/checkout',headers={'X-CSRF-Token':csrf},json={
        'customer_name':'Registered Buyer','email':'buyer@example.org','payment_method_id':mid,
        'idempotency_key':'registered-customer-00001','items':[{'product_id':pid,'quantity':1}]})
    assert created.status_code==201,created.text
    orders=c.get('/api/orders/mine/list')
    assert orders.status_code==200,orders.text
    assert orders.json()[0]['public_id']==created.json()['public_id']
    assert c.get('/api/orders/'+created.json()['public_id']).status_code==200

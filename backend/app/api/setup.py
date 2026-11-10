from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.db import get_db
from app.core.config import get_settings
from app.core.security import password_hash, throttle
from app.schemas.dto import InstallIn
from app.models.tables import (Installation, Admin, Role, Permission, RolePermission, SiteSetting, PaymentMethod)

router = APIRouter(prefix='/setup', tags=['setup'])

@router.get('/status')
def status(db: Session = Depends(get_db)):
    state = db.get(Installation, 1)
    return {'installed': bool(state and state.installed), 'database': 'postgresql' if get_settings().database_url.startswith('postgresql') else 'sqlite'}

@router.get('/requirements')
def requirements(db: Session = Depends(get_db)):
    from sqlalchemy import text
    db.execute(text('SELECT 1')).scalar_one()
    cfg = get_settings()
    try:
        import digital_core
        rust_available = bool(digital_core.validate_code('TEST-CODE-123'))
    except ImportError: rust_available = False
    return {'database_connection': True, 'database_engine': 'PostgreSQL' if 'postgresql' in cfg.database_url else 'SQLite (development only)',
            'rust_module_available':rust_available,'encryption_key_configured':bool(cfg.digital_code_key), 'hmac_key_configured':len(cfg.digital_code_hmac_key)>=32,
            'secure_cookies':cfg.cookie_secure, 'mode':cfg.app_env,
            'note':'Database credentials are configured on the server in .env, never sent to the installer browser.'}

@router.post('/complete', status_code=201)
def install(payload: InstallIn, request: Request, db: Session = Depends(get_db)):
    throttle('setup:'+str(request.client.host), 5, 3600)
    if not any(c.isupper() for c in payload.password) or not any(c.islower() for c in payload.password) or not any(c.isdigit() for c in payload.password):
        raise HTTPException(422, 'Password must contain uppercase, lowercase, and digits')
    # Lock singleton row; PostgreSQL serializes concurrent installs.
    state = db.scalar(select(Installation).where(Installation.id == 1).with_for_update())
    if state and state.installed: raise HTTPException(409, 'Installer locked: store already installed')
    if db.scalar(select(Admin.id).limit(1)): raise HTTPException(409, 'Admin exists; installer refused')
    if not state:
        state = Installation(id=1, installed=False)
        db.add(state); db.flush()
    roles = {}
    for name in ('super_admin','manager','support'):
        r=Role(name=name); db.add(r); db.flush(); roles[name]=r
    keys=('dashboard.read','products.write','orders.write','payments.write','settings.write','users.write','support.write')
    for key in keys:
        p = Permission(key=key); db.add(p); db.flush()
        db.add(RolePermission(role_id=roles['super_admin'].id, permission_id=p.id))
        if key in ('dashboard.read','products.write','orders.write'):
            db.add(RolePermission(role_id=roles['manager'].id, permission_id=p.id))
        if key in ('dashboard.read','support.write'):
            db.add(RolePermission(role_id=roles['support'].id, permission_id=p.id))
    db.add(Admin(username=payload.username, email=str(payload.email),
                 password_hash=password_hash(payload.password), role_id=roles['super_admin'].id))
    for key,value in {'shop_name':payload.shop_name,'shop_contact':payload.contact,
                      'timezone':payload.timezone,'currency':'MAD','accent':'#6d5dfc',
                      'hero_title':'منتجات رقمية موثوقة','hero_subtitle':'المنتجات والخدمات الرقمية في مكان واحد'}.items():
        db.add(SiteSetting(key=key,value=value))
    for kind, name in [('bank_transfer','تحويل بنكي'),('cash_plus','Cash Plus'),('card','Bank Card'),('paypal','PayPal')]:
        db.add(PaymentMethod(kind=kind,display_name=name,enabled=False,public_details={}))
    state.installed=True; state.completed_at=datetime.now(timezone.utc)
    try: db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(409, 'Could not complete install; check concurrency and DB state')
    return {'installed':True, 'message':'Installation successful. Please sign in at Admin.'}

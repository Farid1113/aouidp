from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import select, or_
from app.core.db import get_db
from app.core.security import (throttle, password_verify, password_hash, make_session,
                               admin_required, customer_required, session_or_401, clear_session)
from app.models.tables import Admin, User, AuthSession, Role, Installation
from app.schemas.dto import Credentials, Register

router=APIRouter(prefix='/auth', tags=['auth'])

@router.post('/admin/login')
def login_admin(creds: Credentials, request: Request, response: Response, db: Session = Depends(get_db)):
    throttle('admin-login:'+request.client.host+':'+creds.login.casefold())
    admin=db.scalar(select(Admin).where(or_(Admin.username==creds.login, Admin.email==creds.login)))
    if not admin or not admin.active or not password_verify(admin.password_hash,creds.password):
        raise HTTPException(401,'Invalid credentials')
    csrf=make_session(db,response,admin_id=admin.id)
    return {'role':db.get(Role,admin.role_id).name,'username':admin.username,'csrf':csrf}

@router.post('/customer/register', status_code=201)
def register(info: Register,request: Request,response: Response,db: Session=Depends(get_db)):
    throttle('register:'+request.client.host, 10, 3600)
    if db.scalar(select(User.id).where(User.email==str(info.email))): raise HTTPException(409,'Email already registered')
    user=User(email=str(info.email),name=info.name,password_hash=password_hash(info.password))
    db.add(user)
    try: db.commit()
    except Exception: db.rollback(); raise HTTPException(409, 'Email already registered')
    return {'csrf':make_session(db,response,user_id=user.id),'name':user.name}

@router.post('/customer/login')
def login_customer(creds: Credentials,request: Request,response: Response,db: Session=Depends(get_db)):
    throttle('customer-login:'+request.client.host+':'+creds.login.casefold())
    user=db.scalar(select(User).where(User.email==creds.login))
    if not user or not user.active or not password_verify(user.password_hash,creds.password):
        raise HTTPException(401,'Invalid credentials')
    return {'csrf':make_session(db,response,user_id=user.id),'name':user.name}

@router.get('/me')
def me(request: Request,db: Session=Depends(get_db)):
    session = session_or_401(request,db)
    if session.admin_id:
        admin=db.get(Admin,session.admin_id)
        if not admin or not admin.active: raise HTTPException(403)
        return {'kind':'admin','name':admin.username,'role':db.get(Role,admin.role_id).name,'csrf':session.csrf_token}
    user=db.get(User,session.user_id)
    if not user or not user.active: raise HTTPException(403)
    return {'kind':'customer','name':user.name,'email':user.email,'csrf':session.csrf_token}

@router.post('/logout')
def logout(request: Request,response: Response,db: Session=Depends(get_db)):
    session_or_401(request,db)
    clear_session(request,response,db)
    return {'success':True}

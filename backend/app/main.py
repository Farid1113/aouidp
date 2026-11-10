from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from app.core.config import get_settings
from app.api import setup, auth, catalog, checkout, admin

cfg = get_settings()
app = FastAPI(title='DIGITAL STORE PRO API', version='0.3.0',
              docs_url='/api/docs' if cfg.app_env!='production' else None,
              redoc_url=None)
app.add_middleware(CORSMiddleware, allow_origins=cfg.origins, allow_credentials=True,
                   allow_methods=['GET','POST','PUT','PATCH','DELETE'],
                   allow_headers=['Content-Type','X-CSRF-Token','X-Order-Token'])

@app.middleware('http')
async def security_headers(request:Request, call_next):
    if request.method not in ('GET','HEAD','OPTIONS'):
        origin=request.headers.get('origin')
        if origin and origin.rstrip('/') not in cfg.origins:
            return JSONResponse({'detail':'Untrusted origin'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['Cache-Control']='no-store' if request.url.path.startswith('/api/auth/') else 'no-cache'
    if cfg.app_env=='production':response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
    return response

@app.get('/api/health')
def health():
    return {'status':'ok'}

for router in [setup.router,auth.router,catalog.router,checkout.router,admin.router]:
    app.include_router(router,prefix='/api')

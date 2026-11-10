import os
import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'backend'))
from app.core.db import Base, get_db
import app.models  # noqa
from app.main import app
from app.core.security import _attempts

@pytest.fixture
def client():
    _attempts.clear()
    engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    maker=sessionmaker(engine,autoflush=False,expire_on_commit=False)
    def db_override():
        with maker() as db: yield db
    app.dependency_overrides[get_db]=db_override
    with TestClient(app) as c: yield c, maker
    app.dependency_overrides.clear()
    engine.dispose()

@pytest.fixture
def installed(client):
    c,maker=client
    payload={'shop_name':'My Digital Store','username':'owner','email':'owner@example.org',
             'password':'VeryStrongAdminPass123','contact':'test@example.org','timezone':'Africa/Casablanca'}
    r=c.post('/api/setup/complete',json=payload)
    assert r.status_code==201,r.text
    login=c.post('/api/auth/admin/login',json={'login':'owner','password':payload['password']})
    assert login.status_code==200,login.text
    csrf=login.json()['csrf']
    return c,maker,{'X-CSRF-Token':csrf}

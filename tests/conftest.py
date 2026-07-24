import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import pytest
from app import app as flask_app, db
from models import Kullanici

@pytest.fixture
def app():
    # Use testing config
    flask_app.config.update({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "WTF_CSRF_ENABLED": False,
        "JWT_COOKIE_CSRF_PROTECT": False
    })
    
    with flask_app.app_context():
        db.create_all()
        # Create a test admin user
        from werkzeug.security import generate_password_hash
        admin = Kullanici(
            kullanici_adi="test_admin",
            ad_soyad="Test Admin",
            eposta="admin@test.com",
            sifre_hash=generate_password_hash("test_password"),
            rol="admin"
        )
        db.session.add(admin)
        db.session.commit()
        
        yield flask_app
        
        db.session.remove()
        db.drop_all()

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def auth_client(client):
    # Log in as test_admin and save the JWT cookie
    response = client.post('/login', data={
        "kullanici_adi": "test_admin",
        "sifre": "test_password"
    })
    return client

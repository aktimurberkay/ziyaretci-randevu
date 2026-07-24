from app import app, db
from models import Kullanici
from werkzeug.security import generate_password_hash

with app.app_context():
    admin = Kullanici.query.filter_by(kullanici_adi='admin').first()
    if admin:
        admin.sifre_hash = generate_password_hash('admin123')
        db.session.commit()
        print("Admin password updated to admin123")

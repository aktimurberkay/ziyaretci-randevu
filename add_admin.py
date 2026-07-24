from app import app, db
from models import Kullanici
from werkzeug.security import generate_password_hash

with app.app_context():
    if not Kullanici.query.filter_by(eposta="yonetici2@vega.com").first():
        yeni_yonetici = Kullanici(
            ad_soyad="Cemal Yönetici", 
            eposta="yonetici2@vega.com", 
            sifre_hash=generate_password_hash("123"), 
            rol="admin", 
            departman="Pazarlama",
            kullanici_adi="cemaly"
        )
        db.session.add(yeni_yonetici)
        db.session.commit()
        print("2. Yönetici eklendi.")
    else:
        print("2. Yönetici zaten mevcut.")

from flask import Flask, render_template, request, redirect, url_for, flash, session, jsonify
from flask_jwt_extended import JWTManager, create_access_token, jwt_required as _jwt_required, current_user, set_access_cookies, unset_jwt_cookies, verify_jwt_in_request
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import os
from models import db, Kullanici, Ziyaretci, Randevu, Mesaj, now_in_turkey, TakvimEtkinlik, AuditLog, ZiyaretciMailGecmisi, KaraListe, Bildirim
from utils import tc_kimlik_gecerli_mi, send_email, sanitize_text
from audit_utils import log_islem
from auth_utils import (
    rol_gerekli,
    girise_izin_var_mi,
    basarisiz_deneme_kaydet,
    basarili_giris_sonrasi_temizle,
    KILIT_SURESI_SN,
)
from datetime import datetime, timedelta, time
from dotenv import load_dotenv
import os
import secrets
from flask_mail import Mail, Message
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import threading
import io
import csv
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import openpyxl

load_dotenv()

app = Flask(__name__)

_secret_key = os.environ.get('SECRET_KEY')
if not _secret_key:
    # .env dosyası yoksa/SECRET_KEY tanımlı değilse uygulama yine de açılabilsin diye
    # geçici bir anahtar üretilir. UYARI: Bu, her sunucu yeniden başlatıldığında
    # değişir ve tüm oturumları geçersiz kılar. Gerçek kullanımda .env.example
    # dosyasını kopyalayıp .env olarak kaydedin ve kalıcı bir SECRET_KEY girin.
    print("UYARI: SECRET_KEY ortam değişkeni bulunamadı, geçici bir anahtar üretildi. "
          ".env dosyanızda SECRET_KEY tanımlayın (bkz. .env.example).")
    _secret_key = secrets.token_hex(32)

app.config['SECRET_KEY'] = _secret_key
# NOT: Göreli 'sqlite:///randevu.db' yolu Flask-SQLAlchemy tarafından proje kök
# dizinine değil 'instance/' klasörüne göre çözümlenir. Bu, "hangi db dosyası
# gerçek" karışıklığına yol açabildiği için burada mutlak yol kullanılıyor —
# uygulama artık her zaman bu dosyanın yanındaki randevu.db'yi kullanır.
_db_yolu = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'randevu.db')
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{_db_yolu}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

app.config['JWT_TOKEN_LOCATION'] = ['cookies']
app.config['JWT_COOKIE_CSRF_PROTECT'] = False
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = timedelta(minutes=30)

app.config['UPLOAD_FOLDER'] = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static/uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024 # Maksimum 16MB dosya boyutu

# E-Posta Ayarları
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')

mail = Mail(app)

# Hız Sınırlayıcı (Rate Limiter)
redis_url = os.environ.get("REDIS_URL")
limiter = Limiter(
    get_remote_address,
    app=app,
    storage_uri=redis_url if redis_url else "memory://"
)

_debug_modu = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'

db.init_app(app)

jwt = JWTManager(app)

def login_required(func):
    return _jwt_required()(func)

@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
    identity = jwt_data["sub"]
    return Kullanici.query.get(int(identity))

class Anonymous:
    is_authenticated = False
    rol = None

@app.before_request
def try_verify_jwt():
    try:
        verify_jwt_in_request(optional=True)
    except Exception:
        pass

@app.context_processor
def inject_user():
    user = None
    try:
        user = current_user
    except Exception:
        pass
    return dict(current_user=user if user else Anonymous())

@jwt.unauthorized_loader
def unauthorized_callback(callback):
    return redirect(url_for('login'))

@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return redirect(url_for('login'))

@app.context_processor
def inject_now():
    return {'datetime': datetime}

import json as _json

@app.template_filter('from_json')
def from_json_filter(value):
    """JSON string'i Python dict'e çevirir."""
    try:
        return _json.loads(value)
    except (TypeError, ValueError, _json.JSONDecodeError):
        return value

@app.route('/', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def landing():
    if request.method == 'GET' and current_user and getattr(current_user, 'is_authenticated', False):
        resp = redirect(url_for('landing'))
        unset_jwt_cookies(resp)
        return resp
        
    personeller = Kullanici.query.filter_by(rol='personel').all()
    yoneticiler = Kullanici.query.filter_by(rol='admin').all() # İsteğe göre sekreterler de eklenebilir
    gorusulecek_kisiler = personeller + yoneticiler
    
    if request.method == 'POST':
        ad_soyad = sanitize_text(request.form.get('ad_soyad'))
        tc_kimlik = request.form.get('tc_kimlik')
        eposta = request.form.get('eposta')
        sirket = sanitize_text(request.form.get('sirket'))
        personel_id = request.form.get('personel_id')
        randevu_tarihi_str = request.form.get('randevu_tarihi')
        randevu_saati_str = request.form.get('randevu_saati')
        notlar = sanitize_text(request.form.get('notlar'))
        kvkk_onayi = request.form.get('kvkk_onayi') == 'on'
        
        if tc_kimlik:
            gecerli_mi, mesaj = tc_kimlik_gecerli_mi(tc_kimlik)
            if not gecerli_mi:
                flash(mesaj, 'danger')
                return redirect(url_for('landing'))
                
            # Kara Liste Kontrolü (TC)
            kl_tc = KaraListe.query.filter_by(tc_kimlik=tc_kimlik).first()
            if kl_tc:
                flash('Güvenlik sebebiyle randevu talebiniz gerçekleştirilemiyor.', 'danger')
                return redirect(url_for('landing'))
                
        # Kara Liste Kontrolü (E-posta)
        if eposta:
            kl_mail = KaraListe.query.filter_by(eposta=eposta).first()
            if kl_mail:
                flash('Güvenlik sebebiyle randevu talebiniz gerçekleştirilemiyor.', 'danger')
                return redirect(url_for('landing'))
        
        # Tarih ve saat bilgisini birleştir
        if randevu_tarihi_str and randevu_saati_str:
            tarih_saat_str = f"{randevu_tarihi_str}T{randevu_saati_str}"
            try:
                tarih_saat = datetime.strptime(tarih_saat_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                flash("Geçersiz tarih veya saat seçimi.", "danger")
                return redirect(url_for('landing'))
        else:
            flash("Lütfen geçerli bir randevu tarihi ve saati seçin.", "danger")
            return redirect(url_for('landing'))
        
        # Ziyaretçiyi bul veya oluştur
        ziyaretci = Ziyaretci.query.filter_by(tc_kimlik=tc_kimlik).first() if tc_kimlik else None
        if not ziyaretci:
            ziyaretci = Ziyaretci(ad_soyad=ad_soyad, tc_kimlik=tc_kimlik, sirket=sirket, eposta=eposta, kvkk_onayi=kvkk_onayi)
            db.session.add(ziyaretci)
            db.session.commit() # ID almak için commit ediyoruz
        else:
            # Varsa bile yeni girilen şirket ve e-posta bilgilerini güncelleyelim
            ziyaretci.sirket = sirket
            ziyaretci.eposta = eposta
            db.session.commit()
            
        yeni_randevu = Randevu(
            ziyaretci_id=ziyaretci.id,
            personel_id=personel_id,
            tarih_saat=tarih_saat,
            notlar=notlar,
            durum='Bekliyor'
        )
        db.session.add(yeni_randevu)
        b = Bildirim(kullanici_id=personel_id, icerik=f"Yeni randevu talebi: {ad_soyad}")
        db.session.add(b)
        
        # Sekreterine de bildirim gönder
        sekreterler = Kullanici.query.filter_by(bagli_yonetici_id=personel_id, rol='sekreter').all()
        for sekr in sekreterler:
            sb = Bildirim(kullanici_id=sekr.id, icerik=f"Yöneticiniz için yeni randevu talebi: {ad_soyad}")
            db.session.add(sb)
            
        db.session.commit()
        
        personel = Kullanici.query.get(personel_id)
        if personel:
            body = f"Sayın {personel.ad_soyad},\n\n{ad_soyad} isimli ziyaretçi sizinle {tarih_saat.strftime('%d.%m.%Y %H:%M')} tarihi için randevu talep etmiştir.\n\nSisteme giriş yaparak onaylayabilir veya reddedebilirsiniz."
            send_email(
                to_email=personel.eposta,
                subject="Yeni Randevu Talebi",
                body=body
            )
        
        flash('Randevu talebiniz başarıyla iletildi. İlgili personel onayladığında resepsiyona bildirilecektir.', 'success')
        return redirect(url_for('landing'))
        
    return render_template('landing.html', personeller=gorusulecek_kisiler)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user and getattr(current_user, 'is_authenticated', False):
        return redirect(url_for('dashboard'))
        
    if request.method == 'POST':
        kullanici_adi = sanitize_text(request.form.get('kullanici_adi'))
        sifre = request.form.get('sifre')
        ip = request.remote_addr

        if not girise_izin_var_mi(kullanici_adi, ip):
            kilit_dakika = KILIT_SURESI_SN // 60
            flash(f'Çok fazla başarısız giriş denemesi yapıldı. Lütfen {kilit_dakika} dakika sonra tekrar deneyin.', 'danger')
            return render_template('login.html')

        user = Kullanici.query.filter_by(kullanici_adi=kullanici_adi).first()
        if user and check_password_hash(user.sifre_hash, sifre):
            basarili_giris_sonrasi_temizle(kullanici_adi, ip)
            access_token = create_access_token(identity=str(user.id))
            resp = redirect(url_for('dashboard'))
            set_access_cookies(resp, access_token)
            return resp
        else:
            basarisiz_deneme_kaydet(kullanici_adi, ip)
            flash('Geçersiz kullanıcı adı veya şifre.', 'danger')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    resp = redirect(url_for('login'))
    unset_jwt_cookies(resp)
    return resp

@app.route('/dashboard')
@login_required
def dashboard():
    # Otomatik Zaman Aşımı Kontrolü
    simdi = now_in_turkey()
    gecmis_randevular = Randevu.query.filter(Randevu.durum == 'Bekliyor', Randevu.tarih_saat < simdi).all()
    if gecmis_randevular:
        for r in gecmis_randevular:
            r.durum = 'Zaman Aşımı'
        db.session.commit()

    istatistikler = None
    gunluk_veriler = []
    # Rol bazlı randevu sorgusu
    if current_user.rol == 'admin':
        randevular = Randevu.query.order_by(Randevu.tarih_saat.desc()).all()
        # Admin İstatistikleri
        bekleyen = Randevu.query.filter_by(durum='Bekliyor').count()
        onaylandi = Randevu.query.filter_by(durum='Onaylandı').count()
        reddedildi = Randevu.query.filter_by(durum='Reddedildi').count()
        tamamlandi = Randevu.query.filter_by(durum='Tamamlandı').count()
        iceride = Randevu.query.filter_by(durum='İçeride').count()
        bekleme_salonunda = Randevu.query.filter_by(durum='Bekleme Salonunda').count()
        istatistikler = {
            'Bekliyor': bekleyen,
            'Onaylandı': onaylandi,
            'Reddedildi': reddedildi,
            'Tamamlandı': tamamlandi,
            'İçeride': iceride,
            'Bekleme': bekleme_salonunda
        }
        
        # Son 7 Gün verileri
        bugun = now_in_turkey().date()
        for i in range(6, -1, -1):
            g = bugun - timedelta(days=i)
            bas = datetime.combine(g, time.min)
            bit = datetime.combine(g, time.max)
            sayi = Randevu.query.filter(Randevu.tarih_saat >= bas, Randevu.tarih_saat <= bit).count()
            gunluk_veriler.append({'tarih': g.strftime('%d.%m'), 'sayi': sayi})
            
    elif current_user.rol == 'resepsiyon':
        # Resepsiyonist o günün onaylanmışlarını veya bekleyenleri görür
        randevular = Randevu.query.order_by(Randevu.tarih_saat.asc()).all()
    elif current_user.rol == 'sekreter':
        # Sekreterin oluşturdukları VEYA bağlı olduğu yöneticinin randevuları
        if current_user.bagli_yonetici_id:
            randevular = Randevu.query.filter(
                db.or_(Randevu.olusturan_id == current_user.id, Randevu.personel_id == current_user.bagli_yonetici_id)
            ).order_by(Randevu.tarih_saat.asc()).all()
        else:
            randevular = Randevu.query.filter_by(olusturan_id=current_user.id).order_by(Randevu.tarih_saat.asc()).all()
    else:
        # Personel sadece kendi randevularını görür
        randevular = Randevu.query.filter_by(personel_id=current_user.id).order_by(Randevu.tarih_saat.asc()).all()
        
    personeller = Kullanici.query.filter(Kullanici.rol.in_(['personel', 'admin', 'sekreter'])).all()
    bugun = now_in_turkey().date()
        
    return render_template('dashboard.html', randevular=randevular, personeller=personeller, bugun=bugun, istatistikler=istatistikler, gunluk_veriler=gunluk_veriler)

@app.route('/hizli-kayit', methods=['POST'])
@login_required
@rol_gerekli('resepsiyon', 'sekreter')
def hizli_kayit():
    ad_soyad = sanitize_text(request.form.get('ad_soyad'))
    tc_kimlik = request.form.get('tc_kimlik')
    sirket = sanitize_text(request.form.get('sirket'))
    personel_id = request.form.get('personel_id')
    
    islem_tipi = request.form.get('islem_tipi', 'iceri_al')
    
    if tc_kimlik:
        gecerli_mi, mesaj = tc_kimlik_gecerli_mi(tc_kimlik)
        if not gecerli_mi:
            flash(mesaj, 'danger')
            return redirect(url_for('dashboard'))
    
    ziyaretci = Ziyaretci.query.filter_by(tc_kimlik=tc_kimlik).first() if tc_kimlik else None
    if not ziyaretci:
        ziyaretci = Ziyaretci(ad_soyad=ad_soyad, tc_kimlik=tc_kimlik, sirket=sirket)
        db.session.add(ziyaretci)
        db.session.commit()
        
    yeni_randevu = Randevu(
        ziyaretci_id=ziyaretci.id,
        personel_id=personel_id,
        olusturan_id=current_user.id,
        tarih_saat=now_in_turkey(),
        durum='İçeride' if islem_tipi == 'iceri_al' else 'Bekleme Salonunda',
        giris_saati=now_in_turkey() if islem_tipi == 'iceri_al' else None,
        notlar="Hızlı Kayıt"
    )
    db.session.add(yeni_randevu)
    db.session.flush()
    log_islem('randevu_hizli_kayit', hedef_tablo='randevu', hedef_id=yeni_randevu.id,
               detay={'ziyaretci': ad_soyad, 'personel_id': personel_id, 'islem_tipi': islem_tipi})
    db.session.commit()
    
    if islem_tipi == 'iceri_al':
        flash('Hızlı ziyaretçi kaydı oluşturuldu ve doğrudan içeri alındı.', 'success')
        b = Bildirim(kullanici_id=personel_id, icerik=f"Hızlı kayıt: {ad_soyad} doğrudan içeri alındı.")
        db.session.add(b)
    else:
        flash('Hızlı ziyaretçi kaydı oluşturuldu ve bekleme salonuna alındı.', 'success')
        b = Bildirim(kullanici_id=personel_id, icerik=f"Hızlı kayıt: {ad_soyad} bekleme salonuna alındı.")
        db.session.add(b)
        
    db.session.commit()
    return redirect(url_for('dashboard'))

@app.route('/durum-guncelle/<int:randevu_id>', methods=['POST'])
@login_required
def durum_guncelle(randevu_id):
    randevu = Randevu.query.get_or_404(randevu_id)
    islem = request.form.get('islem')
    
    eski_durum = randevu.durum

    if islem == 'onayla' and (current_user.id == randevu.personel_id or current_user.rol == 'admin' or (current_user.rol == 'sekreter' and current_user.bagli_yonetici_id == randevu.personel_id)):
        randevu.durum = 'Onaylandı'
        log_islem('randevu_onay', hedef_tablo='randevu', hedef_id=randevu.id,
                   detay={'eski_durum': eski_durum, 'yeni_durum': randevu.durum})
        
        # Personel onayladığında Resepsiyon ve Adminlere bildirim gitsin
        hedef_kullanicilar = Kullanici.query.filter(Kullanici.rol.in_(['resepsiyon', 'admin'])).all()
        for hk in hedef_kullanicilar:
            b = Bildirim(kullanici_id=hk.id, icerik=f"{randevu.personel.ad_soyad}, {randevu.ziyaretci_bilgisi.ad_soyad} isimli ziyaretçinin randevusunu ONAYLADI.")
            db.session.add(b)
            
        b = Bildirim(kullanici_id=randevu.personel_id, icerik=f"{randevu.ziyaretci_bilgisi.ad_soyad} isimli ziyaretçinizin randevusu onaylandı.")
        db.session.add(b)
        if randevu.ziyaretci_bilgisi.eposta:
            body = f"Sayın {randevu.ziyaretci_bilgisi.ad_soyad},\n\n{randevu.personel.ad_soyad} ile {randevu.tarih_saat.strftime('%d.%m.%Y')} tarihinde saat {randevu.tarih_saat.strftime('%H:%M')} randevu talebiniz onaylanmıştır.\n\nZiyaretinizde görüşmek üzere."
            send_email(
                to_email=randevu.ziyaretci_bilgisi.eposta,
                subject="Randevunuz Onaylandı",
                body=body
            )
            flash(f"Ziyaretçiye ({randevu.ziyaretci_bilgisi.eposta}) onay e-postası başarıyla gönderildi.", 'info')
    elif islem == 'reddet' and (current_user.id == randevu.personel_id or current_user.rol == 'admin' or (current_user.rol == 'sekreter' and current_user.bagli_yonetici_id == randevu.personel_id)):
        randevu.durum = 'Reddedildi'
        red_aciklamasi = sanitize_text(request.form.get('red_aciklamasi'))
        if red_aciklamasi:
            randevu.red_aciklamasi = red_aciklamasi
        log_islem('randevu_red', hedef_tablo='randevu', hedef_id=randevu.id,
                   detay={'eski_durum': eski_durum, 'yeni_durum': randevu.durum, 'aciklama': red_aciklamasi})
        
        # Personel reddettiğinde Resepsiyon ve Adminlere bildirim gitsin
        hedef_kullanicilar = Kullanici.query.filter(Kullanici.rol.in_(['resepsiyon', 'admin'])).all()
        for hk in hedef_kullanicilar:
            b = Bildirim(kullanici_id=hk.id, icerik=f"{randevu.personel.ad_soyad}, {randevu.ziyaretci_bilgisi.ad_soyad} isimli ziyaretçinin randevusunu REDDETTİ.")
            db.session.add(b)
            
        if randevu.ziyaretci_bilgisi.eposta:
            body = f"Sayın {randevu.ziyaretci_bilgisi.ad_soyad},\n\n{randevu.personel.ad_soyad} ile {randevu.tarih_saat.strftime('%d.%m.%Y %H:%M')} tarihindeki randevu talebiniz üzülerek reddedilmiştir."
            if red_aciklamasi:
                body += f"\n\nRed Sebebi: {red_aciklamasi}"
            send_email(
                to_email=randevu.ziyaretci_bilgisi.eposta,
                subject="Randevunuz Reddedildi",
                body=body
            )
            flash(f"Ziyaretçiye ({randevu.ziyaretci_bilgisi.eposta}) ret e-postası başarıyla gönderildi.", 'info')
    elif islem == 'beklemeye_al' and current_user.rol in ['resepsiyon', 'admin', 'sekreter']:
        randevu.durum = 'Bekleme Salonunda'
        log_islem('randevu_beklemeye_al', hedef_tablo='randevu', hedef_id=randevu.id,
                   detay={'eski_durum': eski_durum, 'yeni_durum': randevu.durum})
        b = Bildirim(kullanici_id=randevu.personel_id, icerik=f"Ziyaretçiniz {randevu.ziyaretci_bilgisi.ad_soyad} bekleme salonuna alındı.")
        db.session.add(b)
    elif islem == 'iceri_cagir' and (current_user.id == randevu.personel_id or current_user.rol == 'admin' or (current_user.rol == 'sekreter' and current_user.bagli_yonetici_id == randevu.personel_id)):
        if randevu.durum == 'Bekleme Salonunda':
            randevu.durum = 'İçeride'
            randevu.giris_saati = now_in_turkey()
            log_islem('randevu_iceri_cagir', hedef_tablo='randevu', hedef_id=randevu.id,
                       detay={'eski_durum': eski_durum, 'yeni_durum': randevu.durum})
        else:
            flash('Ziyaretçi bekleme salonunda değil.', 'danger')
            return redirect(url_for('dashboard'))
    elif islem == 'giris' and current_user.rol in ['resepsiyon', 'admin']:
        if randevu.durum in ['Onaylandı', 'Bekleme Salonunda']:
            randevu.durum = 'İçeride'
            randevu.giris_saati = now_in_turkey()
            log_islem('randevu_giris', hedef_tablo='randevu', hedef_id=randevu.id,
                       detay={'eski_durum': eski_durum, 'yeni_durum': randevu.durum})
            b = Bildirim(kullanici_id=randevu.personel_id, icerik=f"Ziyaretçiniz {randevu.ziyaretci_bilgisi.ad_soyad} kuruma giriş yaptı.")
            db.session.add(b)
        else:
            flash('Sadece onaylanmış veya bekleme salonundaki ziyaretçilere giriş verilebilir!', 'danger')
            return redirect(url_for('dashboard'))
    elif islem == 'cikis' and current_user.rol in ['resepsiyon', 'admin']:
        randevu.durum = 'Tamamlandı'
        randevu.cikis_saati = now_in_turkey()
        log_islem('randevu_cikis', hedef_tablo='randevu', hedef_id=randevu.id,
                   detay={'eski_durum': eski_durum, 'yeni_durum': randevu.durum})
    else:
        flash('Bu işlemi yapmaya yetkiniz yok.', 'danger')
        return redirect(url_for('dashboard'))
        
    db.session.commit()
    flash(f'Randevu durumu güncellendi: {randevu.durum}', 'success')
    return redirect(url_for('dashboard'))

@app.route('/personel-aktif-durum', methods=['POST'])
@login_required
def personel_aktif_durum():
    yeni_durum = request.form.get('aktif_durum')
    if yeni_durum in ['Müsait', 'Meşgul', 'Toplantıda', 'Dışarıda']:
        current_user.aktif_durum = yeni_durum
        db.session.commit()
        flash(f'Durumunuz güncellendi: {yeni_durum}', 'success')
        return redirect(url_for('dashboard'))

@app.route('/randevu-duzenle/<int:id>', methods=['POST'])
@login_required
def randevu_duzenle(id):
    randevu = Randevu.query.get_or_404(id)
    
    # Sadece onaylı randevular düzenlenebilir
    if randevu.durum != 'Onaylandı':
        flash('Sadece onaylanmış randevular düzenlenebilir.', 'danger')
        return redirect(url_for('dashboard'))
        
    # Yetki kontrolü (Kendi randevusu veya admin/resepsiyon)
    if current_user.id != randevu.personel_id and current_user.rol not in ['admin', 'resepsiyon', 'sekreter']:
        flash('Bu randevuyu düzenleme yetkiniz yok.', 'danger')
        return redirect(url_for('dashboard'))
        
    yeni_tarih_str = request.form.get('tarih_saat')
    yeni_notlar = sanitize_text(request.form.get('notlar'))
    
    try:
        yeni_tarih = datetime.strptime(yeni_tarih_str, '%Y-%m-%dT%H:%M')
        
        eski_detay = {
            'tarih_saat': randevu.tarih_saat.strftime('%Y-%m-%d %H:%M'),
            'notlar': randevu.notlar
        }
        
        randevu.tarih_saat = yeni_tarih
        randevu.notlar = yeni_notlar
        randevu.son_guncelleme_tarihi = datetime.now()
        randevu.guncelleyen_kullanici_id = current_user.id
        
        yeni_detay = {
            'tarih_saat': randevu.tarih_saat.strftime('%Y-%m-%d %H:%M'),
            'notlar': randevu.notlar
        }
        
        log_islem('randevu_duzenle', hedef_tablo='randevu', hedef_id=randevu.id, detay={'eski': eski_detay, 'yeni': yeni_detay})
        db.session.commit()
        flash('Randevu başarıyla güncellendi.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash('Geçersiz tarih formatı.', 'danger')
        
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/randevu-sil/<int:id>', methods=['POST'])
@login_required
def randevu_sil(id):
    randevu = Randevu.query.get_or_404(id)
    
    # Yetki kontrolü
    yetkili = (
        current_user.id == randevu.personel_id or
        current_user.rol in ['admin', 'resepsiyon'] or
        (current_user.rol == 'sekreter' and current_user.bagli_yonetici_id == randevu.personel_id)
    )

    if not yetkili:
        flash('Bu randevuyu silme yetkiniz yok.', 'danger')
        return redirect(request.referrer or url_for('dashboard'))
        
    # İlişkili verileri silmeden ÖNCE al (lazy load sorununu önlemek için)
    ziyaretci_adi = randevu.ziyaretci_bilgisi.ad_soyad if randevu.ziyaretci_bilgisi else 'Bilinmiyor'
    personel_adi = randevu.personel.ad_soyad if randevu.personel else 'Bilinmiyor'
    randevu_tarihi = randevu.tarih_saat.strftime('%d.%m.%Y %H:%M')
    randevu_durumu = randevu.durum
    
    detay = {
        'islem': 'Randevu silindi',
        'ziyaretci': ziyaretci_adi,
        'personel': personel_adi,
        'tarih': randevu_tarihi,
        'durum': randevu_durumu,
        'silen': current_user.ad_soyad
    }
    
    log_islem('randevu_sil', hedef_tablo='randevu', hedef_id=id, detay=detay)
    
    db.session.delete(randevu)
    db.session.commit()
    flash('Randevu başarıyla silindi.', 'success')
    return redirect(request.referrer or url_for('dashboard'))

@app.route('/yeni-randevu', methods=['GET', 'POST'])
@login_required
def yeni_randevu():
    personeller = Kullanici.query.filter(Kullanici.rol.in_(['personel', 'admin', 'sekreter'])).order_by(Kullanici.ad_soyad.asc()).all()

    if request.method == 'POST':
        ad_soyad = sanitize_text(request.form.get('ad_soyad'))
        tc_kimlik = request.form.get('tc_kimlik')
        eposta = request.form.get('eposta')
        sirket = sanitize_text(request.form.get('sirket'))
        tarih_saat_str = request.form.get('tarih_saat')
        notlar = sanitize_text(request.form.get('notlar'))

        kendi_adina = current_user.rol == 'personel'
        if kendi_adina:
            personel_id = current_user.id
        else:
            personel_id = request.form.get('personel_id')

        if not ad_soyad or not tarih_saat_str or not personel_id:
            flash('Lütfen zorunlu alanları doldurun.', 'danger')
            return redirect(url_for('yeni_randevu'))

        if tc_kimlik:
            gecerli_mi, mesaj = tc_kimlik_gecerli_mi(tc_kimlik)
            if not gecerli_mi:
                flash(mesaj, 'danger')
                return redirect(url_for('yeni_randevu'))

        try:
            tarih_saat = datetime.strptime(tarih_saat_str, '%Y-%m-%dT%H:%M')
        except ValueError:
            flash('Tarih/saat formatı geçersiz.', 'danger')
            return redirect(url_for('yeni_randevu'))

        ziyaretci = Ziyaretci.query.filter_by(tc_kimlik=tc_kimlik).first() if tc_kimlik else None
        if not ziyaretci:
            ziyaretci = Ziyaretci(ad_soyad=ad_soyad, tc_kimlik=tc_kimlik, sirket=sirket, eposta=eposta)
            db.session.add(ziyaretci)
            db.session.commit()

        # Personel kendi ziyaretçisi için randevu oluşturuyorsa onay beklemeden otomatik onaylanır.
        # Sekreter/Resepsiyon/Admin başkası adına oluşturuyorsa ilgili personelin onayı gerekir.
        durum = 'Onaylandı' if kendi_adina else 'Bekliyor'

        yeni = Randevu(
            ziyaretci_id=ziyaretci.id,
            personel_id=personel_id,
            olusturan_id=current_user.id,
            tarih_saat=tarih_saat,
            notlar=notlar,
            durum=durum
        )
        db.session.add(yeni)
        db.session.commit()

        if kendi_adina:
            flash('Randevu oluşturuldu ve otomatik onaylandı.', 'success')
        else:
            flash('Randevu talebi oluşturuldu, ilgili personelin onayı bekleniyor.', 'success')
        return redirect(url_for('dashboard'))

    return render_template('yeni_randevu.html', personeller=personeller)


@app.route('/ziyaretciler')
@login_required
@rol_gerekli('admin', 'resepsiyon', 'sekreter')
def ziyaretciler():
    arama = request.args.get('q', '').strip()
    filtre = request.args.get('filtre', 'tumu')  # tumu | icerde

    query = Ziyaretci.query
    if arama:
        like = f'%{arama}%'
        query = query.filter(
            db.or_(
                Ziyaretci.ad_soyad.ilike(like),
                Ziyaretci.tc_kimlik.ilike(like),
                Ziyaretci.sirket.ilike(like)
            )
        )

    ziyaretciler_listesi = query.order_by(Ziyaretci.ad_soyad.asc()).all()

    kayitlar = []
    for z in ziyaretciler_listesi:
        son_randevu = Randevu.query.filter_by(ziyaretci_id=z.id).order_by(Randevu.tarih_saat.desc()).first()
        icerde_mi = son_randevu is not None and son_randevu.durum == 'İçeride'

        if filtre == 'icerde' and not icerde_mi:
            continue

        kayitlar.append({
            'ziyaretci': z,
            'son_randevu': son_randevu,
            'icerde_mi': icerde_mi,
            'ziyaret_sayisi': len(z.randevular)
        })

    return render_template('ziyaretciler.html', kayitlar=kayitlar, arama=arama, filtre=filtre)


@app.route('/personel-yonetimi', methods=['GET', 'POST'])
@login_required
@rol_gerekli('admin')
def personel_yonetimi():
    if request.method == 'POST':
        ad_soyad = sanitize_text(request.form.get('ad_soyad'))
        kullanici_adi = sanitize_text(request.form.get('kullanici_adi'))
        eposta = request.form.get('eposta')
        sifre = request.form.get('sifre')
        rol = request.form.get('rol')
        departman = sanitize_text(request.form.get('departman'))
        bagli_yonetici_id = request.form.get('bagli_yonetici_id')
        if rol != 'sekreter':
            bagli_yonetici_id = None
        elif bagli_yonetici_id == '':
            bagli_yonetici_id = None

        if not ad_soyad or not kullanici_adi or not eposta or not sifre or not rol:
            flash('Lütfen tüm zorunlu alanları doldurun.', 'danger')
            return redirect(url_for('personel_yonetimi'))

        if Kullanici.query.filter_by(eposta=eposta).first():
            flash('Bu e-posta adresi zaten kayıtlı.', 'danger')
            return redirect(url_for('personel_yonetimi'))
            
        if Kullanici.query.filter_by(kullanici_adi=kullanici_adi).first():
            flash('Bu kullanıcı adı zaten alınmış.', 'danger')
            return redirect(url_for('personel_yonetimi'))

        yeni_kullanici = Kullanici(
            ad_soyad=ad_soyad,
            kullanici_adi=kullanici_adi,
            eposta=eposta,
            sifre_hash=generate_password_hash(sifre),
            rol=rol,
            departman=departman,
            bagli_yonetici_id=bagli_yonetici_id
        )
        
        if 'profil_resmi' in request.files:
            file = request.files['profil_resmi']
            if file and file.filename != '':
                filename = secure_filename(f"{kullanici_adi}_{file.filename}")
                file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
                yeni_kullanici.profil_resmi = filename

        db.session.add(yeni_kullanici)
        db.session.flush()  # commit'ten önce yeni_kullanici.id'yi alabilmek için
        log_islem('personel_ekle', hedef_tablo='kullanici', hedef_id=yeni_kullanici.id,
                   detay={'ad_soyad': ad_soyad, 'kullanici_adi': kullanici_adi, 'eposta': eposta, 'rol': rol})
        db.session.commit()
        flash(f'{ad_soyad} başarıyla eklendi.', 'success')
        return redirect(url_for('personel_yonetimi'))

    kullanicilar = Kullanici.query.order_by(Kullanici.ad_soyad.asc()).all()
    yoneticiler = Kullanici.query.filter_by(rol='admin').order_by(Kullanici.ad_soyad.asc()).all()
    return render_template('personel_yonetimi.html', kullanicilar=kullanicilar, yoneticiler=yoneticiler)

@app.route('/personel-duzenle/<int:kullanici_id>', methods=['POST'])
@login_required
@rol_gerekli('admin')
def personel_duzenle(kullanici_id):
    kullanici = Kullanici.query.get_or_404(kullanici_id)
    
    kullanici.ad_soyad = sanitize_text(request.form.get('ad_soyad', kullanici.ad_soyad))
    kullanici.kullanici_adi = sanitize_text(request.form.get('kullanici_adi', kullanici.kullanici_adi))
    kullanici.eposta = request.form.get('eposta', kullanici.eposta)
    kullanici.rol = request.form.get('rol', kullanici.rol)
    kullanici.departman = sanitize_text(request.form.get('departman', kullanici.departman))
    
    bagli_yonetici_id = request.form.get('bagli_yonetici_id')
    if kullanici.rol == 'sekreter' and bagli_yonetici_id:
        kullanici.bagli_yonetici_id = bagli_yonetici_id
    else:
        kullanici.bagli_yonetici_id = None
    
    sifre = request.form.get('sifre')
    if sifre:
        kullanici.sifre_hash = generate_password_hash(sifre)
        
    if 'profil_resmi' in request.files:
        file = request.files['profil_resmi']
        if file and file.filename != '':
            filename = secure_filename(f"{kullanici.kullanici_adi}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            kullanici.profil_resmi = filename
            
    db.session.commit()
    flash(f'{kullanici.ad_soyad} başarıyla güncellendi.', 'success')
    return redirect(url_for('personel_yonetimi'))

@app.route('/personel-sil/<int:kullanici_id>', methods=['POST'])
@login_required
@rol_gerekli('admin')
def personel_sil(kullanici_id):
    if kullanici_id == current_user.id:
        flash('Kendi hesabınızı silemezsiniz.', 'danger')
        return redirect(url_for('personel_yonetimi'))

    kullanici = Kullanici.query.get_or_404(kullanici_id)
    if kullanici.rol == 'admin' and Kullanici.query.filter_by(rol='admin').count() <= 1:
        flash('Sistemdeki son admini silemezsiniz.', 'danger')
        return redirect(url_for('personel_yonetimi'))

    log_islem('personel_sil', hedef_tablo='kullanici', hedef_id=kullanici.id,
              detay={'silinen': kullanici.eposta})
    db.session.delete(kullanici)
    db.session.commit()
    flash('Kullanıcı başarıyla silindi.', 'success')
    return redirect(url_for('personel_yonetimi'))

@app.route('/takvim')
@login_required
def takvim():
    personeller = []
    if current_user.rol in ['admin', 'resepsiyon']:
        # Admin ve resepsiyon tüm personelleri görebilir
        personeller = Kullanici.query.order_by(Kullanici.ad_soyad.asc()).all()
    elif current_user.rol == 'sekreter' and current_user.bagli_yonetici_id:
        personeller = [current_user]
        yonetici = Kullanici.query.get(current_user.bagli_yonetici_id)
        if yonetici:
            personeller.append(yonetici)
    else:
        personeller = [current_user]
            
    return render_template('takvim.html', personeller=personeller)

@app.route('/api/takvim', methods=['GET'])
@login_required
def api_takvim_getir():
    personel_ids_str = request.args.get('personel_ids')
    
    # Admin ve resepsiyon tüm etkinlikleri veya seçili personellerin etkinliklerini görür
    if current_user.rol in ['admin', 'resepsiyon']:
        if personel_ids_str and personel_ids_str != 'all':
            if personel_ids_str == 'none':
                etkinlikler = []
            else:
                p_ids = [int(pid) for pid in personel_ids_str.split(',') if pid.strip()]
                etkinlikler = TakvimEtkinlik.query.filter(TakvimEtkinlik.sahibi_id.in_(p_ids)).all()
        else:
            etkinlikler = TakvimEtkinlik.query.all()
    elif current_user.rol == 'sekreter' and current_user.bagli_yonetici_id:
        # Sekreter kendi ve bağlı olduğu yöneticinin takvimini görür
        p_ids = [current_user.id, current_user.bagli_yonetici_id]
        if personel_ids_str and personel_ids_str != 'all':
            if personel_ids_str == 'none':
                p_ids = []
            else:
                requested_ids = [int(pid) for pid in personel_ids_str.split(',') if pid.strip()]
                p_ids = [pid for pid in requested_ids if pid in p_ids]
        
        if not p_ids:
            etkinlikler = []
        else:
            etkinlikler = TakvimEtkinlik.query.filter(TakvimEtkinlik.sahibi_id.in_(p_ids)).all()
    else:
        # Normal kullanıcı sadece kendi takvimini görebilir
        if personel_ids_str:
            p_ids = [int(pid) for pid in personel_ids_str.split(',') if pid.strip()]
            # Güvenlik: sadece kendi ID'sine izin ver
            p_ids = [pid for pid in p_ids if pid == current_user.id]
            if p_ids:
                etkinlikler = TakvimEtkinlik.query.filter(TakvimEtkinlik.sahibi_id.in_(p_ids)).all()
            else:
                etkinlikler = []
        else:
            etkinlikler = TakvimEtkinlik.query.filter_by(sahibi_id=current_user.id).all()
        
    events = []
    
    # 1. Takvim Etkinlikleri
    for e in etkinlikler:
        color = '#3788d8' # default (toplanti)
        if e.tip == 'izin': color = '#10b981' # yesil
        elif e.tip == 'disarida': color = '#f59e0b' # turuncu
        elif e.tip == 'musait_degil': color = '#ef4444' # kirmizi
        
        title = e.baslik
        if current_user.rol in ['admin', 'resepsiyon'] or (current_user.rol == 'sekreter' and current_user.bagli_yonetici_id):
            title = f"{e.baslik} ({e.sahibi.ad_soyad})"
            
        events.append({
            'id': str(e.id),
            'title': title,
            'start': e.baslangic.isoformat(),
            'end': e.bitis.isoformat(),
            'backgroundColor': color,
            'extendedProps': {
                'tip': e.tip,
                'aciklama': e.aciklama
            }
        })
        
    # 2. Onaylı Randevular (Takvimde Göstermek İçin)
    if current_user.rol in ['admin', 'resepsiyon']:
        if personel_ids_str and personel_ids_str != 'all':
            if personel_ids_str == 'none':
                randevular = []
            else:
                p_ids = [int(pid) for pid in personel_ids_str.split(',') if pid.strip()]
                randevular = Randevu.query.filter(Randevu.personel_id.in_(p_ids), Randevu.durum == 'Onaylandı').all()
        else:
            randevular = Randevu.query.filter_by(durum='Onaylandı').all()
    elif current_user.rol == 'sekreter' and current_user.bagli_yonetici_id:
        p_ids = [current_user.id, current_user.bagli_yonetici_id]
        if personel_ids_str and personel_ids_str != 'all':
            if personel_ids_str == 'none':
                p_ids = []
            else:
                requested_ids = [int(pid) for pid in personel_ids_str.split(',') if pid.strip()]
                p_ids = [pid for pid in requested_ids if pid in p_ids]
        
        if not p_ids:
            randevular = []
        else:
            randevular = Randevu.query.filter(Randevu.personel_id.in_(p_ids), Randevu.durum == 'Onaylandı').all()
    else:
        randevular = Randevu.query.filter_by(personel_id=current_user.id, durum='Onaylandı').all()
        
    for r in randevular:
        bitis_saati = r.tarih_saat + timedelta(minutes=30) # Varsayılan randevu süresi 30 dk
        title = f'Randevu: {r.ziyaretci_bilgisi.ad_soyad}'
        if current_user.rol in ['admin', 'resepsiyon'] or (current_user.rol == 'sekreter' and current_user.bagli_yonetici_id):
            title = f'Randevu: {r.ziyaretci_bilgisi.ad_soyad} ({r.personel.ad_soyad})'
            
        events.append({
            'id': 'r_' + str(r.id),
            'title': title,
            'start': r.tarih_saat.isoformat(),
            'end': bitis_saati.isoformat(),
            'backgroundColor': '#8b5cf6', # Mor (Randevu rengi)
            'extendedProps': {
                'tip': 'randevu',
                'aciklama': f'{r.ziyaretci_bilgisi.sirket or "Bireysel"} - {r.notlar or ""}',
                'rawNotlar': r.notlar or ''
            }
        })
        
    response = jsonify(events)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/api/takvim', methods=['POST'])
@login_required
def api_takvim_ekle():
    data = request.json
    try:
        baslangic = datetime.fromisoformat(data['baslangic'])
        bitis = datetime.fromisoformat(data['bitis'])
        
        # Hedef takvim: varsayılan olarak kendi takvimi
        hedef_id = current_user.id
        talep_edilen_id = data.get('sahibi_id')
        
        if talep_edilen_id:
            talep_edilen_id = int(talep_edilen_id)
            # Yetki kontrolü: admin herkesin takvimine, sekreter yöneticisinin takvimine ekleyebilir
            if current_user.rol == 'admin':
                hedef_id = talep_edilen_id
            elif current_user.rol == 'sekreter' and current_user.bagli_yonetici_id == talep_edilen_id:
                hedef_id = talep_edilen_id
        
        yeni_etkinlik = TakvimEtkinlik(
            sahibi_id=hedef_id,
            olusturan_id=current_user.id,
            baslik=sanitize_text(data.get('baslik')),
            baslangic=baslangic,
            bitis=bitis,
            tip=data.get('tip', 'toplanti'),
            aciklama=sanitize_text(data.get('aciklama'))
        )
        db.session.add(yeni_etkinlik)
        db.session.commit()
        return jsonify({'success': True, 'id': yeni_etkinlik.id})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/takvim/<int:id>', methods=['PUT', 'DELETE'])
@login_required
def api_takvim_duzenle_sil(id):
    etkinlik = TakvimEtkinlik.query.get_or_404(id)
    
    yetkili = (
        etkinlik.sahibi_id == current_user.id or
        current_user.rol == 'admin' or
        (current_user.rol == 'sekreter' and current_user.bagli_yonetici_id == etkinlik.sahibi_id)
    )
    if not yetkili:
        return jsonify({'success': False, 'error': 'Yetkisiz erişim'})
        
    if request.method == 'DELETE':
        db.session.delete(etkinlik)
        db.session.commit()
        return jsonify({'success': True})
        
    data = request.json
    try:
        etkinlik.baslik = sanitize_text(data.get('baslik'))
        etkinlik.baslangic = datetime.fromisoformat(data['baslangic'])
        etkinlik.bitis = datetime.fromisoformat(data['bitis'])
        etkinlik.tip = data.get('tip')
        etkinlik.aciklama = sanitize_text(data.get('aciklama'))
        db.session.commit()
        return jsonify({'success': True})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/loglar')
@login_required
@rol_gerekli('admin')
def loglar():
    baslangic = request.args.get('baslangic', '')
    bitis = request.args.get('bitis', '')

    query = Randevu.query

    if baslangic:
        try:
            baslangic_tarih = datetime.strptime(baslangic, '%Y-%m-%d')
            query = query.filter(Randevu.tarih_saat >= baslangic_tarih)
        except ValueError:
            flash('Başlangıç tarihi geçersiz formatta, filtre uygulanmadı.', 'danger')

    if bitis:
        try:
            bitis_tarih = datetime.strptime(bitis, '%Y-%m-%d')
            query = query.filter(Randevu.tarih_saat <= bitis_tarih)
        except ValueError:
            flash('Bitiş tarihi geçersiz formatta, filtre uygulanmadı.', 'danger')

    kayitlar = query.order_by(Randevu.tarih_saat.desc()).all()

    toplam = len(kayitlar)
    tamamlanan = len([k for k in kayitlar if k.durum == 'Tamamlandı'])
    reddedilen = len([k for k in kayitlar if k.durum == 'Reddedildi'])
    bekleyen = len([k for k in kayitlar if k.durum == 'Bekliyor'])

    audit_query = AuditLog.query
    if baslangic:
        try:
            audit_query = audit_query.filter(AuditLog.tarih >= baslangic_tarih)
        except ValueError:
            pass
    if bitis:
        try:
            audit_query = audit_query.filter(AuditLog.tarih <= bitis_tarih)
        except ValueError:
            pass
            
    audit_kayitlar = audit_query.order_by(AuditLog.tarih.desc()).all()

    return render_template(
        'loglar.html',
        kayitlar=kayitlar,
        toplam=toplam,
        tamamlanan=tamamlanan,
        reddedilen=reddedilen,
        bekleyen=bekleyen,
        baslangic=baslangic,
        bitis=bitis,
        bugun=datetime.now().date(),
        audit_kayitlar=audit_kayitlar
    )


@app.route('/sistem-loglari')
@login_required
@rol_gerekli('admin')
def sistem_loglari():
    from models import AuditLog

    islem_tipi_filtre = request.args.get('islem_tipi', '')
    baslangic = request.args.get('baslangic', '')
    bitis = request.args.get('bitis', '')

    query = AuditLog.query

    if islem_tipi_filtre:
        query = query.filter(AuditLog.islem_tipi == islem_tipi_filtre)

    if baslangic:
        try:
            baslangic_tarih = datetime.strptime(baslangic, '%Y-%m-%d')
            query = query.filter(AuditLog.tarih >= baslangic_tarih)
        except ValueError:
            flash('Başlangıç tarihi geçersiz formatta, filtre uygulanmadı.', 'danger')

    if bitis:
        try:
            bitis_tarih = datetime.strptime(bitis, '%Y-%m-%d') + timedelta(days=1)
            query = query.filter(AuditLog.tarih < bitis_tarih)
        except ValueError:
            flash('Bitiş tarihi geçersiz formatta, filtre uygulanmadı.', 'danger')

    kayitlar = query.order_by(AuditLog.tarih.desc()).limit(500).all()

    # Filtre dropdown'ı için mevcut işlem tiplerini çıkar
    tum_tipler = db.session.query(AuditLog.islem_tipi).distinct().order_by(AuditLog.islem_tipi).all()
    tum_tipler = [t[0] for t in tum_tipler]

    return render_template(
        'sistem_loglari.html',
        kayitlar=kayitlar,
        islem_tipi_filtre=islem_tipi_filtre,
        baslangic=baslangic,
        bitis=bitis,
        tum_tipler=tum_tipler
    )


@app.route('/seed')
def seed():
    # Güvenlik: bu route sadece geliştirme ortamında (FLASK_DEBUG=True) çalışır.
    # Production'da açık bırakılırsa herkes tahmin edilebilir şifrelerle
    # (admin@tgs.com / 123 vb.) test kullanıcıları oluşturabilir/görebilir.
    if not _debug_modu:
        return "Bulunamadı.", 404

    if Kullanici.query.first():
        return "Veritabanı zaten dolu. Tekrar oluşturulmadı."
        
    kullanicilar = [
        Kullanici(ad_soyad="Sistem Yöneticisi", eposta="admin@vega.com", sifre_hash=generate_password_hash("123"), rol="admin", departman="IT"),
        Kullanici(ad_soyad="Ahmet Güvenlik", eposta="resepsiyon@vega.com", sifre_hash=generate_password_hash("123"), rol="resepsiyon", departman="Güvenlik"),
        Kullanici(ad_soyad="Ayşe Asistan", eposta="sekreter@vega.com", sifre_hash=generate_password_hash("123"), rol="sekreter", departman="Yönetim"),
        Kullanici(ad_soyad="Berkay Personel", eposta="personel@vega.com", sifre_hash=generate_password_hash("123"), rol="personel", departman="Yazılım")
    ]
    
    for k in kullanicilar:
        db.session.add(k)
    db.session.commit()
    
    return "Test kullanıcıları başarıyla eklendi! Şifrelerin hepsi: 123"

@app.route('/api/musaitlik-kontrol')
def musaitlik_kontrol():
    from flask import jsonify
    personel_id = request.args.get('personel_id')
    tarih_saat_str = request.args.get('tarih_saat') # format: YYYY-MM-DDTHH:MM
    
    if not personel_id or not tarih_saat_str:
        return jsonify({'uyari': 'Eksik parametre.'}), 400
        
    personel = Kullanici.query.get(personel_id)
    if not personel:
        return jsonify({'uyari': 'Personel bulunamadı.'}), 404
        
    try:
        istenen_zaman = datetime.strptime(tarih_saat_str, '%Y-%m-%dT%H:%M')
    except ValueError:
        return jsonify({'uyari': 'Geçersiz tarih formatı.'}), 400
        
    # Eğer personel şu an genel olarak "Dışarıda" ise veya tüm gün "Meşgul" ise (Gün bazlı checkler eklenebilir)
    
    ayni_saatte_randevu = Randevu.query.filter(
        Randevu.personel_id == personel_id,
        db.func.strftime('%Y-%m-%d %H', Randevu.tarih_saat) == istenen_zaman.strftime('%Y-%m-%d %H'),
        Randevu.durum.in_(['Onaylandı', 'Bekliyor', 'İçeride', 'Bekleme Salonunda'])
    ).first()
    
    ayni_gun_randevular = Randevu.query.filter(
        Randevu.personel_id == personel_id,
        db.func.strftime('%Y-%m-%d', Randevu.tarih_saat) == istenen_zaman.strftime('%Y-%m-%d'),
        Randevu.durum.in_(['Onaylandı', 'Bekliyor', 'İçeride', 'Bekleme Salonunda'])
    ).count()

    if ayni_saatte_randevu:
        return jsonify({
            'musait_mi': False,
            'mesaj': f'{personel.ad_soyad} seçtiğiniz saatte başka bir randevusu bulunduğu için müsait değil.'
        })
        
    if ayni_gun_randevular >= 10:
        return jsonify({
            'musait_mi': False,
            'mesaj': f'{personel.ad_soyad} seçtiğiniz gün için randevu kapasitesini doldurmuştur (tamamen dolu).'
        })
        
    return jsonify({
        'musait_mi': True,
        'mesaj': f'{personel.ad_soyad} seçtiğiniz gün ve saatte müsait görünüyor.'
    })

# --- SOHBET API ROTALARI ---

@app.route('/api/mesaj-kisiler')
@login_required
def api_mesaj_kisiler():
    from flask import jsonify
    kisiler = Kullanici.query.filter(Kullanici.id != current_user.id).all()
    sonuclar = []
    for kisi in kisiler:
        okunmamis = Mesaj.query.filter_by(gonderen_id=kisi.id, alici_id=current_user.id, okundu=False).count()
        sonuclar.append({
            'id': kisi.id,
            'ad_soyad': kisi.ad_soyad,
            'rol': kisi.rol,
            'okunmamis': okunmamis
        })
    response = jsonify(sonuclar)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/api/mesajlar/<int:kisi_id>')
@login_required
def api_mesajlar(kisi_id):
    from flask import jsonify
    # Okunmayanları okundu olarak işaretle
    Mesaj.query.filter_by(gonderen_id=kisi_id, alici_id=current_user.id, okundu=False).update({'okundu': True})
    db.session.commit()
    
    mesajlar = Mesaj.query.filter(
        db.or_(
            db.and_(Mesaj.gonderen_id == current_user.id, Mesaj.alici_id == kisi_id),
            db.and_(Mesaj.gonderen_id == kisi_id, Mesaj.alici_id == current_user.id)
        )
    ).order_by(Mesaj.tarih_saat.asc()).all()
    
    sonuclar = []
    for m in mesajlar:
        sonuclar.append({
            'id': m.id,
            'gonderen_id': m.gonderen_id,
            'icerik': m.icerik,
            'tarih_saat': m.tarih_saat.strftime('%H:%M'),
            'okundu': m.okundu
        })
    response = jsonify(sonuclar)
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/api/mesaj-gonder', methods=['POST'])
@login_required
def api_mesaj_gonder():
    from flask import jsonify
    data = request.get_json()
    alici_id = data.get('alici_id')
    icerik = sanitize_text(data.get('icerik'))
    
    if not alici_id or not icerik:
        return jsonify({'hata': 'Eksik bilgi'}), 400
        
    yeni_mesaj = Mesaj(
        gonderen_id=current_user.id,
        alici_id=alici_id,
        icerik=icerik
    )
    db.session.add(yeni_mesaj)
    db.session.commit()
    
    return jsonify({'basari': True, 'tarih_saat': yeni_mesaj.tarih_saat.strftime('%H:%M')})

@app.route('/api/ziyaretci/<int:ziyaretci_id>/mail_gonder', methods=['POST'])
@login_required
def api_ziyaretci_mail_gonder(ziyaretci_id):
    from flask import jsonify
    ziyaretci = Ziyaretci.query.get_or_404(ziyaretci_id)
    if not ziyaretci.eposta:
        return jsonify({'basari': False, 'hata': 'Ziyaretçinin e-posta adresi yok.'}), 400
        
    data = request.get_json()
    konu = sanitize_text(data.get('konu'))
    icerik = sanitize_text(data.get('icerik'))
    
    if not konu or not icerik:
        return jsonify({'basari': False, 'hata': 'Konu ve içerik boş olamaz.'}), 400
        
    try:
        # Mail gönderimi
        send_email(to_email=ziyaretci.eposta, subject=konu, body=icerik)
        
        # Veritabanı geçmiş kaydı
        yeni_kayit = ZiyaretciMailGecmisi(
            ziyaretci_id=ziyaretci.id,
            gonderen_kullanici_id=current_user.id,
            konu=konu,
            icerik=icerik
        )
        db.session.add(yeni_kayit)
        
        # Audit log
        log_islem('ziyaretci_mail_gonder', hedef_tablo='ziyaretci', hedef_id=ziyaretci.id, 
                 detay={'konu': konu, 'gonderen': current_user.eposta})
                 
        db.session.commit()
        return jsonify({'basari': True})
    except Exception as e:
        db.session.rollback()
        return jsonify({'basari': False, 'hata': str(e)}), 500

@app.route('/api/musait-saatler')
def api_musait_saatler():
    personel_id = request.args.get('personel_id')
    tarih_str = request.args.get('tarih')
    
    if not personel_id or not tarih_str:
        return jsonify({'success': False, 'error': 'Eksik parametre'})
        
    try:
        tarih = datetime.strptime(tarih_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({'success': False, 'error': 'Geçersiz tarih formatı'})
        
    # Varsayılan çalışma saatleri: 09:00 - 17:00 (30 dk aralıklar)
    baslangic_saati = time(9, 0)
    bitis_saati = time(17, 0)
    
    saatler = []
    mevcut = datetime.combine(tarih, baslangic_saati)
    bitis_dt = datetime.combine(tarih, bitis_saati)
    
    while mevcut < bitis_dt:
        saatler.append(mevcut)
        mevcut += timedelta(minutes=30)
        
    # O günkü dolu randevular (Onaylandı veya Bekliyor)
    randevular = Randevu.query.filter(
        Randevu.personel_id == personel_id,
        db.func.date(Randevu.tarih_saat) == tarih,
        Randevu.durum.in_(['Onaylandı', 'Bekliyor', 'Tamamlandı'])
    ).all()
    
    dolu_zamanlar = []
    for r in randevular:
        dolu_zamanlar.append(r.tarih_saat)
        
    # O günkü takvim etkinlikleri (TakvimEtkinlik)
    takvim_etkinlikleri = TakvimEtkinlik.query.filter(
        TakvimEtkinlik.sahibi_id == personel_id,
        TakvimEtkinlik.baslangic < datetime.combine(tarih + timedelta(days=1), time(0, 0)),
        TakvimEtkinlik.bitis > datetime.combine(tarih, time(0, 0))
    ).all()
    
    musait_saatler = []
    
    for saat in saatler:
        if saat in dolu_zamanlar:
            continue
            
        cakisma_var = False
        for etkinlik in takvim_etkinlikleri:
            if etkinlik.baslangic <= saat < etkinlik.bitis:
                cakisma_var = True
                break
                
        if tarih == datetime.now().date() and saat.time() <= datetime.now().time():
            cakisma_var = True
            
        if not cakisma_var:
            musait_saatler.append(saat.strftime('%H:%M'))
            
    return jsonify({'success': True, 'saatler': musait_saatler})

from flask import Response

@app.route('/api/rapor/excel')
@login_required
@rol_gerekli('admin')
def rapor_excel():
    baslangic = request.args.get('baslangic')
    bitis = request.args.get('bitis')
    
    query = Randevu.query
    if baslangic: query = query.filter(Randevu.tarih_saat >= datetime.strptime(baslangic, '%Y-%m-%d'))
    if bitis: query = query.filter(Randevu.tarih_saat <= datetime.strptime(bitis, '%Y-%m-%d'))
    kayitlar = query.order_by(Randevu.tarih_saat.desc()).all()
    
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Randevu Raporu"
    
    headers = ['Tarih/Saat', 'Ziyaretçi', 'Firma', 'Görüşülen Personel', 'Durum', 'Giriş Saati', 'Çıkış Saati']
    ws.append(headers)
    
    for r in kayitlar:
        ws.append([
            r.tarih_saat.strftime('%d.%m.%Y %H:%M'),
            r.ziyaretci_bilgisi.ad_soyad,
            r.ziyaretci_bilgisi.sirket,
            r.personel.ad_soyad,
            r.durum,
            r.giris_saati.strftime('%H:%M') if r.giris_saati else '-',
            r.cikis_saati.strftime('%H:%M') if r.cikis_saati else '-'
        ])
        
    excel_file = io.BytesIO()
    wb.save(excel_file)
    excel_file.seek(0)
    
    return Response(
        excel_file,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-disposition": "attachment; filename=randevu_raporu.xlsx"}
    )

@app.route('/api/rapor/pdf')
@login_required
@rol_gerekli('admin')
def rapor_pdf():
    baslangic = request.args.get('baslangic')
    bitis = request.args.get('bitis')
    
    query = Randevu.query
    if baslangic: query = query.filter(Randevu.tarih_saat >= datetime.strptime(baslangic, '%Y-%m-%d'))
    if bitis: query = query.filter(Randevu.tarih_saat <= datetime.strptime(bitis, '%Y-%m-%d'))
    kayitlar = query.order_by(Randevu.tarih_saat.desc()).all()
    
    pdf_buffer = io.BytesIO()
    
    # Türkçe font kayıt işlemi
    font_path = os.path.join(app.root_path, 'static', 'fonts', 'Roboto-Regular.ttf')
    font_bold_path = os.path.join(app.root_path, 'static', 'fonts', 'Roboto-Bold.ttf')
    try:
        pdfmetrics.registerFont(TTFont('Roboto', font_path))
        pdfmetrics.registerFont(TTFont('Roboto-Bold', font_bold_path))
        font_name = 'Roboto'
        font_bold = 'Roboto-Bold'
    except Exception as e:
        print(f"Font loading error: {e}")
        font_name = 'Helvetica'
        font_bold = 'Helvetica-Bold'

    doc = SimpleDocTemplate(pdf_buffer, pagesize=landscape(A4), rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=18)
    elements = []
    
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontName=font_bold,
        fontSize=16,
        spaceAfter=20,
        textColor=colors.HexColor("#0f172a")
    )
    
    elements.append(Paragraph("Vega A.Ş. - Randevu Raporu", title_style))
    
    # Tablo Başlıkları
    data = [["Tarih/Saat", "Giriş-Çıkış", "Süre", "Ziyaretçi", "Personel", "Durum", "Açıklama"]]
    
    for r in kayitlar:
        tarih = r.tarih_saat.strftime('%d.%m.%Y %H:%M')
        giris_cikis = f"{r.giris_saati.strftime('%H:%M') if r.giris_saati else '-'} / {r.cikis_saati.strftime('%H:%M') if r.cikis_saati else '-'}"
        sure = r.iceride_kalis_suresi
        ziyaretci = r.ziyaretci_bilgisi.ad_soyad
        personel = r.personel.ad_soyad if r.personel else "Bilinmiyor"
        durum = r.durum
        
        if durum == 'Reddedildi' and r.red_aciklamasi:
            ham_aciklama = r.red_aciklamasi
        else:
            ham_aciklama = r.notlar
            
        aciklama = (ham_aciklama[:40] + '...') if ham_aciklama and len(ham_aciklama) > 40 else (ham_aciklama or "-")
        
        data.append([tarih, giris_cikis, sure, ziyaretci, personel, durum, aciklama])
        
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), font_bold),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 10),
        ('TOPPADDING', (0, 0), (-1, 0), 10),
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.HexColor("#334155")),
        ('FONTNAME', (0, 1), (-1, -1), font_name),
        ('FONTSIZE', (0, 1), (-1, -1), 10),
        ('ALIGN', (0, 1), (-1, -1), 'LEFT'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 8),
    ]))
    
    elements.append(table)
    doc.build(elements)
    
    pdf_buffer.seek(0)
    
    return Response(
        pdf_buffer,
        mimetype="application/pdf",
        headers={"Content-disposition": "attachment; filename=randevu_raporu.pdf"}
    )

@app.route('/kara-liste', methods=['GET', 'POST'])
@login_required
@rol_gerekli('admin')
def kara_liste():
    if request.method == 'POST':
        tc_kimlik = request.form.get('tc_kimlik')
        eposta = request.form.get('eposta')
        sebep = sanitize_text(request.form.get('sebep'))
        if not tc_kimlik and not eposta:
            flash("Lütfen TC Kimlik veya E-posta giriniz.", "danger")
            return redirect(url_for('kara_liste'))
        
        yeni = KaraListe(tc_kimlik=tc_kimlik, eposta=eposta, sebep=sebep, ekleyen_id=current_user.id)
        db.session.add(yeni)
        db.session.commit()
        flash("Kara listeye eklendi.", "success")
        return redirect(url_for('kara_liste'))
    
    liste = KaraListe.query.order_by(KaraListe.eklenme_tarihi.desc()).all()
    return render_template('kara_liste.html', liste=liste)

@app.route('/kara-liste-sil/<int:id>', methods=['POST'])
@login_required
@rol_gerekli('admin')
def kara_liste_sil(id):
    kl = KaraListe.query.get_or_404(id)
    db.session.delete(kl)
    db.session.commit()
    flash("Kara listeden çıkarıldı.", "success")
    return redirect(url_for('kara_liste'))

def kvkk_anonimlestir():
    alti_ay_once = now_in_turkey().replace(tzinfo=None) - timedelta(days=180)
    eski_ziyaretciler = []
    tum_ziyaretciler = Ziyaretci.query.all()
    for z in tum_ziyaretciler:
        son_r = Randevu.query.filter_by(ziyaretci_id=z.id).order_by(Randevu.tarih_saat.desc()).first()
        if son_r and son_r.tarih_saat < alti_ay_once:
            eski_ziyaretciler.append(z)
        elif not son_r:
            eski_ziyaretciler.append(z)

    sayac = 0
    for z in eski_ziyaretciler:
        if z.tc_kimlik and len(z.tc_kimlik) == 11 and not z.tc_kimlik.startswith('***'):
            z.tc_kimlik = z.tc_kimlik[:3] + "*****" + z.tc_kimlik[-3:]
            sayac += 1
        if z.eposta and '@' in z.eposta and not z.eposta.startswith('***'):
            parts = z.eposta.split('@')
            z.eposta = parts[0][:1] + "***@" + parts[1]
            sayac += 1
        if z.telefon and len(z.telefon) >= 10 and not z.telefon.startswith('***'):
            z.telefon = z.telefon[:3] + "*****" + z.telefon[-2:]
            sayac += 1
    if sayac > 0:
        db.session.commit()

_son_kvkk_calisma = None

@app.before_request
def otomatik_kvkk_kontrolu():
    global _son_kvkk_calisma
    bugun = datetime.now().date()
    if _son_kvkk_calisma != bugun:
        _son_kvkk_calisma = bugun
        try:
            kvkk_anonimlestir()
        except Exception as e:
            app.logger.error(f"KVKK Anonimleştirme hatası: {e}")

@app.route('/api/bildirimler', methods=['GET'])
@login_required
def get_bildirimler():
    bildirimler = Bildirim.query.filter_by(kullanici_id=current_user.id, okundu=False).order_by(Bildirim.tarih_saat.desc()).all()
    res = [{'id': b.id, 'icerik': b.icerik, 'tarih': b.tarih_saat.strftime('%H:%M')} for b in bildirimler]
    return jsonify(res)

@app.route('/api/bildirim-okundu/<int:id>', methods=['POST'])
@login_required
def bildirim_okundu(id):
    b = Bildirim.query.filter_by(id=id, kullanici_id=current_user.id).first()
    if b:
        b.okundu = True
        db.session.commit()
        return jsonify({'basari': True})
    return jsonify({'basari': False})

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=_debug_modu, port=5001, threaded=True)

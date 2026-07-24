from flask_sqlalchemy import SQLAlchemy

from datetime import datetime, timedelta
import pytz

db = SQLAlchemy()

# Türkiye saati için yardımcı fonksiyon
def now_in_turkey():
    tz = pytz.timezone('Europe/Istanbul')
    return datetime.now(tz)

class Kullanici(db.Model):
    __tablename__ = 'kullanici'
    is_authenticated = True
    id = db.Column(db.Integer, primary_key=True)
    kullanici_adi = db.Column(db.String(50), unique=True, nullable=False)
    ad_soyad = db.Column(db.String(100), nullable=False)
    eposta = db.Column(db.String(120), unique=True, nullable=False)
    sifre_hash = db.Column(db.String(256), nullable=False)
    rol = db.Column(db.String(20), nullable=False) # 'admin', 'resepsiyon', 'sekreter', 'personel'
    departman = db.Column(db.String(100), nullable=True)
    aktif_durum = db.Column(db.String(20), default='Müsait') # 'Müsait', 'Meşgul', 'Toplantıda', 'Dışarıda'
    profil_resmi = db.Column(db.String(255), default='default.png')
    bagli_yonetici_id = db.Column(db.Integer, db.ForeignKey('kullanici.id'), nullable=True)

    # İkincil ilişkiler (Bir personelin kendi misafirleri ve bir sekreterin başkası adına oluşturduğu randevular)
    yonetici = db.relationship('Kullanici', remote_side=[id], backref='sekreterler')
    olusturdugu_randevular = db.relationship('Randevu', foreign_keys='Randevu.olusturan_id', backref='olusturan', lazy=True)
    kendi_randevulari = db.relationship('Randevu', foreign_keys='Randevu.personel_id', backref='personel', lazy=True)

class Ziyaretci(db.Model):
    __tablename__ = 'ziyaretci'
    id = db.Column(db.Integer, primary_key=True)
    ad_soyad = db.Column(db.String(100), nullable=False)
    tc_kimlik = db.Column(db.String(11), nullable=True) # Güvenlik için TCKN
    eposta = db.Column(db.String(120), nullable=True)
    sirket = db.Column(db.String(100), nullable=True)
    telefon = db.Column(db.String(20), nullable=True)
    kvkk_onayi = db.Column(db.Boolean, default=False)
    
    randevular = db.relationship('Randevu', backref='ziyaretci_bilgisi', lazy=True)

class Randevu(db.Model):
    __tablename__ = 'randevu'
    id = db.Column(db.Integer, primary_key=True)
    ziyaretci_id = db.Column(db.Integer, db.ForeignKey('ziyaretci.id'), nullable=False)
    personel_id = db.Column(db.Integer, db.ForeignKey('kullanici.id'), nullable=False) # Ziyaret edilecek personel
    olusturan_id = db.Column(db.Integer, db.ForeignKey('kullanici.id'), nullable=True) # Sekreter veya Resepsiyonist açtıysa
    
    tarih_saat = db.Column(db.DateTime, nullable=False) # Randevu Zamanı
    durum = db.Column(db.String(20), default='Bekliyor') # Bekliyor, Onaylandı, Reddedildi, İçeride, Tamamlandı
    giris_saati = db.Column(db.DateTime, nullable=True)
    cikis_saati = db.Column(db.DateTime, nullable=True)
    notlar = db.Column(db.Text, nullable=True)
    red_aciklamasi = db.Column(db.Text, nullable=True)
    
    son_guncelleme_tarihi = db.Column(db.DateTime, nullable=True)
    guncelleyen_kullanici_id = db.Column(db.Integer, db.ForeignKey('kullanici.id'), nullable=True)
    guncelleyen_kullanici = db.relationship('Kullanici', foreign_keys=[guncelleyen_kullanici_id])
    
    @property
    def beklemeye_uygun_mu(self):
        # Eğer durum Onaylandı ise ve randevu saati, şu andan itibaren 60 dakika (veya daha kısa) bir zaman zarfında gerçekleşecekse ya da geçmişse
        # Ve sadece randevu günü (bugün) için geçerli olacaksa:
        simdi = now_in_turkey()
        # Tarihler farklıysa zaten bugün değildir
        if self.durum != 'Onaylandı' or self.tarih_saat.date() != simdi.date():
            return False
            
        simdi_naive = simdi.replace(tzinfo=None)
        fark = self.tarih_saat - simdi_naive
        # Eğer geçmişse (fark negatifse) veya 60 dakikadan az kalmışsa
        return fark <= timedelta(minutes=60)
    
    olusturma_tarihi = db.Column(db.DateTime, default=now_in_turkey)

    @property
    def iceride_kalis_suresi(self):
        if self.giris_saati and self.cikis_saati:
            fark = self.cikis_saati - self.giris_saati
            toplam_saniye = int(fark.total_seconds())
            saat = toplam_saniye // 3600
            dakika = (toplam_saniye % 3600) // 60
            if saat > 0:
                return f"{saat} saat {dakika} dk"
            return f"{dakika} dk"
        return "-"

class AuditLog(db.Model):
    __tablename__ = 'audit_log'
    id = db.Column(db.Integer, primary_key=True)
    kullanici_id = db.Column(db.Integer, db.ForeignKey('kullanici.id'), nullable=True)  # sistem işlemlerinde null olabilir
    islem_tipi = db.Column(db.String(50), nullable=False)   # 'randevu_onay', 'randevu_red', 'randevu_duzenle', vb.
    hedef_tablo = db.Column(db.String(50), nullable=True)   # 'randevu', 'kullanici', 'takvim_etkinlik'
    hedef_id = db.Column(db.Integer, nullable=True)
    detay = db.Column(db.Text, nullable=True)               # JSON string - eski/yeni değer vb.
    tarih = db.Column(db.DateTime, default=now_in_turkey)

    kullanici = db.relationship('Kullanici', foreign_keys=[kullanici_id])

class TakvimEtkinlik(db.Model):
    __tablename__ = 'takvim_etkinlik'
    id = db.Column(db.Integer, primary_key=True)
    sahibi_id = db.Column(db.Integer, db.ForeignKey('kullanici.id'), nullable=False)
    baslik = db.Column(db.String(150), nullable=False)
    baslangic = db.Column(db.DateTime, nullable=False)
    bitis = db.Column(db.DateTime, nullable=False)
    tip = db.Column(db.String(50), default='toplanti') # toplanti, izin, disarida, musait_degil, randevu
    olusturan_id = db.Column(db.Integer, db.ForeignKey('kullanici.id'), nullable=False)
    aciklama = db.Column(db.Text, nullable=True)
    
    sahibi = db.relationship('Kullanici', foreign_keys=[sahibi_id])
    olusturan = db.relationship('Kullanici', foreign_keys=[olusturan_id])


class Mesaj(db.Model):
    __tablename__ = 'mesaj'
    id = db.Column(db.Integer, primary_key=True)
    gonderen_id = db.Column(db.Integer, db.ForeignKey('kullanici.id'), nullable=False)
    alici_id = db.Column(db.Integer, db.ForeignKey('kullanici.id'), nullable=False)
    icerik = db.Column(db.Text, nullable=False)
    okundu = db.Column(db.Boolean, default=False)
    tarih_saat = db.Column(db.DateTime, default=now_in_turkey)

    gonderen = db.relationship('Kullanici', foreign_keys=[gonderen_id], backref='gonderdigi_mesajlar')
    alici = db.relationship('Kullanici', foreign_keys=[alici_id], backref='aldigi_mesajlar')

class ZiyaretciMailGecmisi(db.Model):
    __tablename__ = 'ziyaretci_mail_gecmisi'
    id = db.Column(db.Integer, primary_key=True)
    ziyaretci_id = db.Column(db.Integer, db.ForeignKey('ziyaretci.id'), nullable=False)
    gonderen_kullanici_id = db.Column(db.Integer, db.ForeignKey('kullanici.id'), nullable=False)
    konu = db.Column(db.String(200), nullable=False)
    icerik = db.Column(db.Text, nullable=False)
    tarih_saat = db.Column(db.DateTime, default=now_in_turkey)
    
    ziyaretci = db.relationship('Ziyaretci', foreign_keys=[ziyaretci_id], backref='aldigi_mailler')
    gonderen = db.relationship('Kullanici', foreign_keys=[gonderen_kullanici_id])

class KaraListe(db.Model):
    __tablename__ = 'kara_liste'
    id = db.Column(db.Integer, primary_key=True)
    tc_kimlik = db.Column(db.String(11), nullable=True)
    eposta = db.Column(db.String(120), nullable=True)
    sebep = db.Column(db.Text, nullable=True)
    eklenme_tarihi = db.Column(db.DateTime, default=now_in_turkey)
    ekleyen_id = db.Column(db.Integer, db.ForeignKey('kullanici.id'), nullable=False)

    ekleyen = db.relationship('Kullanici', foreign_keys=[ekleyen_id])

class Bildirim(db.Model):
    __tablename__ = 'bildirim'
    id = db.Column(db.Integer, primary_key=True)
    kullanici_id = db.Column(db.Integer, db.ForeignKey('kullanici.id'), nullable=False)
    icerik = db.Column(db.String(255), nullable=False)
    okundu = db.Column(db.Boolean, default=False)
    tarih_saat = db.Column(db.DateTime, default=now_in_turkey)

    kullanici = db.relationship('Kullanici', foreign_keys=[kullanici_id], backref='bildirimler')

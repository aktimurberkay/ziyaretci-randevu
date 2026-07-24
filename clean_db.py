from app import app, db, Ziyaretci, Randevu

with app.app_context():
    # Ziyaretçi tablosunu temizle
    ziyaretciler = Ziyaretci.query.all()
    for z in ziyaretciler:
        if z.sirket and '&lt;' in z.sirket:
            z.sirket = z.sirket.replace('&lt;', '').replace('&gt;', '')
        if z.ad_soyad and '&lt;' in z.ad_soyad:
            z.ad_soyad = z.ad_soyad.replace('&lt;', '').replace('&gt;', '')
            
    # Randevu notlarını temizle
    randevular = Randevu.query.all()
    for r in randevular:
        if r.notlar and '&lt;' in r.notlar:
            r.notlar = r.notlar.replace('&lt;', '').replace('&gt;', '')
        if r.red_aciklamasi and '&lt;' in r.red_aciklamasi:
            r.red_aciklamasi = r.red_aciklamasi.replace('&lt;', '').replace('&gt;', '')
            
    db.session.commit()
    print("Veritabanı başarıyla temizlendi.")

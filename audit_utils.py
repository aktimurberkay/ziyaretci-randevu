"""
Audit log yardımcı fonksiyonu.

Kullanışı:
    from audit_utils import log_islem
    log_islem('randevu_onay', hedef_tablo='randevu', hedef_id=randevu.id,
               detay={'eski_durum': 'Bekliyor', 'yeni_durum': 'Onaylandı'})

Not: Bu fonksiyon db.session.add() yapar ama commit ETMEZ. Çağıran fonksiyon
kendi işlemiyle birlikte (randevu güncellemesi vb.) tek seferde commit etmelidir.
Böylece log kaydı ile asıl işlem her zaman birlikte kaydedilir ya da hiç kaydedilmez
(atomiklik korunur).
"""

import json
from flask_jwt_extended import current_user
from models import db, AuditLog


def log_islem(islem_tipi, hedef_tablo=None, hedef_id=None, detay=None):
    kullanici_id = None
    try:
        if current_user and current_user.is_authenticated:
            kullanici_id = current_user.id
    except Exception:
        # current_user bağlamı yoksa (örn. arka plan işi) sessizce geç
        pass

    detay_json = None
    if detay is not None:
        try:
            detay_json = json.dumps(detay, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            detay_json = str(detay)

    kayit = AuditLog(
        kullanici_id=kullanici_id,
        islem_tipi=islem_tipi,
        hedef_tablo=hedef_tablo,
        hedef_id=hedef_id,
        detay=detay_json,
    )
    db.session.add(kayit)
    return kayit

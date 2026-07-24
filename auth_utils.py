"""
Güvenlik yardımcıları:
- rol_gerekli: route'larda tekrar eden 'if current_user.rol not in [...]' kontrolünü
  tekilleştiren decorator.
- Basit login deneme sınırlama (brute-force koruması). Tek process/tek worker'lı
  geliştirme ortamı için bellek-içi (in-memory) bir çözümdür. Birden fazla worker/
  process ile production'da çalıştırılacaksa (gunicorn -w 4 vb.) bu sayaçlar
  worker'lar arasında paylaşılmaz; böyle bir durumda Redis tabanlı bir çözüme
  (örn. Flask-Limiter + Redis) geçilmesi gerekir.
"""

import time
import os
from collections import defaultdict
from functools import wraps
from flask import redirect, url_for, flash
from flask_jwt_extended import current_user

# ---- Rol bazlı erişim kontrolü ----

def rol_gerekli(*izinli_roller):
    """Kullanılışı: @rol_gerekli('admin', 'sekreter')"""
    def decorator(f):
        @wraps(f)
        def sarmalanmis(*args, **kwargs):
            if current_user.rol not in izinli_roller:
                flash('Bu işlem için yetkiniz yok.', 'danger')
                return redirect(url_for('dashboard'))
            return f(*args, **kwargs)
        return sarmalanmis
    return decorator


# ---- Login brute-force koruması ----

MAX_DENEME = 5          # bu kadar başarısız denemeden sonra
KILIT_SURESI_SN = 300   # bu kadar saniye (5 dk) giriş kilitlenir

redis_url = os.environ.get("REDIS_URL")
if redis_url:
    import redis
    r = redis.Redis.from_url(redis_url)
    USE_REDIS = True
else:
    USE_REDIS = False
    _basarisiz_denemeler = defaultdict(list)  # in-memory fallback


def _anahtar(kullanici_adi, ip):
    # Hem kullanıcı adı hem IP bazlı kilitleme: aynı hesaba farklı IP'lerden
    # yapılan saldırılar da, aynı IP'den farklı hesaplara yapılan
    # saldırılar da yakalanır.
    return f"login_deneme::{(kullanici_adi or '').lower()}::{ip}"


def girise_izin_var_mi(kullanici_adi, ip):
    anahtar = _anahtar(kullanici_adi, ip)
    if USE_REDIS:
        sayac = r.get(anahtar)
        return int(sayac or 0) < MAX_DENEME
    else:
        simdi = time.time()
        guncel_denemeler = [t for t in _basarisiz_denemeler[anahtar] if simdi - t < KILIT_SURESI_SN]
        _basarisiz_denemeler[anahtar] = guncel_denemeler
        return len(guncel_denemeler) < MAX_DENEME


def basarisiz_deneme_kaydet(kullanici_adi, ip):
    anahtar = _anahtar(kullanici_adi, ip)
    if USE_REDIS:
        pipe = r.pipeline()
        pipe.incr(anahtar, 1)
        pipe.expire(anahtar, KILIT_SURESI_SN)
        pipe.execute()
    else:
        _basarisiz_denemeler[anahtar].append(time.time())


def basarili_giris_sonrasi_temizle(kullanici_adi, ip):
    anahtar = _anahtar(kullanici_adi, ip)
    if USE_REDIS:
        r.delete(anahtar)
    else:
        _basarisiz_denemeler.pop(anahtar, None)

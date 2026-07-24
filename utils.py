def _csharp_mod(a, b):
    # Python'da % işlemi negatif sayılarda C#'tan farklı sonuç verir
    # (Python bölenin işaretini alır, C# ise bölünenin işaretini alır).
    # C# ile birebir aynı sonucu almak için bu yardımcı fonksiyon kullanılır.
    q = int(a / b)
    return a - q * b

def tc_kimlik_gecerli_mi(kimlik_str):
    if not kimlik_str:
        return True, "" # Eğer opsiyonel ise boş geçilebilir, değilse formda required olmalı
        
    if len(kimlik_str) != 11 or not kimlik_str.isdigit():
        return False, "T.C. Kimlik numaranız 11 haneli sadece rakamlardan oluşmalıdır!"
        
    kimlik_no = int(kimlik_str)
    ilk9 = kimlik_no // 100
    son2 = kimlik_no % 100
    tekler = 0
    ciftler = 0

    for i in range(1, 10):
        basamak = ilk9 % 10   # O anki birler basamağı okunur.
        if i % 2 == 0:
            ciftler += basamak
        else:
            tekler += basamak
        ilk9 //= 10            # O anki birler basamağı atılır.

    b10 = _csharp_mod(tekler * 7 - ciftler, 10)
    b11 = _csharp_mod(tekler + ciftler + b10, 10)

    if son2 == b10 * 10 + b11:
        return True, ""
    else:
        return False, "Girilen T.C. Kimlik numarası hatalı (algoritma doğrulanamadı)!"

import threading

def _send_async_email(app, mail, msg):
    with app.app_context():
        try:
            mail.send(msg)
            print(f"E-POSTA BAŞARIYLA GÖNDERİLDİ: {msg.recipients}")
        except Exception as e:
            print(f"E-POSTA GÖNDERİM HATASI: {e}")

def send_email(to_email, subject, body):
    """
    Gerçek SMTP sunucusu üzerinden e-posta gönderir (Arka planda çalışır).
    """
    from app import app, mail, Message # Circular import'u önlemek için fonksiyon içinde import ediyoruz
    
    # Eğer SMTP ayarları girilmemişse, eskisi gibi terminale yazdırıp dön
    if not app.config.get('MAIL_USERNAME') or app.config.get('MAIL_USERNAME') == 'sizin_mailiniz@gmail.com':
        print("\n" + "="*50)
        print(f"📧 E-POSTA GÖNDERİLİYOR (SİMÜLASYON - SMTP ayarları yapılmamış)...")
        print(f"Kime   : {to_email}")
        print(f"Konu   : {subject}")
        print(f"Mesaj  :\n{body}")
        print("="*50 + "\n")
        return

    msg = Message(subject,
                  sender=app.config.get('MAIL_DEFAULT_SENDER'),
                  recipients=[to_email])
    msg.body = body
    
    # Gönderimi arka planda yap (arayüzü dondurmaması için)
    thr = threading.Thread(target=_send_async_email, args=[app, mail, msg])
    thr.start()

import re

def sanitize_text(text):
    """
    XSS ve veritabanı kilitlenmelerini (emoji vb.) önlemek için dışarıdan gelen metni temizler.
    HTML taglerini ( < ve > ) ve emojileri tamamen siler, sadece güvenli karakterlere izin verir.
    """
    if not text:
        return text
    
    text = str(text)
    
    # 1. Tester'in gönderdiği SQL ve XSS kelime engelleme kuralı
    # SELECT, UPDATE, SCRIPT gibi kelimeleri bulursa bunları metinden siler
    sql_keywords = r'\b(SELECT|INSERT|DELETE|UPDATE|DROP|ALTER|UNION|WHERE|FROM|TABLE|JOIN|CREATE|EXEC|TRUNCATE|MERGE|GRANT|REVOKE|SHOW|DESCRIBE|SCRIPT|ALERT|CONSOLE|LOG)\b'
    clean_text = re.sub(sql_keywords, '', text, flags=re.IGNORECASE)

    # 2. Emojileri ve garip sembolleri sil (sadece harf, rakam, boşluk ve temel noktalama işaretlerine izin ver)
    # < ve > işaretlerini kasıtlı olarak sildik ki kullanıcılar <html> yazamasın.
    clean_text = re.sub(r'[^\w\s.,!?\'"()\[\]{}:;&%*+=\-@/\\_]', '', clean_text)
    
    return clean_text.strip()


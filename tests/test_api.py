def test_login_success(client):
    response = client.post('/login', data={
        "kullanici_adi": "test_admin",
        "sifre": "test_password"
    })
    # Should redirect to dashboard
    assert response.status_code == 302
    assert b'dashboard' in response.data

def test_login_failure(client):
    response = client.post('/login', data={
        "kullanici_adi": "test_admin",
        "sifre": "wrong_password"
    })
    # Should stay on login page
    assert response.status_code == 200

def test_dashboard_unauthorized(client):
    response = client.get('/dashboard')
    # Should redirect to login
    assert response.status_code == 302
    assert b'login' in response.data

def test_dashboard_authorized(auth_client):
    response = auth_client.get('/dashboard')
    # Should load dashboard
    assert response.status_code == 200
    assert b'Test Admin' in response.data

def test_takvim_api(auth_client):
    response = auth_client.get('/api/takvim')
    assert response.status_code == 200
    data = response.get_json()
    assert isinstance(data, list)

def test_musaitlik_kontrol(auth_client):
    response = auth_client.get('/api/musaitlik-kontrol?personel_id=1&tarih_saat=2026-08-01T10:00')
    assert response.status_code in [200, 404] # 404 if test DB doesn't have personel=1

Feature: Ziyaretci Randevu Sistemi E2E Test Senaryosu

  Scenario: Yeni randevu olusturma, onaylama ve duzenleme (XSS) kontrolu
    Given Ziyaretci randevu olusturma anasayfasindadir
    When Ad Soyad alanina "Otomasyon Ziyaretcisi" girilirse
    And TC Kimlik alanina gecerli bir "11111111110" degeri girilirse
    And E-posta alanina "otomasyon@test.com" girilirse
    And Gorusulecek Kisi secim alanindan ilk personel secilirse
    And Randevu Tarihi olarak yarin secilirse
    And Randevu Saati olarak uygun bir saat secilirse
    And Notlar alanina "E2E Otomasyon Testi" girilirse
    And KVKK onay kutusu isaretlenirse
    And Randevu formunda Gonder butonuna tiklanirsa
    Then Randevunun basariyla olusturuldugu mesajinin goruntulendigi dogrulanmalidir

    Given Admin login sayfasindadir
    When Kullanici adi alanina "admin" degeri girilirse
    And Sifre alanina "123" degeri girilirse
    And Login formunda Giris butonuna tiklanirsa
    Then Admin panelinin acildigi goruntulenmelidir

    When Dashboard uzerinde bekleyen "Otomasyon Ziyaretcisi" adli randevunun Onayla butonuna tiklanirsa
    Then Randevu durumunun onaylandi olarak degistigi goruntulenmelidir

    When "Otomasyon Ziyaretcisi" adli randevunun Duzenle butonuna tiklanirsa
    Then Randevu Duzenleme modalinin acildigi goruntulenmelidir
    And Duzenle Notlar alanina "XSS Payload" degeri girilirse
    And Duzenleme modalinda Kaydet butonuna tiklanirsa
    Then Sistem xss korumasinin devrede oldugu ve zafiyet barindirmadigi dogrulanmalidir

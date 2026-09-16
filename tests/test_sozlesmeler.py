"""Ortak sözleşme testleri: katı tür doğrulama, durum adları, hata ailesi, sayfalama."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from defteriki import sozlesmeler as sz

# --- KurusTutar (K05) ---------------------------------------------------------


@given(st.integers(min_value=0))
def test_kurus_tutar_sifir_ve_pozitif_tam_sayi_kabul(deger: int) -> None:
    assert sz.kurus_tutar_dogrula(deger) == deger


@given(st.integers(max_value=-1))
def test_kurus_tutar_negatif_reddedilir(deger: int) -> None:
    with pytest.raises(sz.TutarGecersiz):
        sz.kurus_tutar_dogrula(deger)


@given(st.floats(allow_nan=False, allow_infinity=False))
def test_kurus_tutar_float_reddedilir_tam_sayi_gorunumlu_bile(deger: float) -> None:
    with pytest.raises(sz.TutarGecersiz):
        sz.kurus_tutar_dogrula(deger)


@pytest.mark.parametrize("deger", [True, False, "100", "12.50", None, 10**30 * 1.0])
def test_kurus_tutar_bool_metin_ve_bos_reddedilir(deger: object) -> None:
    with pytest.raises(sz.TutarGecersiz) as bilgi:
        sz.kurus_tutar_dogrula(deger, alan="satir_tutari")

    assert bilgi.value.kod == "TUTAR_GECERSIZ"
    assert bilgi.value.alan == "satir_tutari"
    assert bilgi.value.tekrar_denenebilir is False


def test_kurus_tutar_buyuk_degerler_kaybolmaz() -> None:
    deger = 10**18  # 10 katrilyon TL; SQLite INTEGER sınırı içinde

    assert sz.kurus_tutar_dogrula(deger) == deger


# --- Kimlik ------------------------------------------------------------------


@given(st.integers(min_value=1))
def test_kimlik_pozitif_tam_sayi_kabul(deger: int) -> None:
    assert sz.kimlik_dogrula(deger) == deger


@pytest.mark.parametrize("deger", [0, -1, 1.0, True, "1", None])
def test_kimlik_gecersiz_degerler_reddedilir(deger: object) -> None:
    with pytest.raises(sz.GirdiGecersiz) as bilgi:
        sz.kimlik_dogrula(deger, alan="defter_id")

    assert bilgi.value.kod == "GIRDI_GECERSIZ"
    assert bilgi.value.alan == "defter_id"


# --- para birimi (C09) ---------------------------------------------------------


@pytest.mark.parametrize("deger", ["TRY", sz.ParaBirimi.TRY])
def test_para_birimi_try_kabul(deger: object) -> None:
    assert sz.para_birimi_dogrula(deger) is sz.ParaBirimi.TRY


@pytest.mark.parametrize("deger", ["USD", "EUR", "try", "", None, 949])
def test_para_birimi_try_disi_reddedilir(deger: object) -> None:
    with pytest.raises(sz.ParaBirimiDesteklenmiyor) as bilgi:
        sz.para_birimi_dogrula(deger)

    assert bilgi.value.kod == "PARA_BIRIMI_DESTEKLENMIYOR"
    assert "TRY" in bilgi.value.mesaj


# --- durum adları (C08) ----------------------------------------------------------


def test_belge_durumlari_c08_ile_ayni() -> None:
    assert [d.value for d in sz.BelgeDurumu] == [
        "ARSIVLENDI",
        "OKUNUYOR",
        "KARAR_BEKLIYOR",
        "HAZIR",
        "KAYITLI",
        "GECERSIZ",
        "YERINE_GECILDI",
    ]


def test_satir_durumlari_c08_ile_ayni() -> None:
    assert [d.value for d in sz.SatirDurumu] == [
        "YAZILDI",
        "KARAR_BEKLIYOR",
        "MEVCUDA_BAGLANDI",
        "KAPSAM_DISI",
    ]


def test_nesne_yon_eksen_degerleri() -> None:
    assert [d.value for d in sz.NesneDurumu] == ["AKTIF", "ENGELLI", "PASIF", "SILINDI"]
    assert [d.value for d in sz.Yon] == ["ARTTIR", "AZALT"]
    assert [d.value for d in sz.Eksen] == ["VARLIK", "BORC", "GIDER"]


def test_durum_sabitleri_metin_gibi_davranir() -> None:
    # Veritabanına ve JSON'a düz metin olarak gider.
    assert sz.BelgeDurumu.KAYITLI == "KAYITLI"
    assert f"{sz.SatirDurumu.YAZILDI}" == "YAZILDI"


# --- hata ailesi (Tam Plan 11.2) ----------------------------------------------


def test_hata_kodlari_benzersiz_ve_11_2_ile_ortusur() -> None:
    kodlar = [sinif.kod for sinif in sz.HATA_KODLARI]

    assert len(kodlar) == len(set(kodlar))
    assert set(kodlar) >= {
        "BELGE_YOK",
        "ARSIV_EKSIK",
        "DEFTER_UYUSMAZLIGI",
        "SEVIYE_CAKISMASI",
        "NESNE_ENGELLI",
        "YENI_NESNE_ENGELI",
        "TUTAR_GECERSIZ",
        "PARA_BIRIMI_DESTEKLENMIYOR",
        "ANAHTAR_ICERIK_CAKISMASI",
        "HEDEF_SURUMU_DEGISTI",
        "BELGE_HAZIR_DEGIL",
        "MUTABAKAT_FARKI",
        "KAYNAK_CAKISMASI",
        "VERITABANI_MESGUL",
    }
    assert all(issubclass(sinif, sz.DefterikiHatasi) for sinif in sz.HATA_KODLARI)


def test_yalniz_veritabani_mesgul_tekrar_denenebilir() -> None:
    tekrar = [sinif.kod for sinif in sz.HATA_KODLARI if sinif.tekrar_denenebilir]

    assert tekrar == ["VERITABANI_MESGUL"]


def test_hata_metni_kod_alan_konum_ve_mesaj_tasir() -> None:
    hata = sz.MutabakatFarki("kapanış bakiyesi tutmuyor", alan="satirlar", konum=7)

    assert str(hata) == "MUTABAKAT_FARKI [satirlar#7]: kapanış bakiyesi tutmuyor"
    assert str(sz.BelgeYok("belge bulunamadı")) == "BELGE_YOK: belge bulunamadı"
    assert isinstance(hata, Exception)


# --- sayfalama -----------------------------------------------------------------


def test_sayfalama_varsayilan_100_ve_ust_sinir_500() -> None:
    assert sz.Sayfalama() == sz.Sayfalama(sinir=100, baslangic=0)
    assert sz.Sayfalama(sinir=500, baslangic=1000).sinir == 500


@pytest.mark.parametrize(
    ("sinir", "baslangic", "alan"),
    [(0, 0, "sinir"), (501, 0, "sinir"), (True, 0, "sinir"), (10, -1, "baslangic")],
)
def test_sayfalama_sinir_disi_reddedilir(sinir: int, baslangic: int, alan: str) -> None:
    with pytest.raises(sz.GirdiGecersiz) as bilgi:
        sz.Sayfalama(sinir=sinir, baslangic=baslangic)

    assert bilgi.value.alan == alan

"""HESAP_HAREKETI sözleşmesi (Teslim 4.6): saf doğrulama, S20 tutar sınırları."""

from datetime import date, datetime
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from defteriki import finansal_kurallar as fk
from defteriki import sozlesmeler as sz

TARIH = date(2026, 8, 15)


def _hareket(**degisiklik: object) -> fk.HesapHareketi:
    alanlar: dict[str, object] = {
        "nesne_id": 7,
        "yon": "ARTTIR",
        "tutar_kurus": 12_345,
        "islem_tarihi": TARIH,
    }
    alanlar.update(degisiklik)
    return fk.HesapHareketi(**alanlar)  # pyright: ignore[reportArgumentType]


def test_gecerli_hareket_tek_varlik_etkisi_uretir() -> None:
    taslak = fk.hesap_hareketi_dogrula(
        _hareket(valor_tarihi="2026-08-16", aciklama="  Maaş  ", yon=sz.Yon.AZALT)
    )

    assert taslak == fk.HareketTaslagi(
        islem_turu=fk.IslemTuru.HESAP_HAREKETI,
        asil_nesne_id=7,
        islem_tarihi=TARIH,
        valor_tarihi=date(2026, 8, 16),
        aciklama="Maaş",
        etkiler=(
            fk.EtkiTaslagi(7, sz.Eksen.VARLIK, sz.Yon.AZALT, 12_345, sz.ParaBirimi.TRY),
        ),
    )


def test_tarih_metin_kabul_valor_ve_aciklama_istege_bagli() -> None:
    taslak = fk.hesap_hareketi_dogrula(_hareket(islem_tarihi="2026-08-15", aciklama=""))
    assert taslak.islem_tarihi == TARIH
    assert taslak.valor_tarihi is None and taslak.aciklama is None


# --- S20: float, boolean, artık ondalık, taşma ---------------------------------


@pytest.mark.parametrize(
    "tutar",
    [12.0, 12.5, True, False, "100", "12,50", Decimal("10"), None, -1, 0],
)
def test_s20_tutar_reddi(tutar: object) -> None:
    with pytest.raises(sz.TutarGecersiz):
        fk.hesap_hareketi_dogrula(_hareket(tutar_kurus=tutar))


def test_s20_tasma_reddedilir_sinir_kabul() -> None:
    with pytest.raises(sz.TutarGecersiz, match="taşma"):
        fk.tutar_dogrula(fk.AZAMI_TUTAR_KURUS + 1)
    assert fk.tutar_dogrula(fk.AZAMI_TUTAR_KURUS) == fk.AZAMI_TUTAR_KURUS
    assert fk.tutar_dogrula(1) == 1


@given(st.integers(min_value=1, max_value=fk.AZAMI_TUTAR_KURUS))
def test_pozitif_tam_sayi_her_zaman_kabul(tutar: int) -> None:
    assert fk.tutar_dogrula(tutar) == tutar


@given(st.integers(max_value=0) | st.integers(min_value=fk.AZAMI_TUTAR_KURUS + 1))
def test_sifir_negatif_ve_tasma_her_zaman_ret(tutar: int) -> None:
    with pytest.raises(sz.TutarGecersiz):
        fk.tutar_dogrula(tutar)


@given(st.floats(allow_nan=False, allow_infinity=False) | st.booleans())
def test_float_ve_bool_her_zaman_ret(tutar: float | bool) -> None:
    with pytest.raises(sz.TutarGecersiz):
        fk.tutar_dogrula(tutar)


# --- diğer alanlar -------------------------------------------------------------------


@pytest.mark.parametrize("nesne_id", [0, -3, 2.0, True, "7", None])
def test_nesne_kimligi_kati(nesne_id: object) -> None:
    with pytest.raises(sz.GirdiGecersiz, match="kimlik"):
        fk.hesap_hareketi_dogrula(_hareket(nesne_id=nesne_id))


@pytest.mark.parametrize("yon", ["arttir", "GIRIS", "", None, 1])
def test_yon_izinli_degerler(yon: object) -> None:
    with pytest.raises(sz.GirdiGecersiz, match="yön"):
        fk.hesap_hareketi_dogrula(_hareket(yon=yon))


def test_try_disi_para_birimi() -> None:
    with pytest.raises(sz.ParaBirimiDesteklenmiyor):
        fk.hesap_hareketi_dogrula(_hareket(para_birimi="USD"))


@pytest.mark.parametrize(
    ("alan", "deger"),
    [
        ("islem_tarihi", "15.08.2026"),
        ("islem_tarihi", "2026-13-01"),
        ("islem_tarihi", None),
        ("islem_tarihi", datetime(2026, 8, 15, 10, 0)),
        ("islem_tarihi", 20260815),
        ("valor_tarihi", "dün"),
    ],
)
def test_tarih_bicimi(alan: str, deger: object) -> None:
    with pytest.raises(sz.GirdiGecersiz) as hata:
        fk.hesap_hareketi_dogrula(_hareket(**{alan: deger}))
    assert hata.value.alan == alan


def test_aciklama_metin_ve_sinirli() -> None:
    with pytest.raises(sz.GirdiGecersiz, match="metin"):
        fk.hesap_hareketi_dogrula(_hareket(aciklama=42))
    with pytest.raises(sz.GirdiGecersiz, match="512"):
        fk.hesap_hareketi_dogrula(_hareket(aciklama="x" * 513))


def test_dogrulama_veritabanina_dokunmaz(tmp_path: object) -> None:
    """Saf işlev: yalnız girdi ve çıktı; nesnenin varlığı yazma anında denetlenir."""
    taslak = fk.hesap_hareketi_dogrula(_hareket(nesne_id=999_999))
    assert taslak.asil_nesne_id == 999_999

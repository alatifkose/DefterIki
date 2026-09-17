"""Pencere işlevleri testleri (Teslim 6.1): "veri değişti mi?" sorusu.

Pencere tarafı bu modülü çağırır; SQLite ayrıntısı (``data_version``) burada
saklı kalır. Yazmalar ayrı bir ``Veritabani`` nesnesinden yapılır: gerçek
kullanımda MCP sunucusu ve onay komutu ayrı süreçtir.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from defteriki import ayarlar as ay
from defteriki import denetim, gunluk, nesneler, onaylar, pencere_islevleri
from defteriki import sozlesmeler as sz
from defteriki import veritabani as vt
from defteriki.baslangic import ortami_hazirla

DEGISKENLER = (
    ay.ORTAM_DEGISKENI,
    ay.VERI_KOKU_DEGISKENI,
    ay.VERITABANI_YOLU_DEGISKENI,
    ay.BELGE_DIZINI_DEGISKENI,
    ay.LOG_DIZINI_DEGISKENI,
    ay.GELEN_DIZINI_DEGISKENI,
)


@pytest.fixture
def ayarlar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ay.Ayarlar]:
    for degisken in DEGISKENLER:
        monkeypatch.delenv(degisken, raising=False)
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(tmp_path / "kok"))
    gunluk.gunlugu_kapat()
    yield ortami_hazirla().ayarlar
    gunluk.gunlugu_kapat()


@pytest.fixture
def islevler(ayarlar: ay.Ayarlar) -> Iterator[pencere_islevleri.PencereIslevleri]:
    i = pencere_islevleri.pencere_islevleri_ac(ayarlar)
    yield i
    i.kapat()


def _baska_surec_yazar(ayarlar: ay.Ayarlar) -> None:
    db = vt.veritabani_ac(ayarlar)
    try:
        with db.yazma_islemi() as oturum:
            denetim.olay_yaz(
                oturum,
                aktor=sz.DenetimAktoru.UYGULAMA,
                eylem="test",
                hedef="test",
                simdi=datetime.now(UTC),
            )
    finally:
        db.kapat()


def test_ilk_soru_baslangic_noktasidir(
    islevler: pencere_islevleri.PencereIslevleri,
) -> None:
    assert islevler.degisti_mi() is False
    assert islevler.degisti_mi() is False


def test_baska_surecin_yazmasi_bir_kez_evet_doner(
    islevler: pencere_islevleri.PencereIslevleri, ayarlar: ay.Ayarlar
) -> None:
    islevler.degisti_mi()

    _baska_surec_yazar(ayarlar)
    assert islevler.degisti_mi() is True
    assert islevler.degisti_mi() is False  # aynı değişiklik ikinci kez bildirilmez

    _baska_surec_yazar(ayarlar)
    _baska_surec_yazar(ayarlar)
    assert islevler.degisti_mi() is True  # iki yazma tek "evet"
    assert islevler.degisti_mi() is False


def test_soru_yazmayi_engellemez(
    islevler: pencere_islevleri.PencereIslevleri, ayarlar: ay.Ayarlar
) -> None:
    islevler.degisti_mi()
    _baska_surec_yazar(ayarlar)  # kilit beklemeden tamamlanır
    assert islevler.degisti_mi() is True


def test_kapat_sonrasi_yeniden_sorulabilir(ayarlar: ay.Ayarlar) -> None:
    islevler = pencere_islevleri.pencere_islevleri_ac(ayarlar)
    islevler.degisti_mi()
    islevler.kapat()
    assert islevler.degisti_mi() is False
    islevler.kapat()


# --- karar kutusu işlevleri (6.2) -----------------------------------------------------


def _cowork_onerir(
    ayarlar: ay.Ayarlar,
    anahtar: str,
    ozellikler: list[tuple[str, object]],
    ust_idleri: tuple[int, ...] = (),
) -> tuple[int, int]:
    """Cowork GONDER gibi: nesne ONAY_BEKLIYOR + talep. (nesne_id, talep_id)."""
    db = vt.veritabani_ac(ayarlar)
    try:
        with db.yazma_islemi() as oturum:
            sonuc = nesneler.nesne_tanimla(
                oturum,
                ozellikler=[nesneler.OzellikGirdisi(a, d) for a, d in ozellikler],
                islem_anahtari=anahtar,
                aktor=sz.DenetimAktoru.COWORK,
                ust_idleri=ust_idleri,
            )
            return sonuc.nesne.id, sonuc.onay_talebi.id
    finally:
        db.kapat()


def _nesne(ayarlar: ay.Ayarlar, nesne_id: int) -> nesneler.NesneAyrinti:
    db = vt.veritabani_ac(ayarlar)
    try:
        with db.okuma_islemi() as oturum:
            return nesneler.nesne_getir(oturum, nesne_id)
    finally:
        db.kapat()


@pytest.fixture
def banka_ve_hesap(ayarlar: ay.Ayarlar) -> tuple[int, int, int, int]:
    """Akbank (talep 1) ve altında bir hesap (talep 2). (banka, t1, hesap, t2)."""
    banka, t1 = _cowork_onerir(ayarlar, "b", [("ad", "Akbank"), ("tür", "banka")])
    hesap, t2 = _cowork_onerir(
        ayarlar,
        "h",
        [("ad", "ME"), ("tür", "vadesiz hesap"), ("iban", "TR00"), ("şube", "0120")],
        ust_idleri=(banka,),
    )
    return banka, t1, hesap, t2


def test_bekleyenler_bos_defterde_bos(
    islevler: pencere_islevleri.PencereIslevleri,
) -> None:
    assert islevler.bekleyenler() == []


def test_bekleyenler_eskiden_yeniye_hedef_ozetiyle(
    islevler: pencere_islevleri.PencereIslevleri,
    banka_ve_hesap: tuple[int, int, int, int],
) -> None:
    banka, t1, hesap, t2 = banka_ve_hesap
    liste = islevler.bekleyenler()

    assert [(t.talep_id, t.hedef_id, t.hedef_surumu) for t in liste] == [
        (t1, banka, 1),
        (t2, hesap, 1),
    ]
    assert liste[0].tur == "NESNE_ACILISI"
    assert liste[0].hedef_ozeti == "ad=Akbank; tür=banka"
    assert liste[1].hedef_ozeti == "ad=ME; tür=vadesiz hesap; iban=TR00"  # en çok üç
    assert liste[0].olusturma_zamani.tzinfo is not None  # yerel saat, dilimli


def test_yerel_saat_utc_yi_cevirir() -> None:
    utc = datetime(2026, 9, 17, 9, 34, 7)
    yerel = pencere_islevleri.yerel_saat(utc)
    assert yerel.tzinfo is not None
    assert yerel.astimezone(UTC).replace(tzinfo=None) == utc


def test_talep_ayrintisi_nesne_ustler_ve_ozellikler(
    islevler: pencere_islevleri.PencereIslevleri,
    banka_ve_hesap: tuple[int, int, int, int],
) -> None:
    banka, _t1, hesap, t2 = banka_ve_hesap
    a = islevler.talep_ayrintisi(t2)

    assert (a.talep.talep_id, a.nesne_id, a.seviye) == (t2, hesap, 1)
    assert a.nesne_durumu == "ONAY_BEKLIYOR" and a.nesne_surumu == 1
    assert a.ustler == (f"nesne {banka}: ad=Akbank; tür=banka",)
    assert [(o.alan_adi, o.deger, o.deger_turu, o.sart) for o in a.ozellikler] == [
        ("ad", "ME", "METIN", False),
        ("tür", "vadesiz hesap", "METIN", False),
        ("iban", "TR00", "METIN", False),
        ("şube", "0120", "METIN", False),
    ]
    assert len({o.ozellik_id for o in a.ozellikler}) == 4


def test_talep_ayrintisi_olmayan_talep(
    islevler: pencere_islevleri.PencereIslevleri,
) -> None:
    with pytest.raises(sz.HedefBulunamadi):
        islevler.talep_ayrintisi(99)


def test_onay_sart_secimiyle_nesneyi_aktif_yapar(
    islevler: pencere_islevleri.PencereIslevleri,
    ayarlar: ay.Ayarlar,
    banka_ve_hesap: tuple[int, int, int, int],
) -> None:
    _banka, _t1, hesap, t2 = banka_ve_hesap
    a = islevler.talep_ayrintisi(t2)
    iban = next(o.ozellik_id for o in a.ozellikler if o.alan_adi == "iban")

    sonuc = islevler.karar_ver(
        t2, a.nesne_surumu, onaylandi=True, secilen_sartlar=(iban,), gerekce="ok"
    )

    assert sonuc == pencere_islevleri.KararSonucu(t2, "ONAYLANDI", hesap, "AKTIF", 2)
    ayrinti = _nesne(ayarlar, hesap)
    assert [o.alan_adi for o in ayrinti.ozellikler if o.sart] == ["iban"]
    assert [t.talep_id for t in islevler.bekleyenler()] == [_t1]


def test_red_nesneyi_siler(
    islevler: pencere_islevleri.PencereIslevleri,
    ayarlar: ay.Ayarlar,
    banka_ve_hesap: tuple[int, int, int, int],
) -> None:
    banka, t1, _hesap, _t2 = banka_ve_hesap

    sonuc = islevler.karar_ver(t1, 1, onaylandi=False)

    assert (sonuc.talep_durumu, sonuc.nesne_durumu) == ("REDDEDILDI", "SILINDI")
    assert _nesne(ayarlar, banka).nesne.durum is sz.NesneDurumu.SILINDI


def test_eski_surumle_karar_uygulanmaz(
    islevler: pencere_islevleri.PencereIslevleri,
    ayarlar: ay.Ayarlar,
    banka_ve_hesap: tuple[int, int, int, int],
) -> None:
    banka, t1, _hesap, _t2 = banka_ve_hesap
    gorulen = islevler.talep_ayrintisi(t1).nesne_surumu

    # başka bir yerden (onay komutu gibi) karar verildi, sürüm 2 oldu
    islevler.karar_ver(t1, gorulen, onaylandi=True)

    with pytest.raises(sz.GirdiGecersiz):  # talep zaten sonuçlanmış
        islevler.karar_ver(t1, gorulen, onaylandi=False)
    assert _nesne(ayarlar, banka).nesne.durum is sz.NesneDurumu.AKTIF


def test_hedef_surumu_degistiyse_karar_uygulanmaz(
    islevler: pencere_islevleri.PencereIslevleri,
    banka_ve_hesap: tuple[int, int, int, int],
) -> None:
    _banka, t1, _hesap, _t2 = banka_ve_hesap
    with pytest.raises(sz.HedefSurumuDegisti):
        islevler.karar_ver(t1, 7, onaylandi=True)
    assert [t.talep_id for t in islevler.bekleyenler()] == [t1, _t2]


def test_karar_bos_gerekceyi_none_yapar(
    islevler: pencere_islevleri.PencereIslevleri,
    ayarlar: ay.Ayarlar,
    banka_ve_hesap: tuple[int, int, int, int],
) -> None:
    _banka, t1, _hesap, _t2 = banka_ve_hesap
    islevler.karar_ver(t1, 1, onaylandi=True, gerekce="")
    db = vt.veritabani_ac(ayarlar)
    try:
        with db.okuma_islemi() as oturum:
            talep = onaylar.talep_getir(oturum, t1)
    finally:
        db.kapat()
    assert talep.karar is not None and talep.karar["gerekce"] is None
    assert talep.karar["aktor"] == "KULLANICI"

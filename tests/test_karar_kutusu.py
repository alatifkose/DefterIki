"""Karar kutusu testleri (Teslim 6.2): liste, ayrıntı, şart seçimi, onay/ret/ertele.

Ortam ``test``, ekransız Qt. Cowork'un önerisi ayrı bir bağlantıdan
``nesneler.nesne_tanimla`` ile yazılır; karar pencereden verilir.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from defteriki import ayarlar as ay
from defteriki import gunluk, nesneler, pencere_islevleri
from defteriki import sozlesmeler as sz
from defteriki import veritabani as vt
from defteriki.arayuz import ana_pencere, karar_kutusu
from defteriki.baslangic import Hazirlik, ortami_hazirla

DEGISKENLER = (
    ay.ORTAM_DEGISKENI,
    ay.VERI_KOKU_DEGISKENI,
    ay.VERITABANI_YOLU_DEGISKENI,
    ay.BELGE_DIZINI_DEGISKENI,
    ay.LOG_DIZINI_DEGISKENI,
    ay.GELEN_DIZINI_DEGISKENI,
)
YOKLAMA_MS = 20
BEKLEME_MS = 3000


@pytest.fixture
def hazirlik(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Hazirlik]:
    for degisken in DEGISKENLER:
        monkeypatch.delenv(degisken, raising=False)
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(tmp_path / "kok"))
    gunluk.gunlugu_kapat()
    yield ortami_hazirla()
    gunluk.gunlugu_kapat()


def _cowork_onerir(
    ayarlar: ay.Ayarlar,
    anahtar: str,
    ozellikler: list[tuple[str, object]],
    ust_idleri: tuple[int, ...] = (),
) -> tuple[int, int]:
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


def _nesne_durumu(ayarlar: ay.Ayarlar, nesne_id: int) -> tuple[str, list[str]]:
    db = vt.veritabani_ac(ayarlar)
    try:
        with db.okuma_islemi() as oturum:
            a = nesneler.nesne_getir(oturum, nesne_id)
            return a.nesne.durum.value, [o.alan_adi for o in a.ozellikler if o.sart]
    finally:
        db.kapat()


@pytest.fixture
def oneriler(hazirlik: Hazirlik) -> tuple[int, int, int, int]:
    banka, t1 = _cowork_onerir(
        hazirlik.ayarlar, "b", [("ad", "Akbank"), ("tür", "banka")]
    )
    hesap, t2 = _cowork_onerir(
        hazirlik.ayarlar,
        "h",
        [("ad", "ME"), ("iban", "TR00")],
        ust_idleri=(banka,),
    )
    return banka, t1, hesap, t2


@pytest.fixture
def kutu(hazirlik: Hazirlik, qtbot: QtBot) -> Iterator[karar_kutusu.KararKutusu]:
    islevler = pencere_islevleri.pencere_islevleri_ac(hazirlik.ayarlar)
    k = karar_kutusu.KararKutusu(islevler)
    qtbot.addWidget(k)
    k.show()
    yield k
    k.close()
    islevler.kapat()


def _sart_isaretle(kutu: karar_kutusu.KararKutusu, alan_adi: str) -> None:
    for satir in range(kutu.ozellik_tablosu.rowCount()):
        alan = kutu.ozellik_tablosu.item(satir, karar_kutusu.SUTUN_ALAN)
        sart = kutu.ozellik_tablosu.item(satir, karar_kutusu.SUTUN_SART)
        assert alan is not None and sart is not None
        if alan.text() == alan_adi:
            sart.setCheckState(Qt.CheckState.Checked)
            return
    raise AssertionError(f"alan yok: {alan_adi}")


# --- liste ve ayrıntı -----------------------------------------------------------------


def test_bos_defterde_liste_bos_ve_dugmeler_kapali(
    kutu: karar_kutusu.KararKutusu,
) -> None:
    assert kutu.bekleyen_sayisi == 0
    assert kutu.baslik_etiketi.text() == karar_kutusu.METIN_BEKLEYEN_YOK
    assert not kutu.onayla_dugmesi.isEnabled()
    assert not kutu.reddet_dugmesi.isEnabled()
    assert not kutu.ertele_dugmesi.isEnabled()


def test_bekleyenler_listelenir_secim_ayrintiyi_gosterir(
    kutu: karar_kutusu.KararKutusu, oneriler: tuple[int, int, int, int]
) -> None:
    banka, t1, hesap, t2 = oneriler
    kutu.yenile()

    assert kutu.bekleyen_sayisi == 2
    assert (
        kutu.liste.item(0).text().startswith(f"Talep {t1} · NESNE_ACILISI · ad=Akbank")
    )
    assert kutu.baslik_etiketi.text() == karar_kutusu.METIN_SECIM_YOK

    kutu.liste.setCurrentRow(1)

    assert kutu.secili_talep_id == t2
    assert (
        f"nesne {hesap} (seviye 1, ONAY_BEKLIYOR, sürüm 1)"
        in kutu.baslik_etiketi.text()
    )
    assert kutu.ustler_etiketi.text() == f"Üstler: nesne {banka}: ad=Akbank; tür=banka"
    assert kutu.ozellik_tablosu.rowCount() == 2
    alanlar = [
        kutu.ozellik_tablosu.item(s, karar_kutusu.SUTUN_ALAN).text()  # type: ignore[union-attr]
        for s in range(2)
    ]
    assert alanlar == ["ad", "iban"]
    assert kutu.secili_sartlar() == ()
    assert kutu.onayla_dugmesi.isEnabled()


# --- kararlar -------------------------------------------------------------------------


def test_sart_isaretleyip_onayla_nesne_aktif_liste_kisalir(
    kutu: karar_kutusu.KararKutusu,
    hazirlik: Hazirlik,
    oneriler: tuple[int, int, int, int],
    qtbot: QtBot,
) -> None:
    _banka, t1, hesap, t2 = oneriler
    kutu.yenile()
    kutu.liste.setCurrentRow(1)
    _sart_isaretle(kutu, "iban")
    kutu.gerekce.setText("ekstre kanıtı")

    with qtbot.waitSignal(kutu.karar_verildi, timeout=BEKLEME_MS):
        kutu.onayla_dugmesi.click()

    assert _nesne_durumu(hazirlik.ayarlar, hesap) == ("AKTIF", ["iban"])
    assert kutu.mesaj_etiketi.text() == (
        f"Talep {t2} ONAYLANDI; nesne {hesap} AKTIF (sürüm 2)."
    )
    assert kutu.bekleyen_sayisi == 1 and kutu.liste.item(0).text().startswith(
        f"Talep {t1}"
    )
    assert kutu.secili_talep_id is None
    assert not kutu.onayla_dugmesi.isEnabled()


def test_reddet_nesneyi_siler(
    kutu: karar_kutusu.KararKutusu,
    hazirlik: Hazirlik,
    oneriler: tuple[int, int, int, int],
) -> None:
    banka, t1, _hesap, _t2 = oneriler
    kutu.yenile()
    kutu.liste.setCurrentRow(0)

    kutu.reddet_dugmesi.click()

    assert _nesne_durumu(hazirlik.ayarlar, banka)[0] == "SILINDI"
    assert f"Talep {t1} REDDEDILDI; nesne {banka} SILINDI" in kutu.mesaj_etiketi.text()
    assert kutu.bekleyen_sayisi == 1


def test_ertele_hicbir_sey_yazmaz(
    kutu: karar_kutusu.KararKutusu,
    hazirlik: Hazirlik,
    oneriler: tuple[int, int, int, int],
) -> None:
    banka, _t1, _hesap, _t2 = oneriler
    kutu.yenile()
    kutu.liste.setCurrentRow(0)

    kutu.ertele_dugmesi.click()

    assert kutu.secili_talep_id is None
    assert kutu.mesaj_etiketi.text() == karar_kutusu.METIN_ERTELENDI
    assert kutu.bekleyen_sayisi == 2
    assert _nesne_durumu(hazirlik.ayarlar, banka)[0] == "ONAY_BEKLIYOR"
    assert not kutu.onayla_dugmesi.isEnabled()


def test_talep_baska_yerden_sonuclandiysa_mesaj_ve_liste_yenilenir(
    kutu: karar_kutusu.KararKutusu,
    hazirlik: Hazirlik,
    oneriler: tuple[int, int, int, int],
) -> None:
    """Kullanıcı bakarken talep başka yerden (onay komutu) sonuçlandı."""
    banka, t1, _hesap, _t2 = oneriler
    kutu.yenile()
    kutu.liste.setCurrentRow(0)

    baska = pencere_islevleri.pencere_islevleri_ac(hazirlik.ayarlar)
    try:
        baska.karar_ver(t1, 1, onaylandi=False)  # nesne SILINDI, sürüm 2
    finally:
        baska.kapat()

    kutu.onayla_dugmesi.click()

    assert kutu.mesaj_etiketi.text() == (
        "Karar uygulanamadı: onay talebi zaten sonuçlanmış (REDDEDILDI)"
    )
    assert _nesne_durumu(hazirlik.ayarlar, banka)[0] == "SILINDI"  # onay uygulanmadı
    assert kutu.bekleyen_sayisi == 1  # liste yenilendi, t1 düştü
    assert kutu.secili_talep_id is None


def test_hedef_surumu_degistiyse_ozel_mesaj_ve_liste_yenilenir(
    kutu: karar_kutusu.KararKutusu,
    oneriler: tuple[int, int, int, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Hedef sürümü görülenden farklı: onaylar HEDEF_SURUMU_DEGISTI verir."""
    kutu.yenile()
    kutu.liste.setCurrentRow(0)
    yenilemeler: list[int] = []
    kutu.yenilendi.connect(yenilemeler.append)

    def degisti(*_a: object, **_k: object) -> pencere_islevleri.KararSonucu:
        raise sz.HedefSurumuDegisti(
            "hedef karar beklerken değişti", alan="hedef_surumu"
        )

    monkeypatch.setattr(kutu._islevler, "karar_ver", degisti)  # pyright: ignore[reportPrivateUsage]

    kutu.reddet_dugmesi.click()

    assert kutu.mesaj_etiketi.text() == karar_kutusu.METIN_HEDEF_DEGISTI
    assert yenilemeler == [2]  # liste yenilendi, iki talep hâlâ bekliyor


def test_seciliyken_baska_talep_gelirse_secim_korunur(
    kutu: karar_kutusu.KararKutusu,
    hazirlik: Hazirlik,
    oneriler: tuple[int, int, int, int],
) -> None:
    _banka, _t1, _hesap, t2 = oneriler
    kutu.yenile()
    kutu.liste.setCurrentRow(1)
    _sart_isaretle(kutu, "iban")

    _cowork_onerir(hazirlik.ayarlar, "g", [("ad", "Garanti BBVA")])
    kutu.yenile()

    assert kutu.bekleyen_sayisi == 3
    assert kutu.secili_talep_id == t2
    assert kutu.secili_sartlar() == ()  # ayrıntı yeniden çekildi; işaret veritabanından


# --- pencereyle bütünleşme ------------------------------------------------------------


def test_pencere_sekme_basligi_bekleyen_sayisini_tasir_ve_degisiklikte_yenilenir(
    hazirlik: Hazirlik, qtbot: QtBot
) -> None:
    islevler = pencere_islevleri.pencere_islevleri_ac(hazirlik.ayarlar)
    pencere = ana_pencere.AnaPencere(hazirlik, islevler, yoklama_araligi_ms=YOKLAMA_MS)
    qtbot.addWidget(pencere)
    pencere.show()
    try:
        assert pencere.sekmeler.tabText(0) == ana_pencere.SEKME_KARAR_KUTUSU
        assert pencere.statusBar().currentMessage() == (
            f"Veritabanı: {hazirlik.ayarlar.veritabani_yolu}"
        )

        with qtbot.waitSignal(pencere.karar_kutusu.yenilendi, timeout=BEKLEME_MS):
            _cowork_onerir(hazirlik.ayarlar, "b", [("ad", "Akbank")])

        assert pencere.sekmeler.tabText(0) == f"{ana_pencere.SEKME_KARAR_KUTUSU} (1)"
        assert pencere.karar_kutusu.bekleyen_sayisi == 1
    finally:
        pencere.close()
        islevler.kapat()


def test_pencere_kapanip_acilinca_bekleyenler_yerinde(
    hazirlik: Hazirlik, oneriler: tuple[int, int, int, int], qtbot: QtBot
) -> None:
    """S19'un ilk yarısı: talepler veritabanında, pencere belleğinde değil."""
    for _ in range(2):
        islevler = pencere_islevleri.pencere_islevleri_ac(hazirlik.ayarlar)
        pencere = ana_pencere.AnaPencere(hazirlik, islevler, yoklama_araligi_ms=10_000)
        qtbot.addWidget(pencere)
        pencere.show()
        assert pencere.karar_kutusu.bekleyen_sayisi == 2
        assert pencere.sekmeler.tabText(0).endswith("(2)")
        pencere.close()
        islevler.kapat()

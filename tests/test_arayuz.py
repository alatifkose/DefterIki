"""Pencere kabuğu testleri (Teslim 6.1): başlangıç, durum çubuğu, değişiklik izleme.

Ortam ``test``, veri kökü tmp_path; ekransız Qt (``conftest``). Yazmalar
pencerenin bağlantısından değil ayrı bir ``Veritabani`` nesnesinden yapılır:
gerçek kullanımda MCP sunucusu ve onay komutu da ayrı süreçtir.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PySide6.QtWidgets import QApplication
from pytestqt.qtbot import QtBot

from defteriki import ayarlar as ay
from defteriki import denetim, gunluk, pencere_islevleri
from defteriki import sozlesmeler as sz
from defteriki import veritabani as vt
from defteriki.arayuz import ana_pencere, baslat, degisiklik_izleme
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


@pytest.fixture
def pencere(hazirlik: Hazirlik, qtbot: QtBot) -> Iterator[ana_pencere.AnaPencere]:
    islevler = pencere_islevleri.pencere_islevleri_ac(hazirlik.ayarlar)
    p = ana_pencere.AnaPencere(hazirlik, islevler, yoklama_araligi_ms=YOKLAMA_MS)
    qtbot.addWidget(p)
    p.show()
    yield p
    p.close()
    islevler.kapat()


def _baska_surec_yazar(hazirlik: Hazirlik) -> None:
    """MCP sunucusu ya da onay komutu gibi ayrı bağlantıdan bir yazma."""
    db = vt.veritabani_ac(hazirlik.ayarlar)
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


def _log_metni(hazirlik: Hazirlik) -> str:
    return hazirlik.log_dosyasi.read_text(encoding="utf-8")


# --- kabuk ---------------------------------------------------------------------------


def test_pencere_basligi_boyutu_ve_durum_cubugu(
    pencere: ana_pencere.AnaPencere, hazirlik: Hazirlik
) -> None:
    assert pencere.windowTitle() == "DEFTERIKI"
    assert pencere.width() == ana_pencere.PENCERE_GENISLIK
    assert pencere.height() == ana_pencere.PENCERE_YUKSEKLIK
    assert pencere.ortam_etiketi.text() == "Ortam: test"
    assert pencere.sema_etiketi.text() == f"Şema: {hazirlik.sema_surumu}"
    assert pencere.degisiklik_etiketi.text() == ana_pencere.METIN_DEGISIKLIK_YOK
    assert pencere.izleyici.calisiyor


def test_pencere_kapaninca_izleme_durur(
    pencere: ana_pencere.AnaPencere,
) -> None:
    pencere.close()
    assert not pencere.izleyici.calisiyor


# --- değişiklik izleme -------------------------------------------------------------


def test_baska_baglantinin_yazmasi_durum_cubuguna_duser(
    pencere: ana_pencere.AnaPencere, hazirlik: Hazirlik, qtbot: QtBot
) -> None:
    with qtbot.waitSignal(pencere.izleyici.degisti, timeout=BEKLEME_MS):
        _baska_surec_yazar(hazirlik)

    assert pencere.degisiklik_sayisi == 1
    assert pencere.degisiklik_etiketi.text().startswith("Son değişiklik: ")
    assert pencere.degisiklik_etiketi.text().endswith("(1)")

    with qtbot.waitSignal(pencere.izleyici.degisti, timeout=BEKLEME_MS):
        _baska_surec_yazar(hazirlik)
    assert pencere.degisiklik_sayisi == 2


def test_yazma_yoksa_sinyal_yok(pencere: ana_pencere.AnaPencere, qtbot: QtBot) -> None:
    with qtbot.assertNotEmitted(pencere.izleyici.degisti, wait=YOKLAMA_MS * 10):
        pass
    assert pencere.degisiklik_sayisi == 0


def test_izleyici_yokla_degisimi_bildirir(hazirlik: Hazirlik, qtbot: QtBot) -> None:
    islevler = pencere_islevleri.pencere_islevleri_ac(hazirlik.ayarlar)
    try:
        izleyici = degisiklik_izleme.DegisiklikIzleyici(islevler, aralik_ms=10_000)
        izleyici.baslat()
        assert izleyici.yokla() is False

        _baska_surec_yazar(hazirlik)
        with qtbot.waitSignal(izleyici.degisti, timeout=BEKLEME_MS):
            assert izleyici.yokla() is True
        assert izleyici.yokla() is False
        izleyici.durdur()
    finally:
        islevler.kapat()


def test_yoklama_hatasi_izlemeyi_durdurur_ve_gunluge_yazar(
    pencere: ana_pencere.AnaPencere,
    hazirlik: Hazirlik,
    qtbot: QtBot,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def bozuk_soru() -> bool:
        raise OSError("disk yok")

    monkeypatch.setattr(
        pencere.izleyici._islevler,  # pyright: ignore[reportPrivateUsage]
        "degisti_mi",
        bozuk_soru,
    )
    with qtbot.waitSignal(pencere.izleyici.durdu, timeout=BEKLEME_MS):
        pass

    assert not pencere.izleyici.calisiyor
    assert pencere.degisiklik_etiketi.text() == "Değişiklik: izleme durdu (OSError)"
    assert degisiklik_izleme.OLAY_IZLEME_HATASI in _log_metni(hazirlik)
    assert "OSError" in _log_metni(hazirlik)


# --- başlangıç ----------------------------------------------------------------------


def test_main_basarili_pencere_acar_ve_olay_yazar(
    hazirlik: Hazirlik, qtbot: QtBot
) -> None:
    gorulen: list[str] = []

    def dongu(_uygulama: object) -> int:
        acik = [
            w
            for w in QApplication.topLevelWidgets()
            if isinstance(w, ana_pencere.AnaPencere) and w.isVisible()
        ]
        gorulen.extend(w.windowTitle() for w in acik)
        return 0

    kod = baslat.main(
        argv=["defteriki-arayuz"], hata_goster=lambda m: None, dongu=dongu
    )

    assert kod == 0
    assert gorulen == ["DEFTERIKI"]
    assert baslat.OLAY_ARAYUZ_BASLANGIC in _log_metni(hazirlik)


def test_main_ayar_hatasinda_ileti_ve_bir_doner(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    qtbot: QtBot,
) -> None:
    for degisken in DEGISKENLER:
        monkeypatch.delenv(degisken, raising=False)
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")  # veri kökü yok → ayar hatası
    gorulen: list[str] = []

    kod = baslat.main(argv=["defteriki-arayuz"], hata_goster=gorulen.append)

    assert kod == 1
    assert len(gorulen) == 1 and gorulen[0].startswith("Ayar hatası")
    assert "DEFTERIKI penceresi açılamadı" in capsys.readouterr().err


def test_main_beklenmeyen_hatayi_gunluge_yazar_ve_bir_doner(
    hazirlik: Hazirlik, qtbot: QtBot
) -> None:
    gorulen: list[str] = []

    def patlayan_dongu(_uygulama: object) -> int:
        raise RuntimeError("olay döngüsü patladı")

    kod = baslat.main(
        argv=["defteriki-arayuz"], hata_goster=gorulen.append, dongu=patlayan_dongu
    )

    assert kod == 1
    assert gorulen == ["Beklenmeyen hata (RuntimeError): olay döngüsü patladı"]
    assert baslat.OLAY_ARAYUZ_HATASI in _log_metni(hazirlik)


def test_komut_girisi_pyprojectte() -> None:
    metin = (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(
        encoding="utf-8"
    )
    assert 'defteriki-arayuz = "defteriki.arayuz.baslat:main"' in metin


# --- katman sınırı (K20) --------------------------------------------------------------


def test_arayuz_altyapi_modullerini_import_etmez() -> None:
    """Pencere → pencere_islevleri → veritabanı: arayuz/ altında veritabani,
    sema, sqlalchemy ya da sqlite3 import edilmez, SQL yazılmaz."""
    yasakli = ("defteriki.veritabani", "defteriki.sema", "sqlalchemy", "sqlite3")
    arayuz = Path(__file__).resolve().parent.parent / "src" / "defteriki" / "arayuz"
    for dosya in sorted(arayuz.glob("*.py")):
        for satir in dosya.read_text(encoding="utf-8").splitlines():
            if satir.startswith(("import ", "from ")):
                assert not any(ad in satir for ad in yasakli), f"{dosya.name}: {satir}"
            assert "PRAGMA" not in satir and "SELECT " not in satir, (
                f"{dosya.name}: {satir}"
            )

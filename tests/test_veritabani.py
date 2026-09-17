"""Veritabanı bağlantısı ve işlem sınırı testleri.

Bütün dosyalar tmp_path altındadır. İki süreç testi, aynı ortam değişkenleriyle
başlatılan bir alt sürecin aynı dosyayı çözdüğünü sınar.
"""

import os
import sqlite3
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from defteriki import ayarlar as ay
from defteriki import sozlesmeler as sz
from defteriki import veritabani as vt

DEFTERIKI_DEGISKENLERI = (
    ay.ORTAM_DEGISKENI,
    ay.VERI_KOKU_DEGISKENI,
    ay.VERITABANI_YOLU_DEGISKENI,
    ay.BELGE_DIZINI_DEGISKENI,
    ay.LOG_DIZINI_DEGISKENI,
    ay.GELEN_DIZINI_DEGISKENI,
)

SEMA = (
    "CREATE TABLE ust (id INTEGER PRIMARY KEY, ad TEXT NOT NULL)",
    "CREATE TABLE alt (id INTEGER PRIMARY KEY, ust_id INTEGER NOT NULL "
    "REFERENCES ust(id))",
)


@pytest.fixture(autouse=True)
def temiz_cevre(monkeypatch: pytest.MonkeyPatch) -> None:
    for degisken in DEFTERIKI_DEGISKENLERI:
        monkeypatch.delenv(degisken, raising=False)


@pytest.fixture
def yol(tmp_path: Path) -> Path:
    return tmp_path / "vt" / "deneme.sqlite3"


@pytest.fixture
def veritabani(yol: Path) -> Iterator[vt.Veritabani]:
    yol.parent.mkdir()
    db = vt.Veritabani(yol, mesgul_bekleme_ms=200)
    yield db
    db.kapat()


def _semayi_kur(db: vt.Veritabani) -> None:
    with db.yazma_islemi() as oturum:
        for ifade in SEMA:
            oturum.execute(text(ifade))


def _sayi(db: vt.Veritabani, tablo: str) -> int:
    with db.okuma_islemi() as oturum:
        return int(oturum.execute(text(f"SELECT count(*) FROM {tablo}")).scalar_one())


# --- dosya oluşturma zamanı ------------------------------------------------------


def test_import_ve_kurulum_dosya_olusturmaz(yol: Path) -> None:
    yol.parent.mkdir()

    db = vt.Veritabani(yol)

    assert not yol.exists()
    assert list(yol.parent.iterdir()) == []
    db.kapat()


def test_ilk_yazma_islemi_dosyayi_olusturur(
    veritabani: vt.Veritabani, yol: Path
) -> None:
    _semayi_kur(veritabani)

    assert yol.is_file()


def test_goreli_yol_reddedilir() -> None:
    with pytest.raises(ValueError, match="mutlak"):
        vt.Veritabani(Path("goreli.sqlite3"))


def test_veritabani_ac_ayarlardaki_yolu_kullanir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(tmp_path / "kok"))
    ayarlar = ay.ayarlari_yukle()

    db = vt.veritabani_ac(ayarlar)

    assert db.yol == ayarlar.veritabani_yolu
    assert not db.yol.exists()
    db.kapat()


# --- PRAGMA değerleri --------------------------------------------------------------


def _pragmalar(oturum: Session) -> dict[str, object]:
    adlar = (
        "foreign_keys",
        "journal_mode",
        "busy_timeout",
        "synchronous",
        "query_only",
    )
    return {ad: oturum.execute(text(f"PRAGMA {ad}")).scalar() for ad in adlar}


def test_yazma_baglantisi_pragmalari(veritabani: vt.Veritabani) -> None:
    with veritabani.yazma_islemi() as oturum:
        degerler = _pragmalar(oturum)

    assert degerler == {
        "foreign_keys": 1,
        "journal_mode": "wal",
        "busy_timeout": 200,
        "synchronous": 2,  # FULL
        "query_only": 0,
    }


def test_okuma_baglantisi_salt_okunur(veritabani: vt.Veritabani) -> None:
    _semayi_kur(veritabani)

    with veritabani.okuma_islemi() as oturum:
        degerler = _pragmalar(oturum)
        with pytest.raises(OperationalError, match="readonly"):
            oturum.execute(text("INSERT INTO ust (ad) VALUES ('x')"))

    assert degerler["query_only"] == 1
    assert degerler["foreign_keys"] == 1
    assert degerler["journal_mode"] == "wal"
    assert _sayi(veritabani, "ust") == 0


def test_varsayilan_bekleme_5_saniye(yol: Path) -> None:
    yol.parent.mkdir()
    db = vt.Veritabani(yol)

    with db.yazma_islemi() as oturum:
        bekleme = oturum.execute(text("PRAGMA busy_timeout")).scalar()

    assert bekleme == vt.MESGUL_BEKLEME_MS == 5000
    db.kapat()


# --- işlem sınırları -----------------------------------------------------------------


def test_basarili_islem_commit_eder(veritabani: vt.Veritabani) -> None:
    _semayi_kur(veritabani)

    with veritabani.yazma_islemi() as oturum:
        oturum.execute(text("INSERT INTO ust (ad) VALUES ('bir')"))

    assert _sayi(veritabani, "ust") == 1


def test_hata_sonrasi_yarim_satir_kalmaz(veritabani: vt.Veritabani) -> None:
    _semayi_kur(veritabani)

    with pytest.raises(RuntimeError, match="ortada patladı"):
        with veritabani.yazma_islemi() as oturum:
            oturum.execute(text("INSERT INTO ust (ad) VALUES ('bir')"))
            oturum.execute(text("INSERT INTO ust (ad) VALUES ('iki')"))
            raise RuntimeError("ortada patladı")

    assert _sayi(veritabani, "ust") == 0


def test_fk_ihlali_reddedilir_ve_islem_geri_alinir(veritabani: vt.Veritabani) -> None:
    _semayi_kur(veritabani)

    with pytest.raises(IntegrityError):
        with veritabani.yazma_islemi() as oturum:
            oturum.execute(text("INSERT INTO ust (ad) VALUES ('bir')"))
            oturum.execute(text("INSERT INTO alt (ust_id) VALUES (999)"))

    assert _sayi(veritabani, "ust") == 0
    assert _sayi(veritabani, "alt") == 0


def test_yazma_islemi_begin_immediate_ile_acilir(
    veritabani: vt.Veritabani, yol: Path
) -> None:
    """Başka bir bağlantı yazma kilidini tutarken salt SELECT bile beklemeye düşer.

    Sürücünün varsayılan BEGIN'i (DEFERRED) bu SELECT'i sorunsuz çalıştırırdı;
    IMMEDIATE olduğu için kilit kapıda istenir ve süre dolunca VeritabaniMesgul.
    """
    _semayi_kur(veritabani)
    kilit = sqlite3.connect(yol, isolation_level=None)
    kilit.execute("BEGIN IMMEDIATE")
    try:
        with pytest.raises(sz.VeritabaniMesgul) as bilgi:
            with veritabani.yazma_islemi() as oturum:
                oturum.execute(text("SELECT count(*) FROM ust"))
    finally:
        kilit.rollback()
        kilit.close()

    assert bilgi.value.kod == "VERITABANI_MESGUL"
    assert bilgi.value.tekrar_denenebilir is True
    assert isinstance(bilgi.value.__cause__, OperationalError)


def test_yazar_kilidi_okumayi_engellemez(veritabani: vt.Veritabani, yol: Path) -> None:
    """WAL: yazma sürerken okuma bekletilmez ve commit öncesi veriyi görmez."""
    _semayi_kur(veritabani)
    kilit = sqlite3.connect(yol, isolation_level=None)
    kilit.execute("BEGIN IMMEDIATE")
    kilit.execute("INSERT INTO ust (ad) VALUES ('henüz yok')")
    try:
        assert _sayi(veritabani, "ust") == 0
    finally:
        kilit.rollback()
        kilit.close()


def test_kilit_serbest_kalinca_yazma_bekleyip_basarir(
    veritabani: vt.Veritabani, yol: Path
) -> None:
    """busy_timeout içinde kilit bırakılırsa işlem hatasız tamamlanır."""
    _semayi_kur(veritabani)
    kilit = sqlite3.connect(yol, isolation_level=None)
    kilit.execute("BEGIN IMMEDIATE")
    kilit.execute("INSERT INTO ust (ad) VALUES ('öteki')")
    kilit.execute("COMMIT")  # kilit hemen bırakıldı
    kilit.close()

    with veritabani.yazma_islemi() as oturum:
        oturum.execute(text("INSERT INTO ust (ad) VALUES ('biz')"))

    assert _sayi(veritabani, "ust") == 2


# --- iki süreç aynı dosya ------------------------------------------------------

ALT_SUREC_BETIGI = """
from sqlalchemy import text
from defteriki.ayarlar import ayarlari_yukle, dizinleri_hazirla
from defteriki.veritabani import veritabani_ac
ayarlar = ayarlari_yukle()
dizinleri_hazirla(ayarlar)
db = veritabani_ac(ayarlar)
with db.yazma_islemi() as oturum:
    oturum.execute(
        text("CREATE TABLE IF NOT EXISTS iz (id INTEGER PRIMARY KEY, kim TEXT)")
    )
    oturum.execute(text("INSERT INTO iz (kim) VALUES ('alt süreç')"))
db.kapat()
print(db.yol)
"""


def test_iki_surec_ayni_ayarlarla_ayni_dosyayi_cozer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(tmp_path / "kok"))
    baska_dizin = tmp_path / "baska_calisma_dizini"
    baska_dizin.mkdir()

    sonuc = subprocess.run(
        [sys.executable, "-c", ALT_SUREC_BETIGI],
        cwd=baska_dizin,
        env={**os.environ, "PYTHONUTF8": "1"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
        check=False,
    )
    assert sonuc.returncode == 0, sonuc.stderr

    ayarlar = ay.ayarlari_yukle()
    db = vt.veritabani_ac(ayarlar)
    try:
        with db.yazma_islemi() as oturum:
            oturum.execute(text("INSERT INTO iz (kim) VALUES ('ana süreç')"))
        with db.okuma_islemi() as oturum:
            kimler = (
                oturum.execute(text("SELECT kim FROM iz ORDER BY id")).scalars().all()
            )
    finally:
        db.kapat()

    assert Path(sonuc.stdout.strip()) == ayarlar.veritabani_yolu
    assert list(kimler) == ["alt süreç", "ana süreç"]
    assert not any(baska_dizin.iterdir())


# --- değişiklik sayacı -------------------------------------------------------------


def test_degisiklik_sayaci_baska_baglantinin_commitiyle_degisir(
    veritabani: vt.Veritabani, yol: Path
) -> None:
    _semayi_kur(veritabani)
    izleyen = vt.Veritabani(yol, mesgul_bekleme_ms=200)
    try:
        ilk = izleyen.degisiklik_sayaci()
        assert izleyen.degisiklik_sayaci() == ilk  # yazma yoksa sabit

        with veritabani.yazma_islemi() as oturum:
            oturum.execute(text("INSERT INTO ust (ad) VALUES ('bir')"))

        ikinci = izleyen.degisiklik_sayaci()
        assert ikinci != ilk
        assert izleyen.degisiklik_sayaci() == ikinci
    finally:
        izleyen.kapat()


def test_degisiklik_sayaci_okuma_kilidi_tutmaz(
    veritabani: vt.Veritabani, yol: Path
) -> None:
    """Sayaç okunduktan sonra başka bağlantı beklemeden yazabilir."""
    _semayi_kur(veritabani)
    izleyen = vt.Veritabani(yol, mesgul_bekleme_ms=200)
    try:
        izleyen.degisiklik_sayaci()
        with veritabani.yazma_islemi() as oturum:
            oturum.execute(text("INSERT INTO ust (ad) VALUES ('bir')"))
        assert _sayi(veritabani, "ust") == 1
    finally:
        izleyen.kapat()


def test_kapat_izleme_baglantisini_birakir(veritabani: vt.Veritabani) -> None:
    _semayi_kur(veritabani)
    veritabani.degisiklik_sayaci()
    veritabani.kapat()
    assert veritabani._izleme_baglantisi is None  # pyright: ignore[reportPrivateUsage]
    veritabani.degisiklik_sayaci()  # kapandıktan sonra yeniden açılabilir

"""Alembic'in veritabanı yolunu `ayarlar` modülünden aldığını sınar (K-004).

Bu dosyadaki sınama gerçek bir `alembic upgrade head` koşturur. Amaç, yolun ikinci bir
yerde tanımlanmasını engellemek: `alembic.ini` içine bir adres geri yazılırsa ya da
`env.py` onu okumaya dönerse buradaki testler kırılır.
"""

import configparser
import os
import subprocess
import sys
from pathlib import Path

from defteriki import ayarlar

DEPO_KOKU = Path(__file__).resolve().parent.parent
# .gitignore ile ayni kume: dosya adi, WAL ve SHM eslikcileri.
VERITABANI_DESENLERI = tuple(
    f"*.{uzanti}{ek}" for uzanti in ("db", "sqlite", "sqlite3") for ek in ("", "-wal", "-shm")
)


def _koktenki_veritabani_dosyalari() -> set[Path]:
    return {yol for desen in VERITABANI_DESENLERI for yol in DEPO_KOKU.glob(desen)}


def test_ini_dosyasinda_baglanti_adresi_tanimli_degil() -> None:
    okuyucu = configparser.ConfigParser()
    okuyucu.read(DEPO_KOKU / "alembic.ini", encoding="utf-8")

    assert okuyucu.get("alembic", "sqlalchemy.url", fallback="").strip() == ""


def test_goc_ortam_degiskeninin_gosterdigi_dosyaya_yazar(tmp_path: Path) -> None:
    hedef = tmp_path / "gocler" / "defteriki.sqlite3"
    ortam = dict(os.environ)
    ortam[ayarlar.VERITABANI_DEGISKENI] = str(hedef)
    onceki = _koktenki_veritabani_dosyalari()

    sonuc = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=DEPO_KOKU,
        env=ortam,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert sonuc.returncode == 0, sonuc.stderr
    # Dizin yoktu; env.py bagli olmadan once olusturmali.
    assert hedef.is_file(), sonuc.stderr
    # Asil kural: hicbir sey depo kokune (yani OneDrive'a) dusmemeli.
    assert _koktenki_veritabani_dosyalari() == onceki


def test_goc_calisma_dizininden_bagimsizdir(tmp_path: Path) -> None:
    """Yol goreli olsaydi baska bir dizinden kosunca baska dosya olusurdu."""
    hedef = tmp_path / "defteriki.sqlite3"
    calisma = tmp_path / "baska_dizin"
    calisma.mkdir()
    ortam = dict(os.environ)
    ortam[ayarlar.VERITABANI_DEGISKENI] = str(hedef)

    sonuc = subprocess.run(
        [sys.executable, "-m", "alembic", "-c", str(DEPO_KOKU / "alembic.ini"), "upgrade", "head"],
        cwd=calisma,
        env=ortam,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert sonuc.returncode == 0, sonuc.stderr
    assert hedef.is_file()
    assert list(calisma.iterdir()) == []

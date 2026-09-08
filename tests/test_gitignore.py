"""Veritabanı dosyalarının depoya giremeyeceğini sınar.

Canlı veritabanı zaten depo dışında durur (K-004). Buradaki sınama ikinci savunmadır:
elle alınan bir kopya, bir dışa aktarım ya da yanlış ayarlanmış bir araç veritabanını
depo köküne bırakırsa `git add .` onu sessizce commit'lemesin.

`ayarlar.VERITABANI_DOSYA_ADI` doğrudan sınanır: veritabanının adı ilerde değişir de
`.gitignore` güncellenmezse test kırılır.
"""

import subprocess
from pathlib import Path

import pytest

from defteriki import ayarlar

DEPO_KOKU = Path(__file__).resolve().parent.parent

YOKSAYILMASI_GEREKENLER = [
    ayarlar.VERITABANI_DOSYA_ADI,
    f"{ayarlar.VERITABANI_DOSYA_ADI}-wal",
    f"{ayarlar.VERITABANI_DOSYA_ADI}-shm",
    "defteriki.db",
    "defteriki.db-wal",
    "defteriki.db-shm",
    "defteriki.sqlite",
    "yedek.sqlite3",
    "alt/dizin/kopya.sqlite3",
    ".venv/env.sqlite3",
]


def _yoksayiliyor_mu(yol: str) -> bool:
    """`git check-ignore` gercek kurallari uygular; kendi desen yorumumuzu degil."""
    sonuc = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", "--", yol],
        cwd=DEPO_KOKU,
        capture_output=True,
        timeout=60,
    )
    # 0: yoksayiliyor, 1: yoksayilmiyor, digerleri: hata
    assert sonuc.returncode in (0, 1), sonuc.stderr.decode(errors="replace")
    return sonuc.returncode == 0


@pytest.mark.parametrize("yol", YOKSAYILMASI_GEREKENLER)
def test_veritabani_dosyalari_yoksayilir(yol: str) -> None:
    assert _yoksayiliyor_mu(yol), f"{yol} .gitignore tarafindan yakalanmiyor"


def test_kaynak_dosyalar_yoksayilmaz() -> None:
    """Desenler fazla genis olmasin: gercek kod hala izlenebilmeli."""
    for yol in ("src/defteriki/ayarlar.py", "tests/test_gitignore.py", "README.md"):
        assert not _yoksayiliyor_mu(yol), f"{yol} yanlislikla yoksayiliyor"


def test_izlenen_dosyalar_arasinda_veritabani_yok() -> None:
    sonuc = subprocess.run(
        ["git", "ls-files"],
        cwd=DEPO_KOKU,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert sonuc.returncode == 0, sonuc.stderr

    uzantilar = (".db", ".sqlite", ".sqlite3")
    izlenen = [
        satir
        for satir in sonuc.stdout.splitlines()
        if any(satir.lower().endswith(uzanti) for uzanti in uzantilar)
    ]
    assert izlenen == [], f"Depoda veritabani dosyasi izleniyor: {izlenen}"

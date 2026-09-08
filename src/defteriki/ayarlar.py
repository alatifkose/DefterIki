"""Yol ve ortam kararlarının tek sahibi.

Veritabanının nerede durduğunu **yalnız bu modül** bilir. Hem uygulama hem Alembic
(`alembic/env.py`) yolu buradan alır; `alembic.ini` içindeki `sqlalchemy.url` bu yüzden
bilerek boş bırakılmıştır (K-004). Yol iki yerde yazılı olursa er ya da geç ayrışır ve
şema göçü bir dosyaya, uygulama başka dosyaya yazar — üstelik bu sessizce olur.

Fonksiyonlar önbelleklenmez: ortam değişkeni değişince sonuç da değişmelidir, testler
buna dayanır.
"""

from __future__ import annotations

import os
from pathlib import Path

UYGULAMA_ADI = "DefterIki"
VERITABANI_DOSYA_ADI = "defteriki.sqlite3"

#: Veritabanının tam dosya yolunu ezer. Testler ve ayrı bir kopyayla çalışmak içindir.
VERITABANI_DEGISKENI = "DEFTERIKI_VERITABANI"


def veri_dizini() -> Path:
    """Uygulama verisinin kök dizini.

    Windows'ta `%LOCALAPPDATA%\\DefterIki`. Canlı veritabanı bilerek OneDrive'ın
    dışında tutulur: bulut senkronu ile SQLite'ın WAL dosyaları birlikte veri
    bozulmasına yol açar.

    Windows dışında (CI, Linux kabuğu) XDG karşılığı kullanılır; buradaki amaç
    testlerin her iki tarafta da koşabilmesidir.
    """
    yerel = os.environ.get("LOCALAPPDATA")
    if yerel:
        return Path(yerel) / UYGULAMA_ADI
    xdg = os.environ.get("XDG_DATA_HOME")
    taban = Path(xdg) if xdg else Path.home() / ".local" / "share"
    return taban / UYGULAMA_ADI


def veritabani_yolu() -> Path:
    """Canlı veritabanı dosyasının mutlak yolu."""
    ozel = os.environ.get(VERITABANI_DEGISKENI)
    if ozel:
        return Path(ozel).expanduser().resolve()
    return (veri_dizini() / VERITABANI_DOSYA_ADI).resolve()


def veri_dizinini_hazirla() -> Path:
    """Veritabanının bulunacağı dizini oluşturur ve döndürür.

    SQLite eksik dizini kendisi açmaz; bağlanmadan önce çağrılır.
    """
    dizin = veritabani_yolu().parent
    dizin.mkdir(parents=True, exist_ok=True)
    return dizin


def veritabani_url() -> str:
    """SQLAlchemy bağlantı adresi.

    Yol POSIX ayracıyla yazılır (`sqlite:///C:/Users/.../defteriki.sqlite3`); ters bölü
    adres içinde kaçış karakteri sayıldığı için taşınabilir değildir.
    """
    return f"sqlite:///{veritabani_yolu().as_posix()}"

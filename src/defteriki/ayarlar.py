"""Yol ve ortam kararlarının tek sahibi.

Veritabanının ve belge arşivinin nerede durduğunu **yalnız bu modül** bilir (K-004,
K-011). Hem uygulama hem Alembic (`alembic/env.py`) yolu buradan alır; `alembic.ini`
içindeki `sqlalchemy.url` bu yüzden bilerek boş bırakılmıştır. Yol iki yerde yazılı olursa
er ya da geç ayrışır ve şema göçü bir dosyaya, uygulama başka dosyaya yazar — üstelik bu
sessizce olur.

Fonksiyonlar önbelleklenmez: ortam değişkeni değişince sonuç da değişmelidir, testler
buna dayanır.
"""

from __future__ import annotations

import os
from pathlib import Path

UYGULAMA_ADI = "DefterIki"
VERITABANI_DOSYA_ADI = "defteriki.sqlite3"

BELGE_ARSIVI_DIZIN_ADI = "belgeler"

#: Veritabanının tam dosya yolunu ezer. Testler ve ayrı bir kopyayla çalışmak içindir.
VERITABANI_DEGISKENI = "DEFTERIKI_VERITABANI"
#: Belge arşivi dizinini ezer (K-011).
BELGE_ARSIVI_DEGISKENI = "DEFTERIKI_BELGE_ARSIVI"


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


def belge_arsivi_yolu() -> Path:
    """Arşivlenen belgelerin dizini; mutlak yol (K-011).

    Belge içeriği burada, SHA-256 ile adlandırılmış dosyalar olarak durur; veritabanı
    yalnız kimliği ve üstverisini tutar. Varsayılan veri dizininin altındadır ki yedek tek
    klasör olsun.
    """
    ozel = os.environ.get(BELGE_ARSIVI_DEGISKENI)
    if ozel:
        return Path(ozel).expanduser().resolve()
    return (veri_dizini() / BELGE_ARSIVI_DIZIN_ADI).resolve()


def belge_arsivini_hazirla() -> Path:
    """Belge arşivi dizinini oluşturur ve döndürür; ilk belge işlenmeden önce çağrılır."""
    dizin = belge_arsivi_yolu()
    dizin.mkdir(parents=True, exist_ok=True)
    return dizin

"""Veritabanı motorunun ve oturumun tek sahibi.

Bağlantı ayarları (WAL, yabancı anahtar, meşgul bekleme) yalnız burada kurulur; paket
içinde başka bir yerde `create_engine` çağrılmaz. Tek istisna `alembic/env.py`: göç
sırasında yabancı anahtar **kapalı** kalmalıdır (batch modu tabloyu yeniden kurar), bu
yüzden Alembic motorunu pragmasız, kendisi kurar (K-004 ek). Yol `defteriki.ayarlar`dan
gelir (K-004).

SQLite'ta `foreign_keys` **bağlantı başına** açılır ve varsayılanı kapalıdır; buradaki
dinleyici her yeni bağlantıda açar. `busy_timeout` MCP süreci ile masaüstü uygulaması
aynı dosyayı aynı anda kullandığında "database is locked" hatasını önler.
`synchronous=NORMAL` WAL ile birlikte güvenlidir (çökmede son işlemler kaybolabilir,
dosya bozulmaz) ve her commit'te tam disk senkronu beklemez.
"""

from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from defteriki import ayarlar

MESGUL_BEKLEME_MS = 5000

# Sıra önemli: `busy_timeout` ilk gelir. `journal_mode=WAL` dosyaya kilit ister; dosya o an
# başka bir süreçte (MCP + masaüstü) kilitliyse bekleme süresi henüz tanımlı olmadığından
# ilk bağlantı "database is locked" ile düşerdi (B-009). Diğer pragmalar kilit istemez.
PRAGMALAR: tuple[str, ...] = (
    f"PRAGMA busy_timeout={MESGUL_BEKLEME_MS}",
    "PRAGMA journal_mode=WAL",
    "PRAGMA foreign_keys=ON",
    "PRAGMA synchronous=NORMAL",
)


def _pragmalari_uygula(baglanti: Any, _kayit: Any) -> None:
    imlec = baglanti.cursor()
    try:
        for pragma in PRAGMALAR:
            imlec.execute(pragma)
    finally:
        imlec.close()


def motor_kur(url: str | None = None) -> Engine:
    """Canlı veritabanı için motor. `url` verilmezse `ayarlar` yolunu kullanır.

    Dizin yoksa açılır; SQLite eksik dizini kendisi oluşturmaz.
    """
    if url is None:
        ayarlar.veri_dizinini_hazirla()
        url = ayarlar.veritabani_url()
    motor = create_engine(url)
    event.listen(motor, "connect", _pragmalari_uygula)
    return motor


def oturum_ureticisi(motor: Engine) -> sessionmaker[Session]:
    return sessionmaker(motor, expire_on_commit=False)


@contextmanager
def oturum(motor: Engine) -> Generator[Session]:
    """Tek iş birimi: blok sorunsuz biterse commit, hata çıkarsa rollback.

    İç içe kullanılmaz; bir servis çağrısı bir oturumdur.
    """
    with oturum_ureticisi(motor)() as s:
        try:
            yield s
            s.commit()
        except BaseException:
            s.rollback()
            raise

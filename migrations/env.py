"""DEFTERIKI Alembic ortamı.

İki kullanım:

* **Uygulama içi** (``defteriki.sema.semayi_yukselt``): açık bir SQLAlchemy
  bağlantısı ``config.attributes["connection"]`` ile verilir; migration o
  bağlantının işlemi içinde çalışır (``BEGIN IMMEDIATE``), COMMIT/ROLLBACK
  çağıranındır.
* **Komut satırı** (``uv run alembic ...``): bağlantı verilmemişse yol merkezi
  ayarlardan alınır (``DEFTERIKI_*`` ortam değişkenleri); ``alembic.ini``'de
  URL yoktur, göreli yol çözümlenmez.

Karşılaştırma hedefi ``defteriki.sema.METADATA``; ``alembic revision
--autogenerate`` bu tanıma göre fark üretir.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import Connection

from defteriki.sema import METADATA

ayar = context.config


def _uygulama_baglantisiyla(baglanti: Connection) -> None:
    context.configure(
        connection=baglanti,
        target_metadata=METADATA,
        render_as_batch=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def _ayarlardan() -> None:
    from defteriki.ayarlar import ayarlari_yukle, dizinleri_hazirla
    from defteriki.veritabani import veritabani_ac

    ayarlar = ayarlari_yukle()
    dizinleri_hazirla(ayarlar)
    veritabani = veritabani_ac(ayarlar)
    try:
        with veritabani.yazma_islemi() as oturum:
            _uygulama_baglantisiyla(oturum.connection())
    finally:
        veritabani.kapat()


if context.is_offline_mode():
    raise SystemExit("DEFTERIKI çevrimdışı (SQL üretme) modunu desteklemez.")

verilen = ayar.attributes.get("connection")
if verilen is not None:
    _uygulama_baglantisiyla(verilen)
else:
    _ayarlardan()

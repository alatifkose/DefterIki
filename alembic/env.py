from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from defteriki import ayarlar
from defteriki.cekirdek.temel.model import Temel

# Alembic Config nesnesi: alembic.ini icindeki degerlere erisim saglar.
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Tek metadata: tum modeller Temel'den turer (model.py). Autogenerate bunu hedef alir.
target_metadata = Temel.metadata

# Baglanti adresi alembic.ini'den DEGIL ayarlar modulunden gelir (K-004): veritabani
# yolunun tek sahibi odur. ini'deki sqlalchemy.url bilerek bostur; buradan okunsaydi
# yol iki yerde yazili olur ve gocler ile uygulama farkli dosyalara yazabilirdi.


def run_migrations_offline() -> None:
    """Migration'lari 'offline' modda, yalnizca URL ile calistir."""
    context.configure(
        url=ayarlar.veritabani_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Migration'lari 'online' modda, canli baglanti uzerinden calistir."""
    ayarlar.veri_dizinini_hazirla()
    connectable = create_engine(ayarlar.veritabani_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        # render_as_batch: SQLite sutun/kisit degistiremez; batch modu tabloyu kopyalayarak
        # yapar. compare_type: sutun tipi degisiklikleri de autogenerate'e dussun.
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

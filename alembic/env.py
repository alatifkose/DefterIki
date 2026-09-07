from logging.config import fileConfig

from alembic import context
from sqlalchemy import MetaData, engine_from_config, pool

# Alembic Config nesnesi: alembic.ini içindeki degerlere erisim saglar.
config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Henuz model yok; autogenerate icin metadata ilerideki adimda baglanacak.
target_metadata: MetaData | None = None


def run_migrations_offline() -> None:
    """Migration'lari 'offline' modda, yalnizca URL ile calistir."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Migration'lari 'online' modda, canli baglanti uzerinden calistir."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

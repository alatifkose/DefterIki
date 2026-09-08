"""Tüm tabloların ortak tabanı ve kısıt adlandırma kuralı.

SQLite adsız kısıtları sonradan düşüremez; Alembic'in batch modu (`alembic/env.py`)
bir kısıdı kaldırmak için adını bilmek zorundadır. Adlandırma kuralı burada, tek
`MetaData` üzerinde tanımlanır; her model bu tabandan türer ve Alembic bu metadata'yı
hedef alır. İkinci bir `MetaData` açılırsa `tests/test_gocler.py` ayrışmayı yakalar.
"""

from __future__ import annotations

from sqlalchemy import MetaData
from sqlalchemy.orm import DeclarativeBase

# `column_0_N_name`: kısıttaki TÜM sütunlar alt çizgiyle art arda (`a_b_c`). Yalnız ilk
# sütun (`column_0_name`) kullanılsaydı aynı tabloda ilk sütunu ortak iki kısıt aynı adı
# alır, SQLite "index already exists" ile dururdu. Kural ilk göçten sonra değişirse her
# kısıt için yeniden adlandırma göçü gerekir; bu yüzden ilk göçten önce böyle sabitlendi.
ADLANDIRMA_KURALI: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Temel(DeclarativeBase):
    """Tüm ORM modellerinin tabanı. Tek metadata, adlandırılmış kısıtlar."""

    metadata = MetaData(naming_convention=ADLANDIRMA_KURALI)

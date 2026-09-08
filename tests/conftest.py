"""Ortak fikstürler: geçici veritabanı, gerçek göçlerle açılmış motor ve oturum.

Testler şemayı `Temel.metadata.create_all` ile DEĞİL, Alembic göçleriyle kurar. Aksi
hâlde göçler ile modeller sessizce ayrışır ve bunu üretimde fark ederiz.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from defteriki import ayarlar
from defteriki.cekirdek.temel import veritabani

DEPO_KOKU = Path(__file__).resolve().parent.parent


def alembic_ayari() -> Config:
    return Config(str(DEPO_KOKU / "alembic.ini"))


@pytest.fixture
def veritabani_yolu(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Ortam değişkenini geçici bir dosyaya çevirir ve göçleri `head`e kadar uygular."""
    hedef = tmp_path / "test.sqlite3"
    monkeypatch.setenv(ayarlar.VERITABANI_DEGISKENI, str(hedef))
    command.upgrade(alembic_ayari(), "head")
    return hedef


@pytest.fixture
def motor(veritabani_yolu: Path) -> Iterator[Engine]:
    m = veritabani.motor_kur()
    try:
        yield m
    finally:
        m.dispose()


@pytest.fixture
def oturum(motor: Engine) -> Iterator[Session]:
    with veritabani.oturum(motor) as s:
        yield s

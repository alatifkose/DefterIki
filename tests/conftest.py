"""Ortak fikstürler: geçici veri dizini, gerçek göçlerle açılmış motor ve oturum.

Her test kendi geçici veri dizininde koşar (`veri_dizini`, autouse): veritabanı **ve**
belge arşivi (K-011) oraya yönlendirilir. Hiçbir test gerçek `%LOCALAPPDATA%\\DefterIki`
klasörüne yazamaz; bkz. `BULGULAR.md` B-008 ve `tests/test_fiksturler.py`.

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


@pytest.fixture(autouse=True)
def veri_dizini(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Veritabanı ve belge arşivi yollarını testin geçici dizinine çevirir.

    Autouse: fikstür istemeyen bir test bile `ayarlar` üzerinden gerçek kullanıcı
    klasörüne ulaşamaz. Ortamı bilerek temizleyen testler (`test_ayarlar`) değişkenleri
    kendileri siler; monkeypatch test bitince hepsini geri alır.
    """
    dizin = tmp_path / "veri"
    monkeypatch.setenv(ayarlar.VERITABANI_DEGISKENI, str(dizin / ayarlar.VERITABANI_DOSYA_ADI))
    monkeypatch.setenv(ayarlar.BELGE_ARSIVI_DEGISKENI, str(dizin / ayarlar.BELGE_ARSIVI_DIZIN_ADI))
    return dizin


@pytest.fixture
def veritabani_yolu(veri_dizini: Path) -> Path:
    """Göçleri `head`e kadar uygular; dosya geçici veri dizinindedir."""
    command.upgrade(alembic_ayari(), "head")
    return ayarlar.veritabani_yolu()


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

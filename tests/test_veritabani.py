"""Motorun her bağlantıda doğru SQLite ayarlarını açtığını sınar."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError

from defteriki.cekirdek.temel import veritabani

KAYNAK = Path(__file__).resolve().parent.parent / "src" / "defteriki"


def _pragma(motor: Engine, ad: str) -> object:
    with motor.connect() as b:
        return b.execute(text(f"PRAGMA {ad}")).scalar()


def test_yabanci_anahtar_acik(motor: Engine) -> None:
    assert _pragma(motor, "foreign_keys") == 1


def test_wal_modu(motor: Engine) -> None:
    assert str(_pragma(motor, "journal_mode")).lower() == "wal"


def test_mesgul_bekleme(motor: Engine) -> None:
    assert _pragma(motor, "busy_timeout") == veritabani.MESGUL_BEKLEME_MS


def test_yabanci_anahtar_gercekten_uygulanir(motor: Engine) -> None:
    """Pragma degeri 1 gorunse de uygulanmiyor olabilir; ihlali dene."""
    with motor.begin() as b:
        b.execute(text("CREATE TABLE ana (id INTEGER PRIMARY KEY)"))
        b.execute(
            text("CREATE TABLE bagli (id INTEGER PRIMARY KEY, ana_id INTEGER REFERENCES ana(id))")
        )
    with pytest.raises(IntegrityError), motor.begin() as b:
        b.execute(text("INSERT INTO bagli (ana_id) VALUES (999)"))


def test_motor_ayarlardaki_dosyayi_acar(motor: Engine, veritabani_yolu: Path) -> None:
    with motor.begin() as b:
        b.execute(text("CREATE TABLE iz (id INTEGER PRIMARY KEY)"))
    assert veritabani_yolu.is_file()
    assert veritabani_yolu.stat().st_size > 0


def test_oturum_hata_cikinca_geri_alir(motor: Engine) -> None:
    with motor.begin() as b:
        b.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY)"))
    with pytest.raises(RuntimeError), veritabani.oturum(motor) as s:
        s.execute(text("INSERT INTO t (id) VALUES (1)"))
        raise RuntimeError("bilerek")
    with motor.connect() as b:
        assert b.execute(text("SELECT COUNT(*) FROM t")).scalar() == 0


def test_oturum_sorunsuz_bitince_yazar(motor: Engine) -> None:
    with motor.begin() as b:
        b.execute(text("CREATE TABLE t (id INTEGER PRIMARY KEY)"))
    with veritabani.oturum(motor) as s:
        s.execute(text("INSERT INTO t (id) VALUES (1)"))
    with motor.connect() as b:
        assert b.execute(text("SELECT COUNT(*) FROM t")).scalar() == 1


def test_create_engine_paket_icinde_yalniz_veritabani_modulunde() -> None:
    """Pragmalar tek yerden gelsin; ikinci bir motor sessizce yabanci anahtarsiz kalirdi.

    `alembic/env.py` paket disindadir ve bilerek istisnadir (K-004 ek, test_gocler).
    """
    cagiranlar = sorted(
        yol.relative_to(KAYNAK).as_posix()
        for yol in KAYNAK.rglob("*.py")
        if "create_engine" in yol.read_text(encoding="utf-8")
    )
    assert cagiranlar == ["cekirdek/temel/veritabani.py"]

"""Göçler ile modellerin ayrışmadığını ve SQLite için batch modunun açık olduğunu sınar.

`head`e kadar uygulanmış şema ile `Temel.metadata` karşılaştırılır; fark varsa bir model
değişmiş ama göçü yazılmamıştır (ya da tersi). Kural: model değişikliği göçüyle gelir.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import CheckConstraint, Column, Engine, Integer, MetaData, Table
from sqlalchemy.exc import InvalidRequestError

from defteriki.cekirdek.temel.model import ADLANDIRMA_KURALI, Temel

DEPO_KOKU = Path(__file__).resolve().parent.parent


def test_head_semasi_modellerle_ayni(motor: Engine) -> None:
    with motor.connect() as b:
        baglam = MigrationContext.configure(b, opts={"compare_type": True, "render_as_batch": True})
        fark = compare_metadata(baglam, Temel.metadata)
    assert fark == [], f"Goc ile model ayristi: {fark}"


def test_env_batch_modunda() -> None:
    """SQLite sutun/kisit degistiremez; batch modu kapaliysa ikinci goc elle yazilir."""
    metin = (DEPO_KOKU / "alembic" / "env.py").read_text(encoding="utf-8")
    assert metin.count("render_as_batch=True") == 2, "hem offline hem online modda acik olmali"
    assert "target_metadata = Temel.metadata" in metin


def test_env_motoru_pragmasiz_kendisi_kurar() -> None:
    """K-004 ek: goc sirasinda yabanci anahtar kapali kalmali.

    env.py `motor_kur` kullanmaya "duzeltilirse" her baglantida foreign_keys acilir ve batch
    modu tabloyu yeniden kurarken bagli satirlar silinebilir. Istisna bilerek korunur.
    """
    metin = (DEPO_KOKU / "alembic" / "env.py").read_text(encoding="utf-8")
    agac = ast.parse(metin)
    ice_alinanlar = {
        f"{d.module}.{ad.name}" if isinstance(d, ast.ImportFrom) else ad.name
        for d in ast.walk(agac)
        if isinstance(d, ast.Import | ast.ImportFrom)
        for ad in d.names
    }
    assert "sqlalchemy.create_engine" in ice_alinanlar
    assert not any("veritabani" in ad for ad in ice_alinanlar), ice_alinanlar
    dizgeler = [
        d.value for d in ast.walk(agac) if isinstance(d, ast.Constant) and isinstance(d.value, str)
    ]
    assert not any("PRAGMA" in s for s in dizgeler), dizgeler


def test_kisitlar_adlandirilmis() -> None:
    """Adsiz kisit batch modunda dusurulemez; kural tek metadata uzerinde tanimli olmali."""
    assert Temel.metadata.naming_convention == ADLANDIRMA_KURALI
    assert set(ADLANDIRMA_KURALI) == {"ix", "uq", "ck", "fk", "pk"}


def test_adsiz_check_kisiti_tanim_aninda_reddedilir() -> None:
    """K-012: CheckConstraint her zaman name= ile yazilir.

    Kural SQLAlchemy tarafindan zorlanir: `%(constraint_name)s` iceren adlandirma kurali,
    adsiz kisit tabloya baglanirken InvalidRequestError verir; model modulu import bile
    edilemez. Bu test kuralin zayiflatilmadigini (token'in kaldirilmadigini) korur.
    """
    meta = MetaData(naming_convention=ADLANDIRMA_KURALI)
    with pytest.raises(InvalidRequestError, match="explicitly named"):
        Table("deneme", meta, Column("id", Integer, primary_key=True), CheckConstraint("id > 0"))

    adli = MetaData(naming_convention=ADLANDIRMA_KURALI)
    tablo = Table(
        "deneme",
        adli,
        Column("id", Integer, primary_key=True),
        CheckConstraint("id > 0", name="pozitif"),
    )
    (kisit,) = (k for k in tablo.constraints if isinstance(k, CheckConstraint))
    assert str(kisit.name) == "ck_deneme_pozitif"

"""Şema ve migration testleri (Teslim 4.2; tek defter).

Boş bir SQLite dosyasına Alembic ile kurulum; bütünlük denetimleri; metadata
ile migration'ın ürettiği şema arasında fark olmaması; sürüm denetimi; şema
kısıtlarının veritabanı düzeyinde çalışması; komut satırından yükseltme.
"""

import os
import subprocess
import sys
from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from defteriki import ayarlar as ay
from defteriki import sema
from defteriki import veritabani as vt

DEFTERIKI_DEGISKENLERI = (
    ay.ORTAM_DEGISKENI,
    ay.VERI_KOKU_DEGISKENI,
    ay.VERITABANI_YOLU_DEGISKENI,
    ay.BELGE_DIZINI_DEGISKENI,
    ay.LOG_DIZINI_DEGISKENI,
    ay.GELEN_DIZINI_DEGISKENI,
)

BEKLENEN_TABLOLAR = {
    "nesne",
    "nesne_ozellik",
    "nesne_baglanti",
    "nesne_sart",
    "nesne_kaynak",
    "arsiv_dosya",
    "belge",
    "okuma",
    "okuma_satir",
    "kayit",
    "kayit_kaynak",
    "etki",
    "onay_talep",
    "islem_anahtari",
    "denetim_olay",
}

SIMDI = datetime(2026, 9, 16, 12, 0)


@pytest.fixture(autouse=True)
def temiz_cevre(monkeypatch: pytest.MonkeyPatch) -> None:
    for degisken in DEFTERIKI_DEGISKENLERI:
        monkeypatch.delenv(degisken, raising=False)


@pytest.fixture
def veritabani(tmp_path: Path) -> Iterator[vt.Veritabani]:
    yol = tmp_path / "vt" / "sema.sqlite3"
    yol.parent.mkdir()
    db = vt.Veritabani(yol, mesgul_bekleme_ms=200)
    yield db
    db.kapat()


@pytest.fixture
def kurulu(veritabani: vt.Veritabani) -> vt.Veritabani:
    sema.semayi_yukselt(veritabani)
    return veritabani


def _tablolar(db: vt.Veritabani) -> set[str]:
    with db.okuma_islemi() as oturum:
        return set(inspect(oturum.connection()).get_table_names())


# --- kurulum ve sürüm ----------------------------------------------------------------


def test_bos_veritabanina_kurulum_on_bes_tablo(kurulu: vt.Veritabani) -> None:
    tablolar = _tablolar(kurulu)

    assert tablolar == BEKLENEN_TABLOLAR | {"alembic_version"}
    assert set(sema.TABLOLAR) == BEKLENEN_TABLOLAR
    assert len(sema.TABLOLAR) == 15
    assert "defter" not in tablolar


def test_hic_bir_tabloda_defter_kimligi_yok(kurulu: vt.Veritabani) -> None:
    """Sözlük "Defter": DEFTERIKI tek bütünleşik defterdir."""
    with kurulu.okuma_islemi() as oturum:
        denetci = inspect(oturum.connection())
        sutunlar = {
            tablo: [s["name"] for s in denetci.get_columns(tablo)]
            for tablo in BEKLENEN_TABLOLAR
        }

    assert all("defter_id" not in adlar for adlar in sutunlar.values())


def test_yukseltme_surumu_dondurur_ve_denetim_gecer(veritabani: vt.Veritabani) -> None:
    assert sema.sema_surumu(veritabani) is None
    with pytest.raises(sema.SemaSurumuUyumsuz, match="kurulmamış"):
        sema.semayi_denetle(veritabani)

    surum = sema.semayi_yukselt(veritabani)

    assert surum == sema.BEKLENEN_SEMA_SURUMU == "0001"
    assert sema.sema_surumu(veritabani) == "0001"
    assert sema.semayi_denetle(veritabani) == "0001"


def test_yukseltme_tekrar_calistirilabilir(kurulu: vt.Veritabani) -> None:
    assert sema.semayi_yukselt(kurulu) == "0001"
    assert _tablolar(kurulu) == BEKLENEN_TABLOLAR | {"alembic_version"}


def test_farkli_surume_yazilmaz(kurulu: vt.Veritabani) -> None:
    with kurulu.yazma_islemi() as oturum:
        oturum.execute(text("UPDATE alembic_version SET version_num = '0999'"))

    with pytest.raises(sema.SemaSurumuUyumsuz, match="0999") as bilgi:
        sema.semayi_denetle(kurulu)

    assert "yedek" in str(bilgi.value)


def test_butunluk_ve_dis_anahtar_denetimi_temiz(kurulu: vt.Veritabani) -> None:
    sema.butunlugu_denetle(kurulu)

    with kurulu.okuma_islemi() as oturum:
        assert oturum.execute(text("PRAGMA foreign_key_check")).all() == []
        assert oturum.execute(text("PRAGMA integrity_check")).scalar() == "ok"


def test_metadata_ile_migration_arasinda_fark_yok(kurulu: vt.Veritabani) -> None:
    with kurulu.okuma_islemi() as oturum:
        baglam = MigrationContext.configure(
            oturum.connection(),
            opts={"compare_type": True, "render_as_batch": True},
        )
        fark = compare_metadata(baglam, sema.METADATA)

    assert fark == []


def test_geri_alma_butun_tablolari_kaldirir(kurulu: vt.Veritabani) -> None:
    ayar = Config(str(sema.ALEMBIC_INI))
    ayar.set_main_option("script_location", str(sema.MIGRATIONS_DIZINI))
    with kurulu.yazma_islemi() as oturum:
        ayar.attributes["connection"] = oturum.connection()
        command.downgrade(ayar, "base")

    assert _tablolar(kurulu) == {"alembic_version"}
    assert sema.sema_surumu(kurulu) is None


# --- kısıtlar veritabanı düzeyinde ------------------------------------------------


def _nesne_ac(db: vt.Veritabani, seviye: int = 0) -> int:
    with db.yazma_islemi() as oturum:
        return int(
            oturum.execute(
                sema.nesne.insert()
                .values(seviye=seviye, durum="AKTIF", olusturma_zamani=SIMDI)
                .returning(sema.nesne.c.id)
            ).scalar_one()
        )


def _kayit_ekle(db: vt.Veritabani, nesne_id: int) -> int:
    with db.yazma_islemi() as oturum:
        return int(
            oturum.execute(
                sema.kayit.insert()
                .values(
                    asil_nesne_id=nesne_id,
                    islem_tarihi=date(2026, 9, 1),
                    durum="AKTIF",
                    olusturma_zamani=SIMDI,
                )
                .returning(sema.kayit.c.id)
            ).scalar_one()
        )


def test_izinli_olmayan_durum_reddedilir(kurulu: vt.Veritabani) -> None:
    with pytest.raises(IntegrityError, match="ck_nesne_durum_izinli"):
        with kurulu.yazma_islemi() as oturum:
            oturum.execute(
                sema.nesne.insert().values(
                    seviye=0, durum="HAYALET", olusturma_zamani=SIMDI
                )
            )


def test_olmayan_nesneye_kayit_baglanamaz(kurulu: vt.Veritabani) -> None:
    with pytest.raises(IntegrityError, match="FOREIGN KEY"):
        _kayit_ekle(kurulu, 999)

    nesne_id = _nesne_ac(kurulu)
    assert _kayit_ekle(kurulu, nesne_id) >= 1


def test_negatif_tutar_ve_try_disi_para_birimi_reddedilir(
    kurulu: vt.Veritabani,
) -> None:
    nesne_id = _nesne_ac(kurulu)
    kayit_id = _kayit_ekle(kurulu, nesne_id)

    def etki_ekle(tutar: int, para_birimi: str) -> None:
        with kurulu.yazma_islemi() as oturum:
            oturum.execute(
                sema.etki.insert().values(
                    kayit_id=kayit_id,
                    nesne_id=nesne_id,
                    eksen="VARLIK",
                    yon="ARTTIR",
                    tutar_kurus=tutar,
                    para_birimi=para_birimi,
                )
            )

    with pytest.raises(IntegrityError, match="ck_etki_tutar_negatif_degil"):
        etki_ekle(-1, "TRY")
    with pytest.raises(IntegrityError, match="ck_etki_para_birimi_izinli"):
        etki_ekle(100, "USD")
    etki_ekle(0, "TRY")


def test_nesne_kendine_baglanamaz_ve_bos_alan_adi_reddedilir(
    kurulu: vt.Veritabani,
) -> None:
    nesne_id = _nesne_ac(kurulu)

    with pytest.raises(IntegrityError, match="ck_nesne_baglanti_kendine_bagli_degil"):
        with kurulu.yazma_islemi() as oturum:
            oturum.execute(
                sema.nesne_baglanti.insert().values(alt_id=nesne_id, ust_id=nesne_id)
            )
    with pytest.raises(IntegrityError, match="ck_nesne_ozellik_alan_adi_bos_degil"):
        with kurulu.yazma_islemi() as oturum:
            oturum.execute(
                sema.nesne_ozellik.insert().values(
                    nesne_id=nesne_id, alan_adi="", deger_turu="METIN", deger="x"
                )
            )


def test_ayni_nesnede_ayni_alan_adi_iki_kez_reddedilir(kurulu: vt.Veritabani) -> None:
    nesne_id = _nesne_ac(kurulu)
    ekle = sema.nesne_ozellik.insert().values(
        nesne_id=nesne_id, alan_adi="iban", deger_turu="METIN", deger="TR00"
    )

    with kurulu.yazma_islemi() as oturum:
        oturum.execute(ekle)
    # SQLite UNIQUE hatası kısıt adını değil sütunları söyler.
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed: nesne_ozellik"):
        with kurulu.yazma_islemi() as oturum:
            oturum.execute(ekle)


def test_ayni_dosya_ikinci_belge_olamaz(kurulu: vt.Veritabani) -> None:
    """Tek defter: aynı arşiv dosyası yalnız bir belgeye bağlanır."""
    with kurulu.yazma_islemi() as oturum:
        dosya_id = int(
            oturum.execute(
                sema.arsiv_dosya.insert()
                .values(
                    sha256="a" * 64,
                    boyut=1,
                    mime="application/pdf",
                    goreli_yol="2026/a.pdf",
                    olusturma_zamani=SIMDI,
                )
                .returning(sema.arsiv_dosya.c.id)
            ).scalar_one()
        )
    belge_ekle = sema.belge.insert().values(
        dosya_id=dosya_id, durum="ARSIVLENDI", olusturma_zamani=SIMDI
    )

    with kurulu.yazma_islemi() as oturum:
        oturum.execute(belge_ekle)
    with pytest.raises(
        IntegrityError, match="UNIQUE constraint failed: belge.dosya_id"
    ):
        with kurulu.yazma_islemi() as oturum:
            oturum.execute(belge_ekle)


def test_kimlikler_yeniden_kullanilmaz(kurulu: vt.Veritabani) -> None:
    """AUTOINCREMENT: silinen son kimlik bir sonraki kayda verilmez."""
    ilk = _nesne_ac(kurulu)
    with kurulu.yazma_islemi() as oturum:
        oturum.execute(sema.nesne.delete().where(sema.nesne.c.id == ilk))

    ikinci = _nesne_ac(kurulu)

    assert ikinci == ilk + 1


# --- komut satırı: yol ayarlardan -------------------------------------------------


def test_alembic_komutu_yolu_ayarlardan_alir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(tmp_path / "kok"))
    baska_dizin = tmp_path / "baska"
    baska_dizin.mkdir()

    sonuc = subprocess.run(
        [
            sys.executable,
            "-m",
            "alembic",
            "-c",
            str(sema.ALEMBIC_INI),
            "upgrade",
            "head",
        ],
        cwd=baska_dizin,
        env={**os.environ, "PYTHONUTF8": "1"},
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )

    assert sonuc.returncode == 0, sonuc.stderr
    ayarlar = ay.ayarlari_yukle()
    db = vt.veritabani_ac(ayarlar)
    try:
        assert sema.semayi_denetle(db) == "0001"
    finally:
        db.kapat()
    assert not any(baska_dizin.iterdir())

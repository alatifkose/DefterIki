"""DEFTERIKI veritabanı şeması ve sürüm denetimi.

Aşama 4 dikey diliminin on beş tablosu burada SQLAlchemy Core ``Table``
nesneleriyle tanımlıdır (Tam Plan bölüm 5; Yürütme Planı Teslim 4.2; sözlük
"Defter" kararıyla defter tablosu ve defter kimlikleri yoktur). Tablolar
veritabanında Alembic migration'larıyla kurulur (``migrations/``); bu
modüldeki tanım ile migration'ın ürettiği şema arasında fark olmaması testle
doğrulanır. Şema değişimi yalnız yeni bir migration ile yapılır; bu dosya
doğrudan ``create_all`` ile kullanılmaz.

Kurallar (Tam Plan 5.3):

* Kimlikler tam sayı ve yeniden kullanılmaz: her tabloda
  ``sqlite_autoincrement=True`` (SQLite ``AUTOINCREMENT``; silinen son kimlik
  yeniden verilmez).
* DEFTERIKI tek bütünleşik defterdir: tablolarda defter kimliği yoktur, dış
  anahtarlar doğrudan hedef kimliğe bağlanır.
* Bütün kısıtlar isimlidir (``NAMING`` kalıbı); durum ve yön sütunları izinli
  değerlerle CHECK'lidir; ``tutar_kurus >= 0``, ``seviye >= 0``.
* Zaman damgaları UTC ``DateTime``; kaynak tarihleri (işlem, valör) ayrı
  ``Date`` alanlarıdır.
* Aşama 8'de gelecek alanlar (``kayit.olay_id``, ``islem_turu``,
  ``yerine_gecen_id``, ``etki.borc_id``) bu şemada yoktur; Aşama 7'nin
  mükerrerlik tabloları da yoktur (``okuma_satir.aday_grup_id`` yer tutucu,
  dış anahtarı 7'de bağlanır).

Modül import edildiğinde diske dokunulmaz.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    Table,
    Text,
    UniqueConstraint,
    inspect,
    text,
)

from defteriki import sozlesmeler as sz
from defteriki.veritabani import Veritabani

PROJE_KOKU = Path(__file__).resolve().parent.parent.parent
ALEMBIC_INI = PROJE_KOKU / "alembic.ini"
MIGRATIONS_DIZINI = PROJE_KOKU / "migrations"

BEKLENEN_SEMA_SURUMU = "0001"
"""Uygulamanın yazmayı kabul ettiği tek şema sürümü (``migrations/versions``)."""

NAMING = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_N_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

METADATA = MetaData(naming_convention=NAMING)


class SemaSurumuUyumsuz(RuntimeError):
    """Veritabanının şema sürümü uygulamanın beklediğinden farklı.

    Eski ya da yeni şemaya yazılmaz; yükseltme açık bir adımdır (yedek sonra
    ``semayi_yukselt``). Kullanıcıya gösterilmeye uygun mesaj taşır.
    """


def _kimlik() -> Column[int]:
    return Column("id", Integer, primary_key=True, autoincrement=True)


def _zaman(ad: str = "olusturma_zamani", *, zorunlu: bool = True) -> Column[datetime]:
    return Column(ad, DateTime, nullable=not zorunlu)


def _izinli(sutun: str, degerler: type[sz.StrEnum], ad: str) -> CheckConstraint:
    liste = ", ".join(f"'{d.value}'" for d in degerler)
    return CheckConstraint(f"{sutun} IN ({liste})", name=ad)


def _bag(sutun: str, hedef: str) -> ForeignKeyConstraint:
    """``<sütun>`` → ``<hedef>.id`` dış anahtarı."""
    return ForeignKeyConstraint([sutun], [f"{hedef}.id"])


# --- 5.1 nesne --------------------------------------------------------------------

nesne = Table(
    "nesne",
    METADATA,
    _kimlik(),
    Column("seviye", Integer, nullable=False),
    Column("durum", Text, nullable=False),
    Column("surum", Integer, nullable=False, server_default=text("1")),
    _zaman(),
    CheckConstraint("seviye >= 0", name="seviye_negatif_degil"),
    CheckConstraint("surum >= 1", name="surum_pozitif"),
    _izinli("durum", sz.NesneDurumu, "durum_izinli"),
    Index(None, "seviye", "id"),
    sqlite_autoincrement=True,
)

nesne_ozellik = Table(
    "nesne_ozellik",
    METADATA,
    _kimlik(),
    Column("nesne_id", Integer, nullable=False),
    Column("alan_adi", Text, nullable=False),
    Column("deger_turu", Text, nullable=False),
    Column("deger", JSON, nullable=False),
    Column("eslesme_degeri", Text, nullable=True),
    _bag("nesne_id", "nesne"),
    UniqueConstraint("nesne_id", "alan_adi"),
    CheckConstraint("alan_adi <> ''", name="alan_adi_bos_degil"),
    _izinli("deger_turu", sz.DegerTuru, "deger_turu_izinli"),
    Index(None, "alan_adi", "deger_turu", "eslesme_degeri"),
    sqlite_autoincrement=True,
)

nesne_baglanti = Table(
    "nesne_baglanti",
    METADATA,
    _kimlik(),
    Column("alt_id", Integer, nullable=False),
    Column("ust_id", Integer, nullable=False),
    _bag("alt_id", "nesne"),
    _bag("ust_id", "nesne"),
    UniqueConstraint("alt_id", "ust_id"),
    CheckConstraint("alt_id <> ust_id", name="kendine_bagli_degil"),
    Index(None, "ust_id"),
    sqlite_autoincrement=True,
)

nesne_sart = Table(
    "nesne_sart",
    METADATA,
    _kimlik(),
    Column("nesne_id", Integer, nullable=False),
    Column("ozellik_id", Integer, nullable=False),
    _bag("nesne_id", "nesne"),
    _bag("ozellik_id", "nesne_ozellik"),
    UniqueConstraint("nesne_id", "ozellik_id"),
    sqlite_autoincrement=True,
)

nesne_kaynak = Table(
    "nesne_kaynak",
    METADATA,
    _kimlik(),
    Column("nesne_id", Integer, nullable=False),
    Column("belge_id", Integer, nullable=False),
    Column("okuma_id", Integer, nullable=True),
    Column("konum", JSON, nullable=True),
    _bag("nesne_id", "nesne"),
    _bag("belge_id", "belge"),
    _bag("okuma_id", "okuma"),
    Index(None, "nesne_id"),
    sqlite_autoincrement=True,
)

# --- 5.2 belge ve finans ------------------------------------------------------------

arsiv_dosya = Table(
    "arsiv_dosya",
    METADATA,
    _kimlik(),
    Column("sha256", Text, nullable=False),
    Column("boyut", Integer, nullable=False),
    Column("mime", Text, nullable=False),
    Column("goreli_yol", Text, nullable=False),
    _zaman(),
    UniqueConstraint("sha256"),
    UniqueConstraint("goreli_yol"),
    CheckConstraint("boyut >= 0", name="boyut_negatif_degil"),
    CheckConstraint("length(sha256) = 64", name="sha256_64_hex"),
    sqlite_autoincrement=True,
)

belge = Table(
    "belge",
    METADATA,
    _kimlik(),
    Column("dosya_id", Integer, nullable=False),
    Column("durum", Text, nullable=False),
    Column("etkin_okuma_id", Integer, nullable=True),
    Column("surum", Integer, nullable=False, server_default=text("1")),
    _zaman(),
    _bag("dosya_id", "arsiv_dosya"),
    # belge ↔ okuma döngüsü: sıralama için use_alter; SQLite'ta satır içi yazılır.
    ForeignKeyConstraint(["etkin_okuma_id"], ["okuma.id"], use_alter=True),
    UniqueConstraint("dosya_id"),
    CheckConstraint("surum >= 1", name="surum_pozitif"),
    _izinli("durum", sz.BelgeDurumu, "durum_izinli"),
    sqlite_autoincrement=True,
)

okuma = Table(
    "okuma",
    METADATA,
    _kimlik(),
    Column("belge_id", Integer, nullable=False),
    Column("surum_no", Integer, nullable=False),
    Column("sema_surumu", Text, nullable=False),
    Column("icerik", JSON, nullable=True),
    Column("tamlik", JSON, nullable=True),
    Column("durum", Text, nullable=False),
    _zaman(),
    _bag("belge_id", "belge"),
    UniqueConstraint("belge_id", "surum_no"),
    CheckConstraint("surum_no >= 1", name="surum_no_pozitif"),
    _izinli("durum", sz.OkumaDurumu, "durum_izinli"),
    sqlite_autoincrement=True,
)

okuma_satir = Table(
    "okuma_satir",
    METADATA,
    _kimlik(),
    Column("okuma_id", Integer, nullable=False),
    Column("satir_anahtari", Text, nullable=False),
    Column("konum", Integer, nullable=False),
    Column("ham", JSON, nullable=False),
    Column("durum", Text, nullable=False),
    Column("aday_grup_id", Integer, nullable=True),
    _bag("okuma_id", "okuma"),
    UniqueConstraint("okuma_id", "satir_anahtari"),
    CheckConstraint("satir_anahtari <> ''", name="satir_anahtari_bos_degil"),
    _izinli("durum", sz.SatirDurumu, "durum_izinli"),
    sqlite_autoincrement=True,
)

kayit = Table(
    "kayit",
    METADATA,
    _kimlik(),
    Column("asil_nesne_id", Integer, nullable=False),
    Column("islem_tarihi", Date, nullable=False),
    Column("valor_tarihi", Date, nullable=True),
    Column("aciklama", Text, nullable=True),
    Column("durum", Text, nullable=False),
    _zaman(),
    _bag("asil_nesne_id", "nesne"),
    _izinli("durum", sz.KayitDurumu, "durum_izinli"),
    Index(None, "asil_nesne_id", "islem_tarihi", "id"),
    sqlite_autoincrement=True,
)

kayit_kaynak = Table(
    "kayit_kaynak",
    METADATA,
    _kimlik(),
    Column("kayit_id", Integer, nullable=False),
    Column("okuma_satir_id", Integer, nullable=False),
    Column("rol", Text, nullable=False),
    Column("durum", Text, nullable=False),
    _bag("kayit_id", "kayit"),
    _bag("okuma_satir_id", "okuma_satir"),
    UniqueConstraint("kayit_id", "okuma_satir_id"),
    _izinli("rol", sz.KaynakRolu, "rol_izinli"),
    _izinli("durum", sz.KaynakDurumu, "durum_izinli"),
    Index(None, "okuma_satir_id"),
    sqlite_autoincrement=True,
)

etki = Table(
    "etki",
    METADATA,
    _kimlik(),
    Column("kayit_id", Integer, nullable=False),
    Column("nesne_id", Integer, nullable=False),
    Column("eksen", Text, nullable=False),
    Column("yon", Text, nullable=False),
    Column("tutar_kurus", Integer, nullable=False),
    Column("para_birimi", Text, nullable=False),
    _bag("kayit_id", "kayit"),
    _bag("nesne_id", "nesne"),
    CheckConstraint("tutar_kurus >= 0", name="tutar_negatif_degil"),
    _izinli("eksen", sz.Eksen, "eksen_izinli"),
    _izinli("yon", sz.Yon, "yon_izinli"),
    _izinli("para_birimi", sz.ParaBirimi, "para_birimi_izinli"),
    Index(None, "nesne_id", "eksen", "para_birimi", "kayit_id"),
    sqlite_autoincrement=True,
)

# --- işletim ------------------------------------------------------------------------

onay_talep = Table(
    "onay_talep",
    METADATA,
    _kimlik(),
    Column("tur", Text, nullable=False),
    Column("hedef_id", Integer, nullable=False),
    Column("hedef_surumu", Integer, nullable=False),
    Column("icerik", JSON, nullable=False),
    Column("durum", Text, nullable=False),
    Column("karar", JSON, nullable=True),
    _zaman(),
    _zaman("cozum_zamani", zorunlu=False),
    _izinli("tur", sz.OnayTuru, "tur_izinli"),
    _izinli("durum", sz.OnayDurumu, "durum_izinli"),
    Index(None, "durum", "id"),
    sqlite_autoincrement=True,
)

islem_anahtari = Table(
    "islem_anahtari",
    METADATA,
    _kimlik(),
    Column("arac_adi", Text, nullable=False),
    Column("anahtar", Text, nullable=False),
    Column("istek_ozeti", Text, nullable=False),
    Column("sonuc", JSON, nullable=True),
    _zaman(),
    UniqueConstraint("arac_adi", "anahtar"),
    CheckConstraint("anahtar <> ''", name="anahtar_bos_degil"),
    sqlite_autoincrement=True,
)

denetim_olay = Table(
    "denetim_olay",
    METADATA,
    _kimlik(),
    Column("islem_id", Integer, nullable=True),
    Column("aktor", Text, nullable=False),
    Column("eylem", Text, nullable=False),
    Column("hedef", Text, nullable=False),
    Column("gerekce", Text, nullable=True),
    Column("onceki_durum", Text, nullable=True),
    Column("sonraki_durum", Text, nullable=True),
    _zaman("zaman"),
    _bag("islem_id", "islem_anahtari"),
    sqlite_autoincrement=True,
)

TABLOLAR: tuple[str, ...] = tuple(sorted(METADATA.tables))
"""Şemadaki tablo adları; on beş tane (Teslim 4.2, defter kararı sonrası)."""


# --- sürüm denetimi ve yükseltme --------------------------------------------------


def sema_surumu(veritabani: Veritabani) -> str | None:
    """Veritabanındaki Alembic sürümü; hiç kurulmamışsa ``None``."""
    with veritabani.okuma_islemi() as oturum:
        baglanti = oturum.connection()
        if not inspect(baglanti).has_table("alembic_version"):
            return None
        deger = baglanti.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar()
        return str(deger) if deger is not None else None


def semayi_denetle(veritabani: Veritabani) -> str:
    """Sürüm beklenenle aynıysa sürümü döndürür; değilse ``SemaSurumuUyumsuz``.

    Başlangıçta çağrılır; eski ya da bilinmeyen şemaya yazılmaz.
    """
    surum = sema_surumu(veritabani)
    if surum is None:
        raise SemaSurumuUyumsuz(
            "Veritabanı şeması kurulmamış; önce şema yükseltme çalıştırılmalı."
        )
    if surum != BEKLENEN_SEMA_SURUMU:
        raise SemaSurumuUyumsuz(
            f"Veritabanı şema sürümü {surum}, uygulama {BEKLENEN_SEMA_SURUMU} "
            "bekliyor; yükseltme öncesi yedek alınmalı, eski şemaya yazılmaz."
        )
    return surum


def semayi_yukselt(veritabani: Veritabani) -> str:
    """Alembic migration'larını en son sürüme kadar uygular; sürümü döndürür.

    Tek yazma işlemi içinde çalışır (``BEGIN IMMEDIATE``): bir adım düşerse
    hiçbiri kalmaz. Ardından ``foreign_key_check`` ve ``integrity_check``
    çalıştırılır; temiz değilse ``SemaSurumuUyumsuz``.
    """
    from alembic import command
    from alembic.config import Config

    ayar = Config(str(ALEMBIC_INI))
    ayar.set_main_option("script_location", str(MIGRATIONS_DIZINI))
    with veritabani.yazma_islemi() as oturum:
        ayar.attributes["connection"] = oturum.connection()
        command.upgrade(ayar, "head")
    butunlugu_denetle(veritabani)
    return semayi_denetle(veritabani)


def butunlugu_denetle(veritabani: Veritabani) -> None:
    """SQLite ``foreign_key_check`` ve ``integrity_check``; sorun varsa hata."""
    with veritabani.okuma_islemi() as oturum:
        fk = oturum.execute(text("PRAGMA foreign_key_check")).all()
        butunluk = oturum.execute(text("PRAGMA integrity_check")).scalars().all()
    if fk:
        raise SemaSurumuUyumsuz(f"Dış anahtar ihlali var: {len(fk)} satır.")
    if list(butunluk) != ["ok"]:
        raise SemaSurumuUyumsuz("SQLite bütünlük denetimi temiz değil.")

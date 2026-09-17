"""DEFTERIKI veritabanı bağlantısı ve işlem sınırları.

SQLite dosyasının yolu yalnız merkezi ayarlardan gelir; çalışma dizinine göre
çözümleme yoktur. Modül import edildiğinde ve ``Veritabani`` kurulduğunda
diske dokunulmaz; dosya ilk işlemde oluşur.

İki motor, tek dosya:

* **Yazma motoru**: her bağlantıda ``foreign_keys=ON``, ``journal_mode=WAL``,
  ``busy_timeout`` (varsayılan 5 s), ``synchronous=FULL``. Her işlem
  ``BEGIN IMMEDIATE`` ile açılır: yazma kilidi işlemin başında alınır, iki
  yazar birbirini ortada değil kapıda bekler. Kilit süresi içinde alınamazsa
  ``VeritabaniMesgul`` (tekrar denenebilir) yükseltilir.
* **Okuma motoru**: aynı PRAGMA'lar ve ``query_only=ON``; bu bağlantıdan
  yazma denemesi SQLite tarafından reddedilir.

İşlem sahibi en dıştaki çağrıdır. ``yazma_islemi()`` içinde çağrılan
işlevler oturumu kullanır ama ``commit`` ya da ``rollback`` yapmaz; çıkışta
başarı COMMIT, herhangi bir hata ROLLBACK demektir. Böylece yarım satır
kalmaz. ``okuma_islemi()`` salt okunur oturum verir ve çıkışta hiçbir şey
yazmaz.

Python'un ``sqlite3`` sürücüsü işlemleri kendi başına açar; bu davranış
kapatılır (``isolation_level = None``) ve BEGIN'i SQLAlchemy'nin ``begin``
olayı üzerinden biz veririz. Aksi hâlde ``BEGIN IMMEDIATE`` uygulanamaz.

**Değişiklik sayacı** (``degisiklik_sayaci``): pencere gibi başka bir süreç
tarafından yazılanları görmek isteyen okuyucular için SQLite
``PRAGMA data_version`` değeri. Sayaç bağlantıya özeldir: aynı bağlantıdan
iki okuma arasında *başka bir bağlantı* commit yaptıysa değer değişir. Bu
yüzden okuma motorundan ayrılmış tek bir bağlantı tutulur; her okuma kısa
bir okuma işlemi açıp kapatır, arada kilit tutulmaz. Sayacın mutlak değeri
anlamsızdır; yalnız değişip değişmediği anlamlıdır.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import cast

from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.engine import URL
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

from defteriki.ayarlar import Ayarlar
from defteriki.sozlesmeler import VeritabaniMesgul

MESGUL_BEKLEME_MS = 5000
"""Yazma kilidi için en fazla bekleme; SQLite ``busy_timeout`` değeri (ms)."""

_MESGUL_IPUCLARI = ("database is locked", "database is busy")


class Veritabani:
    """Tek SQLite dosyasına yazma ve okuma motorları.

    ``mesgul_bekleme_ms`` yalnız testlerin kilit davranışını hızlı sınaması
    için dışa açıktır; ürün kodu varsayılanı kullanır.
    """

    def __init__(self, yol: Path, mesgul_bekleme_ms: int = MESGUL_BEKLEME_MS) -> None:
        if not yol.is_absolute():
            raise ValueError(f"veritabanı yolu mutlak olmalı: {yol}")
        self.yol = yol
        self._yazma_motoru = _motor_kur(yol, mesgul_bekleme_ms, salt_okunur=False)
        self._okuma_motoru = _motor_kur(yol, mesgul_bekleme_ms, salt_okunur=True)
        self._yazma_oturumu = sessionmaker(self._yazma_motoru, expire_on_commit=False)
        self._okuma_oturumu = sessionmaker(self._okuma_motoru)
        self._izleme_baglantisi: Connection | None = None

    @contextmanager
    def yazma_islemi(self) -> Generator[Session]:
        """``BEGIN IMMEDIATE`` ile tek yazma işlemi; başarıda COMMIT, hatada ROLLBACK.

        Kilit ``busy_timeout`` içinde alınamazsa ``VeritabaniMesgul``.
        İçerideki işlevler oturumu kullanır, işlemi bitirmez.
        """
        with self._yazma_oturumu() as oturum:
            try:
                with oturum.begin():
                    yield oturum
            except OperationalError as hata:
                if _mesgul_mu(hata):
                    raise VeritabaniMesgul(
                        "yazma kilidi alınamadı; aynı istek tekrar denenebilir"
                    ) from hata
                raise

    @contextmanager
    def okuma_islemi(self) -> Generator[Session]:
        """Salt okunur oturum; çıkışta hiçbir şey yazılmaz."""
        with self._okuma_oturumu() as oturum:
            try:
                yield oturum
            finally:
                oturum.rollback()

    def degisiklik_sayaci(self) -> int:
        """Başka bağlantıların commit'leriyle değişen sayaç (``data_version``).

        Ayrılmış salt okunur bağlantıda kısa bir okuma işlemi açar, değeri
        alır, işlemi kapatır; kilit tutmaz. İlk çağrı bağlantıyı açar.
        """
        if self._izleme_baglantisi is None:
            self._izleme_baglantisi = self._okuma_motoru.connect()
        baglanti = self._izleme_baglantisi
        try:
            return int(baglanti.exec_driver_sql("PRAGMA data_version").scalar_one())
        finally:
            baglanti.rollback()

    def kapat(self) -> None:
        """Bağlantı havuzlarını boşaltır; dosyaya dokunmaz."""
        if self._izleme_baglantisi is not None:
            self._izleme_baglantisi.close()
            self._izleme_baglantisi = None
        self._yazma_motoru.dispose()
        self._okuma_motoru.dispose()


def veritabani_ac(ayarlar: Ayarlar) -> Veritabani:
    """Ayarlardaki veritabanı yolu için motorları kurar; dosya oluşturmaz."""
    return Veritabani(ayarlar.veritabani_yolu)


def _motor_kur(yol: Path, mesgul_bekleme_ms: int, *, salt_okunur: bool) -> Engine:
    motor = create_engine(URL.create("sqlite", database=str(yol)))

    @event.listens_for(motor, "connect")
    def _baglantiyi_ayarla(
        dbapi_baglantisi: DBAPIConnection, _kayit: ConnectionPoolEntry
    ) -> None:
        baglanti = cast(sqlite3.Connection, dbapi_baglantisi)
        baglanti.isolation_level = None  # BEGIN'i sürücü değil biz veririz
        imlec = baglanti.cursor()
        imlec.execute("PRAGMA foreign_keys=ON")
        imlec.execute("PRAGMA journal_mode=WAL")
        imlec.execute(f"PRAGMA busy_timeout={int(mesgul_bekleme_ms)}")
        imlec.execute("PRAGMA synchronous=FULL")
        if salt_okunur:
            imlec.execute("PRAGMA query_only=ON")
        imlec.close()

    @event.listens_for(motor, "begin")
    def _islemi_basla(baglanti: Connection) -> None:
        baglanti.exec_driver_sql("BEGIN" if salt_okunur else "BEGIN IMMEDIATE")

    return motor


def _mesgul_mu(hata: OperationalError) -> bool:
    mesaj = str(hata.orig or hata).lower()
    return any(ipucu in mesaj for ipucu in _MESGUL_IPUCLARI)

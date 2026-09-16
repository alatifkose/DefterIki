"""DEFTERIKI uygulama başlangıcı.

``uv run defteriki`` bu modülün ``main`` fonksiyonunu çalıştırır. Sıra:

1. ``ayarlari_yukle()`` ile ayarlar ortam değişkenlerinden okunur.
2. ``dizinleri_hazirla()`` ile seçilen ortamın dizinleri açılır.
3. ``gunlugu_kur()`` ile teknik günlük log dizininde kurulur.
4. ``semayi_hazirla()`` ile veritabanı şeması denetlenir: hiç kurulmamışsa
   (yeni kurulum) migration'larla kurulur ve ``sema_kuruldu`` olayı yazılır;
   kuruluysa sürümü uygulamanın beklediğiyle aynı olmalıdır. Eski ya da
   yabancı sürüme yazılmaz: yükseltme açık bir adımdır (önce yedek, sonra
   ``uv run alembic upgrade head``), başlangıç anlaşılır hatayla durur.
5. Başlangıç olayı günlüğe yazılır, kısa bir mesajla sıfır çıkış kodu döner.

Herhangi bir adım başarısızsa anlaşılır bir hata stderr'e yazılır ve çıkış
kodu 1 olur. Ayarlar ya da günlük kurulmadan oluşan hatalar da stderr'e
gider; günlük kurulamadıysa başarılı başlangıç mesajı verilmez.

İlk dört adım ``ortami_hazirla()`` içindedir; MCP kapısı da aynı işlevle
başlar, böylece iki giriş noktası aynı ayarları, aynı günlüğü ve aynı şema
denetimini kullanır.

Modül import edildiğinde dizin ya da dosya oluşturulmaz.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

from defteriki import gunluk, sema
from defteriki.ayarlar import (
    AyarHatasi,
    Ayarlar,
    DizinHazirlamaHatasi,
    ayarlari_yukle,
    dizinleri_hazirla,
)
from defteriki.sozlesmeler import VeritabaniMesgul
from defteriki.veritabani import veritabani_ac

OLAY_BASLANGIC = "baslangic"
OLAY_BASLANGIC_HATASI = "baslangic_hatasi"
OLAY_SEMA_KURULDU = "sema_kuruldu"

CIKIS_BASARILI = 0
CIKIS_HATALI = 1


class BaslangicHatasi(Exception):
    """Ayarlar, dizinler, günlük ya da şema hazırlanamadı.

    Mesajı kullanıcıya gösterilmeye uygundur; hangi adımın düştüğünü söyler.
    """


@dataclass(frozen=True, slots=True)
class Hazirlik:
    """``ortami_hazirla`` sonucu: ayarlar, günlük dosyası, şema sürümü."""

    ayarlar: Ayarlar
    log_dosyasi: Path
    sema_surumu: str


def main() -> int:
    """Uygulamayı başlatır; çıkış kodunu döndürür."""
    try:
        return _baslat()
    except Exception as hata:
        _hata_yaz(f"Beklenmeyen hata ({type(hata).__name__}): {hata}")
        if gunluk.kurulu():
            gunluk.hata_kaydet(OLAY_BASLANGIC_HATASI, hata)
        return CIKIS_HATALI


def ortami_hazirla() -> Hazirlik:
    """Ayarları yükler, dizinleri açar, günlüğü kurar, şemayı hazırlar.

    Bir adım düşerse ``BaslangicHatasi`` yükseltir; günlük kurulmadan düşen
    adımlarda günlük kurulmamış kalır.
    """
    try:
        ayarlar = ayarlari_yukle()
    except AyarHatasi as hata:
        raise BaslangicHatasi(f"Ayar hatası: {hata}") from hata

    try:
        dizinleri_hazirla(ayarlar)
    except DizinHazirlamaHatasi as hata:
        raise BaslangicHatasi(f"Dizin hazırlama hatası: {hata}") from hata

    try:
        log_dosyasi = gunluk.gunlugu_kur(ayarlar.log_dizini)
    except gunluk.GunlukKurulumHatasi as hata:
        raise BaslangicHatasi(f"Günlük kurulum hatası: {hata}") from hata

    sema_surumu = semayi_hazirla(ayarlar)
    return Hazirlik(ayarlar, log_dosyasi, sema_surumu)


def semayi_hazirla(ayarlar: Ayarlar) -> str:
    """Şema yoksa kurar, varsa sürümünü denetler; sürümü döndürür.

    Yeni kurulumda (veritabanı dosyası ya da ``alembic_version`` yok)
    migration'lar uygulanır ve ``sema_kuruldu`` olayı yazılır: yedeklenecek
    bir şey yoktur, kurulum otomatiktir. Kurulu şema beklenenden farklıysa
    ``BaslangicHatasi``; yükseltme açık bir adımdır, burada yapılmaz.
    """
    veritabani = veritabani_ac(ayarlar)
    try:
        if sema.sema_surumu(veritabani) is None:
            surum = sema.semayi_yukselt(veritabani)
            gunluk.olay_kaydet(OLAY_SEMA_KURULDU, f"surum={surum}")
            return surum
        return sema.semayi_denetle(veritabani)
    except sema.SemaSurumuUyumsuz as hata:
        raise BaslangicHatasi(f"Şema hatası: {hata}") from hata
    except VeritabaniMesgul as hata:
        raise BaslangicHatasi(
            f"Veritabanı hatası: {hata.mesaj}; başka bir DEFTERIKI süreci yazıyor "
            "olabilir."
        ) from hata
    finally:
        veritabani.kapat()


def _baslat() -> int:
    try:
        hazirlik = ortami_hazirla()
    except BaslangicHatasi as hata:
        _hata_yaz(str(hata))
        return CIKIS_HATALI

    ayarlar = hazirlik.ayarlar
    gunluk.olay_kaydet(
        OLAY_BASLANGIC,
        f"ortam={ayarlar.ortam.value} veri_koku={ayarlar.veri_koku} "
        f"sema={hazirlik.sema_surumu}",
    )
    _basariyi_bildir(hazirlik)
    return CIKIS_BASARILI


def _basariyi_bildir(hazirlik: Hazirlik) -> None:
    ayarlar = hazirlik.ayarlar
    print(
        f"DEFTERIKI başlatıldı. Ortam: {ayarlar.ortam.value}. "
        f"Veri kökü: {ayarlar.veri_koku}. Şema: {hazirlik.sema_surumu}. "
        f"Günlük: {hazirlik.log_dosyasi}",
        flush=True,
    )


def _hata_yaz(mesaj: str) -> None:
    print(f"DEFTERIKI başlatılamadı. {mesaj}", file=sys.stderr, flush=True)

"""DEFTERIKI teknik hata günlüğü.

Yalnızca standart kütüphanenin ``logging`` modülü kullanılır. Log dosyası
merkezi ayarlardan gelen log dizininde açılır; başka bir yere yazılmaz.
Modül import edildiğinde hiçbir dosya ya da handler oluşturulmaz; kurulum
``gunlugu_kur()`` ile açıkça yapılır.

Her satırda zaman, seviye, olay türü ve kısa bir teknik mesaj bulunur.
Dosya belirli bir boyutu aşınca döndürülür ve sınırlı sayıda yedek tutulur;
günlük sınırsız büyümez.

Gizlilik: belge içeriği, finansal kayıt içeriği, IBAN, kimlik bilgileri,
sırlar ve ortam değişkenleri günlüğe yazılmaz. Ham hata mesajları ve
traceback bu bilgileri taşıyabileceğinden ``hata_kaydet()`` yalnızca hatanın
türünü kaydeder; mesaj ve yığın izi dosyaya dökülmez.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

GUNLUK_ADI = "defteriki"
GUNLUK_DOSYA_ADI = "defteriki.log"
DOSYA_ISLEYICI_ADI = "defteriki.dosya"
AZAMI_DOSYA_BOYUTU = 1_000_000
"""Bayt; aşılınca dosya döndürülür."""
YEDEK_SAYISI = 5
"""Döndürülmüş eski dosyalardan en fazla kaç tanesinin tutulacağı."""
SATIR_BICIMI = "%(asctime)s | %(levelname)s | %(olay)s | %(message)s"
OLAY_YOKSA = "-"


class GunlukKurulumHatasi(OSError):
    """Log dosyası açılamadı ya da log dizini kullanılamaz durumda."""


class _OlayAlaniniTamamla(logging.Filter):
    """Olay türü verilmeden yazılan kayıtlara varsayılan olay değeri koyar."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.__dict__.setdefault("olay", OLAY_YOKSA)
        return True


def gunlugu_kur(log_dizini: Path) -> Path:
    """Dosya günlüğünü kurar; log dosyasının yolunu döndürür.

    Tekrar çağrılabilir: önceki kurulumun handler'ı kapatılıp kaldırılır,
    böylece aynı olay birden fazla kez yazılmaz. Log dizini yoksa ya da
    dosya açılamazsa ``GunlukKurulumHatasi`` yükseltir.
    """
    if not log_dizini.is_dir():
        raise GunlukKurulumHatasi(f"Log dizini yok ya da dizin değil: {log_dizini}")
    dosya = log_dizini / GUNLUK_DOSYA_ADI

    gunluk = logging.getLogger(GUNLUK_ADI)
    gunlugu_kapat()
    try:
        isleyici = RotatingFileHandler(
            dosya,
            maxBytes=AZAMI_DOSYA_BOYUTU,
            backupCount=YEDEK_SAYISI,
            encoding="utf-8",
        )
    except OSError as hata:
        raise GunlukKurulumHatasi(
            f"Log dosyası açılamadı: {dosya} ({hata.strerror or type(hata).__name__})"
        ) from hata
    isleyici.set_name(DOSYA_ISLEYICI_ADI)
    isleyici.setFormatter(logging.Formatter(SATIR_BICIMI))
    isleyici.addFilter(_OlayAlaniniTamamla())
    gunluk.addHandler(isleyici)
    gunluk.setLevel(logging.INFO)
    gunluk.propagate = False
    return dosya


def gunlugu_kapat() -> None:
    """Bu modülün kurduğu dosya handler'ını kapatır ve kaldırır."""
    gunluk = logging.getLogger(GUNLUK_ADI)
    for isleyici in list(gunluk.handlers):
        if isleyici.get_name() == DOSYA_ISLEYICI_ADI:
            gunluk.removeHandler(isleyici)
            isleyici.close()


def kurulu() -> bool:
    """Dosya günlüğü şu an kurulu mu?"""
    gunluk = logging.getLogger(GUNLUK_ADI)
    return any(i.get_name() == DOSYA_ISLEYICI_ADI for i in gunluk.handlers)


def olay_kaydet(olay: str, mesaj: str, seviye: int = logging.INFO) -> None:
    """Kontrollü bir teknik olayı yazar.

    ``mesaj`` çağıranın kendi yazdığı kısa teknik bilgidir; belge ya da
    kayıt içeriği, kimlik bilgisi ya da ortam değişkeni geçirilmemelidir.
    """
    logging.getLogger(GUNLUK_ADI).log(seviye, mesaj, extra={"olay": olay})


def hata_kaydet(olay: str, hata: BaseException) -> None:
    """Bir hatayı yalnızca türüyle kaydeder.

    Hata mesajı ve traceback bilerek yazılmaz: bunlar dosya adı, belge
    içeriği ya da kimlik bilgisi taşıyabilir.
    """
    tur = type(hata)
    olay_kaydet(olay, f"hata türü: {tur.__module__}.{tur.__qualname__}", logging.ERROR)

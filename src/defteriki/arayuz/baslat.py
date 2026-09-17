"""Pencere başlangıcı: ``uv run defteriki-arayuz``.

Uygulama ve MCP kapısıyla aynı hazırlık (``baslangic.ortami_hazirla``):
ayarlar, dizinler, günlük, şema denetimi. Hazırlık düşerse hata bir ileti
kutusunda ve stderr'de gösterilir, çıkış kodu 1. Pencere Qt olay döngüsünde
çalışır; kapanınca veritabanı bağlantıları bırakılır.

Test edilebilirlik için hata gösterici ve olay döngüsü enjekte edilebilir;
ürün kullanımı varsayılanlarla çalışır.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Sequence

from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication, QMessageBox

from defteriki import gunluk
from defteriki.arayuz.ana_pencere import PENCERE_BASLIGI, AnaPencere
from defteriki.baslangic import CIKIS_HATALI, BaslangicHatasi, ortami_hazirla
from defteriki.pencere_islevleri import pencere_islevleri_ac

OLAY_ARAYUZ_BASLANGIC = "arayuz_baslangic"
OLAY_ARAYUZ_HATASI = "arayuz_hatasi"

type HataGosterici = Callable[[str], None]
type OlayDongusu = Callable[[QCoreApplication], int]


def main(
    argv: Sequence[str] | None = None,
    hata_goster: HataGosterici | None = None,
    dongu: OlayDongusu | None = None,
) -> int:
    """Pencereyi başlatır; çıkış kodunu döndürür."""
    uygulama = _uygulamayi_al(argv)
    goster = hata_goster if hata_goster is not None else _ileti_kutusu
    calistir = dongu if dongu is not None else _olay_dongusu

    try:
        hazirlik = ortami_hazirla()
    except BaslangicHatasi as hata:
        _hatayi_bildir(str(hata), goster)
        return CIKIS_HATALI

    ayarlar = hazirlik.ayarlar
    islevler = pencere_islevleri_ac(ayarlar)
    try:
        gunluk.olay_kaydet(
            OLAY_ARAYUZ_BASLANGIC,
            f"ortam={ayarlar.ortam.value} sema={hazirlik.sema_surumu}",
        )
        pencere = AnaPencere(hazirlik, islevler)
        pencere.show()
        kod = calistir(uygulama)
        pencere.close()
        return kod
    except Exception as hata:
        gunluk.hata_kaydet(OLAY_ARAYUZ_HATASI, hata)
        _hatayi_bildir(f"Beklenmeyen hata ({type(hata).__name__}): {hata}", goster)
        return CIKIS_HATALI
    finally:
        islevler.kapat()


def _uygulamayi_al(argv: Sequence[str] | None) -> QCoreApplication:
    mevcut = QCoreApplication.instance()
    if mevcut is not None:
        return mevcut
    return QApplication(list(argv) if argv is not None else sys.argv)


def _olay_dongusu(uygulama: QCoreApplication) -> int:
    return uygulama.exec()


def _ileti_kutusu(mesaj: str) -> None:
    QMessageBox.critical(None, PENCERE_BASLIGI, mesaj)


def _hatayi_bildir(mesaj: str, goster: HataGosterici) -> None:
    print(f"DEFTERIKI penceresi açılamadı. {mesaj}", file=sys.stderr, flush=True)
    goster(mesaj)

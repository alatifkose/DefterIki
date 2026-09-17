"""Veritabanı değişiklik izleme (Teslim 6.1).

Pencere, Cowork'un MCP kapısından ya da onay komutunun yazdıklarını görmek
için veritabanını kısa aralıklarla yoklar: ``Veritabani.degisiklik_sayaci``
salt okunurdur ve kilit tutmaz. Sayaç değişince ``degisti`` sinyali verilir;
görünümler kendi sorgularını o zaman yeniler. Zamanlayıcı Qt olay
döngüsünde çalışır; pencere kapanınca durur.

Yoklama sırasında beklenmeyen bir hata olursa (dosya silinmiş, disk hatası)
izleme durur, hata günlüğe yazılır ve ``durdu`` sinyali verilir; pencere
bunu durum çubuğunda gösterir. Sessizce yeniden deneme yoktur.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from defteriki import gunluk
from defteriki.veritabani import Veritabani

VARSAYILAN_ARALIK_MS = 1000
"""Yoklama aralığı; bir saniye Cowork'un yazdığını görmek için yeterli."""

OLAY_IZLEME_HATASI = "arayuz_izleme_hatasi"


class DegisiklikIzleyici(QObject):
    """Sayaç değişince ``degisti(sayac)``; yoklama düşerse ``durdu(mesaj)``."""

    degisti = Signal(int)
    durdu = Signal(str)

    def __init__(
        self,
        veritabani: Veritabani,
        aralik_ms: int = VARSAYILAN_ARALIK_MS,
        ebeveyn: QObject | None = None,
    ) -> None:
        super().__init__(ebeveyn)
        self._veritabani = veritabani
        self._son: int | None = None
        self._zamanlayici = QTimer(self)
        self._zamanlayici.setInterval(aralik_ms)
        self._zamanlayici.timeout.connect(self.yokla)

    @property
    def calisiyor(self) -> bool:
        return self._zamanlayici.isActive()

    def baslat(self) -> None:
        """Başlangıç değerini alır ve yoklamayı başlatır."""
        self._son = self._veritabani.degisiklik_sayaci()
        self._zamanlayici.start()

    def durdur(self) -> None:
        self._zamanlayici.stop()

    def yokla(self) -> bool:
        """Sayacı okur; değiştiyse sinyal verir ve ``True`` döndürür."""
        try:
            sayac = self._veritabani.degisiklik_sayaci()
        except Exception as hata:
            self.durdur()
            gunluk.hata_kaydet(OLAY_IZLEME_HATASI, hata)
            self.durdu.emit(f"izleme durdu ({type(hata).__name__})")
            return False
        degisti = self._son is not None and sayac != self._son
        self._son = sayac
        if degisti:
            self.degisti.emit(sayac)
        return degisti

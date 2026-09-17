"""Veri değişikliği izleme (Teslim 6.1).

Pencere, Cowork'un MCP kapısından ya da onay komutunun yazdıklarını görmek
için kısa aralıklarla ``PencereIslevleri.degisti_mi()`` sorar; nasıl
anlaşıldığı (SQLite ayrıntısı) pencerenin bilgisi dışındadır. Cevap evetse
``degisti`` sinyali verilir; görünümler kendi verilerini o zaman yeniler.
Zamanlayıcı Qt olay döngüsünde çalışır; pencere kapanınca durur.

Sorgu sırasında beklenmeyen bir hata olursa (dosya silinmiş, disk hatası)
izleme durur, hata günlüğe yazılır ve ``durdu`` sinyali verilir; pencere
bunu durum çubuğunda gösterir. Sessizce yeniden deneme yoktur.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, QTimer, Signal

from defteriki import gunluk
from defteriki.pencere_islevleri import PencereIslevleri

VARSAYILAN_ARALIK_MS = 1000
"""Yoklama aralığı; bir saniye Cowork'un yazdığını görmek için yeterli."""

OLAY_IZLEME_HATASI = "arayuz_izleme_hatasi"


class DegisiklikIzleyici(QObject):
    """Veri değişince ``degisti``; yoklama düşerse ``durdu(mesaj)``."""

    degisti = Signal()
    durdu = Signal(str)

    def __init__(
        self,
        islevler: PencereIslevleri,
        aralik_ms: int = VARSAYILAN_ARALIK_MS,
        ebeveyn: QObject | None = None,
    ) -> None:
        super().__init__(ebeveyn)
        self._islevler = islevler
        self._zamanlayici = QTimer(self)
        self._zamanlayici.setInterval(aralik_ms)
        self._zamanlayici.timeout.connect(self.yokla)

    @property
    def calisiyor(self) -> bool:
        return self._zamanlayici.isActive()

    def baslat(self) -> None:
        """Başlangıç noktasını alır ve yoklamayı başlatır."""
        self._islevler.degisti_mi()
        self._zamanlayici.start()

    def durdur(self) -> None:
        self._zamanlayici.stop()

    def yokla(self) -> bool:
        """Değişiklik sorar; varsa sinyal verir ve ``True`` döndürür."""
        try:
            degisti = self._islevler.degisti_mi()
        except Exception as hata:
            self.durdur()
            gunluk.hata_kaydet(OLAY_IZLEME_HATASI, hata)
            self.durdu.emit(f"izleme durdu ({type(hata).__name__})")
            return False
        if degisti:
            self.degisti.emit()
        return degisti

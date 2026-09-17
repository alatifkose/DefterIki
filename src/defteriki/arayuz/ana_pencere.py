"""Ana pencere (Teslim 6.1: kabuk).

Başlık, orta alan ve durum çubuğu. Durum çubuğu ortamı, şema sürümünü ve
son değişiklik zamanını (yerel saat) gösterir. Karar kutusu (6.2) ve
bakiye/hareket görünümü (6.3) orta alana sonraki teslimlerde eklenir;
``DegisiklikIzleyici.degisti`` sinyali onların yenileme kaynağıdır.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QLabel, QMainWindow, QStatusBar

from defteriki.arayuz.degisiklik_izleme import VARSAYILAN_ARALIK_MS, DegisiklikIzleyici
from defteriki.baslangic import Hazirlik
from defteriki.pencere_islevleri import PencereIslevleri

PENCERE_BASLIGI = "DEFTERIKI"
PENCERE_GENISLIK = 1280
PENCERE_YUKSEKLIK = 720
METIN_DEGISIKLIK_YOK = "Değişiklik: henüz yok"


class AnaPencere(QMainWindow):
    def __init__(
        self,
        hazirlik: Hazirlik,
        islevler: PencereIslevleri,
        yoklama_araligi_ms: int = VARSAYILAN_ARALIK_MS,
    ) -> None:
        super().__init__()
        ayarlar = hazirlik.ayarlar
        self.setWindowTitle(PENCERE_BASLIGI)
        self.resize(PENCERE_GENISLIK, PENCERE_YUKSEKLIK)
        self.degisiklik_sayisi = 0

        orta = QLabel(
            f"{PENCERE_BASLIGI} — {ayarlar.ortam.value} ortamı\n"
            f"Veritabanı: {ayarlar.veritabani_yolu}"
        )
        orta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        orta.setWordWrap(True)  # uzun yol pencereyi genişletmesin
        self.setCentralWidget(orta)

        self.ortam_etiketi = QLabel(f"Ortam: {ayarlar.ortam.value}")
        self.sema_etiketi = QLabel(f"Şema: {hazirlik.sema_surumu}")
        self.degisiklik_etiketi = QLabel(METIN_DEGISIKLIK_YOK)
        cubuk = QStatusBar()
        for etiket in (self.ortam_etiketi, self.sema_etiketi, self.degisiklik_etiketi):
            cubuk.addPermanentWidget(etiket)
        self.setStatusBar(cubuk)

        self.izleyici = DegisiklikIzleyici(islevler, yoklama_araligi_ms, self)
        self.izleyici.degisti.connect(self._degisikligi_goster)
        self.izleyici.durdu.connect(self._izleme_durdu)
        self.izleyici.baslat()

    def _degisikligi_goster(self) -> None:
        self.degisiklik_sayisi += 1
        saat = datetime.now().strftime("%H:%M:%S")
        self.degisiklik_etiketi.setText(
            f"Son değişiklik: {saat} ({self.degisiklik_sayisi})"
        )

    def _izleme_durdu(self, mesaj: str) -> None:
        self.degisiklik_etiketi.setText(f"Değişiklik: {mesaj}")

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 (Qt adı)
        self.izleyici.durdur()
        super().closeEvent(event)

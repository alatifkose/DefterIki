"""Ana pencere (Teslim 6.1 kabuk, 6.2 karar kutusu, 6.3 hareketler).

Başlık, sekmeli orta alan ve durum çubuğu. Sekmeler: "Karar kutusu (n)"
(n bekleyen sayısı) ve "Hareketler". Durum çubuğu solda veritabanı yolunu,
sağda ortamı, şema sürümünü ve son değişiklik zamanını (yerel saat)
gösterir. Değişiklik izleyicisi "veri değişti" deyince iki görünüm de
yenilenir.
"""

from __future__ import annotations

from datetime import datetime

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QLabel, QMainWindow, QStatusBar, QTabWidget

from defteriki.arayuz.degisiklik_izleme import VARSAYILAN_ARALIK_MS, DegisiklikIzleyici
from defteriki.arayuz.hareketler import HareketGorunumu
from defteriki.arayuz.karar_kutusu import KararKutusu
from defteriki.baslangic import Hazirlik
from defteriki.pencere_islevleri import PencereIslevleri

PENCERE_BASLIGI = "DEFTERIKI"
PENCERE_GENISLIK = 1280
PENCERE_YUKSEKLIK = 720
METIN_DEGISIKLIK_YOK = "Değişiklik: henüz yok"
SEKME_KARAR_KUTUSU = "Karar kutusu"
SEKME_HAREKETLER = "Hareketler"


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

        self.sekmeler = QTabWidget()
        self.karar_kutusu = KararKutusu(islevler)
        self.sekmeler.addTab(self.karar_kutusu, SEKME_KARAR_KUTUSU)
        self.karar_kutusu.yenilendi.connect(self._karar_sekmesini_adlandir)
        self._karar_sekmesini_adlandir(self.karar_kutusu.bekleyen_sayisi)
        self.hareketler = HareketGorunumu(islevler)
        self.sekmeler.addTab(self.hareketler, SEKME_HAREKETLER)
        self.setCentralWidget(self.sekmeler)

        self.ortam_etiketi = QLabel(f"Ortam: {ayarlar.ortam.value}")
        self.sema_etiketi = QLabel(f"Şema: {hazirlik.sema_surumu}")
        self.degisiklik_etiketi = QLabel(METIN_DEGISIKLIK_YOK)
        cubuk = QStatusBar()
        for etiket in (self.ortam_etiketi, self.sema_etiketi, self.degisiklik_etiketi):
            cubuk.addPermanentWidget(etiket)
        cubuk.showMessage(f"Veritabanı: {ayarlar.veritabani_yolu}")
        self.setStatusBar(cubuk)

        self.izleyici = DegisiklikIzleyici(islevler, yoklama_araligi_ms, self)
        self.izleyici.degisti.connect(self._degisikligi_goster)
        self.izleyici.degisti.connect(self.karar_kutusu.yenile)
        self.izleyici.degisti.connect(self.hareketler.yenile)
        self.izleyici.durdu.connect(self._izleme_durdu)
        self.izleyici.baslat()

    def _karar_sekmesini_adlandir(self, bekleyen: int) -> None:
        self.sekmeler.setTabText(
            self.sekmeler.indexOf(self.karar_kutusu),
            f"{SEKME_KARAR_KUTUSU} ({bekleyen})" if bekleyen else SEKME_KARAR_KUTUSU,
        )

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

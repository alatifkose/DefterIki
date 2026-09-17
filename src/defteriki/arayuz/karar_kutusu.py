"""Karar kutusu (Teslim 6.2): kullanıcı kararı bekleyen talepler.

Solda bekleyen talepler listesi, sağda seçili talebin hedef nesnesi:
özellikler kutucuklarla listelenir ve kullanıcı mükerrerlik şartı olacak
özellikleri işaretler (0..n, K14); gerekçe isteğe bağlı; Onayla / Reddet /
Ertele. Her karar ``PencereIslevleri.karar_ver`` ile, pencerede görülen
nesne sürümüyle uygulanır; hedef bu arada değişmişse karar uygulanmaz,
mesaj gösterilir ve liste yenilenir. Ertele hiçbir şey yazmaz: talep
``BEKLIYOR`` kalır, seçim kaldırılır.

Bu görünüm veri yorumlamaz, kural koymaz; ``pencere_islevleri``nin verdiği
düz değerleri gösterir ve kullanıcının seçimini geri verir. Liste
``yenile()`` ile yenilenir; pencere bunu değişiklik izleyicisine bağlar.
"""

from __future__ import annotations

from typing import cast

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from defteriki import sozlesmeler as sz
from defteriki.pencere_islevleri import PencereIslevleri, TalepAyrintisi

METIN_BEKLEYEN_YOK = "Karar bekleyen talep yok."
METIN_SECIM_YOK = "Soldan bir talep seç."
METIN_ERTELENDI = "Talep bekliyor; kararı sonra verebilirsin."
METIN_HEDEF_DEGISTI = (
    "Hedef sen bakarken değişti; karar uygulanmadı. Liste yenilendi, yeniden bak."
)
SUTUN_SART = 0
SUTUN_ALAN = 1
SUTUN_DEGER = 2
ZAMAN_BICIMI = "%d.%m.%Y %H:%M"


class KararKutusu(QWidget):
    """``yenilendi(bekleyen_sayisi)`` her yenilemede; ``karar_verildi`` her kararda."""

    yenilendi = Signal(int)
    karar_verildi = Signal()

    def __init__(self, islevler: PencereIslevleri, ebeveyn: QWidget | None = None):
        super().__init__(ebeveyn)
        self._islevler = islevler
        self._ayrinti: TalepAyrintisi | None = None

        self.liste = QListWidget()
        self.liste.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.liste.currentRowChanged.connect(self._secim_degisti)

        self.baslik_etiketi = QLabel(METIN_SECIM_YOK)
        self.baslik_etiketi.setWordWrap(True)
        self.ustler_etiketi = QLabel("")
        self.ustler_etiketi.setWordWrap(True)

        self.ozellik_tablosu = QTableWidget(0, 3)
        self.ozellik_tablosu.setHorizontalHeaderLabels(["Şart", "Alan", "Değer"])
        self.ozellik_tablosu.horizontalHeader().setSectionResizeMode(
            SUTUN_DEGER, QHeaderView.ResizeMode.Stretch
        )
        self.ozellik_tablosu.verticalHeader().setVisible(False)
        self.ozellik_tablosu.setEditTriggers(
            QAbstractItemView.EditTrigger.NoEditTriggers
        )

        self.gerekce = QLineEdit()
        self.gerekce.setPlaceholderText("Gerekçe (isteğe bağlı)")

        self.onayla_dugmesi = QPushButton("Onayla")
        self.reddet_dugmesi = QPushButton("Reddet")
        self.ertele_dugmesi = QPushButton("Ertele")
        self.onayla_dugmesi.clicked.connect(lambda: self._karar_ver(onaylandi=True))
        self.reddet_dugmesi.clicked.connect(lambda: self._karar_ver(onaylandi=False))
        self.ertele_dugmesi.clicked.connect(self.ertele)

        self.mesaj_etiketi = QLabel("")
        self.mesaj_etiketi.setWordWrap(True)

        dugmeler = QHBoxLayout()
        for dugme in (self.onayla_dugmesi, self.reddet_dugmesi, self.ertele_dugmesi):
            dugmeler.addWidget(dugme)
        dugmeler.addStretch(1)

        sag = QVBoxLayout()
        sag.addWidget(self.baslik_etiketi)
        sag.addWidget(self.ustler_etiketi)
        sag.addWidget(self.ozellik_tablosu, 1)
        sag.addWidget(self.gerekce)
        sag.addLayout(dugmeler)
        sag.addWidget(self.mesaj_etiketi)

        yerlesim = QHBoxLayout(self)
        yerlesim.addWidget(self.liste, 1)
        yerlesim.addLayout(sag, 2)

        self._ayrintiyi_temizle()
        self.yenile()

    # --- liste ------------------------------------------------------------------------

    @property
    def bekleyen_sayisi(self) -> int:
        return self.liste.count()

    @property
    def secili_talep_id(self) -> int | None:
        if self.liste.currentRow() < 0:
            return None
        return cast(int, self.liste.currentItem().data(Qt.ItemDataRole.UserRole))

    def yenile(self) -> None:
        """Bekleyenleri yeniden çeker; seçili talep hâlâ bekliyorsa seçili kalır."""
        onceki = self.secili_talep_id
        self.liste.blockSignals(True)
        self.liste.clear()
        talepler = self._islevler.bekleyenler()
        for talep in talepler:
            oge = QListWidgetItem(
                f"Talep {talep.talep_id} · {talep.tur} · {talep.hedef_ozeti} · "
                f"{talep.olusturma_zamani.strftime(ZAMAN_BICIMI)}"
            )
            oge.setData(Qt.ItemDataRole.UserRole, talep.talep_id)
            self.liste.addItem(oge)
        self.liste.blockSignals(False)

        satir = next((i for i, t in enumerate(talepler) if t.talep_id == onceki), -1)
        self.liste.setCurrentRow(satir)
        if satir < 0:
            self._ayrintiyi_temizle()
        else:
            self._secim_degisti(satir)
        self.yenilendi.emit(len(talepler))

    def _secim_degisti(self, satir: int) -> None:
        talep_id = self.secili_talep_id if satir >= 0 else None
        if talep_id is None:
            self._ayrintiyi_temizle()
            return
        try:
            ayrinti = self._islevler.talep_ayrintisi(talep_id)
        except sz.DefterikiHatasi as hata:
            self._ayrintiyi_temizle()
            self.mesaj_etiketi.setText(f"Talep gösterilemedi: {hata.mesaj}")
            return
        self._ayrintiyi_goster(ayrinti)

    # --- ayrıntı ----------------------------------------------------------------------

    def _ayrintiyi_goster(self, ayrinti: TalepAyrintisi) -> None:
        self._ayrinti = ayrinti
        t = ayrinti.talep
        self.baslik_etiketi.setText(
            f"Talep {t.talep_id} · {t.tur} · nesne {ayrinti.nesne_id} "
            f"(seviye {ayrinti.seviye}, {ayrinti.nesne_durumu}, "
            f"sürüm {ayrinti.nesne_surumu})"
        )
        self.ustler_etiketi.setText(
            "Üstler: " + " | ".join(ayrinti.ustler) if ayrinti.ustler else "Üst yok."
        )
        self.ozellik_tablosu.setRowCount(len(ayrinti.ozellikler))
        for satir, o in enumerate(ayrinti.ozellikler):
            sart = QTableWidgetItem()
            sart.setFlags(Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsEnabled)
            sart.setCheckState(
                Qt.CheckState.Checked if o.sart else Qt.CheckState.Unchecked
            )
            sart.setData(Qt.ItemDataRole.UserRole, o.ozellik_id)
            self.ozellik_tablosu.setItem(satir, SUTUN_SART, sart)
            self.ozellik_tablosu.setItem(
                satir, SUTUN_ALAN, QTableWidgetItem(o.alan_adi)
            )
            self.ozellik_tablosu.setItem(
                satir, SUTUN_DEGER, QTableWidgetItem(f"{o.deger} ({o.deger_turu})")
            )
        self.gerekce.clear()
        self._dugmeleri_ayarla(True)

    def _ayrintiyi_temizle(self) -> None:
        self._ayrinti = None
        self.baslik_etiketi.setText(
            METIN_SECIM_YOK if self.liste.count() else METIN_BEKLEYEN_YOK
        )
        self.ustler_etiketi.setText("")
        self.ozellik_tablosu.setRowCount(0)
        self.gerekce.clear()
        self._dugmeleri_ayarla(False)

    def _dugmeleri_ayarla(self, acik: bool) -> None:
        for dugme in (self.onayla_dugmesi, self.reddet_dugmesi, self.ertele_dugmesi):
            dugme.setEnabled(acik)

    def secili_sartlar(self) -> tuple[int, ...]:
        """İşaretli özellik kimlikleri, tablo sırasıyla."""
        secilen: list[int] = []
        for satir in range(self.ozellik_tablosu.rowCount()):
            oge = self.ozellik_tablosu.item(satir, SUTUN_SART)
            if oge is not None and oge.checkState() is Qt.CheckState.Checked:
                secilen.append(cast(int, oge.data(Qt.ItemDataRole.UserRole)))
        return tuple(secilen)

    # --- karar ------------------------------------------------------------------------

    def _karar_ver(self, *, onaylandi: bool) -> None:
        ayrinti = self._ayrinti
        if ayrinti is None:
            return
        try:
            sonuc = self._islevler.karar_ver(
                ayrinti.talep.talep_id,
                ayrinti.nesne_surumu,
                onaylandi=onaylandi,
                secilen_sartlar=self.secili_sartlar() if onaylandi else (),
                gerekce=self.gerekce.text().strip() or None,
            )
        except sz.HedefSurumuDegisti:
            self.mesaj_etiketi.setText(METIN_HEDEF_DEGISTI)
            self.yenile()
            return
        except sz.DefterikiHatasi as hata:
            # Talep başka yerden sonuçlanmış olabilir; liste güncel hâline döner.
            self.mesaj_etiketi.setText(f"Karar uygulanamadı: {hata.mesaj}")
            self.yenile()
            return
        self.mesaj_etiketi.setText(
            f"Talep {sonuc.talep_id} {sonuc.talep_durumu}; nesne {sonuc.nesne_id} "
            f"{sonuc.nesne_durumu} (sürüm {sonuc.nesne_surumu})."
        )
        self.yenile()
        self.karar_verildi.emit()

    def ertele(self) -> None:
        """Hiçbir şey yazmaz; seçimi kaldırır, talep bekliyor kalır."""
        self.liste.setCurrentRow(-1)
        self._ayrintiyi_temizle()
        self.mesaj_etiketi.setText(METIN_ERTELENDI)

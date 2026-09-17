"""Bakiye ve hareket görünümü (Teslim 6.3).

Üstte hesap (AKTIF nesne) seçimi ve etkin bakiye; ortada hareket listesi
(tarih, açıklama, yön, tutar, durum: kayıtlı / yazıldı ama kayıtlı değil,
belgeleri); altta belge listesi durumuyla. Seçili belge "Belgeyi aç" ile ya
da çift tıklamayla işletim sisteminin varsayılan programında açılır; pencere
dosyayı yorumlamaz. Bütün sayılar ``pencere_islevleri``den gelir; görünüm
toplama yapmaz, bakiyeyi kendi hesaplamaz (K20).

``yenile()`` seçili hesabı koruyarak her şeyi yeniden çeker; pencere bunu
değişiklik izleyicisine bağlar.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import cast

from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from defteriki import sozlesmeler as sz
from defteriki.pencere_islevleri import PencereIslevleri, tutar_metni

METIN_HESAP_YOK = (
    "Aktif hesap yok. Cowork bir belge işleyip hesap önerdiğinde burada görünür."
)
METIN_HAREKET_YOK = "Bu hesapta hareket yok."
METIN_BAKIYE_YOK = "Bakiye: hareket yok"
METIN_KAYITLI = "Kayıtlı"
METIN_KAYITLI_DEGIL = "Yazıldı, kayıtlı değil"
TARIH_BICIMI = "%d.%m.%Y"
ZAMAN_BICIMI = "%d.%m.%Y %H:%M"
HAREKET_SUTUNLARI = ("Tarih", "Açıklama", "Yön", "Tutar", "Durum", "Belge")
BELGE_SUTUNLARI = ("Belge", "Kaynak adı", "Durum", "Sürüm", "Zaman")
SUTUN_BELGE_ID = 0

type DosyaAcici = Callable[[Path], None]


def _isletim_sistemiyle_ac(yol: Path) -> None:
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(yol)))


class HareketGorunumu(QWidget):
    """``yenilendi()`` her yenilemede; ``belge_acildi(yol)`` her açmada."""

    yenilendi = Signal()
    belge_acildi = Signal(str)

    def __init__(
        self,
        islevler: PencereIslevleri,
        ebeveyn: QWidget | None = None,
        dosya_acici: DosyaAcici | None = None,
    ) -> None:
        super().__init__(ebeveyn)
        self._islevler = islevler
        self._dosya_ac = dosya_acici or _isletim_sistemiyle_ac

        self.hesap_secimi = QComboBox()
        self.hesap_secimi.currentIndexChanged.connect(self._hesap_degisti)
        self.bakiye_etiketi = QLabel("")
        self.bakiye_etiketi.setWordWrap(True)

        self.hareket_tablosu = _tablo(HAREKET_SUTUNLARI, uzayan=1)
        self.belge_tablosu = _tablo(BELGE_SUTUNLARI, uzayan=1)
        self.belge_tablosu.itemDoubleClicked.connect(self._belgeye_cift_tiklandi)

        self.belge_ac_dugmesi = QPushButton("Belgeyi aç")
        self.belge_ac_dugmesi.clicked.connect(self.belgeyi_ac)
        self.mesaj_etiketi = QLabel("")
        self.mesaj_etiketi.setWordWrap(True)

        ust = QHBoxLayout()
        ust.addWidget(QLabel("Hesap:"))
        ust.addWidget(self.hesap_secimi, 1)
        ust.addWidget(self.bakiye_etiketi, 2)

        alt = QHBoxLayout()
        alt.addWidget(self.belge_ac_dugmesi)
        alt.addWidget(self.mesaj_etiketi, 1)

        yerlesim = QVBoxLayout(self)
        yerlesim.addLayout(ust)
        yerlesim.addWidget(QLabel("Hareketler"))
        yerlesim.addWidget(self.hareket_tablosu, 3)
        yerlesim.addWidget(QLabel("Belgeler"))
        yerlesim.addWidget(self.belge_tablosu, 2)
        yerlesim.addLayout(alt)

        self.yenile()

    # --- yenileme ---------------------------------------------------------------------

    @property
    def secili_nesne_id(self) -> int | None:
        if self.hesap_secimi.currentIndex() < 0:
            return None
        return cast(int, self.hesap_secimi.currentData())

    @property
    def secili_belge_id(self) -> int | None:
        satir = self.belge_tablosu.currentRow()
        if satir < 0:
            return None
        oge = self.belge_tablosu.item(satir, SUTUN_BELGE_ID)
        return None if oge is None else int(oge.text())

    def yenile(self) -> None:
        """Hesapları, bakiyeyi, hareketleri ve belgeleri yeniden çeker."""
        onceki = self.secili_nesne_id
        self.hesap_secimi.blockSignals(True)
        self.hesap_secimi.clear()
        hesaplar = self._islevler.hesaplar()
        for h in hesaplar:
            self.hesap_secimi.addItem(
                f"nesne {h.nesne_id} · seviye {h.seviye} · {h.ozet}", h.nesne_id
            )
        sira = next((i for i, h in enumerate(hesaplar) if h.nesne_id == onceki), -1)
        if sira < 0 and hesaplar:
            sira = 0
        self.hesap_secimi.setCurrentIndex(sira)
        self.hesap_secimi.blockSignals(False)

        self._hesap_degisti(sira)
        self._belgeleri_doldur()
        self.yenilendi.emit()

    def _hesap_degisti(self, sira: int) -> None:
        nesne_id = self.secili_nesne_id if sira >= 0 else None
        if nesne_id is None:
            self.bakiye_etiketi.setText(METIN_HESAP_YOK)
            self.hareket_tablosu.setRowCount(0)
            return
        bakiyeler = self._islevler.bakiyeler(nesne_id)
        self.bakiye_etiketi.setText(
            " | ".join(
                f"Bakiye: {tutar_metni(b.bakiye_kurus, b.para_birimi)} · "
                f"giriş {tutar_metni(b.arttir_kurus, b.para_birimi)} · "
                f"çıkış {tutar_metni(b.azalt_kurus, b.para_birimi)} · "
                f"kayıtlı olmayan kayıt: {b.bekleyen_kayit_sayisi}"
                for b in bakiyeler
            )
            or METIN_BAKIYE_YOK
        )
        hareketler = self._islevler.hareketler(nesne_id)
        self.hareket_tablosu.setRowCount(len(hareketler))
        for satir, h in enumerate(hareketler):
            hucreler = (
                h.islem_tarihi.strftime(TARIH_BICIMI),
                h.aciklama,
                "giriş" if h.yon == sz.Yon.ARTTIR.value else "çıkış",
                tutar_metni(h.tutar_kurus, h.para_birimi),
                METIN_KAYITLI if h.kayitli else METIN_KAYITLI_DEGIL,
                ", ".join(str(b) for b in h.belge_idleri),
            )
            for sutun, metin in enumerate(hucreler):
                self.hareket_tablosu.setItem(satir, sutun, QTableWidgetItem(metin))
        if not hareketler:
            self.mesaj_etiketi.setText(METIN_HAREKET_YOK)

    def _belgeleri_doldur(self) -> None:
        onceki = self.secili_belge_id
        belgeler = self._islevler.belgeler()
        self.belge_tablosu.setRowCount(len(belgeler))
        for satir, b in enumerate(belgeler):
            hucreler = (
                str(b.belge_id),
                b.kaynak_adi,
                b.durum,
                str(b.surum),
                b.olusturma_zamani.strftime(ZAMAN_BICIMI),
            )
            for sutun, metin in enumerate(hucreler):
                self.belge_tablosu.setItem(satir, sutun, QTableWidgetItem(metin))
        sira = next((i for i, b in enumerate(belgeler) if b.belge_id == onceki), -1)
        self.belge_tablosu.setCurrentCell(sira, SUTUN_BELGE_ID)
        self.belge_ac_dugmesi.setEnabled(bool(belgeler))

    # --- belge açma -------------------------------------------------------------------

    def _belgeye_cift_tiklandi(self, _oge: QTableWidgetItem) -> None:
        self.belgeyi_ac()

    def belgeyi_ac(self) -> None:
        """Seçili belgenin arşiv dosyasını işletim sistemine açtırır."""
        belge_id = self.secili_belge_id
        if belge_id is None:
            self.mesaj_etiketi.setText("Önce listeden bir belge seç.")
            return
        try:
            yol = self._islevler.belge_dosya_yolu(belge_id)
        except sz.DefterikiHatasi as hata:
            self.mesaj_etiketi.setText(f"Belge açılamadı: {hata.mesaj}")
            return
        self._dosya_ac(yol)
        self.mesaj_etiketi.setText(f"Belge {belge_id} açıldı: {yol.name}")
        self.belge_acildi.emit(str(yol))


def _tablo(sutunlar: tuple[str, ...], *, uzayan: int) -> QTableWidget:
    tablo = QTableWidget(0, len(sutunlar))
    tablo.setHorizontalHeaderLabels(list(sutunlar))
    tablo.horizontalHeader().setSectionResizeMode(
        uzayan, QHeaderView.ResizeMode.Stretch
    )
    tablo.verticalHeader().setVisible(False)
    tablo.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tablo.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tablo.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    return tablo

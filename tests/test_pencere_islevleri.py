"""Pencere işlevleri testleri (Teslim 6.1): "veri değişti mi?" sorusu.

Pencere tarafı bu modülü çağırır; SQLite ayrıntısı (``data_version``) burada
saklı kalır. Yazmalar ayrı bir ``Veritabani`` nesnesinden yapılır: gerçek
kullanımda MCP sunucusu ve onay komutu ayrı süreçtir.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest

from defteriki import ayarlar as ay
from defteriki import denetim, gunluk, pencere_islevleri
from defteriki import sozlesmeler as sz
from defteriki import veritabani as vt
from defteriki.baslangic import ortami_hazirla

DEGISKENLER = (
    ay.ORTAM_DEGISKENI,
    ay.VERI_KOKU_DEGISKENI,
    ay.VERITABANI_YOLU_DEGISKENI,
    ay.BELGE_DIZINI_DEGISKENI,
    ay.LOG_DIZINI_DEGISKENI,
    ay.GELEN_DIZINI_DEGISKENI,
)


@pytest.fixture
def ayarlar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ay.Ayarlar]:
    for degisken in DEGISKENLER:
        monkeypatch.delenv(degisken, raising=False)
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(tmp_path / "kok"))
    gunluk.gunlugu_kapat()
    yield ortami_hazirla().ayarlar
    gunluk.gunlugu_kapat()


@pytest.fixture
def islevler(ayarlar: ay.Ayarlar) -> Iterator[pencere_islevleri.PencereIslevleri]:
    i = pencere_islevleri.pencere_islevleri_ac(ayarlar)
    yield i
    i.kapat()


def _baska_surec_yazar(ayarlar: ay.Ayarlar) -> None:
    db = vt.veritabani_ac(ayarlar)
    try:
        with db.yazma_islemi() as oturum:
            denetim.olay_yaz(
                oturum,
                aktor=sz.DenetimAktoru.UYGULAMA,
                eylem="test",
                hedef="test",
                simdi=datetime.now(UTC),
            )
    finally:
        db.kapat()


def test_ilk_soru_baslangic_noktasidir(
    islevler: pencere_islevleri.PencereIslevleri,
) -> None:
    assert islevler.degisti_mi() is False
    assert islevler.degisti_mi() is False


def test_baska_surecin_yazmasi_bir_kez_evet_doner(
    islevler: pencere_islevleri.PencereIslevleri, ayarlar: ay.Ayarlar
) -> None:
    islevler.degisti_mi()

    _baska_surec_yazar(ayarlar)
    assert islevler.degisti_mi() is True
    assert islevler.degisti_mi() is False  # aynı değişiklik ikinci kez bildirilmez

    _baska_surec_yazar(ayarlar)
    _baska_surec_yazar(ayarlar)
    assert islevler.degisti_mi() is True  # iki yazma tek "evet"
    assert islevler.degisti_mi() is False


def test_soru_yazmayi_engellemez(
    islevler: pencere_islevleri.PencereIslevleri, ayarlar: ay.Ayarlar
) -> None:
    islevler.degisti_mi()
    _baska_surec_yazar(ayarlar)  # kilit beklemeden tamamlanır
    assert islevler.degisti_mi() is True


def test_kapat_sonrasi_yeniden_sorulabilir(ayarlar: ay.Ayarlar) -> None:
    islevler = pencere_islevleri.pencere_islevleri_ac(ayarlar)
    islevler.degisti_mi()
    islevler.kapat()
    assert islevler.degisti_mi() is False
    islevler.kapat()

"""Geçici onay komutu (Aşama 6'ya kadar): yalnız onaylar işlevlerini çağırır; MCP'de
yoktur."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from defteriki import ayarlar as ay
from defteriki import gunluk, mcp_araclari, mcp_kapisi, nesneler, onay_komutu
from defteriki import sozlesmeler as sz
from defteriki import veritabani as vt
from defteriki.baslangic import ortami_hazirla

Oz = mcp_araclari.OzellikGirdi


@pytest.fixture
def ayarlar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ay.Ayarlar]:
    for degisken in (
        ay.ORTAM_DEGISKENI,
        ay.VERI_KOKU_DEGISKENI,
        ay.VERITABANI_YOLU_DEGISKENI,
        ay.BELGE_DIZINI_DEGISKENI,
        ay.LOG_DIZINI_DEGISKENI,
        ay.GELEN_DIZINI_DEGISKENI,
    ):
        monkeypatch.delenv(degisken, raising=False)
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(tmp_path / "kok"))
    gunluk.gunlugu_kapat()
    yield ortami_hazirla().ayarlar
    gunluk.gunlugu_kapat()


@pytest.fixture
def bekleyen(ayarlar: ay.Ayarlar) -> int:
    """Cowork GONDER ile önerdi: QNB, ONAY_BEKLIYOR. Nesne kimliği."""
    db = vt.veritabani_ac(ayarlar)
    try:
        sonuc = mcp_araclari.nesne_tanimla(
            db,
            mcp_araclari.NesneTanimlaGirdisi(
                adim="GONDER",
                islem_anahtari="q",
                ozellikler=[
                    Oz(alan_adi="ad", deger="QNB"),
                    Oz(alan_adi="swift", deger="FNNBTRIS"),
                ],
            ),
            "k",
        )
    finally:
        db.kapat()
    assert sonuc.nesne_id == 1 and sonuc.talep_id == 1
    return sonuc.nesne_id


def _nesne(ayarlar: ay.Ayarlar, nesne_id: int) -> nesneler.NesneAyrinti:
    db = vt.veritabani_ac(ayarlar)
    try:
        with db.okuma_islemi() as oturum:
            return nesneler.nesne_getir(oturum, nesne_id)
    finally:
        db.kapat()


def test_bekleyenler_ve_goster(
    ayarlar: ay.Ayarlar, bekleyen: int, capsys: pytest.CaptureFixture[str]
) -> None:
    assert onay_komutu.main(["bekleyenler"]) == 0
    cikti = capsys.readouterr().out
    assert "talep 1 | NESNE_ACILISI | hedef 1 | sürüm 1" in cikti

    assert onay_komutu.main(["goster", "1"]) == 0
    cikti = capsys.readouterr().out
    assert "nesne 1 | seviye 0 | durum ONAY_BEKLIYOR | sürüm 1" in cikti
    assert (
        "[1] ad = 'QNB' (METIN)" in cikti and "[2] swift = 'FNNBTRIS' (METIN)" in cikti
    )
    assert "defteriki-onay onayla 1 --surum 1" in cikti


def test_onayla_sart_secerek(
    ayarlar: ay.Ayarlar, bekleyen: int, capsys: pytest.CaptureFixture[str]
) -> None:
    kod = onay_komutu.main(["onayla", "1", "--surum", "1", "--sart", "2"])

    assert kod == 0
    cikti = capsys.readouterr().out
    assert (
        "talep 1 ONAYLANDI" in cikti
        and "nesne 1 AKTIF | sürüm 2 | şartlar [2]" in cikti
    )
    ayrinti = _nesne(ayarlar, bekleyen)
    assert ayrinti.nesne.durum is sz.NesneDurumu.AKTIF and ayrinti.nesne.surum == 2
    assert [(o.alan_adi, o.sart) for o in ayrinti.ozellikler] == [
        ("ad", False),
        ("swift", True),
    ]

    assert onay_komutu.main(["bekleyenler"]) == 0
    assert "Karar bekleyen talep yok." in capsys.readouterr().out


def test_reddet(
    ayarlar: ay.Ayarlar, bekleyen: int, capsys: pytest.CaptureFixture[str]
) -> None:
    assert onay_komutu.main(["reddet", "1", "--surum", "1", "--gerekce", "yanlış"]) == 0
    assert "talep 1 REDDEDILDI" in capsys.readouterr().out
    assert _nesne(ayarlar, bekleyen).nesne.durum is sz.NesneDurumu.SILINDI


def test_eski_surum_ve_olmayan_talep_uygulanmaz(
    ayarlar: ay.Ayarlar, bekleyen: int, capsys: pytest.CaptureFixture[str]
) -> None:
    assert onay_komutu.main(["onayla", "1", "--surum", "5"]) == 1
    err = capsys.readouterr().err
    assert "HEDEF_SURUMU_DEGISTI" in err
    assert _nesne(ayarlar, bekleyen).nesne.durum is sz.NesneDurumu.ONAY_BEKLIYOR

    assert onay_komutu.main(["goster", "9"]) == 1
    assert "HEDEF_BULUNAMADI" in capsys.readouterr().err

    assert onay_komutu.main(["onayla", "1", "--surum", "1", "--sart", "99"]) == 1
    assert "GIRDI_GECERSIZ" in capsys.readouterr().err


def test_onay_komutu_mcp_de_yok() -> None:
    assert not any("onay" in ad for ad in mcp_kapisi.YETENEKLER)

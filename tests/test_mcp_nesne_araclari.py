"""Nesne araçları (Teslim 5.2/1): nesne_bul, nesne_getir, oturum_baglami."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp.types import CallToolResult

from defteriki import ayarlar as ay
from defteriki import gunluk, mcp_araclari, mcp_kapisi, nesneler, onaylar, sema, zarf
from defteriki import sozlesmeler as sz
from defteriki import veritabani as vt

Oz = mcp_araclari.OzellikGirdi


@pytest.fixture
def db(tmp_path: Path) -> Iterator[vt.Veritabani]:
    yol = tmp_path / "vt" / "mcp.sqlite3"
    yol.parent.mkdir()
    veritabani = vt.Veritabani(yol, mesgul_bekleme_ms=200)
    sema.semayi_yukselt(veritabani)
    yield veritabani
    veritabani.kapat()


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
    ayar = ay.ayarlari_yukle()
    ay.dizinleri_hazirla(ayar)
    gunluk.gunlugu_kapat()
    gunluk.gunlugu_kur(ayar.log_dizini)
    yield ayar
    gunluk.gunlugu_kapat()


def _gonder(
    db: vt.Veritabani, anahtar: str, *ozellikler: Oz, ustler: list[int] = []
) -> int:
    sonuc = mcp_araclari.nesne_tanimla(
        db,
        mcp_araclari.NesneTanimlaGirdisi(
            adim="GONDER",
            islem_anahtari=anahtar,
            ozellikler=list(ozellikler),
            ust_idleri=ustler,
        ),
        "k",
    )
    assert sonuc.nesne_id is not None
    return sonuc.nesne_id


def _onayla(db: vt.Veritabani, nesne_id: int, *sart_alanlari: str) -> None:
    with db.yazma_islemi() as oturum:
        ayrinti = nesneler.nesne_getir(oturum, nesne_id)
        (talep,) = [
            t for t in onaylar.bekleyenleri_listele(oturum) if t.hedef_id == nesne_id
        ]
        sartlar = tuple(o.id for o in ayrinti.ozellikler if o.alan_adi in sart_alanlari)
        onaylar.karar_uygula(
            oturum,
            talep_id=talep.id,
            gorulen_hedef_surumu=ayrinti.nesne.surum,
            karar=onaylar.Karar(onaylandi=True, secilen_sartlar=sartlar),
            simdi=sz.simdi_utc(),
        )


@pytest.fixture
def garanti(db: vt.Veritabani) -> tuple[int, int, int]:
    """Garanti (AKTIF, şart ad) → ME (AKTIF, şart iban); GK ONAY_BEKLIYOR."""
    banka = _gonder(
        db,
        "b",
        Oz(alan_adi="ad", deger="Garanti BBVA"),
        Oz(alan_adi="tür", deger="banka"),
    )
    _onayla(db, banka, "ad")
    me = _gonder(
        db,
        "me",
        Oz(alan_adi="ad", deger="ME"),
        Oz(alan_adi="iban", deger="TR000000000000000000000001"),
        ustler=[banka],
    )
    _onayla(db, me, "iban")
    gk = _gonder(db, "gk", Oz(alan_adi="ad", deger="GK"), ustler=[banka])
    return banka, me, gk


def _bul(db: vt.Veritabani, **alanlar: Any) -> zarf.Zarf:
    return mcp_kapisi.araci_calistir(
        mcp_kapisi.ARAC_NESNE_BUL,
        mcp_araclari.nesne_bul,
        db,
        mcp_araclari.NesneBulGirdisi(**alanlar),
    )


# --- nesne_bul --------------------------------------------------------------------


def test_bul_bos_sonuc_yeni_nesne_onerisine_yonlendirir(
    db: vt.Veritabani, ayarlar: ay.Ayarlar
) -> None:
    sonuc = _bul(db, alan_adi="ad", deger="Garanti BBVA")
    assert sonuc.durum is zarf.YanitDurumu.TAMAMLANDI
    assert sonuc.icerik == {
        "nesneler": [],
        "sayfa": {"sinir": 100, "baslangic": 0, "donen": 0},
    }
    assert "nesne_tanimla" in (sonuc.sonraki_adim or "")


def test_bul_mevcut_nesneyi_ozellikleriyle_verir(
    db: vt.Veritabani, ayarlar: ay.Ayarlar, garanti: tuple[int, int, int]
) -> None:
    banka, me, gk = garanti
    sonuc = _bul(db, alan_adi="ad", deger="Garanti BBVA")

    assert sonuc.icerik is not None
    (bulunan,) = sonuc.icerik["nesneler"]
    assert bulunan["id"] == banka and bulunan["durum"] == "AKTIF"
    assert bulunan["seviye"] == 0 and bulunan["surum"] == 2
    assert [(o["alan_adi"], o["deger"], o["sart"]) for o in bulunan["ozellikler"]] == [
        ("ad", "Garanti BBVA", True),
        ("tür", "banka", False),
    ]
    assert "kimliğini kullan" in (sonuc.sonraki_adim or "")

    seviye1 = _bul(db, seviye=1)
    assert seviye1.icerik is not None
    assert [n["id"] for n in seviye1.icerik["nesneler"]] == [me, gk]
    assert [n["durum"] for n in seviye1.icerik["nesneler"]] == [
        "AKTIF",
        "ONAY_BEKLIYOR",
    ]

    yalniz_aktif = _bul(db, seviye=1, durumlar=[sz.NesneDurumu.AKTIF])
    assert yalniz_aktif.icerik is not None
    assert [n["id"] for n in yalniz_aktif.icerik["nesneler"]] == [me]

    sayfa = _bul(db, sayfa_siniri=1, sayfa_baslangici=1)
    assert sayfa.icerik is not None
    assert [n["id"] for n in sayfa.icerik["nesneler"]] == [me]
    assert sayfa.icerik["sayfa"] == {"sinir": 1, "baslangic": 1, "donen": 1}


def test_bul_esleme_turuyle_ve_normalizasyonsuz(
    db: vt.Veritabani, ayarlar: ay.Ayarlar, garanti: tuple[int, int, int]
) -> None:
    assert _bul(db, alan_adi="AD", deger="Garanti BBVA").icerik == {
        "nesneler": [],
        "sayfa": {"sinir": 100, "baslangic": 0, "donen": 0},
    }
    assert _bul(db, alan_adi="ad", deger="garanti bbva").icerik is not None
    assert _bul(db, alan_adi="ad", deger="garanti bbva").icerik["nesneler"] == []  # pyright: ignore[reportOptionalSubscript]


def test_bul_gecersiz_sayfalama_reddedilir(
    db: vt.Veritabani, ayarlar: ay.Ayarlar
) -> None:
    sonuc = _bul(db, sayfa_siniri=0)
    assert sonuc.durum is zarf.YanitDurumu.REDDEDILDI
    assert sonuc.hata is not None and sonuc.hata.kod == "GIRDI_GECERSIZ"
    assert sonuc.hata.alan == "sinir"


# --- nesne_getir --------------------------------------------------------------------


def test_getir_ozellik_ust_alt_ve_surum(
    db: vt.Veritabani, ayarlar: ay.Ayarlar, garanti: tuple[int, int, int]
) -> None:
    banka, me, gk = garanti
    sonuc = mcp_kapisi.araci_calistir(
        mcp_kapisi.ARAC_NESNE_GETIR,
        mcp_araclari.nesne_getir,
        db,
        mcp_araclari.NesneGetirGirdisi(nesne_id=banka),
    )
    assert sonuc.durum is zarf.YanitDurumu.TAMAMLANDI
    assert sonuc.nesne_id == banka and sonuc.hedef_surumu == 2
    assert sonuc.icerik is not None
    assert sonuc.icerik["ust_idleri"] == [] and sonuc.icerik["alt_idleri"] == [me, gk]
    assert sonuc.icerik["ozellikler"][0]["sart"] is True
    assert sonuc.sonraki_adim == "Nesne aktif; kimliğini kullan."

    bekleyen = mcp_kapisi.araci_calistir(
        mcp_kapisi.ARAC_NESNE_GETIR,
        mcp_araclari.nesne_getir,
        db,
        mcp_araclari.NesneGetirGirdisi(nesne_id=gk),
    )
    assert bekleyen.sonraki_adim == mcp_araclari.SONRAKI_ONAY_BEKLE
    assert bekleyen.icerik is not None and bekleyen.icerik["ust_idleri"] == [banka]


def test_getir_olmayan_nesne(db: vt.Veritabani, ayarlar: ay.Ayarlar) -> None:
    sonuc = mcp_kapisi.araci_calistir(
        mcp_kapisi.ARAC_NESNE_GETIR,
        mcp_araclari.nesne_getir,
        db,
        mcp_araclari.NesneGetirGirdisi(nesne_id=77),
    )
    assert sonuc.durum is zarf.YanitDurumu.REDDEDILDI
    assert sonuc.hata is not None and sonuc.hata.kod == "HEDEF_BULUNAMADI"


# --- oturum_baglami (C16) ----------------------------------------------------------


def test_oturum_baglami_bos_defter(db: vt.Veritabani, ayarlar: ay.Ayarlar) -> None:
    sonuc = mcp_kapisi.araci_calistir(
        mcp_kapisi.ARAC_OTURUM_BAGLAMI,
        mcp_araclari.oturum_baglami,
        db,
        mcp_araclari.OturumBaglamiGirdisi(),
    )
    assert sonuc.durum is zarf.YanitDurumu.TAMAMLANDI and sonuc.bekleyen == 0
    assert sonuc.icerik == {"son_nesneler": [], "alan_adlari": [], "bekleyen_isler": []}


def test_oturum_baglami_son_nesneler_alan_adlari_bekleyenler(
    db: vt.Veritabani, ayarlar: ay.Ayarlar, garanti: tuple[int, int, int]
) -> None:
    _, me, gk = garanti
    sonuc = mcp_kapisi.araci_calistir(
        mcp_kapisi.ARAC_OTURUM_BAGLAMI,
        mcp_araclari.oturum_baglami,
        db,
        mcp_araclari.OturumBaglamiGirdisi(son_nesne_sayisi=2),
    )
    assert sonuc.icerik is not None
    assert [n["id"] for n in sonuc.icerik["son_nesneler"]] == [gk, me]  # yeniden eskiye
    assert sonuc.icerik["alan_adlari"] == [
        {"alan_adi": "ad", "kullanim": 3},
        {"alan_adi": "iban", "kullanim": 1},
        {"alan_adi": "tür", "kullanim": 1},
    ]
    (bekleyen,) = sonuc.icerik["bekleyen_isler"]
    assert (bekleyen["tur"], bekleyen["hedef_id"], bekleyen["hedef_surumu"]) == (
        "NESNE_ACILISI",
        gk,
        1,
    )
    assert sonuc.bekleyen == 1
    assert "aynen kullan" in (sonuc.sonraki_adim or "")


# --- sunucu üzerinden -------------------------------------------------------------


def test_sunucu_uzerinden_nesne_araclari(
    db: vt.Veritabani, ayarlar: ay.Ayarlar, garanti: tuple[int, int, int]
) -> None:
    banka = garanti[0]
    sunucu = mcp_kapisi.sunucu_kur(ayarlar, "0001", db)
    araclar = {a.name for a in anyio.run(sunucu.list_tools)}
    assert araclar == set(mcp_kapisi.YETENEKLER)
    assert "onay" not in " ".join(araclar)  # onay komutu MCP'de yok

    def cagir(ad: str, args: dict[str, Any]) -> dict[str, Any]:
        sonuc = anyio.run(sunucu.call_tool, ad, args)
        assert isinstance(sonuc, CallToolResult) and sonuc.is_error is False
        assert sonuc.structured_content is not None
        return sonuc.structured_content

    baglam = cagir(mcp_kapisi.ARAC_OTURUM_BAGLAMI, {})
    assert baglam["durum"] == "TAMAMLANDI" and baglam["bekleyen"] == 1
    bul = cagir(
        mcp_kapisi.ARAC_NESNE_BUL,
        {"girdi": {"alan_adi": "ad", "deger": "Garanti BBVA"}},
    )
    assert bul["icerik"]["nesneler"][0]["id"] == banka
    getir = cagir(mcp_kapisi.ARAC_NESNE_GETIR, {"girdi": {"nesne_id": banka}})
    assert getir["nesne_id"] == banka
    red = cagir(mcp_kapisi.ARAC_NESNE_GETIR, {"girdi": {"nesne_id": "GIZLI"}})
    assert red["hata"]["kod"] == "GIRDI_GECERSIZ" and "GIZLI" not in str(red)

"""Belge ve hareket araçları (Teslim 5.2/2): belge_al, belge_getir, okuma_baslat,
hareket_yaz, okuma_tamamla, belge_kaydet. Ekstre MCP araçlarıyla uçtan uca işlenir."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp.types import CallToolResult
from sqlalchemy import func, select

from defteriki import ayarlar as ay
from defteriki import (
    belgeler,
    gunluk,
    mcp_araclari,
    mcp_kapisi,
    nesneler,
    onaylar,
    sema,
    zarf,
)
from defteriki import hesaplamalar as hs
from defteriki import sozlesmeler as sz
from defteriki import veritabani as vt
from defteriki.baslangic import ortami_hazirla

EKSTRE = b"%PDF-1.7\n%sentetik ekstre 5.2/2\n"
Oz = mcp_araclari.OzellikGirdi


@pytest.fixture
def baglam(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[mcp_araclari.AracBaglami]:
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
    hazirlik = ortami_hazirla()
    veritabani = vt.veritabani_ac(hazirlik.ayarlar)
    yield mcp_araclari.AracBaglami(veritabani, hazirlik.ayarlar)
    veritabani.kapat()
    gunluk.gunlugu_kapat()


@pytest.fixture
def hesap(baglam: mcp_araclari.AracBaglami) -> int:
    """AKTIF hesap nesnesi (ME)."""
    sonuc = mcp_araclari.nesne_tanimla(
        baglam,
        mcp_araclari.NesneTanimlaGirdisi(
            adim="GONDER",
            islem_anahtari="n-me",
            ozellikler=[Oz(alan_adi="ad", deger="ME")],
        ),
        "k",
    )
    assert sonuc.nesne_id is not None and sonuc.talep_id is not None
    with baglam.veritabani.yazma_islemi() as oturum:
        onaylar.karar_uygula(
            oturum,
            talep_id=sonuc.talep_id,
            gorulen_hedef_surumu=1,
            karar=onaylar.Karar(onaylandi=True),
            simdi=sz.simdi_utc(),
        )
    return sonuc.nesne_id


def _calistir(
    baglam: mcp_araclari.AracBaglami, ad: str, govde: Any, girdi: Any
) -> zarf.Zarf:
    return mcp_kapisi.araci_calistir(ad, govde, baglam, girdi)


def _belge_al(
    baglam: mcp_araclari.AracBaglami, ad: str = "ekstre.pdf", anahtar: str = "al-1"
) -> zarf.Zarf:
    dosya = baglam.ayarlar.gelen_dizini / ad
    dosya.write_bytes(EKSTRE)
    return _calistir(
        baglam,
        mcp_kapisi.ARAC_BELGE_AL,
        mcp_araclari.belge_al,
        mcp_araclari.BelgeAlGirdisi(yol=str(dosya), islem_anahtari=anahtar),
    )


def _okuma_baslat(
    baglam: mcp_araclari.AracBaglami, belge_id: int, beklenen: int | None = None
) -> zarf.Zarf:
    return _calistir(
        baglam,
        mcp_kapisi.ARAC_OKUMA_BASLAT,
        mcp_araclari.okuma_baslat,
        mcp_araclari.OkumaBaslatGirdisi(
            belge_id=belge_id,
            islem_anahtari="ob-1",
            icerik={"donem": "2026-08"},
            tamlik=(
                mcp_araclari.TamlikGirdi(beklenen_satir_sayisi=beklenen)
                if beklenen is not None
                else None
            ),
        ),
    )


def _hareket(
    n: int, hesap: int, yon: str = "ARTTIR", tutar: Any = 10_000, gun: int = 1
) -> mcp_araclari.HareketGirdi:
    return mcp_araclari.HareketGirdi(
        satir=mcp_araclari.SatirGirdi(
            satir_anahtari=f"s{n}", konum=n, ham={"metin": f"hareket {n}"}
        ),
        hareket=mcp_araclari.HesapHareketiGirdi(
            nesne_id=hesap,
            yon=sz.Yon(yon),
            tutar_kurus=tutar,
            islem_tarihi=f"2026-08-{gun:02d}",
        ),
    )


def _hareket_yaz(
    baglam: mcp_araclari.AracBaglami,
    okuma_id: int,
    hareketler: list[mcp_araclari.HareketGirdi],
    anahtar: str = "p-1",
) -> zarf.Zarf:
    return _calistir(
        baglam,
        mcp_kapisi.ARAC_HAREKET_YAZ,
        mcp_araclari.hareket_yaz,
        mcp_araclari.HareketYazGirdisi(
            okuma_id=okuma_id, islem_anahtari=anahtar, hareketler=hareketler
        ),
    )


def _tamamla(
    baglam: mcp_araclari.AracBaglami, okuma_id: int, anahtar: str = "ot-1"
) -> zarf.Zarf:
    return _calistir(
        baglam,
        mcp_kapisi.ARAC_OKUMA_TAMAMLA,
        mcp_araclari.okuma_tamamla,
        mcp_araclari.OkumaTamamlaGirdisi(okuma_id=okuma_id, islem_anahtari=anahtar),
    )


def _sayi(baglam: mcp_araclari.AracBaglami, tablo: sema.Table) -> int:
    with baglam.veritabani.okuma_islemi() as oturum:
        return int(oturum.execute(select(func.count()).select_from(tablo)).scalar_one())


# --- uçtan uca ----------------------------------------------------------------------


def test_ekstre_araclarla_ucta_uca(
    baglam: mcp_araclari.AracBaglami, hesap: int
) -> None:
    alinan = _belge_al(baglam)
    assert alinan.durum is zarf.YanitDurumu.TAMAMLANDI
    assert alinan.belge_id == 1 and alinan.yazilan == 1
    assert alinan.belge_kaydi is zarf.BelgeKaydiDurumu.TANIMLANMADI
    assert alinan.icerik is not None
    assert alinan.icerik["belge"]["durum"] == "ARSIVLENDI"
    assert alinan.icerik["dosya"]["kaynak_adi"] == "ekstre.pdf"
    assert alinan.sonraki_adim == mcp_araclari.SONRAKI_OKUMA_AC

    okuma = _okuma_baslat(baglam, 1, beklenen=3)
    assert okuma.durum is zarf.YanitDurumu.TAMAMLANDI
    assert okuma.okuma_id == 1 and okuma.belge_id == 1 and okuma.hedef_surumu == 2
    assert okuma.icerik is not None
    assert okuma.icerik["okuma"]["talimat_surumu"] == zarf.TALIMAT_SURUMU
    assert okuma.icerik["okuma"]["tamlik"]["beklenen_satir_sayisi"] == 3
    assert okuma.icerik["belge"]["durum"] == "OKUNUYOR"

    paket = _hareket_yaz(
        baglam,
        1,
        [
            _hareket(0, hesap, "ARTTIR", 2_000_00, 1),
            _hareket(1, hesap, "AZALT", 600_00, 5),
        ],
    )
    assert paket.durum is zarf.YanitDurumu.TAMAMLANDI
    assert (paket.yazilan, paket.zaten_mevcut) == (2, 0)
    assert (
        paket.belge_kaydi is zarf.BelgeKaydiDurumu.TANIMLANMADI
    )  # yazıldı, kayıtlı değil
    assert paket.icerik is not None
    assert [
        (s["satir_anahtari"], s["kayit_id"], s["zaten_vardi"])
        for s in paket.icerik["satirlar"]
    ] == [
        ("s0", 1, False),
        ("s1", 2, False),
    ]
    with baglam.veritabani.okuma_islemi() as oturum:
        assert hs.etkin_bakiye(oturum, nesne_id=hesap).bakiye_kurus == 0

    eksik = _tamamla(baglam, 1)
    assert eksik.durum is zarf.YanitDurumu.REDDEDILDI
    assert eksik.hata is not None and eksik.hata.kod == "MUTABAKAT_FARKI"
    assert "yeniden tamamla" in (eksik.sonraki_adim or "")

    ikinci = _hareket_yaz(
        baglam, 1, [_hareket(2, hesap, "AZALT", 150_00, 9)], anahtar="p-2"
    )
    assert ikinci.yazilan == 1

    tamam = _tamamla(baglam, 1, anahtar="ot-2")
    assert tamam.durum is zarf.YanitDurumu.TAMAMLANDI
    assert tamam.belge_kaydi is zarf.BelgeKaydiDurumu.KAYITLI
    assert tamam.okuma_id == 1 and tamam.hedef_surumu == 4
    assert tamam.sonraki_adim == mcp_araclari.SONRAKI_KAYITLI
    with baglam.veritabani.okuma_islemi() as oturum:
        assert hs.etkin_bakiye(oturum, nesne_id=hesap).bakiye_kurus == 1_250_00

    getir = _calistir(
        baglam,
        mcp_kapisi.ARAC_BELGE_GETIR,
        mcp_araclari.belge_getir,
        mcp_araclari.BelgeGetirGirdisi(belge_id=1),
    )
    assert getir.belge_kaydi is zarf.BelgeKaydiDurumu.KAYITLI and getir.okuma_id == 1
    assert getir.icerik is not None
    assert [o["durum"] for o in getir.icerik["okumalar"]] == ["TAMAMLANDI"]

    tekrar = _belge_al(baglam, ad="kopya.pdf", anahtar="al-2")
    assert tekrar.belge_id == 1 and tekrar.zaten_mevcut == 1
    assert tekrar.belge_kaydi is zarf.BelgeKaydiDurumu.KAYITLI
    assert tekrar.sonraki_adim == mcp_araclari.SONRAKI_KAYITLI


# --- paket kuralları (K07, K08) -------------------------------------------------------


@pytest.fixture
def acik_okuma(baglam: mcp_araclari.AracBaglami, hesap: int) -> int:
    _belge_al(baglam)
    sonuc = _okuma_baslat(baglam, 1)
    assert sonuc.okuma_id is not None
    return sonuc.okuma_id


def test_paketteki_tek_hata_hepsini_dusurur_konum_soyler(
    baglam: mcp_araclari.AracBaglami, hesap: int, acik_okuma: int
) -> None:
    sonuc = _hareket_yaz(
        baglam,
        acik_okuma,
        [_hareket(0, hesap), _hareket(1, hesap, tutar=12.5), _hareket(2, hesap)],
    )
    assert sonuc.durum is zarf.YanitDurumu.REDDEDILDI
    assert sonuc.hata is not None
    assert (sonuc.hata.kod, sonuc.hata.alan, sonuc.hata.konum) == (
        "TUTAR_GECERSIZ",
        "tutar_kurus",
        1,
    )
    assert "yuvarlama" in (sonuc.sonraki_adim or "")
    assert _sayi(baglam, sema.kayit) == 0 and _sayi(baglam, sema.okuma_satir) == 0
    assert _sayi(baglam, sema.islem_anahtari) == 3  # nesne, belge, okuma; paket düştü

    olmayan = _hareket_yaz(baglam, acik_okuma, [_hareket(0, 999)])
    assert olmayan.hata is not None
    assert (olmayan.hata.kod, olmayan.hata.konum) == ("HEDEF_BULUNAMADI", 0)


def test_ayni_paket_ikinci_kez_yazmaz(
    baglam: mcp_araclari.AracBaglami, hesap: int, acik_okuma: int
) -> None:
    hareketler = [_hareket(0, hesap), _hareket(1, hesap)]
    ilk = _hareket_yaz(baglam, acik_okuma, hareketler)
    tekrar = _hareket_yaz(baglam, acik_okuma, hareketler)

    assert (ilk.yazilan, ilk.zaten_mevcut) == (2, 0)
    assert (tekrar.yazilan, tekrar.zaten_mevcut) == (0, 2)
    assert _sayi(baglam, sema.kayit) == 2

    farkli = _hareket_yaz(baglam, acik_okuma, [_hareket(0, hesap, tutar=1)])
    assert farkli.hata is not None and farkli.hata.kod == "ANAHTAR_ICERIK_CAKISMASI"
    assert farkli.hata.konum == 0


def test_kapali_okumaya_paket_yazilmaz_ve_kayitli_belge_araci(
    baglam: mcp_araclari.AracBaglami, hesap: int, acik_okuma: int
) -> None:
    _hareket_yaz(baglam, acik_okuma, [_hareket(0, hesap)])
    assert _tamamla(baglam, acik_okuma).belge_kaydi is zarf.BelgeKaydiDurumu.KAYITLI

    sonuc = _hareket_yaz(baglam, acik_okuma, [_hareket(1, hesap)], anahtar="p-2")
    assert sonuc.durum is zarf.YanitDurumu.REDDEDILDI
    assert sonuc.hata is not None and sonuc.hata.kod == "GIRDI_GECERSIZ"

    kaydet = _calistir(
        baglam,
        mcp_kapisi.ARAC_BELGE_KAYDET,
        mcp_araclari.belge_kaydet,
        mcp_araclari.BelgeKaydetGirdisi(
            belge_id=1, gorulen_surum=4, islem_anahtari="bk"
        ),
    )
    assert kaydet.hata is not None and kaydet.hata.kod == "BELGE_HAZIR_DEGIL"


def test_belge_kaydet_hazir_belgeyi_kaydeder(
    baglam: mcp_araclari.AracBaglami, hesap: int, acik_okuma: int
) -> None:
    _hareket_yaz(baglam, acik_okuma, [_hareket(0, hesap)])
    with (
        baglam.veritabani.yazma_islemi() as oturum
    ):  # Aşama 7'de karar sonrası kalacak hâl
        oturum.execute(
            sema.okuma.update().values(durum=sz.OkumaDurumu.TAMAMLANDI.value)
        )
        oturum.execute(
            sema.belge.update().values(durum=sz.BelgeDurumu.HAZIR.value, surum=3)
        )

    eski = _calistir(
        baglam,
        mcp_kapisi.ARAC_BELGE_KAYDET,
        mcp_araclari.belge_kaydet,
        mcp_araclari.BelgeKaydetGirdisi(
            belge_id=1, gorulen_surum=2, islem_anahtari="bk-1"
        ),
    )
    assert eski.hata is not None and eski.hata.kod == "HEDEF_SURUMU_DEGISTI"

    sonuc = _calistir(
        baglam,
        mcp_kapisi.ARAC_BELGE_KAYDET,
        mcp_araclari.belge_kaydet,
        mcp_araclari.BelgeKaydetGirdisi(
            belge_id=1, gorulen_surum=3, islem_anahtari="bk-2"
        ),
    )
    assert sonuc.durum is zarf.YanitDurumu.TAMAMLANDI
    assert (
        sonuc.belge_kaydi is zarf.BelgeKaydiDurumu.KAYITLI and sonuc.hedef_surumu == 4
    )
    assert sonuc.okuma_id == acik_okuma


# --- belge_al kuralları ---------------------------------------------------------------


def test_belge_al_izinsiz_yol_ve_anahtarsiz(
    baglam: mcp_araclari.AracBaglami, tmp_path: Path
) -> None:
    disari = tmp_path / "sir.pdf"
    disari.write_bytes(EKSTRE)
    sonuc = _calistir(
        baglam,
        mcp_kapisi.ARAC_BELGE_AL,
        mcp_araclari.belge_al,
        mcp_araclari.BelgeAlGirdisi(yol=str(disari), islem_anahtari="al"),
    )
    assert sonuc.durum is zarf.YanitDurumu.REDDEDILDI
    assert sonuc.hata is not None and sonuc.hata.kod == "GIRDI_GECERSIZ"
    assert sonuc.hata.alan == "yol" and str(tmp_path) not in sonuc.model_dump_json()

    anahtarsiz = _calistir(
        baglam,
        mcp_kapisi.ARAC_BELGE_AL,
        mcp_araclari.belge_al,
        mcp_araclari.BelgeAlGirdisi(yol=str(disari)),
    )
    assert anahtarsiz.hata is not None and anahtarsiz.hata.alan == "islem_anahtari"
    assert _sayi(baglam, sema.belge) == 0


def test_okuma_baslat_arsiv_eksik_ve_belge_yok(
    baglam: mcp_araclari.AracBaglami,
) -> None:
    yok = _okuma_baslat(baglam, 42)
    assert yok.hata is not None and yok.hata.kod == "BELGE_YOK"
    assert "belge_al" in (yok.sonraki_adim or "")

    alinan = _belge_al(baglam)
    assert alinan.icerik is not None
    with baglam.veritabani.okuma_islemi() as oturum:
        goreli = belgeler.belge_getir(oturum, 1).dosya.goreli_yol
    (baglam.ayarlar.belge_dizini / goreli).unlink()
    eksik = _okuma_baslat(baglam, 1)
    assert eksik.hata is not None and eksik.hata.kod == "ARSIV_EKSIK"
    assert "yeniden al" in (eksik.sonraki_adim or "")


# --- sunucu üzerinden -----------------------------------------------------------------


def test_sunucu_uzerinden_belge_araclari(
    baglam: mcp_araclari.AracBaglami, hesap: int
) -> None:
    sunucu = mcp_kapisi.sunucu_kur(baglam.ayarlar, "0001", baglam.veritabani)
    assert {a.name for a in anyio.run(sunucu.list_tools)} == set(mcp_kapisi.YETENEKLER)
    semalar = {a.name: a.input_schema for a in anyio.run(sunucu.list_tools)}
    hareket = semalar[mcp_kapisi.ARAC_HAREKET_YAZ]["$defs"]["HesapHareketiGirdi"]
    assert hareket["properties"]["tutar_kurus"]["type"] == "integer"

    def cagir(ad: str, args: dict[str, Any]) -> dict[str, Any]:
        sonuc = anyio.run(sunucu.call_tool, ad, args)
        assert isinstance(sonuc, CallToolResult) and sonuc.is_error is False
        assert sonuc.structured_content is not None
        return sonuc.structured_content

    dosya = baglam.ayarlar.gelen_dizini / "e.pdf"
    dosya.write_bytes(EKSTRE)
    alinan = cagir(
        mcp_kapisi.ARAC_BELGE_AL, {"girdi": {"yol": str(dosya), "islem_anahtari": "al"}}
    )
    assert alinan["belge_id"] == 1 and alinan["belge_kaydi"] == "TANIMLANMADI"
    okuma = cagir(
        mcp_kapisi.ARAC_OKUMA_BASLAT,
        {
            "girdi": {
                "belge_id": 1,
                "islem_anahtari": "ob",
                "tamlik": {"beklenen_satir_sayisi": 1},
            }
        },
    )
    assert okuma["okuma_id"] == 1
    paket = cagir(
        mcp_kapisi.ARAC_HAREKET_YAZ,
        {
            "girdi": {
                "okuma_id": 1,
                "islem_anahtari": "p",
                "hareketler": [
                    {
                        "satir": {
                            "satir_anahtari": "s0",
                            "konum": 0,
                            "ham": {"m": "x"},
                        },
                        "hareket": {
                            "nesne_id": hesap,
                            "yon": "ARTTIR",
                            "tutar_kurus": 500,
                            "islem_tarihi": "2026-08-01",
                        },
                    }
                ],
            }
        },
    )
    assert paket["yazilan"] == 1 and paket["belge_kaydi"] == "TANIMLANMADI"
    tamam = cagir(
        mcp_kapisi.ARAC_OKUMA_TAMAMLA,
        {"girdi": {"okuma_id": 1, "islem_anahtari": "ot"}},
    )
    assert tamam["durum"] == "TAMAMLANDI" and tamam["belge_kaydi"] == "KAYITLI"
    with baglam.veritabani.okuma_islemi() as oturum:
        assert nesneler.aktif_nesneyi_getir(oturum, hesap).id == hesap
        assert hs.etkin_bakiye(oturum, nesne_id=hesap).bakiye_kurus == 500

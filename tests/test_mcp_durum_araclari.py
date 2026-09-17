"""Durum ve sorgu araçları (Teslim 5.2/3): islem_durumu, bekleyen_isler, sorgu."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp.types import CallToolResult

from defteriki import ayarlar as ay
from defteriki import gunluk, mcp_araclari, mcp_kapisi, onaylar, zarf
from defteriki import sozlesmeler as sz
from defteriki import veritabani as vt
from defteriki.baslangic import ortami_hazirla

EKSTRE = b"%PDF-1.7\n%sentetik ekstre 5.2/3\n"
Oz = mcp_araclari.OzellikGirdi


def _tamlik_girdi(satir: int | None) -> mcp_araclari.TamlikGirdi:
    """Satır sayısı DEGER (None → OKUNAMADI), diğer dört alan BELGEDE_YOK."""
    yok = mcp_araclari.TamlikAlaniGirdi(durum="BELGEDE_YOK")
    return mcp_araclari.TamlikGirdi(
        beklenen_satir_sayisi=(
            mcp_araclari.TamlikAlaniGirdi(durum="DEGER", deger=satir)
            if satir is not None
            else mcp_araclari.TamlikAlaniGirdi(durum="OKUNAMADI")
        ),
        acilis_bakiyesi_kurus=yok,
        kapanis_bakiyesi_kurus=yok,
        toplam_giris_kurus=yok,
        toplam_cikis_kurus=yok,
    )


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


def _calistir(
    baglam: mcp_araclari.AracBaglami, ad: str, govde: Any, girdi: Any
) -> zarf.Zarf:
    return mcp_kapisi.araci_calistir(ad, govde, baglam, girdi)


def _gonder(baglam: mcp_araclari.AracBaglami, ad: str, anahtar: str) -> zarf.Zarf:
    return mcp_araclari.nesne_tanimla(
        baglam,
        mcp_araclari.NesneTanimlaGirdisi(
            adim="GONDER",
            islem_anahtari=anahtar,
            ozellikler=[Oz(alan_adi="ad", deger=ad)],
        ),
        "k",
    )


def _karar(baglam: mcp_araclari.AracBaglami, talep_id: int, onaylandi: bool) -> None:
    with baglam.veritabani.yazma_islemi() as oturum:
        onaylar.karar_uygula(
            oturum,
            talep_id=talep_id,
            gorulen_hedef_surumu=1,
            karar=onaylar.Karar(onaylandi=onaylandi, gerekce="test"),
            simdi=sz.simdi_utc(),
        )


def _durum(baglam: mcp_araclari.AracBaglami, **alanlar: Any) -> zarf.Zarf:
    return _calistir(
        baglam,
        mcp_kapisi.ARAC_ISLEM_DURUMU,
        mcp_araclari.islem_durumu,
        mcp_araclari.IslemDurumuGirdisi(**alanlar),
    )


def _sorgu(baglam: mcp_araclari.AracBaglami, **alanlar: Any) -> zarf.Zarf:
    return _calistir(
        baglam,
        mcp_kapisi.ARAC_SORGU,
        mcp_araclari.sorgu,
        mcp_araclari.SorguGirdisi(**alanlar),
    )


# --- islem_durumu: talep --------------------------------------------------------------


def test_talep_durumu_bekliyor_onaylandi_reddedildi(
    baglam: mcp_araclari.AracBaglami,
) -> None:
    qnb = _gonder(baglam, "QNB", "n-1")
    ak = _gonder(baglam, "Akbank", "n-2")
    assert qnb.talep_id == 1 and ak.talep_id == 2

    bekliyor = _durum(baglam, talep_id=1)
    assert bekliyor.durum is zarf.YanitDurumu.BEKLIYOR and bekliyor.bekleyen == 1
    assert (bekliyor.talep_id, bekliyor.nesne_id, bekliyor.hedef_surumu) == (1, 1, 1)
    assert bekliyor.icerik is not None
    assert bekliyor.icerik["talep"]["durum"] == "BEKLIYOR"
    assert bekliyor.icerik["hedef"]["ozellikler"][0]["deger"] == "QNB"
    assert bekliyor.sonraki_adim == mcp_araclari.SONRAKI_ONAY_BEKLE

    _karar(baglam, 1, True)
    _karar(baglam, 2, False)

    onaylandi = _durum(baglam, talep_id=1)
    assert (
        onaylandi.durum is zarf.YanitDurumu.TAMAMLANDI and onaylandi.hedef_surumu == 2
    )
    assert onaylandi.icerik is not None
    assert onaylandi.icerik["hedef"]["durum"] == "AKTIF"
    assert onaylandi.icerik["talep"]["karar"]["onaylandi"] is True
    assert onaylandi.sonraki_adim == "Nesne aktif; kimliğini kullan."

    reddedildi = _durum(baglam, talep_id=2)
    assert reddedildi.durum is zarf.YanitDurumu.REDDEDILDI and reddedildi.hata is None
    assert reddedildi.icerik is not None
    assert reddedildi.icerik["hedef"]["durum"] == "SILINDI"
    assert "kullanma" in (reddedildi.sonraki_adim or "")

    yok = _durum(baglam, talep_id=9)
    assert yok.hata is not None and yok.hata.kod == "HEDEF_BULUNAMADI"


# --- islem_durumu: anahtar ------------------------------------------------------------


def test_anahtar_durumu_sakli_sonuc_ve_kullanilmamis(
    baglam: mcp_araclari.AracBaglami,
) -> None:
    _gonder(baglam, "QNB", "n-1")

    var = _durum(baglam, arac_adi="nesne_tanimla", islem_anahtari="n-1")
    assert var.durum is zarf.YanitDurumu.TAMAMLANDI
    assert var.icerik is not None
    (kayit,) = var.icerik["kayitlar"]
    assert kayit["anahtar"] == "n-1" and kayit["sonuc"]["nesne_id"] == 1
    assert "yeniden gönderme" in (var.sonraki_adim or "")

    yok = _durum(baglam, arac_adi="nesne_tanimla", islem_anahtari="n-99")
    assert yok.durum is zarf.YanitDurumu.TAMAMLANDI
    assert yok.icerik == {"kayitlar": []}
    assert "hiç kullanılmamış" in (yok.sonraki_adim or "")

    baska_arac = _durum(baglam, arac_adi="belge_al", islem_anahtari="n-1")
    assert baska_arac.icerik == {"kayitlar": []}


def test_paket_anahtari_satir_kayitlariyla_doner(
    baglam: mcp_araclari.AracBaglami,
) -> None:
    sonuc = _gonder(baglam, "ME", "n-me")
    assert sonuc.talep_id is not None and sonuc.nesne_id is not None
    _karar(baglam, sonuc.talep_id, True)
    hesap = sonuc.nesne_id
    dosya = baglam.ayarlar.gelen_dizini / "e.pdf"
    dosya.write_bytes(EKSTRE)
    mcp_araclari.belge_al(
        baglam, mcp_araclari.BelgeAlGirdisi(yol=str(dosya), islem_anahtari="al"), "k"
    )
    mcp_araclari.okuma_baslat(
        baglam,
        mcp_araclari.OkumaBaslatGirdisi(
            belge_id=1, islem_anahtari="ob", tamlik=_tamlik_girdi(None)
        ),
        "k",
    )
    mcp_araclari.hareket_yaz(
        baglam,
        mcp_araclari.HareketYazGirdisi(
            okuma_id=1,
            islem_anahtari="paket-1",
            hareketler=[
                mcp_araclari.HareketGirdi(
                    satir=mcp_araclari.SatirGirdi(
                        satir_anahtari=f"s{n}", konum=n, ham={"n": n}
                    ),
                    hareket=mcp_araclari.HesapHareketiGirdi(
                        nesne_id=hesap,
                        yon=sz.Yon.ARTTIR,
                        tutar_kurus=100,
                        islem_tarihi="2026-08-01",
                    ),
                )
                for n in range(2)
            ],
        ),
        "k",
    )

    durum = _durum(baglam, arac_adi="hareket_yaz", islem_anahtari="paket-1")
    assert durum.icerik is not None
    assert [k["anahtar"] for k in durum.icerik["kayitlar"]] == [
        "paket-1#0",
        "paket-1#1",
    ]
    assert [k["sonuc"]["kayit_id"] for k in durum.icerik["kayitlar"]] == [1, 2]
    assert _durum(baglam, arac_adi="hareket_yaz", islem_anahtari="paket-1#").icerik == {
        "kayitlar": []
    }


def test_islem_durumu_girdi_kurali(baglam: mcp_araclari.AracBaglami) -> None:
    for alanlar in (
        {},
        {"talep_id": 1, "islem_anahtari": "x"},
        {"islem_anahtari": "x"},
    ):
        sonuc = _durum(baglam, **alanlar)
        assert sonuc.durum is zarf.YanitDurumu.REDDEDILDI
        assert sonuc.hata is not None and sonuc.hata.kod == "GIRDI_GECERSIZ"


# --- bekleyen_isler -------------------------------------------------------------------


def test_bekleyen_isler_hedefleriyle_ve_sayfali(
    baglam: mcp_araclari.AracBaglami,
) -> None:
    bos = _calistir(
        baglam,
        mcp_kapisi.ARAC_BEKLEYEN_ISLER,
        mcp_araclari.bekleyen_isler,
        mcp_araclari.BekleyenIslerGirdisi(),
    )
    assert bos.bekleyen == 0 and bos.sonraki_adim == "Bekleyen iş yok."

    for i, ad in enumerate(("QNB", "Akbank", "Garanti")):
        _gonder(baglam, ad, f"n-{i}")
    _karar(baglam, 2, True)

    sonuc = _calistir(
        baglam,
        mcp_kapisi.ARAC_BEKLEYEN_ISLER,
        mcp_araclari.bekleyen_isler,
        mcp_araclari.BekleyenIslerGirdisi(),
    )
    assert sonuc.bekleyen == 2
    assert sonuc.icerik is not None
    assert [t["hedef"]["ozellikler"][0]["deger"] for t in sonuc.icerik["talepler"]] == [
        "QNB",
        "Garanti",
    ]
    assert "onay üretme" in (sonuc.sonraki_adim or "")

    sayfa = _calistir(
        baglam,
        mcp_kapisi.ARAC_BEKLEYEN_ISLER,
        mcp_araclari.bekleyen_isler,
        mcp_araclari.BekleyenIslerGirdisi(sayfa_siniri=1, sayfa_baslangici=1),
    )
    assert sayfa.icerik is not None
    assert [t["id"] for t in sayfa.icerik["talepler"]] == [3]
    assert sayfa.icerik["sayfa"] == {"sinir": 1, "baslangic": 1, "donen": 1}


# --- sorgu ----------------------------------------------------------------------


@pytest.fixture
def kayitli_hesap(baglam: mcp_araclari.AracBaglami) -> int:
    """ME hesabı; ağustos belgesi KAYITLI (+2000, -600), eylül belgesi yazılmış ama
    kayıtsız (-150)."""
    sonuc = _gonder(baglam, "ME", "n-me")
    assert sonuc.talep_id is not None and sonuc.nesne_id is not None
    _karar(baglam, sonuc.talep_id, True)
    hesap = sonuc.nesne_id
    for ay_adi, hareketler, tamamla in (
        (
            "agustos",
            [("ARTTIR", 2_000_00, "2026-08-01"), ("AZALT", 600_00, "2026-08-05")],
            True,
        ),
        ("eylul", [("AZALT", 150_00, "2026-09-03")], False),
    ):
        dosya = baglam.ayarlar.gelen_dizini / f"{ay_adi}.pdf"
        dosya.write_bytes(EKSTRE + ay_adi.encode())
        belge = mcp_araclari.belge_al(
            baglam,
            mcp_araclari.BelgeAlGirdisi(yol=str(dosya), islem_anahtari=f"al-{ay_adi}"),
            "k",
        )
        assert belge.belge_id is not None
        okuma = mcp_araclari.okuma_baslat(
            baglam,
            mcp_araclari.OkumaBaslatGirdisi(
                belge_id=belge.belge_id,
                islem_anahtari=f"ob-{ay_adi}",
                tamlik=_tamlik_girdi(len(hareketler)),
            ),
            "k",
        )
        assert okuma.okuma_id is not None
        mcp_araclari.hareket_yaz(
            baglam,
            mcp_araclari.HareketYazGirdisi(
                okuma_id=okuma.okuma_id,
                islem_anahtari=f"p-{ay_adi}",
                hareketler=[
                    mcp_araclari.HareketGirdi(
                        satir=mcp_araclari.SatirGirdi(
                            satir_anahtari=f"s{n}", konum=n, ham={"n": n}
                        ),
                        hareket=mcp_araclari.HesapHareketiGirdi(
                            nesne_id=hesap,
                            yon=sz.Yon(yon),
                            tutar_kurus=tutar,
                            islem_tarihi=tarih,
                        ),
                    )
                    for n, (yon, tutar, tarih) in enumerate(hareketler)
                ],
            ),
            "k",
        )
        if tamamla:
            mcp_araclari.okuma_tamamla(
                baglam,
                mcp_araclari.OkumaTamamlaGirdisi(
                    okuma_id=okuma.okuma_id, islem_anahtari=f"ot-{ay_adi}"
                ),
                "k",
            )
    return hesap


def test_sorgu_bakiye_yalniz_kayitli_belgeler(
    baglam: mcp_araclari.AracBaglami, kayitli_hesap: int
) -> None:
    sonuc = _sorgu(baglam, rapor="bakiye", nesne_id=kayitli_hesap)
    assert (
        sonuc.durum is zarf.YanitDurumu.TAMAMLANDI and sonuc.nesne_id == kayitli_hesap
    )
    assert sonuc.icerik == {
        "bakiye": {
            "nesne_id": kayitli_hesap,
            "eksen": "VARLIK",
            "para_birimi": "TRY",
            "tarih": None,
            "arttir_kurus": 2_000_00,
            "azalt_kurus": 600_00,
            "bakiye_kurus": 1_400_00,
            "bekleyen_kayit_sayisi": 1,
        }
    }
    assert sonuc.bekleyen == 1 and "bekleyen kayıtlar toplamda yok" in (
        sonuc.sonraki_adim or ""
    )

    tarihli = _sorgu(baglam, rapor="bakiye", nesne_id=kayitli_hesap, tarih="2026-08-01")
    assert tarihli.icerik is not None
    assert tarihli.icerik["bakiye"]["bakiye_kurus"] == 2_000_00
    assert tarihli.icerik["bakiye"]["tarih"] == "2026-08-01"

    borc = _sorgu(baglam, rapor="bakiye", nesne_id=kayitli_hesap, eksen=sz.Eksen.BORC)
    assert borc.icerik is not None and borc.icerik["bakiye"]["bakiye_kurus"] == 0


def test_sorgu_hareketler_kayitli_bayragi_filtre_sayfa(
    baglam: mcp_araclari.AracBaglami, kayitli_hesap: int
) -> None:
    sonuc = _sorgu(baglam, rapor="hareketler", nesne_id=kayitli_hesap)
    assert sonuc.icerik is not None
    assert [
        (h["islem_tarihi"], h["yon"], h["tutar_kurus"], h["kayitli"])
        for h in sonuc.icerik["hareketler"]
    ] == [
        ("2026-08-01", "ARTTIR", 2_000_00, True),
        ("2026-08-05", "AZALT", 600_00, True),
        ("2026-09-03", "AZALT", 150_00, False),
    ]
    assert sonuc.bekleyen == 1

    eylul = _sorgu(
        baglam, rapor="hareketler", nesne_id=kayitli_hesap, baslangic="2026-09-01"
    )
    assert eylul.icerik is not None
    assert [h["kayit_id"] for h in eylul.icerik["hareketler"]] == [3]

    sayfa = _sorgu(
        baglam,
        rapor="hareketler",
        nesne_id=kayitli_hesap,
        sayfa_siniri=1,
        sayfa_baslangici=1,
    )
    assert sayfa.icerik is not None
    assert [h["kayit_id"] for h in sayfa.icerik["hareketler"]] == [2]
    assert sayfa.icerik["sayfa"] == {"sinir": 1, "baslangic": 1, "donen": 1}


def test_sorgu_hatalari(baglam: mcp_araclari.AracBaglami, kayitli_hesap: int) -> None:
    yok = _sorgu(baglam, rapor="bakiye", nesne_id=99)
    assert yok.hata is not None and yok.hata.kod == "HEDEF_BULUNAMADI"
    tarih = _sorgu(baglam, rapor="bakiye", nesne_id=kayitli_hesap, tarih="01.08.2026")
    assert tarih.hata is not None and tarih.hata.alan == "tarih"
    sayfa = _sorgu(baglam, rapor="hareketler", nesne_id=kayitli_hesap, sayfa_siniri=0)
    assert sayfa.hata is not None and sayfa.hata.kod == "GIRDI_GECERSIZ"


# --- sunucu üzerinden -----------------------------------------------------------------


def test_sunucu_uzerinden_durum_araclari(
    baglam: mcp_araclari.AracBaglami, kayitli_hesap: int
) -> None:
    sunucu = mcp_kapisi.sunucu_kur(baglam.ayarlar, "0001", baglam.veritabani)
    assert {a.name for a in anyio.run(sunucu.list_tools)} == set(mcp_kapisi.YETENEKLER)
    assert len(mcp_kapisi.YETENEKLER) == 14

    def cagir(ad: str, args: dict[str, Any]) -> dict[str, Any]:
        sonuc = anyio.run(sunucu.call_tool, ad, args)
        assert isinstance(sonuc, CallToolResult) and sonuc.is_error is False
        assert sonuc.structured_content is not None
        return sonuc.structured_content

    bakiye = cagir(
        mcp_kapisi.ARAC_SORGU, {"girdi": {"rapor": "bakiye", "nesne_id": kayitli_hesap}}
    )
    assert bakiye["icerik"]["bakiye"]["bakiye_kurus"] == 1_400_00
    serbest = cagir(
        mcp_kapisi.ARAC_SORGU,
        {"girdi": {"rapor": "SELECT * FROM kayit", "nesne_id": 1}},
    )
    assert serbest["hata"]["kod"] == "GIRDI_GECERSIZ" and "SELECT" not in str(serbest)
    bekleyen = cagir(mcp_kapisi.ARAC_BEKLEYEN_ISLER, {})
    assert bekleyen["durum"] == "TAMAMLANDI" and bekleyen["bekleyen"] == 0
    durum = cagir(mcp_kapisi.ARAC_ISLEM_DURUMU, {"girdi": {"talep_id": 1}})
    assert (
        durum["durum"] == "TAMAMLANDI" and durum["icerik"]["hedef"]["durum"] == "AKTIF"
    )

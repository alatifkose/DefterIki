"""Bakiye ve hareket görünümü testleri (Teslim 6.3) ve 6.3 pencere işlevleri.

Ekstre MCP araçlarıyla (Cowork gibi) işlenir: bir belge KAYITLI, ikinci belge
OKUNUYOR (hareketi yazılmış, kayıtlı değil). Pencere ile ``sorgu`` aracı aynı
sayıyı göstermeli.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from pytestqt.qtbot import QtBot

from defteriki import ayarlar as ay
from defteriki import gunluk, mcp_araclari, mcp_kapisi, onaylar, pencere_islevleri
from defteriki import sozlesmeler as sz
from defteriki import veritabani as vt
from defteriki.arayuz import ana_pencere, hareketler
from defteriki.baslangic import Hazirlik, ortami_hazirla

DEGISKENLER = (
    ay.ORTAM_DEGISKENI,
    ay.VERI_KOKU_DEGISKENI,
    ay.VERITABANI_YOLU_DEGISKENI,
    ay.BELGE_DIZINI_DEGISKENI,
    ay.LOG_DIZINI_DEGISKENI,
    ay.GELEN_DIZINI_DEGISKENI,
)
EKSTRE_1 = b"%PDF-1.7\n%ekstre bir\n"
EKSTRE_2 = b"%PDF-1.7\n%ekstre iki\n"
YOKLAMA_MS = 20
BEKLEME_MS = 3000
Oz = mcp_araclari.OzellikGirdi


@pytest.fixture
def hazirlik(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Hazirlik]:
    for degisken in DEGISKENLER:
        monkeypatch.delenv(degisken, raising=False)
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(tmp_path / "kok"))
    gunluk.gunlugu_kapat()
    yield ortami_hazirla()
    gunluk.gunlugu_kapat()


@pytest.fixture
def baglam(hazirlik: Hazirlik) -> Iterator[mcp_araclari.AracBaglami]:
    db = vt.veritabani_ac(hazirlik.ayarlar)
    yield mcp_araclari.AracBaglami(db, hazirlik.ayarlar)
    db.kapat()


@pytest.fixture
def islevler(hazirlik: Hazirlik) -> Iterator[pencere_islevleri.PencereIslevleri]:
    i = pencere_islevleri.pencere_islevleri_ac(hazirlik.ayarlar)
    yield i
    i.kapat()


def _arac(baglam: mcp_araclari.AracBaglami, ad: str, govde: Any, girdi: Any) -> Any:
    return mcp_kapisi.araci_calistir(ad, govde, baglam, girdi)


def _aktif_hesap(baglam: mcp_araclari.AracBaglami, ad: str, anahtar: str) -> int:
    sonuc = mcp_araclari.nesne_tanimla(
        baglam,
        mcp_araclari.NesneTanimlaGirdisi(
            adim="GONDER",
            islem_anahtari=anahtar,
            ozellikler=[Oz(alan_adi="ad", deger=ad), Oz(alan_adi="tür", deger="hesap")],
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


def _hareket(n: int, hesap: int, yon: str, tutar: int, gun: int) -> Any:
    return mcp_araclari.HareketGirdi(
        satir=mcp_araclari.SatirGirdi(
            satir_anahtari=f"s{n}", konum=n, ham={"metin": f"hareket {n}"}
        ),
        hareket=mcp_araclari.HesapHareketiGirdi(
            nesne_id=hesap,
            yon=sz.Yon(yon),
            tutar_kurus=tutar,
            islem_tarihi=f"2026-02-{gun:02d}",
            aciklama=f"açıklama {n}",
        ),
    )


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


def _belge_isle(
    baglam: mcp_araclari.AracBaglami,
    ad: str,
    icerik: bytes,
    hareketler_: list[Any],
    *,
    tamamla: bool,
    anahtar: str,
) -> int:
    """belge_al → okuma_baslat → hareket_yaz → (okuma_tamamla). Belge kimliği."""
    dosya = baglam.ayarlar.gelen_dizini / ad
    dosya.write_bytes(icerik)
    alinan = _arac(
        baglam,
        mcp_kapisi.ARAC_BELGE_AL,
        mcp_araclari.belge_al,
        mcp_araclari.BelgeAlGirdisi(yol=str(dosya), islem_anahtari=f"al-{anahtar}"),
    )
    okuma = _arac(
        baglam,
        mcp_kapisi.ARAC_OKUMA_BASLAT,
        mcp_araclari.okuma_baslat,
        mcp_araclari.OkumaBaslatGirdisi(
            belge_id=alinan.belge_id,
            islem_anahtari=f"ob-{anahtar}",
            tamlik=_tamlik_girdi(len(hareketler_)),
        ),
    )
    paket = _arac(
        baglam,
        mcp_kapisi.ARAC_HAREKET_YAZ,
        mcp_araclari.hareket_yaz,
        mcp_araclari.HareketYazGirdisi(
            okuma_id=okuma.okuma_id,
            islem_anahtari=f"p-{anahtar}",
            hareketler=hareketler_,
        ),
    )
    assert paket.durum is mcp_araclari.zarf.YanitDurumu.TAMAMLANDI
    if tamamla:
        tamam = _arac(
            baglam,
            mcp_kapisi.ARAC_OKUMA_TAMAMLA,
            mcp_araclari.okuma_tamamla,
            mcp_araclari.OkumaTamamlaGirdisi(
                okuma_id=okuma.okuma_id, islem_anahtari=f"ot-{anahtar}"
            ),
        )
        assert tamam.belge_kaydi is mcp_araclari.zarf.BelgeKaydiDurumu.KAYITLI
    return int(alinan.belge_id)


@pytest.fixture
def ekstreler(baglam: mcp_araclari.AracBaglami) -> tuple[int, int, int]:
    """(hesap, kayıtlı belge, kayıtlı olmayan belge): 2.000 giriş, 600 çıkış
    kayıtlı; 150 çıkış yazılmış ama belgesi OKUNUYOR."""
    hesap = _aktif_hesap(baglam, "ME", "n-me")
    b1 = _belge_isle(
        baglam,
        "subat.pdf",
        EKSTRE_1,
        [
            _hareket(0, hesap, "ARTTIR", 2_000_00, 1),
            _hareket(1, hesap, "AZALT", 600_00, 5),
        ],
        tamamla=True,
        anahtar="1",
    )
    b2 = _belge_isle(
        baglam,
        "mart.pdf",
        EKSTRE_2,
        [_hareket(0, hesap, "AZALT", 150_00, 9)],
        tamamla=False,
        anahtar="2",
    )
    return hesap, b1, b2


def _sorgu_bakiye(baglam: mcp_araclari.AracBaglami, nesne_id: int) -> dict[str, Any]:
    z = _arac(
        baglam,
        mcp_kapisi.ARAC_SORGU,
        mcp_araclari.sorgu,
        mcp_araclari.SorguGirdisi(rapor="bakiye", nesne_id=nesne_id),
    )
    assert z.icerik is not None
    return dict(z.icerik["bakiye"])


# --- pencere işlevleri (6.3) ---------------------------------------------------------


def test_tutar_metni() -> None:
    assert pencere_islevleri.tutar_metni(0) == "0,00 TL"
    assert pencere_islevleri.tutar_metni(125000) == "1.250,00 TL"
    assert pencere_islevleri.tutar_metni(-2635) == "-26,35 TL"
    assert pencere_islevleri.tutar_metni(123456789) == "1.234.567,89 TL"
    assert pencere_islevleri.tutar_metni(5, "USD") == "0,05 USD"


def test_hesaplar_yalniz_aktif_nesneler(
    islevler: pencere_islevleri.PencereIslevleri, baglam: mcp_araclari.AracBaglami
) -> None:
    assert islevler.hesaplar() == []
    hesap = _aktif_hesap(baglam, "ME", "n-me")
    mcp_araclari.nesne_tanimla(  # onay bekleyen; listeye girmez
        baglam,
        mcp_araclari.NesneTanimlaGirdisi(
            adim="GONDER",
            islem_anahtari="n-gk",
            ozellikler=[Oz(alan_adi="ad", deger="GK")],
        ),
        "k",
    )
    assert islevler.hesaplar() == [
        pencere_islevleri.HesapSecenegi(hesap, 0, "ad=ME; tür=hesap")
    ]


def test_bakiye_ve_hareketler_sorgu_araciyla_ayni(
    islevler: pencere_islevleri.PencereIslevleri,
    baglam: mcp_araclari.AracBaglami,
    ekstreler: tuple[int, int, int],
) -> None:
    hesap, b1, b2 = ekstreler
    b = islevler.bakiye(hesap)
    sorgu = _sorgu_bakiye(baglam, hesap)

    assert (b.bakiye_kurus, b.arttir_kurus, b.azalt_kurus) == (
        1_400_00,
        2_000_00,
        600_00,
    )
    assert b.bekleyen_kayit_sayisi == 1
    assert (b.bakiye_kurus, b.bekleyen_kayit_sayisi) == (
        sorgu["bakiye_kurus"],
        sorgu["bekleyen_kayit_sayisi"],
    )

    h = islevler.hareketler(hesap)
    assert [
        (x.islem_tarihi.day, x.yon, x.tutar_kurus, x.kayitli, x.belge_idleri) for x in h
    ] == [
        (1, "ARTTIR", 2_000_00, True, (b1,)),
        (5, "AZALT", 600_00, True, (b1,)),
        (9, "AZALT", 150_00, False, (b2,)),
    ]
    assert h[0].aciklama == "açıklama 0"


def test_belgeler_yeniden_eskiye_durumuyla(
    islevler: pencere_islevleri.PencereIslevleri, ekstreler: tuple[int, int, int]
) -> None:
    _hesap, b1, b2 = ekstreler
    liste = islevler.belgeler()
    assert [(b.belge_id, b.durum, b.kaynak_adi) for b in liste] == [
        (b2, "OKUNUYOR", "mart.pdf"),
        (b1, "KAYITLI", "subat.pdf"),
    ]
    assert liste[1].boyut == len(EKSTRE_1) and liste[1].mime == "application/pdf"
    assert liste[0].olusturma_zamani.tzinfo is not None


def test_belge_dosya_yolu_ve_arsiv_eksik(
    islevler: pencere_islevleri.PencereIslevleri, ekstreler: tuple[int, int, int]
) -> None:
    _hesap, b1, _b2 = ekstreler
    yol = islevler.belge_dosya_yolu(b1)
    assert yol.is_file() and yol.read_bytes() == EKSTRE_1

    yol.unlink()
    with pytest.raises(sz.ArsivEksik):
        islevler.belge_dosya_yolu(b1)
    with pytest.raises(sz.BelgeYok):
        islevler.belge_dosya_yolu(99)


# --- görünüm -------------------------------------------------------------------------


@pytest.fixture
def acilanlar() -> list[Path]:
    return []


@pytest.fixture
def gorunum(
    hazirlik: Hazirlik, qtbot: QtBot, acilanlar: list[Path]
) -> Iterator[hareketler.HareketGorunumu]:
    islevler = pencere_islevleri.pencere_islevleri_ac(hazirlik.ayarlar)
    g = hareketler.HareketGorunumu(islevler, dosya_acici=acilanlar.append)
    qtbot.addWidget(g)
    g.show()
    yield g
    g.close()
    islevler.kapat()


def _hucre(tablo: Any, satir: int, sutun: int) -> str:
    oge = tablo.item(satir, sutun)
    assert oge is not None
    return str(oge.text())


def test_bos_defterde_hesap_yok_mesaji(gorunum: hareketler.HareketGorunumu) -> None:
    assert gorunum.hesap_secimi.count() == 0
    assert gorunum.bakiye_etiketi.text() == hareketler.METIN_HESAP_YOK
    assert gorunum.hareket_tablosu.rowCount() == 0
    assert gorunum.belge_tablosu.rowCount() == 0
    assert not gorunum.belge_ac_dugmesi.isEnabled()


def test_bakiye_hareketler_ve_belgeler_gosterilir(
    gorunum: hareketler.HareketGorunumu,
    baglam: mcp_araclari.AracBaglami,
    ekstreler: tuple[int, int, int],
) -> None:
    hesap, b1, b2 = ekstreler
    gorunum.yenile()

    assert gorunum.hesap_secimi.count() == 1 and gorunum.secili_nesne_id == hesap
    sorgu = _sorgu_bakiye(baglam, hesap)
    assert gorunum.bakiye_etiketi.text() == (
        f"Bakiye: {pencere_islevleri.tutar_metni(sorgu['bakiye_kurus'])} · "
        "giriş 2.000,00 TL · çıkış 600,00 TL · kayıtlı olmayan kayıt: 1"
    )

    t = gorunum.hareket_tablosu
    assert t.rowCount() == 3
    assert [_hucre(t, s, 0) for s in range(3)] == [
        "01.02.2026",
        "05.02.2026",
        "09.02.2026",
    ]
    assert [_hucre(t, s, 2) for s in range(3)] == ["giriş", "çıkış", "çıkış"]
    assert [_hucre(t, s, 3) for s in range(3)] == [
        "2.000,00 TL",
        "600,00 TL",
        "150,00 TL",
    ]
    assert [_hucre(t, s, 4) for s in range(3)] == [
        hareketler.METIN_KAYITLI,
        hareketler.METIN_KAYITLI,
        hareketler.METIN_KAYITLI_DEGIL,
    ]
    assert [_hucre(t, s, 5) for s in range(3)] == [str(b1), str(b1), str(b2)]

    bt = gorunum.belge_tablosu
    assert [
        (_hucre(bt, s, 0), _hucre(bt, s, 1), _hucre(bt, s, 2)) for s in range(2)
    ] == [
        (str(b2), "mart.pdf", "OKUNUYOR"),
        (str(b1), "subat.pdf", "KAYITLI"),
    ]
    assert gorunum.belge_ac_dugmesi.isEnabled()


def test_belgeyi_ac_isletim_sistemine_yolu_verir(
    gorunum: hareketler.HareketGorunumu,
    ekstreler: tuple[int, int, int],
    acilanlar: list[Path],
    qtbot: QtBot,
) -> None:
    _hesap, b1, _b2 = ekstreler
    gorunum.yenile()
    gorunum.belge_tablosu.setCurrentCell(1, 0)  # subat.pdf (b1)

    with qtbot.waitSignal(gorunum.belge_acildi, timeout=BEKLEME_MS):
        gorunum.belge_ac_dugmesi.click()

    assert len(acilanlar) == 1 and acilanlar[0].read_bytes() == EKSTRE_1
    assert gorunum.mesaj_etiketi.text().startswith(f"Belge {b1} açıldı: ")


def test_belge_secilmeden_ac_ve_arsiv_eksik(
    gorunum: hareketler.HareketGorunumu,
    islevler: pencere_islevleri.PencereIslevleri,
    ekstreler: tuple[int, int, int],
    acilanlar: list[Path],
) -> None:
    _hesap, b1, _b2 = ekstreler
    gorunum.yenile()
    gorunum.belge_tablosu.setCurrentCell(-1, 0)
    gorunum.belgeyi_ac()
    assert gorunum.mesaj_etiketi.text() == "Önce listeden bir belge seç."

    islevler.belge_dosya_yolu(b1).unlink()
    gorunum.belge_tablosu.setCurrentCell(1, 0)
    gorunum.belgeyi_ac()
    assert (
        gorunum.mesaj_etiketi.text() == "Belge açılamadı: belgenin dosyası arşivde yok"
    )
    assert acilanlar == []


def test_yenileme_secili_hesabi_korur(
    gorunum: hareketler.HareketGorunumu,
    baglam: mcp_araclari.AracBaglami,
    ekstreler: tuple[int, int, int],
) -> None:
    hesap, _b1, _b2 = ekstreler
    gorunum.yenile()
    _aktif_hesap(baglam, "GK", "n-gk")  # yeni hesap, kimliği daha büyük
    gorunum.yenile()
    assert gorunum.hesap_secimi.count() == 2
    assert gorunum.secili_nesne_id == hesap


# --- pencereyle bütünleşme ----------------------------------------------------------


def test_pencere_ikinci_sekme_degisiklikte_yenilenir_ve_720ye_sigar(
    hazirlik: Hazirlik, baglam: mcp_araclari.AracBaglami, qtbot: QtBot
) -> None:
    islevler = pencere_islevleri.pencere_islevleri_ac(hazirlik.ayarlar)
    pencere = ana_pencere.AnaPencere(hazirlik, islevler, yoklama_araligi_ms=YOKLAMA_MS)
    qtbot.addWidget(pencere)
    pencere.show()
    try:
        assert pencere.sekmeler.tabText(1) == ana_pencere.SEKME_HAREKETLER
        assert pencere.hareketler.hesap_secimi.count() == 0
        ipucu = pencere.minimumSizeHint()
        assert ipucu.width() <= ana_pencere.PENCERE_GENISLIK
        assert ipucu.height() <= ana_pencere.PENCERE_YUKSEKLIK

        with qtbot.waitSignal(pencere.hareketler.yenilendi, timeout=BEKLEME_MS):
            _aktif_hesap(baglam, "ME", "n-me")

        assert pencere.hareketler.hesap_secimi.count() == 1
        assert pencere.hareketler.bakiye_etiketi.text().startswith("Bakiye: 0,00 TL")
    finally:
        pencere.close()
        islevler.kapat()

"""Nesne tanıtma, seviye kuralları, şart seçimi, bulma (Teslim 4.4).

Abdüllatif'in akışı: Garanti BBVA'dan ME adına ekstre geldi → banka ve yalnız ME hesabı
açılır; ertesi gün GK ekstresi → banka zaten var, yalnız GK hesabı eklenir. Hiçbir nesne
belgesiz ya da toplu açılmaz.
"""

from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import func, select

from defteriki import nesneler as ns
from defteriki import onaylar as on
from defteriki import sema
from defteriki import sozlesmeler as sz
from defteriki import veritabani as vt

SIMDI = datetime(2026, 9, 17, 9, 0)
COWORK = sz.DenetimAktoru.COWORK
Oz = ns.OzellikGirdisi


@pytest.fixture
def db(tmp_path: Path) -> Iterator[vt.Veritabani]:
    yol = tmp_path / "vt" / "nesne.sqlite3"
    yol.parent.mkdir()
    veritabani = vt.Veritabani(yol, mesgul_bekleme_ms=200)
    sema.semayi_yukselt(veritabani)
    yield veritabani
    veritabani.kapat()


def _tanimla(
    db: vt.Veritabani,
    ozellikler: list[ns.OzellikGirdisi],
    *,
    anahtar: str,
    ustler: tuple[int, ...] = (),
    kaynak: ns.NesneKaynagi | None = None,
) -> ns.NesneTanimlamaSonucu:
    with db.yazma_islemi() as oturum:
        return ns.nesne_tanimla(
            oturum,
            ozellikler=ozellikler,
            islem_anahtari=anahtar,
            aktor=COWORK,
            ust_idleri=ustler,
            kaynak=kaynak,
            simdi=SIMDI,
        )


def _onayla(
    db: vt.Veritabani, sonuc: ns.NesneTanimlamaSonucu, *, sartlar: tuple[int, ...] = ()
) -> on.OnayTalebi:
    with db.yazma_islemi() as oturum:
        return on.karar_uygula(
            oturum,
            talep_id=sonuc.onay_talebi.id,
            gorulen_hedef_surumu=sonuc.nesne.surum,
            karar=on.Karar(onaylandi=True, secilen_sartlar=sartlar),
            simdi=SIMDI,
        )


def _ozellik_id(db: vt.Veritabani, nesne_id: int, alan_adi: str) -> int:
    with db.okuma_islemi() as oturum:
        ayrinti = ns.nesne_getir(oturum, nesne_id)
    return next(o.id for o in ayrinti.ozellikler if o.alan_adi == alan_adi)


def _sayi(db: vt.Veritabani, tablo: sema.Table) -> int:
    with db.okuma_islemi() as oturum:
        return int(oturum.execute(select(func.count()).select_from(tablo)).scalar_one())


# --- Abdüllatif'in akışı ------------------------------------------------------


def test_garanti_akisi_banka_ve_hesaplar_tek_tek_acilir(db: vt.Veritabani) -> None:
    # 1. gün: Garanti ME ekstresi. Garanti yok → banka önerilir, altına yalnız ME.
    with db.okuma_islemi() as oturum:
        assert ns.nesne_bul(oturum, alan_adi="ad", deger="Garanti BBVA") == []
    banka = _tanimla(
        db, [Oz("ad", "Garanti BBVA"), Oz("tür", "banka")], anahtar="g-banka"
    )
    me = _tanimla(
        db,
        [Oz("ad", "ME"), Oz("tür", "hesap"), Oz("iban", "TR000000000000000000000001")],
        anahtar="g-me",
        ustler=(banka.nesne.id,),
    )
    assert banka.nesne.durum is sz.NesneDurumu.ONAY_BEKLIYOR
    assert me.nesne.durum is sz.NesneDurumu.ONAY_BEKLIYOR
    assert me.nesne.seviye == banka.nesne.seviye + 1 == 1
    _onayla(db, banka, sartlar=(_ozellik_id(db, banka.nesne.id, "ad"),))
    _onayla(db, me, sartlar=(_ozellik_id(db, me.nesne.id, "iban"),))

    # 2. gün: Garanti GK ekstresi. Cowork önce arar: Garanti var → yalnız GK hesabı.
    with db.okuma_islemi() as oturum:
        (bulunan,) = ns.nesne_bul(oturum, alan_adi="ad", deger="Garanti BBVA")
    assert bulunan.id == banka.nesne.id and bulunan.durum is sz.NesneDurumu.AKTIF
    gk = _tanimla(
        db,
        [Oz("ad", "GK"), Oz("tür", "hesap"), Oz("iban", "TR000000000000000000000002")],
        anahtar="g-gk",
        ustler=(bulunan.id,),
    )
    _onayla(db, gk)

    with db.okuma_islemi() as oturum:
        bankalar = ns.nesne_bul(oturum, alan_adi="tür", deger="banka")
        garanti = ns.nesne_getir(oturum, banka.nesne.id)
    assert [b.id for b in bankalar] == [banka.nesne.id]  # üç banka değil, bir banka
    assert garanti.alt_idleri == (me.nesne.id, gk.nesne.id)  # yalnız gelen hesaplar
    assert _sayi(db, sema.nesne) == 3  # AK için ekstre gelmedi, AK açılmadı


# --- GONDER: nesne ONAY_BEKLIYOR yazılır --------------------------------------


def test_gonder_nesneyi_onay_bekliyor_yazar_ve_talep_acar(db: vt.Veritabani) -> None:
    sonuc = _tanimla(db, [Oz("ad", "QNB"), Oz("tür", "banka")], anahtar="q1")

    assert sonuc.zaten_vardi is False
    assert sonuc.nesne.durum is sz.NesneDurumu.ONAY_BEKLIYOR
    assert sonuc.nesne.seviye == 0 and sonuc.nesne.surum == 1
    talep = sonuc.onay_talebi
    assert talep.tur is sz.OnayTuru.NESNE_ACILISI
    assert talep.durum is sz.OnayDurumu.BEKLIYOR
    assert talep.hedef_id == sonuc.nesne.id and talep.hedef_surumu == 1
    assert talep.icerik["ozellikler"] == [
        {"alan_adi": "ad", "deger_turu": "METIN", "deger": "QNB"},
        {"alan_adi": "tür", "deger_turu": "METIN", "deger": "banka"},
    ]
    with db.okuma_islemi() as oturum:
        ayrinti = ns.nesne_getir(oturum, sonuc.nesne.id)
        with pytest.raises(sz.GirdiGecersiz, match="ONAY_BEKLIYOR"):
            ns.aktif_nesneyi_getir(oturum, sonuc.nesne.id)
    assert [(o.alan_adi, o.deger, o.sart) for o in ayrinti.ozellikler] == [
        ("ad", "QNB", False),
        ("tür", "banka", False),
    ]
    assert ayrinti.ust_idleri == () and ayrinti.alt_idleri == ()


def test_ayni_anahtar_ayni_icerik_yeni_nesne_acmaz(db: vt.Veritabani) -> None:
    ilk = _tanimla(db, [Oz("ad", "QNB")], anahtar="q1")
    tekrar = _tanimla(db, [Oz("ad", "QNB")], anahtar="q1")

    assert tekrar.zaten_vardi is True
    assert tekrar.nesne.id == ilk.nesne.id
    assert tekrar.onay_talebi.id == ilk.onay_talebi.id
    assert _sayi(db, sema.nesne) == 1


def test_ayni_anahtar_farkli_icerik_cakisir(db: vt.Veritabani) -> None:
    _tanimla(db, [Oz("ad", "QNB")], anahtar="q1")

    with pytest.raises(sz.AnahtarIcerikCakismasi):
        _tanimla(db, [Oz("ad", "Akbank")], anahtar="q1")

    assert _sayi(db, sema.nesne) == 1


def test_hata_her_seyi_geri_alir(db: vt.Veritabani) -> None:
    with pytest.raises(RuntimeError, match="sonra patladı"):
        with db.yazma_islemi() as oturum:
            ns.nesne_tanimla(
                oturum, ozellikler=[Oz("ad", "QNB")], islem_anahtari="q1", aktor=COWORK
            )
            raise RuntimeError("sonra patladı")

    for tablo in (sema.nesne, sema.nesne_ozellik, sema.onay_talep, sema.islem_anahtari):
        assert _sayi(db, tablo) == 0


# --- seviye kuralları (K11) ---------------------------------------------------


def test_ust_yoksa_seviye_0_ust_varsa_bir_ustu(db: vt.Veritabani) -> None:
    kurum = _tanimla(db, [Oz("ad", "Garanti Grubu")], anahtar="k")
    banka = _tanimla(
        db, [Oz("ad", "Garanti BBVA")], anahtar="b", ustler=(kurum.nesne.id,)
    )
    hesap = _tanimla(db, [Oz("ad", "ME")], anahtar="h", ustler=(banka.nesne.id,))

    assert (kurum.nesne.seviye, banka.nesne.seviye, hesap.nesne.seviye) == (0, 1, 2)


def test_s02_ayni_alt_iki_gecerli_ustte(db: vt.Veritabani) -> None:
    kart = _tanimla(db, [Oz("ad", "Kart")], anahtar="k")
    hesap = _tanimla(db, [Oz("ad", "Hesap")], anahtar="h")

    fis = _tanimla(
        db, [Oz("ad", "Fiş")], anahtar="f", ustler=(kart.nesne.id, hesap.nesne.id)
    )

    assert fis.nesne.seviye == 1
    with db.okuma_islemi() as oturum:
        ayrinti = ns.nesne_getir(oturum, fis.nesne.id)
    assert ayrinti.ust_idleri == (kart.nesne.id, hesap.nesne.id)


def test_s01_farkli_seviyeli_iki_ust_seviye_cakismasi(db: vt.Veritabani) -> None:
    banka = _tanimla(db, [Oz("ad", "Banka")], anahtar="b")
    hesap = _tanimla(db, [Oz("ad", "Hesap")], anahtar="h", ustler=(banka.nesne.id,))

    with pytest.raises(sz.SeviyeCakismasi) as bilgi:
        _tanimla(
            db, [Oz("ad", "X")], anahtar="x", ustler=(banka.nesne.id, hesap.nesne.id)
        )

    assert bilgi.value.kod == "SEVIYE_CAKISMASI"
    assert _sayi(db, sema.nesne) == 2


def test_olmayan_engelli_ve_pasif_ust_reddedilir(db: vt.Veritabani) -> None:
    ust = _tanimla(db, [Oz("ad", "Banka")], anahtar="b")

    with pytest.raises(sz.HedefBulunamadi):
        _tanimla(db, [Oz("ad", "X")], anahtar="x1", ustler=(999,))
    with db.yazma_islemi() as oturum:
        oturum.execute(
            sema.nesne.update()
            .where(sema.nesne.c.id == ust.nesne.id)
            .values(durum="ENGELLI")
        )
    with pytest.raises(sz.NesneEngelli):
        _tanimla(db, [Oz("ad", "X")], anahtar="x2", ustler=(ust.nesne.id,))
    with db.yazma_islemi() as oturum:
        oturum.execute(
            sema.nesne.update()
            .where(sema.nesne.c.id == ust.nesne.id)
            .values(durum="PASIF")
        )
    with pytest.raises(sz.GirdiGecersiz, match="pasif"):
        _tanimla(db, [Oz("ad", "X")], anahtar="x3", ustler=(ust.nesne.id,))


def test_ayni_ust_iki_kez_reddedilir(db: vt.Veritabani) -> None:
    ust = _tanimla(db, [Oz("ad", "Banka")], anahtar="b")

    with pytest.raises(sz.GirdiGecersiz, match="aynı üst"):
        _tanimla(db, [Oz("ad", "X")], anahtar="x", ustler=(ust.nesne.id, ust.nesne.id))


# --- özellik kuralları (C05, C13, C18) ----------------------------------------


def test_en_az_bir_ozellik_zorunlu(db: vt.Veritabani) -> None:
    with pytest.raises(sz.GirdiGecersiz, match="en az bir özellik"):
        _tanimla(db, [], anahtar="x")


@pytest.mark.parametrize("ad", ["", "   "])
def test_bos_alan_adi_reddedilir(db: vt.Veritabani, ad: str) -> None:
    with pytest.raises(sz.GirdiGecersiz, match="boş olamaz") as bilgi:
        _tanimla(db, [Oz(ad, "x")], anahtar="x")

    assert bilgi.value.konum == 0


def test_ayni_alan_adi_iki_kez_reddedilir(db: vt.Veritabani) -> None:
    with pytest.raises(sz.GirdiGecersiz, match="iki kez") as bilgi:
        _tanimla(db, [Oz("ad", "a"), Oz("ad", "b")], anahtar="x")

    assert bilgi.value.konum == 1
    assert _sayi(db, sema.nesne) == 0


def test_alan_adi_normalize_edilmez(db: vt.Veritabani) -> None:
    """C05: ' IBAN' ile 'IBAN' ayrı alanlardır; boşluk silinmez."""
    sonuc = _tanimla(
        db, [Oz(" IBAN", "a"), Oz("IBAN", "b"), Oz("iban", "c")], anahtar="x"
    )

    with db.okuma_islemi() as oturum:
        adlar = [o.alan_adi for o in ns.nesne_getir(oturum, sonuc.nesne.id).ozellikler]
    assert adlar == [" IBAN", "IBAN", "iban"]


def test_sinir_asimi_acik_hata(db: vt.Veritabani) -> None:
    with pytest.raises(sz.GirdiGecersiz, match="en çok 200"):
        _tanimla(db, [Oz(f"a{i}", i) for i in range(201)], anahtar="x1")
    with pytest.raises(sz.GirdiGecersiz, match="128"):
        _tanimla(db, [Oz("a" * 129, "x")], anahtar="x2")
    with pytest.raises(sz.GirdiGecersiz, match="4096"):
        _tanimla(db, [Oz("uzun", "x" * 4097)], anahtar="x3")
    assert _sayi(db, sema.nesne) == 0


# --- değer türü ve eşleşme değeri ---------------------------------------------


def test_deger_turu_cikarimi_ve_eslesme_degeri(db: vt.Veritabani) -> None:
    sonuc = _tanimla(
        db,
        [
            Oz("metin", "123"),
            Oz("sayi", 123),
            Oz("ondalik", 2.50),
            Oz("mantik", True),
            Oz("tarih", "2026-09-17", sz.DegerTuru.TARIH),
            Oz("tarih2", date(2026, 9, 17)),
            Oz("liste", [1, 2]),
            Oz("bos", ""),
        ],
        anahtar="x",
    )

    with db.okuma_islemi() as oturum:
        ozellikler = {
            o.alan_adi: (o.deger_turu, o.eslesme_degeri)
            for o in ns.nesne_getir(oturum, sonuc.nesne.id).ozellikler
        }
    assert ozellikler == {
        "metin": (sz.DegerTuru.METIN, "METIN:123"),
        "sayi": (sz.DegerTuru.TAMSAYI, "TAMSAYI:123"),
        "ondalik": (sz.DegerTuru.ONDALIK, "ONDALIK:2.5"),
        "mantik": (sz.DegerTuru.MANTIKSAL, "MANTIKSAL:true"),
        "tarih": (sz.DegerTuru.TARIH, "TARIH:2026-09-17"),
        "tarih2": (sz.DegerTuru.TARIH, "TARIH:2026-09-17"),
        "liste": (sz.DegerTuru.JSON, "JSON:[1,2]"),
        "bos": (sz.DegerTuru.METIN, None),
    }


def test_eslesme_turuyle_yapilir_metin_123_tam_sayi_123_esit_degil() -> None:
    assert ns.eslesme_degeri("123", sz.DegerTuru.METIN) != ns.eslesme_degeri(
        123, sz.DegerTuru.TAMSAYI
    )
    assert ns.eslesme_degeri("2.50", sz.DegerTuru.ONDALIK) == ns.eslesme_degeri(
        Decimal("2.5"), sz.DegerTuru.ONDALIK
    )
    assert ns.eslesme_degeri(None, sz.DegerTuru.METIN) is None
    assert ns.eslesme_degeri({}, sz.DegerTuru.JSON) is None


@pytest.mark.parametrize(
    ("girdi", "hata"),
    [
        (Oz("t", "17.09.2026", sz.DegerTuru.TARIH), "YYYY-AA-GG"),
        (Oz("s", "12", sz.DegerTuru.TAMSAYI), "tam sayı"),
        (Oz("s", True, sz.DegerTuru.TAMSAYI), "tam sayı"),
        (Oz("m", "evet", sz.DegerTuru.MANTIKSAL), "doğru/yanlış"),
        (Oz("o", "abc", sz.DegerTuru.ONDALIK), "sayı"),
    ],
)
def test_ture_uymayan_deger_reddedilir(
    db: vt.Veritabani, girdi: ns.OzellikGirdisi, hata: str
) -> None:
    with pytest.raises(sz.GirdiGecersiz, match=hata):
        _tanimla(db, [girdi], anahtar="x")


# --- karar: şart seçimi (K14) -------------------------------------------------


def test_sartsiz_onay_nesneyi_aktif_yapar(db: vt.Veritabani) -> None:
    sonuc = _tanimla(db, [Oz("ad", "QNB")], anahtar="q")

    talep = _onayla(db, sonuc)

    assert talep.durum is sz.OnayDurumu.ONAYLANDI
    with db.okuma_islemi() as oturum:
        ayrinti = ns.nesne_getir(oturum, sonuc.nesne.id)
        aktif = ns.aktif_nesneyi_getir(oturum, sonuc.nesne.id)
    assert aktif.durum is sz.NesneDurumu.AKTIF and aktif.surum == 2
    assert all(not o.sart for o in ayrinti.ozellikler)
    assert _sayi(db, sema.nesne_sart) == 0


def test_sart_secimi_kalici_yazilir(db: vt.Veritabani) -> None:
    sonuc = _tanimla(
        db, [Oz("ad", "ME"), Oz("iban", "TR00"), Oz("tür", "hesap")], anahtar="h"
    )
    iban_id = _ozellik_id(db, sonuc.nesne.id, "iban")
    ad_id = _ozellik_id(db, sonuc.nesne.id, "ad")

    talep = _onayla(db, sonuc, sartlar=(iban_id, ad_id, iban_id))

    assert talep.karar is not None
    assert talep.karar["secilen_sartlar"] == [iban_id, ad_id, iban_id]
    with db.okuma_islemi() as oturum:
        ayrinti = ns.nesne_getir(oturum, sonuc.nesne.id)
    assert {o.alan_adi for o in ayrinti.ozellikler if o.sart} == {"iban", "ad"}
    assert _sayi(db, sema.nesne_sart) == 2  # tekrar eden seçim bir kez


def test_baska_nesnenin_ozelligi_sart_olamaz(db: vt.Veritabani) -> None:
    a = _tanimla(db, [Oz("ad", "A")], anahtar="a")
    b = _tanimla(db, [Oz("ad", "B")], anahtar="b")
    b_ad = _ozellik_id(db, b.nesne.id, "ad")

    with pytest.raises(sz.GirdiGecersiz, match="bu nesneye ait değil"):
        _onayla(db, a, sartlar=(b_ad,))

    with db.okuma_islemi() as oturum:
        assert (
            ns.nesne_getir(oturum, a.nesne.id).nesne.durum
            is sz.NesneDurumu.ONAY_BEKLIYOR
        )
    assert _sayi(db, sema.nesne_sart) == 0


def test_red_nesneyi_silindi_yapar(db: vt.Veritabani) -> None:
    sonuc = _tanimla(db, [Oz("ad", "Yanlış")], anahtar="y")

    with db.yazma_islemi() as oturum:
        on.karar_uygula(
            oturum,
            talep_id=sonuc.onay_talebi.id,
            gorulen_hedef_surumu=1,
            karar=on.Karar(onaylandi=False, gerekce="böyle bir banka yok"),
            simdi=SIMDI,
        )

    with db.okuma_islemi() as oturum:
        nesne = ns.nesne_getir(oturum, sonuc.nesne.id).nesne
        assert ns.nesne_bul(oturum, alan_adi="ad", deger="Yanlış") == []
    assert nesne.durum is sz.NesneDurumu.SILINDI and nesne.surum == 2


def test_onay_bekleyen_ust_altina_nesne_acilabilir(db: vt.Veritabani) -> None:
    """Garanti ve ME aynı anda önerilebilir; ME'nin üstü henüz onaylanmamış Garanti."""
    banka = _tanimla(db, [Oz("ad", "Garanti BBVA")], anahtar="b")

    hesap = _tanimla(db, [Oz("ad", "ME")], anahtar="h", ustler=(banka.nesne.id,))

    assert hesap.nesne.seviye == 1


# --- kaynak belge -------------------------------------------------------------


def _belge_ac(db: vt.Veritabani) -> int:
    with db.yazma_islemi() as oturum:
        dosya_id = oturum.execute(
            sema.arsiv_dosya.insert()
            .values(
                sha256="b" * 64,
                boyut=10,
                mime="application/pdf",
                uzanti=".pdf",
                kaynak_adi="ekstre.pdf",
                goreli_yol="2026/ekstre.pdf",
                olusturma_zamani=SIMDI,
            )
            .returning(sema.arsiv_dosya.c.id)
        ).scalar_one()
        return int(
            oturum.execute(
                sema.belge.insert()
                .values(dosya_id=dosya_id, durum="ARSIVLENDI", olusturma_zamani=SIMDI)
                .returning(sema.belge.c.id)
            ).scalar_one()
        )


def test_kaynak_belge_kaydedilir(db: vt.Veritabani) -> None:
    belge_id = _belge_ac(db)

    sonuc = _tanimla(
        db,
        [Oz("ad", "ME")],
        anahtar="h",
        kaynak=ns.NesneKaynagi(belge_id=belge_id, konum={"sayfa": 1}),
    )

    with db.okuma_islemi() as oturum:
        (kaynak,) = oturum.execute(select(sema.nesne_kaynak)).all()
    assert (kaynak.nesne_id, kaynak.belge_id, kaynak.okuma_id, kaynak.konum) == (
        sonuc.nesne.id,
        belge_id,
        None,
        {"sayfa": 1},
    )
    assert sonuc.onay_talebi.icerik["kaynak"] == {
        "belge_id": belge_id,
        "okuma_id": None,
        "konum": {"sayfa": 1},
    }


def test_olmayan_kaynak_belge_reddedilir(db: vt.Veritabani) -> None:
    with pytest.raises(sz.HedefBulunamadi, match="kaynak belge"):
        _tanimla(
            db, [Oz("ad", "ME")], anahtar="h", kaynak=ns.NesneKaynagi(belge_id=999)
        )

    assert _sayi(db, sema.nesne) == 0


def test_kurum_belgesiz_acilabilir(db: vt.Veritabani) -> None:
    """C13: kaynak belge zorunlu değil."""
    sonuc = _tanimla(db, [Oz("ad", "Garanti Grubu")], anahtar="k")

    assert sonuc.nesne.seviye == 0
    assert _sayi(db, sema.nesne_kaynak) == 0


# --- bulma ve form ------------------------------------------------------------


def test_nesne_bul_alan_deger_ve_seviye_filtreleri(db: vt.Veritabani) -> None:
    banka = _tanimla(db, [Oz("ad", "Garanti BBVA"), Oz("tür", "banka")], anahtar="b")
    _onayla(db, banka)
    hesap = _tanimla(
        db,
        [Oz("ad", "ME"), Oz("tür", "hesap"), Oz("no", 123)],
        anahtar="h",
        ustler=(banka.nesne.id,),
    )

    with db.okuma_islemi() as oturum:
        turler = ns.nesne_bul(oturum, alan_adi="tür")
        bankalar = ns.nesne_bul(oturum, alan_adi="tür", deger="banka")
        no_metin = ns.nesne_bul(oturum, alan_adi="no", deger="123")
        no_sayi = ns.nesne_bul(oturum, alan_adi="no", deger=123)
        seviye_1 = ns.nesne_bul(oturum, seviye=1)
        yalniz_aktif = ns.nesne_bul(oturum, durumlar=(sz.NesneDurumu.AKTIF,))
        bos = ns.nesne_bul(oturum, alan_adi="ad", deger="")

    assert [n.id for n in turler] == [banka.nesne.id, hesap.nesne.id]
    assert [n.id for n in bankalar] == [banka.nesne.id]
    assert no_metin == [] and [n.id for n in no_sayi] == [hesap.nesne.id]
    assert [n.id for n in seviye_1] == [hesap.nesne.id]
    assert [n.id for n in yalniz_aktif] == [banka.nesne.id]
    assert bos == []


def test_olmayan_nesne_hedef_bulunamadi(db: vt.Veritabani) -> None:
    with db.okuma_islemi() as oturum:
        with pytest.raises(sz.HedefBulunamadi):
            ns.nesne_getir(oturum, 999)


def test_tanitma_formu_bos_ve_kurallari_soyler(tmp_path: Path) -> None:
    form = ns.tanitma_formu()

    assert form.satir_sablonu == {"alan_adi": "", "deger": None, "deger_turu": None}
    assert set(form.deger_turleri) == {t.value for t in sz.DegerTuru}
    assert any("belgesiz" in k for k in form.kurallar)
    assert any("ONAY_BEKLIYOR" in k for k in form.kurallar)
    assert list(tmp_path.iterdir()) == []


def test_denetim_olaylari_ve_anahtar_kaydi(db: vt.Veritabani) -> None:
    sonuc = _tanimla(db, [Oz("ad", "QNB")], anahtar="cowork-2026-09-17-01")
    _onayla(db, sonuc)

    with db.okuma_islemi() as oturum:
        olaylar = oturum.execute(
            select(sema.denetim_olay).order_by(sema.denetim_olay.c.id)
        ).all()
        anahtar = oturum.execute(select(sema.islem_anahtari)).one()
    assert [(o.eylem, o.aktor, o.sonraki_durum) for o in olaylar] == [
        (ns.EYLEM_NESNE_TANIMLA, "COWORK", "ONAY_BEKLIYOR"),
        (on.EYLEM_TALEP_OLUSTUR, "COWORK", "BEKLIYOR"),
        (ns.EYLEM_NESNE_ONAYI, "KULLANICI", "AKTIF"),
        (on.EYLEM_KARAR, "KULLANICI", "ONAYLANDI"),
    ]
    assert anahtar.arac_adi == ns.ARAC_NESNE_TANIMLA
    assert anahtar.sonuc == {
        "nesne_id": sonuc.nesne.id,
        "onay_talebi_id": sonuc.onay_talebi.id,
    }

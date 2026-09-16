"""Belge, okuma, gönderim ve belge kaydı (Teslim 4.5).

Akış: dosya gelen dizinine → belge_al (ARSIVLENDI) → okuma_baslat (OKUNUYOR)
→ satir_gonder paketleri → okuma_tamamla (TAMAMLANDI, HAZIR, uygulama belge
kaydını tanımlar: KAYITLI). Sentetik içerik; gerçek belge yok.
"""

import os
import subprocess
import sys
import time
from collections.abc import Iterator, Sequence
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

from defteriki import arsiv, sema
from defteriki import belgeler as bl
from defteriki import sozlesmeler as sz
from defteriki import veritabani as vt

SIMDI = datetime(2026, 9, 17, 10, 0)
COWORK = sz.DenetimAktoru.COWORK
PDF = b"%PDF-1.7\n%sentetik ekstre\n"
SEMA = "cowork-0.1"
Satir = bl.SatirGirdisi


@pytest.fixture
def db(tmp_path: Path) -> Iterator[vt.Veritabani]:
    yol = tmp_path / "vt" / "belge.sqlite3"
    yol.parent.mkdir()
    veritabani = vt.Veritabani(yol, mesgul_bekleme_ms=200)
    sema.semayi_yukselt(veritabani)
    yield veritabani
    veritabani.kapat()


@pytest.fixture
def gelen(tmp_path: Path) -> Path:
    dizin = tmp_path / "gelen"
    dizin.mkdir()
    return dizin


@pytest.fixture
def arsiv_dizini(tmp_path: Path) -> Path:
    dizin = tmp_path / "belgeler"
    dizin.mkdir()
    return dizin


def _dosya_birak(gelen: Path, ad: str = "ekstre.pdf", icerik: bytes = PDF) -> Path:
    yol = gelen / ad
    yol.write_bytes(icerik)
    return yol


def _belge_al(
    db: vt.Veritabani,
    gelen: Path,
    arsiv_dizini: Path,
    *,
    ad: str = "ekstre.pdf",
    icerik: bytes = PDF,
    anahtar: str = "al-1",
) -> bl.BelgeTanimlamaSonucu:
    yol = _dosya_birak(gelen, ad, icerik)
    return bl.belge_al(
        db,
        yol=str(yol),
        gelen_dizini=gelen,
        belge_dizini=arsiv_dizini,
        islem_anahtari=anahtar,
        aktor=COWORK,
        simdi=SIMDI,
    )


def _okuma_baslat(
    db: vt.Veritabani,
    belge_id: int,
    arsiv_dizini: Path,
    *,
    anahtar: str = "ob-1",
    tamlik: bl.Tamlik | None = None,
    icerik: dict[str, object] | None = None,
) -> bl.Okuma:
    with db.yazma_islemi() as oturum:
        return bl.okuma_baslat(
            oturum,
            belge_id=belge_id,
            sema_surumu=SEMA,
            belge_dizini=arsiv_dizini,
            islem_anahtari=anahtar,
            aktor=COWORK,
            icerik=icerik,
            tamlik=tamlik,
            simdi=SIMDI,
        )


def _gonder(
    db: vt.Veritabani,
    okuma_id: int,
    satirlar: Sequence[bl.SatirGirdisi],
    *,
    anahtar: str = "sg-1",
) -> bl.GonderimSonucu:
    with db.yazma_islemi() as oturum:
        return bl.satir_gonder(
            oturum,
            okuma_id=okuma_id,
            satirlar=satirlar,
            islem_anahtari=anahtar,
            aktor=COWORK,
            simdi=SIMDI,
        )


def _tamamla(
    db: vt.Veritabani,
    okuma_id: int,
    *,
    anahtar: str = "ot-1",
    tamlik: bl.Tamlik | None = None,
) -> bl.OkumaTamamlamaSonucu:
    with db.yazma_islemi() as oturum:
        return bl.okuma_tamamla(
            oturum,
            okuma_id=okuma_id,
            islem_anahtari=anahtar,
            aktor=COWORK,
            tamlik=tamlik,
            simdi=SIMDI,
        )


def _hazir_okuma(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> tuple[bl.Belge, bl.Okuma]:
    belge = _belge_al(db, gelen, arsiv_dizini).belge
    okuma = _okuma_baslat(db, belge.id, arsiv_dizini)
    return belge, okuma


def _satir(n: int, **ham: object) -> bl.SatirGirdisi:
    return Satir(f"s{n}", n, {"aciklama": f"hareket {n}", "tutar": n * 100, **ham})


def _sayi(db: vt.Veritabani, tablo: sema.Table) -> int:
    with db.okuma_islemi() as oturum:
        return int(oturum.execute(select(func.count()).select_from(tablo)).scalar_one())


def _belge(db: vt.Veritabani, belge_id: int) -> bl.Belge:
    with db.okuma_islemi() as oturum:
        return bl.belge_getir(oturum, belge_id).belge


def _okuma(db: vt.Veritabani, okuma_id: int) -> bl.Okuma:
    with db.okuma_islemi() as oturum:
        return bl.okuma_getir(oturum, okuma_id)


def _olaylar(db: vt.Veritabani) -> list[tuple[str, str, str | None, str | None]]:
    with db.okuma_islemi() as oturum:
        satirlar = oturum.execute(
            select(
                sema.denetim_olay.c.eylem,
                sema.denetim_olay.c.hedef,
                sema.denetim_olay.c.onceki_durum,
                sema.denetim_olay.c.sonraki_durum,
            ).order_by(sema.denetim_olay.c.id)
        ).all()
    return [(str(s[0]), str(s[1]), s[2], s[3]) for s in satirlar]


# --- uçtan uca -----------------------------------------------------------------


def test_belge_akisi_arsivden_kayitliya(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> None:
    alinan = _belge_al(db, gelen, arsiv_dizini)
    assert alinan.zaten_vardi is False
    assert alinan.belge.durum is sz.BelgeDurumu.ARSIVLENDI
    assert alinan.belge.surum == 1 and alinan.belge.etkin_okuma_id is None
    assert alinan.dosya.mime == "application/pdf" and alinan.dosya.boyut == len(PDF)
    assert arsiv.arsivde_var_mi(arsiv_dizini, alinan.dosya.goreli_yol, len(PDF))

    okuma = _okuma_baslat(
        db,
        alinan.belge.id,
        arsiv_dizini,
        tamlik=bl.Tamlik(beklenen_satir_sayisi=5, kapanis_bakiyesi_kurus=-2500),
        icerik={"donem": "2026-08", "hesap": "ME"},
    )
    assert okuma.durum is sz.OkumaDurumu.ACIK
    assert okuma.surum_no == 1 and okuma.sema_surumu == SEMA
    assert okuma.icerik == {"donem": "2026-08", "hesap": "ME"}
    assert okuma.tamlik == bl.Tamlik(
        beklenen_satir_sayisi=5, kapanis_bakiyesi_kurus=-2500
    )
    belge = _belge(db, alinan.belge.id)
    assert belge.durum is sz.BelgeDurumu.OKUNUYOR and belge.surum == 2

    ilk = _gonder(db, okuma.id, [_satir(0), _satir(1), _satir(2)], anahtar="p1")
    ikinci = _gonder(
        db,
        okuma.id,
        [
            Satir(
                "baslik", 3, {"metin": "Devreden bakiye"}, sz.SatirDurumu.KAPSAM_DISI
            ),
            _satir(4),
        ],
        anahtar="p2",
    )
    assert [s.satir_anahtari for s in ilk.yazilan] == ["s0", "s1", "s2"]
    assert ilk.zaten_mevcut == ()
    assert [(s.satir_anahtari, s.durum) for s in ikinci.yazilan] == [
        ("baslik", sz.SatirDurumu.KAPSAM_DISI),
        ("s4", sz.SatirDurumu.YAZILDI),
    ]

    sonuc = _tamamla(db, okuma.id)
    assert sonuc.okuma.durum is sz.OkumaDurumu.TAMAMLANDI
    assert sonuc.belge.durum is sz.BelgeDurumu.KAYITLI
    assert sonuc.belge.etkin_okuma_id == okuma.id
    assert sonuc.belge.surum == 4  # ARSIVLENDI→OKUNUYOR→HAZIR→KAYITLI

    with db.okuma_islemi() as oturum:
        ayrinti = bl.belge_getir(oturum, alinan.belge.id)
        satirlar = bl.satirlari_listele(oturum, okuma.id)
    assert [o.id for o in ayrinti.okumalar] == [okuma.id]
    assert [s.konum for s in satirlar] == [0, 1, 2, 3, 4]
    assert satirlar[1].ham == {"aciklama": "hareket 1", "tutar": 100}

    hedef_belge = f"belge:{alinan.belge.id}"
    hedef_okuma = f"okuma:{okuma.id}"
    assert _olaylar(db) == [
        ("belge_al", hedef_belge, None, "ARSIVLENDI"),
        ("okuma_baslat", hedef_belge, "ARSIVLENDI", "OKUNUYOR"),
        ("satir_gonder", hedef_okuma, None, None),
        ("satir_gonder", hedef_okuma, None, None),
        ("okuma_tamamla", hedef_okuma, "ACIK", "TAMAMLANDI"),
        ("belge_hazir", hedef_belge, "OKUNUYOR", "HAZIR"),
        ("belge_kaydet", hedef_belge, "HAZIR", "KAYITLI"),
    ]
    with db.okuma_islemi() as oturum:
        aktorler = (
            oturum.execute(
                select(sema.denetim_olay.c.aktor).where(
                    sema.denetim_olay.c.eylem == "belge_kaydet"
                )
            )
            .scalars()
            .all()
        )
    assert list(aktorler) == ["UYGULAMA"]  # belge kaydını uygulama tanımlar (C07)


# --- belge alma (K18) --------------------------------------------------------------


def test_ayni_dosya_iki_kez_tek_belge(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> None:
    ilk = _belge_al(db, gelen, arsiv_dizini, ad="agustos.pdf", anahtar="al-1")
    tekrar = _belge_al(db, gelen, arsiv_dizini, ad="kopya.pdf", anahtar="al-2")

    assert tekrar.zaten_vardi is True
    assert tekrar.belge.id == ilk.belge.id and tekrar.dosya.id == ilk.dosya.id
    assert _sayi(db, sema.belge) == 1 and _sayi(db, sema.arsiv_dosya) == 1
    assert len([p for p in arsiv_dizini.rglob("*") if p.is_file()]) == 1
    assert len(_olaylar(db)) == 1  # ikinci alım olay yazmaz, hiçbir şey değişmedi


def test_ayni_anahtar_ayni_dosya_sakli_sonuc_farkli_dosya_cakisir(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> None:
    ilk = _belge_al(db, gelen, arsiv_dizini, anahtar="al-1")
    tekrar = _belge_al(db, gelen, arsiv_dizini, anahtar="al-1")
    assert tekrar.belge.id == ilk.belge.id and tekrar.zaten_vardi is False

    with pytest.raises(sz.AnahtarIcerikCakismasi):
        _belge_al(
            db, gelen, arsiv_dizini, ad="b.pdf", icerik=PDF + b"x", anahtar="al-1"
        )
    assert _sayi(db, sema.belge) == 1


def test_farkli_icerik_ayri_belge(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> None:
    a = _belge_al(db, gelen, arsiv_dizini, ad="a.pdf", anahtar="al-1")
    b = _belge_al(
        db, gelen, arsiv_dizini, ad="b.pdf", icerik=PDF + b"2", anahtar="al-2"
    )

    assert a.belge.id != b.belge.id and a.dosya.sha256 != b.dosya.sha256
    assert _sayi(db, sema.belge) == 2


def test_veritabani_duserse_dosya_arsivde_kalir_belge_olusmaz(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> None:
    """Dosya ve veritabanı tek işlem değil (Tam Plan 8.1): kaynaksız kayıt yok."""
    yol = _dosya_birak(gelen)
    with pytest.raises(sz.GirdiGecersiz):
        bl.belge_al(
            db,
            yol=str(yol),
            gelen_dizini=gelen,
            belge_dizini=arsiv_dizini,
            islem_anahtari="   ",  # boş anahtar: veritabanı adımı düşer
            aktor=COWORK,
        )
    assert _sayi(db, sema.belge) == 0 and _sayi(db, sema.arsiv_dosya) == 0
    assert len([p for p in arsiv_dizini.rglob("*") if p.is_file()]) == 1


def test_izinsiz_yol_belge_olmaz(
    db: vt.Veritabani, tmp_path: Path, gelen: Path, arsiv_dizini: Path
) -> None:
    disari = tmp_path / "sir.pdf"
    disari.write_bytes(PDF)
    with pytest.raises(sz.GirdiGecersiz, match=arsiv.GEREKCE_DIZIN_DISI):
        bl.belge_al(
            db,
            yol=str(disari),
            gelen_dizini=gelen,
            belge_dizini=arsiv_dizini,
            islem_anahtari="al-1",
            aktor=COWORK,
        )
    assert _sayi(db, sema.belge) == 0


def test_belge_getir_yoksa_belge_yok(db: vt.Veritabani) -> None:
    with db.okuma_islemi() as oturum:
        with pytest.raises(sz.BelgeYok):
            bl.belge_getir(oturum, 99)


# --- okuma başlatma ve S10 ------------------------------------------------------


def test_s10_belgesiz_okuma_baslamaz(db: vt.Veritabani, arsiv_dizini: Path) -> None:
    with pytest.raises(sz.BelgeYok):
        _okuma_baslat(db, 42, arsiv_dizini)
    assert _sayi(db, sema.okuma) == 0


def test_s10_arsiv_dosyasi_yoksa_okuma_baslamaz(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> None:
    alinan = _belge_al(db, gelen, arsiv_dizini)
    arsiv.arsiv_yolu(arsiv_dizini, alinan.dosya.goreli_yol).unlink()

    with pytest.raises(sz.ArsivEksik):
        _okuma_baslat(db, alinan.belge.id, arsiv_dizini)

    assert _sayi(db, sema.okuma) == 0
    assert _belge(db, alinan.belge.id).durum is sz.BelgeDurumu.ARSIVLENDI


def test_s10_olmayan_okumaya_satir_gonderilmez(db: vt.Veritabani) -> None:
    with pytest.raises(sz.HedefBulunamadi):
        _gonder(db, 7, [_satir(0)])
    assert _sayi(db, sema.okuma_satir) == 0


def test_okunuyor_ya_da_kayitli_belgede_ikinci_okuma_acilmaz(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> None:
    belge, okuma = _hazir_okuma(db, gelen, arsiv_dizini)
    with pytest.raises(sz.GirdiGecersiz, match="OKUNUYOR"):
        _okuma_baslat(db, belge.id, arsiv_dizini, anahtar="ob-2")

    _gonder(db, okuma.id, [_satir(0)])
    _tamamla(db, okuma.id)
    with pytest.raises(sz.GirdiGecersiz, match="KAYITLI"):
        _okuma_baslat(db, belge.id, arsiv_dizini, anahtar="ob-3")
    assert _sayi(db, sema.okuma) == 1


def test_ayni_anahtarla_okuma_baslat_tek_okuma(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> None:
    belge = _belge_al(db, gelen, arsiv_dizini).belge
    ilk = _okuma_baslat(db, belge.id, arsiv_dizini, anahtar="ob-1")
    tekrar = _okuma_baslat(db, belge.id, arsiv_dizini, anahtar="ob-1")
    assert tekrar.id == ilk.id and _sayi(db, sema.okuma) == 1


@pytest.mark.parametrize("surum", ["", "   ", "x" * 33])
def test_sema_surumu_gecersiz(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path, surum: str
) -> None:
    belge = _belge_al(db, gelen, arsiv_dizini).belge
    with pytest.raises(sz.GirdiGecersiz, match="şema sürümü"):
        with db.yazma_islemi() as oturum:
            bl.okuma_baslat(
                oturum,
                belge_id=belge.id,
                sema_surumu=surum,
                belge_dizini=arsiv_dizini,
                islem_anahtari="ob-1",
                aktor=COWORK,
            )


@pytest.mark.parametrize(
    "tamlik",
    [
        bl.Tamlik(beklenen_satir_sayisi=-1),
        bl.Tamlik(beklenen_satir_sayisi=True),  # pyright: ignore[reportArgumentType]
        bl.Tamlik(toplam_giris_kurus=-5),
        bl.Tamlik(kapanis_bakiyesi_kurus=12.5),  # pyright: ignore[reportArgumentType]
    ],
)
def test_tamlik_gecersiz(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path, tamlik: bl.Tamlik
) -> None:
    belge = _belge_al(db, gelen, arsiv_dizini).belge
    with pytest.raises(sz.GirdiGecersiz, match="tamlık"):
        _okuma_baslat(db, belge.id, arsiv_dizini, tamlik=tamlik)
    assert _sayi(db, sema.okuma) == 0


def test_tamlik_negatif_bakiye_kabul(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> None:
    belge = _belge_al(db, gelen, arsiv_dizini).belge
    tamlik = bl.Tamlik(acilis_bakiyesi_kurus=-100, kapanis_bakiyesi_kurus=-250)
    okuma = _okuma_baslat(db, belge.id, arsiv_dizini, tamlik=tamlik)
    assert okuma.tamlik == tamlik


# --- gönderim (K07, S11) ------------------------------------------------------------


@pytest.mark.parametrize(
    ("bozuk", "alan"),
    [
        (Satir("", 1, {"a": 1}), "satir_anahtari"),
        (Satir("  ", 1, {"a": 1}), "satir_anahtari"),
        (Satir("x" * 129, 1, {"a": 1}), "satir_anahtari"),
        (Satir("s0", 1, {"a": 1}), "satir_anahtari"),  # pakette ikinci kez
        (Satir("k", -1, {"a": 1}), "konum"),
        (Satir("k", 1.0, {"a": 1}), "konum"),  # pyright: ignore[reportArgumentType]
        (Satir("k", 1, {}), "ham"),
        (Satir("k", 1, {"a": object()}), "ham"),
        (Satir("k", 1, {"a": "x" * 5000}), "ham"),
        (Satir("k", 1, {"a": 1}, sz.SatirDurumu.KARAR_BEKLIYOR), "durum"),
    ],
)
def test_s11_bicim_hatali_satir_paketin_tamamini_dusurur(
    db: vt.Veritabani,
    gelen: Path,
    arsiv_dizini: Path,
    bozuk: bl.SatirGirdisi,
    alan: str,
) -> None:
    _, okuma = _hazir_okuma(db, gelen, arsiv_dizini)

    with pytest.raises(sz.GirdiGecersiz) as hata:
        _gonder(db, okuma.id, [_satir(0), bozuk, _satir(2)])

    assert hata.value.alan == alan and hata.value.konum == 1
    assert _sayi(db, sema.okuma_satir) == 0
    assert _sayi(db, sema.islem_anahtari) == 2  # yalnız belge_al ve okuma_baslat


def test_bos_ve_asiri_paket(db: vt.Veritabani, gelen: Path, arsiv_dizini: Path) -> None:
    _, okuma = _hazir_okuma(db, gelen, arsiv_dizini)
    with pytest.raises(sz.GirdiGecersiz, match="en az bir satır"):
        _gonder(db, okuma.id, [])
    with pytest.raises(sz.GirdiGecersiz, match="en çok 500"):
        _gonder(db, okuma.id, [_satir(n) for n in range(501)])
    assert _sayi(db, sema.okuma_satir) == 0


def test_tekrar_gonderim_ayni_icerik_mevcut_farkli_icerik_cakisir(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> None:
    _, okuma = _hazir_okuma(db, gelen, arsiv_dizini)
    ilk = _gonder(db, okuma.id, [_satir(0), _satir(1)], anahtar="p1")

    tekrar = _gonder(db, okuma.id, [_satir(1), _satir(2)], anahtar="p2")
    assert [s.satir_anahtari for s in tekrar.yazilan] == ["s2"]
    assert [s.id for s in tekrar.zaten_mevcut] == [ilk.yazilan[1].id]

    with pytest.raises(sz.AnahtarIcerikCakismasi) as hata:
        _gonder(db, okuma.id, [_satir(3), _satir(0, tutar=999)], anahtar="p3")
    assert hata.value.konum == 1
    assert _sayi(db, sema.okuma_satir) == 3  # s3 de yazılmadı: paket bütündür


def test_ayni_islem_anahtari_ikinci_kez_yazmaz(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> None:
    _, okuma = _hazir_okuma(db, gelen, arsiv_dizini)
    ilk = _gonder(db, okuma.id, [_satir(0)], anahtar="p1")
    tekrar = _gonder(db, okuma.id, [_satir(0)], anahtar="p1")

    assert [s.id for s in tekrar.yazilan] == [s.id for s in ilk.yazilan]
    assert _sayi(db, sema.okuma_satir) == 1
    with pytest.raises(sz.AnahtarIcerikCakismasi):
        _gonder(db, okuma.id, [_satir(1)], anahtar="p1")


def test_kapali_okumaya_satir_gonderilmez(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> None:
    _, okuma = _hazir_okuma(db, gelen, arsiv_dizini)
    _gonder(db, okuma.id, [_satir(0)], anahtar="p1")
    _tamamla(db, okuma.id)

    with pytest.raises(sz.GirdiGecersiz, match="TAMAMLANDI"):
        _gonder(db, okuma.id, [_satir(1)], anahtar="p2")
    assert _sayi(db, sema.okuma_satir) == 1


# --- okuma tamamlama ve belge kaydı (C07, K19) ---------------------------------------


def test_mutabakat_farki_hicbir_durumu_degistirmez(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> None:
    belge = _belge_al(db, gelen, arsiv_dizini).belge
    okuma = _okuma_baslat(
        db, belge.id, arsiv_dizini, tamlik=bl.Tamlik(beklenen_satir_sayisi=3)
    )
    _gonder(db, okuma.id, [_satir(0), _satir(1)], anahtar="p1")

    with pytest.raises(sz.MutabakatFarki, match="beklenen satır sayısı 3, yazılan 2"):
        _tamamla(db, okuma.id, anahtar="ot-1")

    assert _okuma(db, okuma.id).durum is sz.OkumaDurumu.ACIK
    guncel = _belge(db, belge.id)
    assert guncel.durum is sz.BelgeDurumu.OKUNUYOR and guncel.surum == 2
    assert _sayi(db, sema.islem_anahtari) == 3  # düşen tamamlama anahtar bırakmaz

    _gonder(db, okuma.id, [_satir(2)], anahtar="p2")  # eksik satır gelir
    sonuc = _tamamla(db, okuma.id, anahtar="ot-2")
    assert sonuc.belge.durum is sz.BelgeDurumu.KAYITLI


def test_tamamlarken_verilen_tamlik_okumadakinin_yerine_gecer(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> None:
    belge = _belge_al(db, gelen, arsiv_dizini).belge
    okuma = _okuma_baslat(
        db, belge.id, arsiv_dizini, tamlik=bl.Tamlik(beklenen_satir_sayisi=9)
    )
    _gonder(db, okuma.id, [_satir(0), _satir(1)])

    yeni = bl.Tamlik(beklenen_satir_sayisi=2, kapanis_bakiyesi_kurus=500)
    sonuc = _tamamla(db, okuma.id, tamlik=yeni)

    assert sonuc.okuma.tamlik == yeni
    assert sonuc.belge.durum is sz.BelgeDurumu.KAYITLI


def test_tamlik_yoksa_satir_sayisi_denetlenmez(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> None:
    _, okuma = _hazir_okuma(db, gelen, arsiv_dizini)
    sonuc = _tamamla(db, okuma.id)  # sıfır satır, tamlık bilgisi yok
    assert sonuc.belge.durum is sz.BelgeDurumu.KAYITLI
    assert sonuc.okuma.tamlik is None


def test_tamamlanmis_okuma_yeniden_tamamlanmaz_ayni_anahtar_sakli(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> None:
    _, okuma = _hazir_okuma(db, gelen, arsiv_dizini)
    _gonder(db, okuma.id, [_satir(0)])
    ilk = _tamamla(db, okuma.id, anahtar="ot-1")
    tekrar = _tamamla(db, okuma.id, anahtar="ot-1")
    assert tekrar.belge.surum == ilk.belge.surum == 4

    with pytest.raises(sz.GirdiGecersiz, match="zaten sonuçlanmış"):
        _tamamla(db, okuma.id, anahtar="ot-2")


def test_hata_her_seyi_geri_alir(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> None:
    belge, okuma = _hazir_okuma(db, gelen, arsiv_dizini)
    with pytest.raises(RuntimeError, match="sonra patladı"):
        with db.yazma_islemi() as oturum:
            bl.satir_gonder(
                oturum,
                okuma_id=okuma.id,
                satirlar=[_satir(0)],
                islem_anahtari="p1",
                aktor=COWORK,
            )
            bl.okuma_tamamla(
                oturum, okuma_id=okuma.id, islem_anahtari="ot-1", aktor=COWORK
            )
            raise RuntimeError("sonra patladı")

    assert _sayi(db, sema.okuma_satir) == 0
    assert _okuma(db, okuma.id).durum is sz.OkumaDurumu.ACIK
    assert _belge(db, belge.id).durum is sz.BelgeDurumu.OKUNUYOR


def _hazir_belge(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> tuple[bl.Belge, bl.Okuma]:
    """HAZIR belge ve TAMAMLANDI okuma (Aşama 7'de karar sonrası kalacak hâl)."""
    belge, okuma = _hazir_okuma(db, gelen, arsiv_dizini)
    _gonder(db, okuma.id, [_satir(0)])
    with db.yazma_islemi() as oturum:
        oturum.execute(
            sema.okuma.update()
            .where(sema.okuma.c.id == okuma.id)
            .values(durum=sz.OkumaDurumu.TAMAMLANDI.value)
        )
        oturum.execute(
            sema.belge.update()
            .where(sema.belge.c.id == belge.id)
            .values(durum=sz.BelgeDurumu.HAZIR.value, surum=3)
        )
    return _belge(db, belge.id), _okuma(db, okuma.id)


def test_belge_kaydet_hazir_belgeyi_kayitli_yapar(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> None:
    belge, okuma = _hazir_belge(db, gelen, arsiv_dizini)

    with db.yazma_islemi() as oturum:
        sonuc = bl.belge_kaydet(
            oturum,
            belge_id=belge.id,
            gorulen_surum=belge.surum,
            islem_anahtari="bk-1",
            simdi=SIMDI,
        )

    assert sonuc.durum is sz.BelgeDurumu.KAYITLI
    assert sonuc.etkin_okuma_id == okuma.id and sonuc.surum == belge.surum + 1


def test_belge_kaydet_eski_surum_ve_hazir_olmayan_belge(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> None:
    belge, _ = _hazir_belge(db, gelen, arsiv_dizini)
    with pytest.raises(sz.HedefSurumuDegisti):
        with db.yazma_islemi() as oturum:
            bl.belge_kaydet(
                oturum,
                belge_id=belge.id,
                gorulen_surum=belge.surum - 1,
                islem_anahtari="bk-1",
            )
    assert _belge(db, belge.id).durum is sz.BelgeDurumu.HAZIR

    okunan = _belge_al(
        db, gelen, arsiv_dizini, ad="b.pdf", icerik=PDF + b"2", anahtar="al-2"
    ).belge
    with pytest.raises(sz.BelgeHazirDegil, match="ARSIVLENDI"):
        with db.yazma_islemi() as oturum:
            bl.belge_kaydet(
                oturum,
                belge_id=okunan.id,
                gorulen_surum=okunan.surum,
                islem_anahtari="bk-2",
            )


def test_sonuclanmamis_satir_belge_kaydini_engeller(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> None:
    """Aşama 7 KARAR_BEKLIYOR satır yazacak; C07 koşulu şimdiden duruyor."""
    belge, okuma = _hazir_okuma(db, gelen, arsiv_dizini)
    _gonder(db, okuma.id, [_satir(0)])
    with db.yazma_islemi() as oturum:
        oturum.execute(
            sema.okuma_satir.update().values(durum=sz.SatirDurumu.KARAR_BEKLIYOR.value)
        )

    with pytest.raises(sz.BelgeHazirDegil, match="KARAR_BEKLIYOR"):
        _tamamla(db, okuma.id)

    assert _okuma(db, okuma.id).durum is sz.OkumaDurumu.ACIK
    assert _belge(db, belge.id).durum is sz.BelgeDurumu.OKUNUYOR


# --- eşzamanlı süreçler ---------------------------------------------------------------

ALT_SUREC_BETIGI = """
import sys, time
from pathlib import Path
from defteriki import belgeler as bl
from defteriki import sozlesmeler as sz
from defteriki import veritabani as vt

vt_yolu, gelen, arsiv_dizini, kaynak, isaret, anahtar = sys.argv[1:7]
son = time.monotonic() + 20
while not Path(isaret).exists():
    if time.monotonic() > son:
        raise SystemExit("başlama işareti gelmedi")
    time.sleep(0.002)
db = vt.Veritabani(Path(vt_yolu))
try:
    sonuc = bl.belge_al(
        db,
        yol=kaynak,
        gelen_dizini=Path(gelen),
        belge_dizini=Path(arsiv_dizini),
        islem_anahtari=anahtar,
        aktor=sz.DenetimAktoru.COWORK,
    )
finally:
    db.kapat()
print(sonuc.belge.id, sonuc.dosya.id, sonuc.dosya.goreli_yol, sonuc.zaten_vardi)
"""


def test_es_zamanli_surecler_ayni_icerigi_tek_dosya_tek_belge_yapar(
    db: vt.Veritabani, gelen: Path, arsiv_dizini: Path
) -> None:
    """Dört süreç aynı anda aynı içeriği farklı adlarla getirir: arşivde tek
    fiziksel dosya, veritabanında tek arşiv kaydı ve tek belge, geçici dosya yok."""
    icerik = PDF + os.urandom(2 * arsiv.OKUMA_PARCA_BOYUTU)
    adlar = ["a.pdf", "b.pdf", "ekstre", "kopya.pdf"]
    kaynaklar = [_dosya_birak(gelen, ad, icerik) for ad in adlar]
    isaret = gelen.parent / "basla"

    surecler = [
        subprocess.Popen(
            [
                sys.executable,
                "-c",
                ALT_SUREC_BETIGI,
                str(db.yol),
                str(gelen),
                str(arsiv_dizini),
                str(kaynak),
                str(isaret),
                f"surec-{i}",
            ],
            env={**os.environ, "PYTHONUTF8": "1"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
        )
        for i, kaynak in enumerate(kaynaklar)
    ]
    time.sleep(0.5)  # hepsi import edip işareti beklesin
    isaret.write_text("basla")
    ciktilar = [s.communicate(timeout=120) for s in surecler]
    for surec, (_, hata) in zip(surecler, ciktilar, strict=True):
        assert surec.returncode == 0, hata

    satirlar = [cikti.split() for cikti, _ in ciktilar]
    belge_idleri = {int(s[0]) for s in satirlar}
    dosya_idleri = {int(s[1]) for s in satirlar}
    yollar = {s[2] for s in satirlar}
    assert len(belge_idleri) == 1 and len(dosya_idleri) == 1 and len(yollar) == 1
    assert sorted(s[3] for s in satirlar) == ["False", "True", "True", "True"]

    assert _sayi(db, sema.belge) == 1 and _sayi(db, sema.arsiv_dosya) == 1
    assert _sayi(db, sema.islem_anahtari) == 4  # her sürecin anahtarı kayıtlı
    dosyalar = [p for p in arsiv_dizini.rglob("*") if p.is_file()]
    assert [p.relative_to(arsiv_dizini).as_posix() for p in dosyalar] == list(yollar)
    assert dosyalar[0].read_bytes() == icerik
    assert not any((arsiv_dizini / arsiv.GECICI_DIZIN_ADI).iterdir())

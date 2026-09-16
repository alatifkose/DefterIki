"""Defter tanımlama, işlem anahtarı koruması, kapsam denetimi (Teslim 4.3)."""

import sqlite3
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

from defteriki import defterler as df
from defteriki import islem_anahtarlari, sema
from defteriki import sozlesmeler as sz
from defteriki import veritabani as vt

SIMDI = datetime(2026, 9, 16, 21, 0)
COWORK = sz.DenetimAktoru.COWORK


@pytest.fixture
def db(tmp_path: Path) -> Iterator[vt.Veritabani]:
    yol = tmp_path / "vt" / "defter.sqlite3"
    yol.parent.mkdir()
    veritabani = vt.Veritabani(yol, mesgul_bekleme_ms=200)
    sema.semayi_yukselt(veritabani)
    yield veritabani
    veritabani.kapat()


def _sayi(db: vt.Veritabani, tablo: sema.Table) -> int:
    with db.okuma_islemi() as oturum:
        return int(oturum.execute(select(func.count()).select_from(tablo)).scalar_one())


def _tanimla(
    db: vt.Veritabani, ad: str = "Ev", anahtar: str = "ilk"
) -> df.DefterTanimlamaSonucu:
    with db.yazma_islemi() as oturum:
        return df.defter_tanimla(
            oturum, ad=ad, islem_anahtari=anahtar, aktor=COWORK, simdi=SIMDI
        )


# --- tanımlama ---------------------------------------------------------------------


def test_defter_onay_bekliyor_dogar_ve_talep_acilir(db: vt.Veritabani) -> None:
    sonuc = _tanimla(db)

    assert sonuc.zaten_vardi is False
    assert sonuc.defter.durum is sz.DefterDurumu.ONAY_BEKLIYOR
    assert sonuc.defter.surum == 1
    assert sonuc.defter.ad == "Ev"
    assert sonuc.defter.olusturma_zamani == SIMDI
    talep = sonuc.onay_talebi
    assert talep.tur is sz.OnayTuru.DEFTER_TANIMLAMA
    assert talep.durum is sz.OnayDurumu.BEKLIYOR
    assert talep.hedef_id == sonuc.defter.id
    assert talep.hedef_surumu == 1
    assert talep.icerik == {"ad": "Ev"}
    assert talep.karar is None and talep.cozum_zamani is None


def test_ilk_defter_sistem_kapsamli_anahtarla_yazilir(db: vt.Veritabani) -> None:
    sonuc = _tanimla(db, anahtar="cowork-2026-09-16-01")

    with db.okuma_islemi() as oturum:
        anahtar = oturum.execute(select(sema.islem_anahtari)).one()
        olaylar = oturum.execute(
            select(sema.denetim_olay).order_by(sema.denetim_olay.c.id)
        ).all()

    assert anahtar.kapsam_turu == "SISTEM"
    assert anahtar.kapsam_id == islem_anahtarlari.SISTEM_KAPSAM_ID == 0
    assert anahtar.arac_adi == df.ARAC_DEFTER_TANIMLA
    assert anahtar.anahtar == "cowork-2026-09-16-01"
    assert anahtar.sonuc == {
        "defter_id": sonuc.defter.id,
        "onay_talebi_id": sonuc.onay_talebi.id,
    }
    assert [(o.eylem, o.aktor, o.sonraki_durum) for o in olaylar] == [
        (df.EYLEM_DEFTER_TANIMLA, "COWORK", "ONAY_BEKLIYOR"),
        ("onay_talebi_olustur", "COWORK", "BEKLIYOR"),
    ]
    assert all(o.islem_id == anahtar.id for o in olaylar)


def test_ayni_anahtar_ayni_icerik_yeni_defter_acmaz(db: vt.Veritabani) -> None:
    ilk = _tanimla(db, ad="Ev", anahtar="ilk")

    tekrar = _tanimla(db, ad="Ev", anahtar="ilk")

    assert tekrar.zaten_vardi is True
    assert tekrar.defter.id == ilk.defter.id
    assert tekrar.onay_talebi.id == ilk.onay_talebi.id
    assert _sayi(db, sema.defter) == 1
    assert _sayi(db, sema.onay_talep) == 1
    assert _sayi(db, sema.denetim_olay) == 2


def test_ayni_anahtar_farkli_icerik_cakisir_ve_yazmaz(db: vt.Veritabani) -> None:
    _tanimla(db, ad="Ev", anahtar="ilk")

    with pytest.raises(sz.AnahtarIcerikCakismasi) as bilgi:
        _tanimla(db, ad="İş", anahtar="ilk")

    assert bilgi.value.kod == "ANAHTAR_ICERIK_CAKISMASI"
    assert _sayi(db, sema.defter) == 1


def test_farkli_anahtar_ikinci_defter_acar(db: vt.Veritabani) -> None:
    ev = _tanimla(db, ad="Ev", anahtar="bir")
    is_ = _tanimla(db, ad="İş", anahtar="iki")

    with db.okuma_islemi() as oturum:
        liste = df.defter_listele(oturum)

    assert [d.id for d in liste] == [ev.defter.id, is_.defter.id]
    assert is_.defter.id == ev.defter.id + 1


@pytest.mark.parametrize(
    ("ad", "anahtar", "alan"),
    [("", "x", "ad"), ("  ", "x", "ad"), ("Ev", "", "islem_anahtari")],
)
def test_bos_ad_ve_bos_anahtar_reddedilir(
    db: vt.Veritabani, ad: str, anahtar: str, alan: str
) -> None:
    with pytest.raises(sz.GirdiGecersiz) as bilgi:
        _tanimla(db, ad=ad, anahtar=anahtar)

    assert bilgi.value.alan == alan
    assert _sayi(db, sema.defter) == 0


def test_islem_sahibi_cagirandir_hata_her_seyi_geri_alir(db: vt.Veritabani) -> None:
    with pytest.raises(RuntimeError, match="sonra patladı"):
        with db.yazma_islemi() as oturum:
            df.defter_tanimla(oturum, ad="Ev", islem_anahtari="ilk", aktor=COWORK)
            raise RuntimeError("sonra patladı")

    assert _sayi(db, sema.defter) == 0
    assert _sayi(db, sema.onay_talep) == 0
    assert _sayi(db, sema.islem_anahtari) == 0
    assert _sayi(db, sema.denetim_olay) == 0


def test_kullanici_beklerken_kilit_tutulmaz(db: vt.Veritabani) -> None:
    """Talep kalıcı; işlem kapanmış, başka bir yazar hemen kilit alabilir."""
    _tanimla(db)

    ham = sqlite3.connect(db.yol, isolation_level=None, timeout=0.2)
    try:
        ham.execute("BEGIN IMMEDIATE")  # kilit tutuluyor olsa burada patlardı
        ham.execute("ROLLBACK")
    finally:
        ham.close()


def test_sahip_bilgisi_serbest_json_saklanir(db: vt.Veritabani) -> None:
    with db.yazma_islemi() as oturum:
        sonuc = df.defter_tanimla(
            oturum,
            ad="Ev",
            islem_anahtari="ilk",
            aktor=COWORK,
            sahip_bilgisi={"kisi": "KISI ALFA", "sehir": "Edirne"},
            simdi=SIMDI,
        )

    assert sonuc.defter.sahip_bilgisi == {"kisi": "KISI ALFA", "sehir": "Edirne"}


# --- kapsam ve aktiflik ---------------------------------------------------------


def test_onay_uygulanmadan_defter_yazma_kabul_etmez(db: vt.Veritabani) -> None:
    sonuc = _tanimla(db)

    with db.okuma_islemi() as oturum:
        assert (
            df.defter_getir(oturum, sonuc.defter.id).durum
            is sz.DefterDurumu.ONAY_BEKLIYOR
        )
        with pytest.raises(sz.DefterUyusmazligi, match="ONAY_BEKLIYOR"):
            df.aktif_defteri_getir(oturum, sonuc.defter.id)


def test_olmayan_defter_defter_uyusmazligi(db: vt.Veritabani) -> None:
    with db.okuma_islemi() as oturum:
        with pytest.raises(sz.DefterUyusmazligi) as bilgi:
            df.defter_getir(oturum, 999)

    assert bilgi.value.kod == "DEFTER_UYUSMAZLIGI"


def test_baska_defterin_kaydina_erisim_kesilir(db: vt.Veritabani) -> None:
    ev = _tanimla(db, ad="Ev", anahtar="bir")
    is_ = _tanimla(db, ad="İş", anahtar="iki")

    with db.okuma_islemi() as oturum:
        df.defterde_oldugunu_dogrula(
            oturum,
            defter_id=ev.defter.id,
            tablo=sema.onay_talep,
            kimlik=ev.onay_talebi.id,
            alan="talep_id",
        )
        with pytest.raises(sz.DefterUyusmazligi) as bilgi:
            df.defterde_oldugunu_dogrula(
                oturum,
                defter_id=ev.defter.id,
                tablo=sema.onay_talep,
                kimlik=is_.onay_talebi.id,
                alan="talep_id",
            )

    assert bilgi.value.alan == "talep_id"


def test_listeleme_sayfalanir(db: vt.Veritabani) -> None:
    for i in range(5):
        _tanimla(db, ad=f"D{i}", anahtar=f"a{i}")

    with db.okuma_islemi() as oturum:
        ilk_iki = df.defter_listele(oturum, sayfalama=sz.Sayfalama(sinir=2))
        sonraki = df.defter_listele(
            oturum, sayfalama=sz.Sayfalama(sinir=2, baslangic=2)
        )

    assert [d.ad for d in ilk_iki] == ["D0", "D1"]
    assert [d.ad for d in sonraki] == ["D2", "D3"]

"""Onay talepleri ve karar uygulama (Teslim 4.3)."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from defteriki import defterler as df
from defteriki import onaylar as on
from defteriki import sema
from defteriki import sozlesmeler as sz
from defteriki import veritabani as vt

SIMDI = datetime(2026, 9, 16, 21, 0)
SONRA = SIMDI + timedelta(hours=3)
COWORK = sz.DenetimAktoru.COWORK


@pytest.fixture
def db(tmp_path: Path) -> Iterator[vt.Veritabani]:
    yol = tmp_path / "vt" / "onay.sqlite3"
    yol.parent.mkdir()
    veritabani = vt.Veritabani(yol, mesgul_bekleme_ms=200)
    sema.semayi_yukselt(veritabani)
    yield veritabani
    veritabani.kapat()


@pytest.fixture
def bekleyen(db: vt.Veritabani) -> df.DefterTanimlamaSonucu:
    with db.yazma_islemi() as oturum:
        return df.defter_tanimla(
            oturum, ad="Ev", islem_anahtari="ilk", aktor=COWORK, simdi=SIMDI
        )


def _karar(
    db: vt.Veritabani,
    sonuc: df.DefterTanimlamaSonucu,
    *,
    onaylandi: bool,
    gorulen: int = 1,
    gerekce: str | None = None,
) -> on.OnayTalebi:
    with db.yazma_islemi() as oturum:
        return on.karar_uygula(
            oturum,
            defter_id=sonuc.defter.id,
            talep_id=sonuc.onay_talebi.id,
            gorulen_hedef_surumu=gorulen,
            karar=on.Karar(onaylandi=onaylandi, gerekce=gerekce),
            simdi=SONRA,
        )


def test_onay_defteri_aktif_yapar_surumu_artirir(
    db: vt.Veritabani, bekleyen: df.DefterTanimlamaSonucu
) -> None:
    talep = _karar(db, bekleyen, onaylandi=True, gerekce="benim defterim")

    assert talep.durum is sz.OnayDurumu.ONAYLANDI
    assert talep.cozum_zamani == SONRA
    assert talep.karar == {
        "onaylandi": True,
        "gerekce": "benim defterim",
        "aktor": "KULLANICI",
        "gorulen_hedef_surumu": 1,
    }
    with db.okuma_islemi() as oturum:
        defter = df.aktif_defteri_getir(oturum, bekleyen.defter.id)
        olaylar = oturum.execute(
            select(sema.denetim_olay).order_by(sema.denetim_olay.c.id)
        ).all()
    assert defter.durum is sz.DefterDurumu.AKTIF
    assert defter.surum == 2
    assert [
        (o.eylem, o.aktor, o.onceki_durum, o.sonraki_durum) for o in olaylar[2:]
    ] == [
        (df.EYLEM_DEFTER_ONAYI, "KULLANICI", "ONAY_BEKLIYOR", "AKTIF"),
        (on.EYLEM_KARAR, "KULLANICI", "BEKLIYOR", "ONAYLANDI"),
    ]


def test_red_defteri_pasif_yapar(
    db: vt.Veritabani, bekleyen: df.DefterTanimlamaSonucu
) -> None:
    talep = _karar(db, bekleyen, onaylandi=False, gerekce="yanlışlıkla")

    assert talep.durum is sz.OnayDurumu.REDDEDILDI
    with db.okuma_islemi() as oturum:
        defter = df.defter_getir(oturum, bekleyen.defter.id)
        with pytest.raises(sz.DefterUyusmazligi, match="PASIF"):
            df.aktif_defteri_getir(oturum, bekleyen.defter.id)
    assert defter.durum is sz.DefterDurumu.PASIF
    assert defter.surum == 2


def test_eski_surumle_karar_reddedilir_ve_yazilmaz(
    db: vt.Veritabani, bekleyen: df.DefterTanimlamaSonucu
) -> None:
    """Kullanıcının ekranda gördüğü sürüm hedefin güncel sürümüyle uyuşmalı."""
    with pytest.raises(sz.HedefSurumuDegisti) as bilgi:
        _karar(db, bekleyen, onaylandi=True, gorulen=0)

    assert bilgi.value.kod == "HEDEF_SURUMU_DEGISTI"
    with db.okuma_islemi() as oturum:
        talep = on.talep_getir(
            oturum, defter_id=bekleyen.defter.id, talep_id=bekleyen.onay_talebi.id
        )
        defter = df.defter_getir(oturum, bekleyen.defter.id)
    assert talep.durum is sz.OnayDurumu.BEKLIYOR
    assert defter.durum is sz.DefterDurumu.ONAY_BEKLIYOR and defter.surum == 1


def test_hedef_arkadan_degisirse_talep_eskir(
    db: vt.Veritabani, bekleyen: df.DefterTanimlamaSonucu
) -> None:
    """Talep açıldıktan sonra hedef değişmişse doğru görünen sürümle bile uygulanmaz."""
    with db.yazma_islemi() as oturum:
        oturum.execute(
            sema.defter.update()
            .where(sema.defter.c.id == bekleyen.defter.id)
            .values(surum=2)
        )

    with pytest.raises(sz.HedefSurumuDegisti):
        _karar(db, bekleyen, onaylandi=True, gorulen=2)


def test_sonuclanmis_talebe_yeniden_karar_verilemez(
    db: vt.Veritabani, bekleyen: df.DefterTanimlamaSonucu
) -> None:
    _karar(db, bekleyen, onaylandi=True)

    with pytest.raises(sz.GirdiGecersiz, match="zaten sonuçlanmış"):
        _karar(db, bekleyen, onaylandi=False, gorulen=2)

    with db.okuma_islemi() as oturum:
        assert (
            df.defter_getir(oturum, bekleyen.defter.id).durum is sz.DefterDurumu.AKTIF
        )


def test_baska_defterin_talebine_karar_verilemez(
    db: vt.Veritabani, bekleyen: df.DefterTanimlamaSonucu
) -> None:
    with db.yazma_islemi() as oturum:
        baska = df.defter_tanimla(
            oturum, ad="İş", islem_anahtari="iki", aktor=COWORK, simdi=SIMDI
        )

    with pytest.raises(sz.DefterUyusmazligi):
        with db.yazma_islemi() as oturum:
            on.karar_uygula(
                oturum,
                defter_id=baska.defter.id,  # yanlış defter
                talep_id=bekleyen.onay_talebi.id,
                gorulen_hedef_surumu=1,
                karar=on.Karar(onaylandi=True),
                simdi=SONRA,
            )


def test_bekleyenler_yalniz_bekliyor_olanlar(
    db: vt.Veritabani, bekleyen: df.DefterTanimlamaSonucu
) -> None:
    with db.yazma_islemi() as oturum:
        ikinci = on.talep_olustur(
            oturum,
            defter_id=bekleyen.defter.id,
            tur=sz.OnayTuru.DEFTER_TANIMLAMA,
            hedef_id=bekleyen.defter.id,
            hedef_surumu=1,
            icerik={"not": "ikinci"},
            simdi=SIMDI,
            aktor=COWORK,
        )
    with db.okuma_islemi() as oturum:
        once = on.bekleyenleri_listele(oturum, defter_id=bekleyen.defter.id)

    _karar(db, bekleyen, onaylandi=True)

    with db.okuma_islemi() as oturum:
        sonra = on.bekleyenleri_listele(oturum, defter_id=bekleyen.defter.id)
        sayfali = on.bekleyenleri_listele(
            oturum, defter_id=bekleyen.defter.id, sayfalama=sz.Sayfalama(sinir=1)
        )

    assert [t.id for t in once] == [bekleyen.onay_talebi.id, ikinci.id]
    assert [t.id for t in sonra] == [ikinci.id]
    assert len(sayfali) == 1


def test_karar_uygulamasi_olmayan_tur_acik_hata(
    db: vt.Veritabani,
    bekleyen: df.DefterTanimlamaSonucu,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(on.KARAR_ETKILERI, sz.OnayTuru.DEFTER_TANIMLAMA)

    with pytest.raises(sz.GirdiGecersiz, match="karar uygulaması henüz yok"):
        _karar(db, bekleyen, onaylandi=True)


def test_karar_hatasi_her_seyi_geri_alir(
    db: vt.Veritabani, bekleyen: df.DefterTanimlamaSonucu
) -> None:
    with pytest.raises(RuntimeError, match="ekran çöktü"):
        with db.yazma_islemi() as oturum:
            on.karar_uygula(
                oturum,
                defter_id=bekleyen.defter.id,
                talep_id=bekleyen.onay_talebi.id,
                gorulen_hedef_surumu=1,
                karar=on.Karar(onaylandi=True),
                simdi=SONRA,
            )
            raise RuntimeError("ekran çöktü")

    with db.okuma_islemi() as oturum:
        defter = df.defter_getir(oturum, bekleyen.defter.id)
        talep = on.talep_getir(
            oturum, defter_id=bekleyen.defter.id, talep_id=bekleyen.onay_talebi.id
        )
    assert defter.durum is sz.DefterDurumu.ONAY_BEKLIYOR and defter.surum == 1
    assert talep.durum is sz.OnayDurumu.BEKLIYOR

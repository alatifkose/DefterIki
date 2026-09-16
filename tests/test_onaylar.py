"""Onay talepleri ve karar uygulama (Teslim 4.3).

Hedef olarak ``nesne`` tablosuna doğrudan satır yazılır (nesne işlevleri 4.4'te);
karar etkisi testte kaydedilir: onay → AKTIF, red → PASIF, sürüm bir artar.
"""

import sqlite3
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import func, select

from defteriki import onaylar as on
from defteriki import sema
from defteriki import sozlesmeler as sz
from defteriki import veritabani as vt
from defteriki.denetim import olay_yaz

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


def _nesne_onayini_uygula(
    oturum: object, talep: on.OnayTalebi, karar: on.Karar, simdi: datetime
) -> None:
    """Test etkisi: 4.4'te nesneler.py'nin kaydedeceği etkinin sade hâli."""
    from sqlalchemy.orm import Session

    assert isinstance(oturum, Session)
    yeni = sz.NesneDurumu.AKTIF if karar.onaylandi else sz.NesneDurumu.PASIF
    oturum.execute(
        sema.nesne.update()
        .where(sema.nesne.c.id == talep.hedef_id)
        .values(durum=yeni.value, surum=talep.hedef_surumu + 1)
    )
    olay_yaz(
        oturum,
        aktor=sz.DenetimAktoru.KULLANICI,
        eylem="nesne_onayi",
        hedef=f"nesne:{talep.hedef_id}",
        simdi=simdi,
        sonraki_durum=yeni.value,
    )


@pytest.fixture(autouse=True)
def etki(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(
        on.KARAR_ETKILERI, sz.OnayTuru.NESNE_ACILISI, _nesne_onayini_uygula
    )


@pytest.fixture
def bekleyen(db: vt.Veritabani) -> tuple[int, on.OnayTalebi]:
    """ENGELLI durumda bir nesne ve onun NESNE_ACILISI talebi."""
    with db.yazma_islemi() as oturum:
        nesne_id = int(
            oturum.execute(
                sema.nesne.insert()
                .values(seviye=0, durum="ENGELLI", surum=1, olusturma_zamani=SIMDI)
                .returning(sema.nesne.c.id)
            ).scalar_one()
        )
        talep = on.talep_olustur(
            oturum,
            tur=sz.OnayTuru.NESNE_ACILISI,
            hedef_id=nesne_id,
            hedef_surumu=1,
            icerik={"ad": "QNB"},
            simdi=SIMDI,
            aktor=COWORK,
        )
    return nesne_id, talep


def _nesne_durumu(db: vt.Veritabani, nesne_id: int) -> tuple[str, int]:
    with db.okuma_islemi() as oturum:
        satir = oturum.execute(
            select(sema.nesne.c.durum, sema.nesne.c.surum).where(
                sema.nesne.c.id == nesne_id
            )
        ).one()
    return str(satir.durum), int(satir.surum)


def _karar(
    db: vt.Veritabani,
    talep_id: int,
    *,
    onaylandi: bool,
    gorulen: int = 1,
    gerekce: str | None = None,
) -> on.OnayTalebi:
    with db.yazma_islemi() as oturum:
        return on.karar_uygula(
            oturum,
            talep_id=talep_id,
            gorulen_hedef_surumu=gorulen,
            karar=on.Karar(onaylandi=onaylandi, gerekce=gerekce),
            simdi=SONRA,
        )


# --- talep ------------------------------------------------------------------------


def test_talep_bekliyor_dogar_ve_denetim_olayi_yazar(
    db: vt.Veritabani, bekleyen: tuple[int, on.OnayTalebi]
) -> None:
    nesne_id, talep = bekleyen

    assert talep.tur is sz.OnayTuru.NESNE_ACILISI
    assert talep.durum is sz.OnayDurumu.BEKLIYOR
    assert talep.hedef_id == nesne_id and talep.hedef_surumu == 1
    assert talep.icerik == {"ad": "QNB"}
    assert talep.karar is None and talep.cozum_zamani is None
    assert talep.olusturma_zamani == SIMDI
    with db.okuma_islemi() as oturum:
        (olay,) = oturum.execute(select(sema.denetim_olay)).all()
    assert (olay.eylem, olay.aktor, olay.gerekce, olay.sonraki_durum) == (
        on.EYLEM_TALEP_OLUSTUR,
        "COWORK",
        "NESNE_ACILISI",
        "BEKLIYOR",
    )


def test_kullanici_beklerken_kilit_tutulmaz(
    db: vt.Veritabani, bekleyen: tuple[int, on.OnayTalebi]
) -> None:
    """Talep kalıcı; işlem kapanmış, başka bir yazar hemen kilit alabilir."""
    ham = sqlite3.connect(db.yol, isolation_level=None, timeout=0.2)
    try:
        ham.execute("BEGIN IMMEDIATE")  # kilit tutuluyor olsa burada patlardı
        ham.execute("ROLLBACK")
    finally:
        ham.close()
    with db.okuma_islemi() as oturum:
        assert on.talep_getir(oturum, bekleyen[1].id).durum is sz.OnayDurumu.BEKLIYOR


def test_olmayan_talep_hedef_bulunamadi(db: vt.Veritabani) -> None:
    with db.okuma_islemi() as oturum:
        with pytest.raises(sz.HedefBulunamadi) as bilgi:
            on.talep_getir(oturum, 999)

    assert bilgi.value.kod == "HEDEF_BULUNAMADI"


# --- karar --------------------------------------------------------------------------


def test_onay_hedefi_aktif_yapar_surumu_artirir(
    db: vt.Veritabani, bekleyen: tuple[int, on.OnayTalebi]
) -> None:
    nesne_id, talep = bekleyen

    sonuc = _karar(db, talep.id, onaylandi=True, gerekce="bu benim bankam")

    assert sonuc.durum is sz.OnayDurumu.ONAYLANDI
    assert sonuc.cozum_zamani == SONRA
    assert sonuc.karar == {
        "onaylandi": True,
        "gerekce": "bu benim bankam",
        "aktor": "KULLANICI",
        "gorulen_hedef_surumu": 1,
    }
    assert _nesne_durumu(db, nesne_id) == ("AKTIF", 2)
    with db.okuma_islemi() as oturum:
        olaylar = oturum.execute(
            select(sema.denetim_olay).order_by(sema.denetim_olay.c.id)
        ).all()
    assert [
        (o.eylem, o.aktor, o.onceki_durum, o.sonraki_durum) for o in olaylar[1:]
    ] == [
        ("nesne_onayi", "KULLANICI", None, "AKTIF"),
        (on.EYLEM_KARAR, "KULLANICI", "BEKLIYOR", "ONAYLANDI"),
    ]


def test_red_hedefi_pasif_yapar(
    db: vt.Veritabani, bekleyen: tuple[int, on.OnayTalebi]
) -> None:
    nesne_id, talep = bekleyen

    sonuc = _karar(db, talep.id, onaylandi=False, gerekce="yanlış banka")

    assert sonuc.durum is sz.OnayDurumu.REDDEDILDI
    assert _nesne_durumu(db, nesne_id) == ("PASIF", 2)


def test_eski_surumle_karar_reddedilir_ve_yazilmaz(
    db: vt.Veritabani, bekleyen: tuple[int, on.OnayTalebi]
) -> None:
    """Kullanıcının ekranda gördüğü sürüm hedefin güncel sürümüyle uyuşmalı."""
    nesne_id, talep = bekleyen

    with pytest.raises(sz.HedefSurumuDegisti) as bilgi:
        _karar(db, talep.id, onaylandi=True, gorulen=0)

    assert bilgi.value.kod == "HEDEF_SURUMU_DEGISTI"
    with db.okuma_islemi() as oturum:
        assert on.talep_getir(oturum, talep.id).durum is sz.OnayDurumu.BEKLIYOR
    assert _nesne_durumu(db, nesne_id) == ("ENGELLI", 1)


def test_hedef_arkadan_degisirse_talep_eskir(
    db: vt.Veritabani, bekleyen: tuple[int, on.OnayTalebi]
) -> None:
    """Talep açıldıktan sonra hedef değişmişse doğru görünen sürümle bile uygulanmaz."""
    nesne_id, talep = bekleyen
    with db.yazma_islemi() as oturum:
        oturum.execute(
            sema.nesne.update().where(sema.nesne.c.id == nesne_id).values(surum=2)
        )

    with pytest.raises(sz.HedefSurumuDegisti):
        _karar(db, talep.id, onaylandi=True, gorulen=2)


def test_sonuclanmis_talebe_yeniden_karar_verilemez(
    db: vt.Veritabani, bekleyen: tuple[int, on.OnayTalebi]
) -> None:
    nesne_id, talep = bekleyen
    _karar(db, talep.id, onaylandi=True)

    with pytest.raises(sz.GirdiGecersiz, match="zaten sonuçlanmış"):
        _karar(db, talep.id, onaylandi=False, gorulen=2)

    assert _nesne_durumu(db, nesne_id) == ("AKTIF", 2)


def test_hedefi_silinmis_talep_hedef_bulunamadi(
    db: vt.Veritabani, bekleyen: tuple[int, on.OnayTalebi]
) -> None:
    nesne_id, talep = bekleyen
    with db.yazma_islemi() as oturum:
        oturum.execute(sema.nesne.delete().where(sema.nesne.c.id == nesne_id))

    with pytest.raises(sz.HedefBulunamadi, match="hedefi"):
        _karar(db, talep.id, onaylandi=True)


def test_bekleyenler_yalniz_bekliyor_olanlar(
    db: vt.Veritabani, bekleyen: tuple[int, on.OnayTalebi]
) -> None:
    nesne_id, talep = bekleyen
    with db.yazma_islemi() as oturum:
        ikinci = on.talep_olustur(
            oturum,
            tur=sz.OnayTuru.NESNE_ACILISI,
            hedef_id=nesne_id,
            hedef_surumu=1,
            icerik={"not": "ikinci"},
            simdi=SIMDI,
            aktor=COWORK,
        )
    with db.okuma_islemi() as oturum:
        once = on.bekleyenleri_listele(oturum)

    _karar(db, talep.id, onaylandi=True)

    with db.okuma_islemi() as oturum:
        sonra = on.bekleyenleri_listele(oturum)
        sayfali = on.bekleyenleri_listele(oturum, sayfalama=sz.Sayfalama(sinir=1))

    assert [t.id for t in once] == [talep.id, ikinci.id]
    assert [t.id for t in sonra] == [ikinci.id]
    assert len(sayfali) == 1


def test_karar_uygulamasi_olmayan_tur_acik_hata(
    db: vt.Veritabani,
    bekleyen: tuple[int, on.OnayTalebi],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delitem(on.KARAR_ETKILERI, sz.OnayTuru.NESNE_ACILISI)

    with pytest.raises(sz.GirdiGecersiz, match="karar uygulaması henüz yok"):
        _karar(db, bekleyen[1].id, onaylandi=True)


def test_karar_hatasi_her_seyi_geri_alir(
    db: vt.Veritabani, bekleyen: tuple[int, on.OnayTalebi]
) -> None:
    nesne_id, talep = bekleyen

    with pytest.raises(RuntimeError, match="ekran çöktü"):
        with db.yazma_islemi() as oturum:
            on.karar_uygula(
                oturum,
                talep_id=talep.id,
                gorulen_hedef_surumu=1,
                karar=on.Karar(onaylandi=True),
                simdi=SONRA,
            )
            raise RuntimeError("ekran çöktü")

    assert _nesne_durumu(db, nesne_id) == ("ENGELLI", 1)
    with db.okuma_islemi() as oturum:
        assert on.talep_getir(oturum, talep.id).durum is sz.OnayDurumu.BEKLIYOR
        olay_sayisi = oturum.execute(
            select(func.count()).select_from(sema.denetim_olay)
        ).scalar_one()
    assert olay_sayisi == 1  # yalnız talep oluşturma olayı

"""Hareket yazma (Teslim 4.6): kaynak satırı zorunlu, anahtar, tek etki (S18 tek süreç).

Akış: belge_al → okuma_baslat → nesne AKTIF → hareket_yaz (satır + kayıt + etki +
kaynak bağı, tek işlem) → okuma_tamamla → KAYITLI.
"""

from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

from defteriki import belgeler as bl
from defteriki import finansal_kurallar as fk
from defteriki import kayitlar as ky
from defteriki import nesneler as ns
from defteriki import onaylar as on
from defteriki import sema
from defteriki import sozlesmeler as sz
from defteriki import veritabani as vt

SIMDI = datetime(2026, 9, 17, 11, 0)
COWORK = sz.DenetimAktoru.COWORK
PDF = b"%PDF-1.7\n%sentetik ekstre 4.6\n"
Satir = bl.SatirGirdisi


@pytest.fixture
def db(tmp_path: Path) -> Iterator[vt.Veritabani]:
    yol = tmp_path / "vt" / "kayit.sqlite3"
    yol.parent.mkdir()
    veritabani = vt.Veritabani(yol, mesgul_bekleme_ms=200)
    sema.semayi_yukselt(veritabani)
    yield veritabani
    veritabani.kapat()


@pytest.fixture
def dizinler(tmp_path: Path) -> tuple[Path, Path]:
    gelen = tmp_path / "gelen"
    arsiv = tmp_path / "belgeler"
    gelen.mkdir()
    arsiv.mkdir()
    return gelen, arsiv


@pytest.fixture
def hesap(db: vt.Veritabani) -> int:
    """AKTIF bir hesap nesnesi (ME)."""
    return _aktif_nesne(db, "ME", "n-me")


def _aktif_nesne(db: vt.Veritabani, ad: str, anahtar: str) -> int:
    with db.yazma_islemi() as oturum:
        sonuc = ns.nesne_tanimla(
            oturum,
            ozellikler=[ns.OzellikGirdisi("ad", ad)],
            islem_anahtari=anahtar,
            aktor=COWORK,
            simdi=SIMDI,
        )
    with db.yazma_islemi() as oturum:
        on.karar_uygula(
            oturum,
            talep_id=sonuc.onay_talebi.id,
            gorulen_hedef_surumu=1,
            karar=on.Karar(onaylandi=True),
            simdi=SIMDI,
        )
    return sonuc.nesne.id


@pytest.fixture
def okuma(db: vt.Veritabani, dizinler: tuple[Path, Path]) -> bl.Okuma:
    return _okuma_ac(db, dizinler, "ekstre.pdf", PDF, "al-1", "ob-1")


def _okuma_ac(
    db: vt.Veritabani,
    dizinler: tuple[Path, Path],
    ad: str,
    icerik: bytes,
    al_anahtari: str,
    ob_anahtari: str,
) -> bl.Okuma:
    gelen, arsiv = dizinler
    (gelen / ad).write_bytes(icerik)
    belge = bl.belge_al(
        db,
        yol=str(gelen / ad),
        gelen_dizini=gelen,
        belge_dizini=arsiv,
        islem_anahtari=al_anahtari,
        aktor=COWORK,
        simdi=SIMDI,
    ).belge
    with db.yazma_islemi() as oturum:
        return bl.okuma_baslat(
            oturum,
            belge_id=belge.id,
            sema_surumu="cowork-0.1",
            belge_dizini=arsiv,
            islem_anahtari=ob_anahtari,
            aktor=COWORK,
            simdi=SIMDI,
        )


def _satir(n: int, **ham: object) -> bl.SatirGirdisi:
    return Satir(f"s{n}", n, {"aciklama": f"hareket {n}", **ham})


def _hareket(
    nesne_id: int, tutar: int = 10_000, **degisiklik: object
) -> fk.HesapHareketi:
    alanlar: dict[str, object] = {
        "nesne_id": nesne_id,
        "yon": "ARTTIR",
        "tutar_kurus": tutar,
        "islem_tarihi": date(2026, 8, 1),
    }
    alanlar.update(degisiklik)
    return fk.HesapHareketi(**alanlar)  # pyright: ignore[reportArgumentType]


def _yaz(
    db: vt.Veritabani,
    okuma_id: int,
    satir: bl.SatirGirdisi,
    hareket: fk.HesapHareketi,
    *,
    anahtar: str = "h-1",
) -> ky.HareketSonucu:
    with db.yazma_islemi() as oturum:
        return ky.hareket_yaz(
            oturum,
            okuma_id=okuma_id,
            satir=satir,
            hareket=hareket,
            islem_anahtari=anahtar,
            aktor=COWORK,
            simdi=SIMDI,
        )


def _sayi(db: vt.Veritabani, tablo: sema.Table) -> int:
    with db.okuma_islemi() as oturum:
        return int(oturum.execute(select(func.count()).select_from(tablo)).scalar_one())


# --- yazma ---------------------------------------------------------------------------


def test_hareket_kayit_etki_kaynak_ve_satiri_tek_islemde_yazar(
    db: vt.Veritabani, okuma: bl.Okuma, hesap: int
) -> None:
    sonuc = _yaz(
        db,
        okuma.id,
        _satir(0, tutar="100,00"),
        _hareket(hesap, 10_000, valor_tarihi="2026-08-02", aciklama="Maaş"),
    )

    assert sonuc.zaten_vardi is False
    kayit = sonuc.kayit.kayit
    assert kayit.asil_nesne_id == hesap and kayit.durum is sz.KayitDurumu.AKTIF
    assert (kayit.islem_tarihi, kayit.valor_tarihi, kayit.aciklama) == (
        date(2026, 8, 1),
        date(2026, 8, 2),
        "Maaş",
    )
    (etki,) = sonuc.kayit.etkiler
    assert (
        etki.nesne_id,
        etki.eksen,
        etki.yon,
        etki.tutar_kurus,
        etki.para_birimi,
    ) == (
        hesap,
        sz.Eksen.VARLIK,
        sz.Yon.ARTTIR,
        10_000,
        sz.ParaBirimi.TRY,
    )
    (kaynak,) = sonuc.kayit.kaynaklar
    assert kaynak.okuma_satir_id == sonuc.satir.id
    assert (kaynak.rol, kaynak.durum) == (sz.KaynakRolu.ASIL, sz.KaynakDurumu.AKTIF)
    assert sonuc.satir.durum is sz.SatirDurumu.YAZILDI
    assert sonuc.satir.ham == {"aciklama": "hareket 0", "tutar": "100,00"}

    with db.okuma_islemi() as oturum:
        olay = oturum.execute(
            select(sema.denetim_olay).where(sema.denetim_olay.c.eylem == "hareket_yaz")
        ).one()
    assert olay.hedef == f"kayit:{kayit.id}" and olay.islem_id is not None
    assert "ARTTIR 10000 TRY" in str(olay.gerekce)


def test_s18_ayni_anahtar_iki_kez_tek_etki(
    db: vt.Veritabani, okuma: bl.Okuma, hesap: int
) -> None:
    ilk = _yaz(db, okuma.id, _satir(0), _hareket(hesap), anahtar="h-1")
    tekrar = _yaz(db, okuma.id, _satir(0), _hareket(hesap), anahtar="h-1")

    assert tekrar.zaten_vardi is True
    assert tekrar.kayit.kayit.id == ilk.kayit.kayit.id
    assert _sayi(db, sema.etki) == 1 and _sayi(db, sema.kayit) == 1
    assert _sayi(db, sema.okuma_satir) == 1

    with pytest.raises(sz.AnahtarIcerikCakismasi):
        _yaz(db, okuma.id, _satir(0), _hareket(hesap, 99), anahtar="h-1")
    assert _sayi(db, sema.etki) == 1


def test_ayni_satir_farkli_anahtar_ayni_hareket_tekrar_gonderim(
    db: vt.Veritabani, okuma: bl.Okuma, hesap: int
) -> None:
    """Tam Plan 8.5.1: aynı okuma, aynı satır anahtarı, aynı içerik → tekrar."""
    ilk = _yaz(db, okuma.id, _satir(0), _hareket(hesap), anahtar="h-1")
    tekrar = _yaz(db, okuma.id, _satir(0), _hareket(hesap), anahtar="h-2")

    assert tekrar.zaten_vardi is True and tekrar.kayit.kayit.id == ilk.kayit.kayit.id
    assert _sayi(db, sema.etki) == 1


def test_ayni_satira_farkli_hareket_kaynak_cakismasi(
    db: vt.Veritabani, okuma: bl.Okuma, hesap: int
) -> None:
    _yaz(db, okuma.id, _satir(0), _hareket(hesap, 10_000), anahtar="h-1")

    with pytest.raises(sz.KaynakCakismasi):
        _yaz(db, okuma.id, _satir(0), _hareket(hesap, 10_001), anahtar="h-2")
    with pytest.raises(sz.KaynakCakismasi):
        _yaz(db, okuma.id, _satir(0), _hareket(hesap, yon="AZALT"), anahtar="h-3")

    assert _sayi(db, sema.kayit) == 1 and _sayi(db, sema.etki) == 1


def test_ayni_satir_anahtari_farkli_ham_paket_duser(
    db: vt.Veritabani, okuma: bl.Okuma, hesap: int
) -> None:
    _yaz(db, okuma.id, _satir(0), _hareket(hesap), anahtar="h-1")
    with pytest.raises(sz.AnahtarIcerikCakismasi, match="satır anahtarı"):
        _yaz(db, okuma.id, _satir(0, ek="x"), _hareket(hesap), anahtar="h-2")
    assert _sayi(db, sema.kayit) == 1


def test_kaydi_olmayan_mevcut_satira_kayit_baglanir(
    db: vt.Veritabani, okuma: bl.Okuma, hesap: int
) -> None:
    """4.5 gönderimiyle yazılmış satır sonradan hareketle desteklenebilir."""
    with db.yazma_islemi() as oturum:
        bl.satir_gonder(
            oturum,
            okuma_id=okuma.id,
            satirlar=[_satir(0)],
            islem_anahtari="p1",
            aktor=COWORK,
            simdi=SIMDI,
        )
    sonuc = _yaz(db, okuma.id, _satir(0), _hareket(hesap))
    assert sonuc.zaten_vardi is False
    assert _sayi(db, sema.okuma_satir) == 1 and _sayi(db, sema.kayit) == 1


# --- S10 ve nesne durumu ---------------------------------------------------------


def test_s10_okumasiz_ya_da_kapali_okumaya_hareket_yazilmaz(
    db: vt.Veritabani, okuma: bl.Okuma, hesap: int
) -> None:
    with pytest.raises(sz.HedefBulunamadi):
        _yaz(db, 404, _satir(0), _hareket(hesap))

    with db.yazma_islemi() as oturum:
        bl.okuma_tamamla(
            oturum, okuma_id=okuma.id, islem_anahtari="ot-1", aktor=COWORK, simdi=SIMDI
        )
    with pytest.raises(sz.GirdiGecersiz, match="TAMAMLANDI"):
        _yaz(db, okuma.id, _satir(0), _hareket(hesap))

    for tablo in (sema.kayit, sema.etki, sema.kayit_kaynak):
        assert _sayi(db, tablo) == 0


def test_kapsam_disi_satira_hareket_baglanmaz(
    db: vt.Veritabani, okuma: bl.Okuma, hesap: int
) -> None:
    baslik = Satir("baslik", 0, {"metin": "Devreden"}, sz.SatirDurumu.KAPSAM_DISI)
    with pytest.raises(sz.GirdiGecersiz, match="YAZILDI"):
        _yaz(db, okuma.id, baslik, _hareket(hesap))
    assert _sayi(db, sema.okuma_satir) == 0


def test_bicim_hatali_satir_hareketi_de_dusurur(
    db: vt.Veritabani, okuma: bl.Okuma, hesap: int
) -> None:
    with pytest.raises(sz.GirdiGecersiz) as hata:
        _yaz(db, okuma.id, Satir("", 0, {"a": 1}), _hareket(hesap))
    assert hata.value.alan == "satir_anahtari"
    assert _sayi(db, sema.kayit) == 0 and _sayi(db, sema.islem_anahtari) == 3


def test_gecersiz_tutar_veritabanina_dokunmadan_reddedilir(
    db: vt.Veritabani, okuma: bl.Okuma, hesap: int
) -> None:
    with pytest.raises(sz.TutarGecersiz):
        _yaz(db, okuma.id, _satir(0), _hareket(hesap, tutar=12.5))  # pyright: ignore[reportArgumentType]
    assert _sayi(db, sema.islem_anahtari) == 3  # yalnız belge_al, okuma_baslat, nesne


def test_onay_bekleyen_ve_engelli_nesneye_yazilmaz(
    db: vt.Veritabani, okuma: bl.Okuma
) -> None:
    with db.yazma_islemi() as oturum:
        bekleyen = ns.nesne_tanimla(
            oturum,
            ozellikler=[ns.OzellikGirdisi("ad", "GK")],
            islem_anahtari="n-gk",
            aktor=COWORK,
            simdi=SIMDI,
        ).nesne
    with pytest.raises(sz.GirdiGecersiz, match="ONAY_BEKLIYOR"):
        _yaz(db, okuma.id, _satir(0), _hareket(bekleyen.id))

    with db.yazma_islemi() as oturum:
        oturum.execute(
            sema.nesne.update()
            .where(sema.nesne.c.id == bekleyen.id)
            .values(durum=sz.NesneDurumu.ENGELLI.value)
        )
    with pytest.raises(sz.NesneEngelli):
        _yaz(db, okuma.id, _satir(0), _hareket(bekleyen.id), anahtar="h-2")

    with pytest.raises(sz.HedefBulunamadi):
        _yaz(db, okuma.id, _satir(0), _hareket(999), anahtar="h-3")
    assert _sayi(db, sema.kayit) == 0 and _sayi(db, sema.okuma_satir) == 0


def test_hata_her_seyi_geri_alir(
    db: vt.Veritabani, okuma: bl.Okuma, hesap: int
) -> None:
    with pytest.raises(RuntimeError, match="sonra patladı"):
        with db.yazma_islemi() as oturum:
            ky.hareket_yaz(
                oturum,
                okuma_id=okuma.id,
                satir=_satir(0),
                hareket=_hareket(hesap),
                islem_anahtari="h-1",
                aktor=COWORK,
            )
            raise RuntimeError("sonra patladı")
    for tablo in (sema.kayit, sema.etki, sema.kayit_kaynak, sema.okuma_satir):
        assert _sayi(db, tablo) == 0


def test_ucta_uca_hareketli_belge_kayitli_olur(
    db: vt.Veritabani, okuma: bl.Okuma, hesap: int
) -> None:
    _yaz(db, okuma.id, _satir(0), _hareket(hesap, 10_000), anahtar="h-1")
    _yaz(db, okuma.id, _satir(1), _hareket(hesap, 2_500, yon="AZALT"), anahtar="h-2")

    with db.yazma_islemi() as oturum:
        sonuc = bl.okuma_tamamla(
            oturum,
            okuma_id=okuma.id,
            islem_anahtari="ot-1",
            aktor=COWORK,
            tamlik=bl.Tamlik(beklenen_satir_sayisi=2),
            simdi=SIMDI,
        )
    assert sonuc.belge.durum is sz.BelgeDurumu.KAYITLI
    with db.okuma_islemi() as oturum:
        with pytest.raises(sz.HedefBulunamadi):
            ky.kayit_getir(oturum, 99)
        ayrinti = ky.kayit_getir(oturum, 2)
    assert ayrinti.etkiler[0].yon is sz.Yon.AZALT

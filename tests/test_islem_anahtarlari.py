"""İşlem anahtarı koruması (K08; Teslim 4.3)."""

from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from defteriki import islem_anahtarlari as ia
from defteriki import sema
from defteriki import sozlesmeler as sz
from defteriki import veritabani as vt

SIMDI = datetime(2026, 9, 16, 21, 0)


@pytest.fixture
def db(tmp_path: Path) -> Iterator[vt.Veritabani]:
    yol = tmp_path / "vt" / "anahtar.sqlite3"
    yol.parent.mkdir()
    veritabani = vt.Veritabani(yol, mesgul_bekleme_ms=200)
    sema.semayi_yukselt(veritabani)
    yield veritabani
    veritabani.kapat()


class Sayac:
    def __init__(self) -> None:
        self.cagri = 0
        self.islem_idleri: list[int] = []

    def islev(self, islem_id: int) -> ia.Sonuc:
        self.cagri += 1
        self.islem_idleri.append(islem_id)
        return {"nesne_id": 42, "sira": self.cagri}


def _calistir(
    oturum: Session, sayac: Sayac, *, anahtar: str = "a1", ad: str = "QNB"
) -> tuple[ia.Sonuc, bool]:
    return ia.anahtarla_calistir(
        oturum,
        arac_adi="nesne_tanimla",
        anahtar=anahtar,
        icerik={"ad": ad, "seviye": 2},
        simdi=SIMDI,
        islev=sayac.islev,
    )


def test_yeni_anahtar_islevi_calistirir_ve_sonucu_saklar(db: vt.Veritabani) -> None:
    sayac = Sayac()
    with db.yazma_islemi() as oturum:
        sonuc, zaten_vardi = _calistir(oturum, sayac)

    assert (sonuc, zaten_vardi) == ({"nesne_id": 42, "sira": 1}, False)
    assert sayac.cagri == 1
    with db.okuma_islemi() as oturum:
        kayit = oturum.execute(select(sema.islem_anahtari)).one()
    assert (kayit.arac_adi, kayit.anahtar) == ("nesne_tanimla", "a1")
    assert kayit.sonuc == {"nesne_id": 42, "sira": 1}
    assert kayit.istek_ozeti == ia.istek_ozeti({"ad": "QNB", "seviye": 2})
    assert sayac.islem_idleri == [kayit.id]


def test_ayni_anahtar_ayni_icerik_sakli_sonucu_verir_islev_calismaz(
    db: vt.Veritabani,
) -> None:
    sayac = Sayac()
    with db.yazma_islemi() as oturum:
        _calistir(oturum, sayac)
    with db.yazma_islemi() as oturum:
        sonuc, zaten_vardi = _calistir(oturum, sayac)

    assert (sonuc, zaten_vardi) == ({"nesne_id": 42, "sira": 1}, True)
    assert sayac.cagri == 1
    with db.okuma_islemi() as oturum:
        assert (
            oturum.execute(
                select(func.count()).select_from(sema.islem_anahtari)
            ).scalar_one()
            == 1
        )


def test_ayni_anahtar_farkli_icerik_cakisir(db: vt.Veritabani) -> None:
    sayac = Sayac()
    with db.yazma_islemi() as oturum:
        _calistir(oturum, sayac, ad="QNB")

    with pytest.raises(sz.AnahtarIcerikCakismasi) as bilgi:
        with db.yazma_islemi() as oturum:
            _calistir(oturum, sayac, ad="Akbank")

    assert bilgi.value.kod == "ANAHTAR_ICERIK_CAKISMASI"
    assert sayac.cagri == 1


def test_ayni_anahtar_farkli_arac_ayri_sayilir(db: vt.Veritabani) -> None:
    sayac = Sayac()
    with db.yazma_islemi() as oturum:
        _calistir(oturum, sayac)
        ia.anahtarla_calistir(
            oturum,
            arac_adi="belge_al",
            anahtar="a1",
            icerik={"yol": "x.pdf"},
            simdi=SIMDI,
            islev=sayac.islev,
        )

    assert sayac.cagri == 2


@pytest.mark.parametrize("anahtar", ["", "   "])
def test_bos_anahtar_reddedilir(db: vt.Veritabani, anahtar: str) -> None:
    sayac = Sayac()
    with pytest.raises(sz.GirdiGecersiz) as bilgi:
        with db.yazma_islemi() as oturum:
            _calistir(oturum, sayac, anahtar=anahtar)

    assert bilgi.value.alan == "islem_anahtari"
    assert sayac.cagri == 0


def test_islev_hatasi_anahtar_kaydini_da_geri_alir(db: vt.Veritabani) -> None:
    def patlayan(islem_id: int) -> ia.Sonuc:
        raise RuntimeError("iş yarıda")

    with pytest.raises(RuntimeError, match="iş yarıda"):
        with db.yazma_islemi() as oturum:
            ia.anahtarla_calistir(
                oturum,
                arac_adi="nesne_tanimla",
                anahtar="a1",
                icerik={},
                simdi=SIMDI,
                islev=patlayan,
            )

    with db.okuma_islemi() as oturum:
        assert (
            oturum.execute(
                select(func.count()).select_from(sema.islem_anahtari)
            ).scalar_one()
            == 0
        )


def test_istek_ozeti_kanonik_ve_siradan_bagimsiz() -> None:
    assert ia.istek_ozeti({"a": 1, "b": [1, 2]}) == ia.istek_ozeti(
        {"b": [1, 2], "a": 1}
    )
    assert ia.istek_ozeti({"a": 1}) != ia.istek_ozeti({"a": "1"})
    assert len(ia.istek_ozeti({})) == 64

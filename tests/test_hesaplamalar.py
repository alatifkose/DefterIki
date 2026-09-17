"""Etkin bakiye ve hareket listesi (Teslim 4.6).

Yazılmış ama kayıtsız belge bakiyeye girmez; belge KAYITLI olunca girer.
Hypothesis: rastgele hareket dizisi için bakiye = ARTTIR toplamı − AZALT toplamı.
"""

from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy import text

from defteriki import belgeler as bl
from defteriki import finansal_kurallar as fk
from defteriki import hesaplamalar as hs
from defteriki import kayitlar as ky
from defteriki import nesneler as ns
from defteriki import onaylar as on
from defteriki import sema
from defteriki import sozlesmeler as sz
from defteriki import veritabani as vt

SIMDI = datetime(2026, 9, 17, 12, 0)
COWORK = sz.DenetimAktoru.COWORK


def _tamlik(satir: int | None) -> bl.Tamlik:
    """Satır sayısı DEGER (None → OKUNAMADI), diğer alanlar BELGEDE_YOK."""
    return bl.Tamlik(
        beklenen_satir_sayisi=(
            bl.TamlikAlani.sayi(satir) if satir is not None else bl.OKUNAMADI
        ),
        acilis_bakiyesi_kurus=bl.BELGEDE_YOK,
        kapanis_bakiyesi_kurus=bl.BELGEDE_YOK,
        toplam_giris_kurus=bl.BELGEDE_YOK,
        toplam_cikis_kurus=bl.BELGEDE_YOK,
    )


class Ortam:
    """Bir veritabanı, bir AKTIF hesap, sırayla açılan belgeler."""

    def __init__(self, kok: Path) -> None:
        (kok / "vt").mkdir()
        self.gelen = kok / "gelen"
        self.arsiv = kok / "belgeler"
        self.gelen.mkdir()
        self.arsiv.mkdir()
        self.db = vt.Veritabani(kok / "vt" / "hesap.sqlite3", mesgul_bekleme_ms=200)
        sema.semayi_yukselt(self.db)
        self.sayac = 0
        self.hesap = self.nesne_ac("ME")

    def kapat(self) -> None:
        self.db.kapat()

    def _anahtar(self, on_ek: str) -> str:
        self.sayac += 1
        return f"{on_ek}-{self.sayac}"

    def nesne_ac(self, ad: str) -> int:
        with self.db.yazma_islemi() as oturum:
            sonuc = ns.nesne_tanimla(
                oturum,
                ozellikler=[ns.OzellikGirdisi("ad", ad)],
                islem_anahtari=self._anahtar("n"),
                aktor=COWORK,
                simdi=SIMDI,
            )
        with self.db.yazma_islemi() as oturum:
            on.karar_uygula(
                oturum,
                talep_id=sonuc.onay_talebi.id,
                gorulen_hedef_surumu=1,
                karar=on.Karar(onaylandi=True),
                simdi=SIMDI,
            )
        return sonuc.nesne.id

    def okuma_ac(self) -> bl.Okuma:
        self.sayac += 1
        dosya = self.gelen / f"belge{self.sayac}.pdf"
        dosya.write_bytes(b"%PDF-1.7\n%belge " + str(self.sayac).encode() + b"\n")
        belge = bl.belge_al(
            self.db,
            yol=str(dosya),
            gelen_dizini=self.gelen,
            belge_dizini=self.arsiv,
            islem_anahtari=self._anahtar("al"),
            aktor=COWORK,
            simdi=SIMDI,
        ).belge
        with self.db.yazma_islemi() as oturum:
            return bl.okuma_baslat(
                oturum,
                belge_id=belge.id,
                sema_surumu="cowork-0.1",
                belge_dizini=self.arsiv,
                islem_anahtari=self._anahtar("ob"),
                aktor=COWORK,
                tamlik=_tamlik(None),  # sayılamadı; kaydet gerçek sayıyı verir
                simdi=SIMDI,
            )

    def hareket(
        self,
        okuma: bl.Okuma,
        yon: str,
        tutar: int,
        tarih: date = date(2026, 8, 1),
        nesne_id: int | None = None,
    ) -> ky.HareketSonucu:
        self.sayac += 1
        with self.db.yazma_islemi() as oturum:
            return ky.hareket_yaz(
                oturum,
                okuma_id=okuma.id,
                satir=bl.SatirGirdisi(f"s{self.sayac}", self.sayac, {"n": self.sayac}),
                hareket=fk.HesapHareketi(
                    nesne_id=nesne_id or self.hesap,
                    yon=yon,
                    tutar_kurus=tutar,
                    islem_tarihi=tarih,
                ),
                islem_anahtari=self._anahtar("h"),
                aktor=COWORK,
                simdi=SIMDI,
            )

    def kaydet(self, okuma: bl.Okuma) -> bl.Belge:
        with self.db.okuma_islemi() as oturum:
            satir_sayisi = len(bl.satirlari_listele(oturum, okuma.id))
        with self.db.yazma_islemi() as oturum:
            return bl.okuma_tamamla(
                oturum,
                okuma_id=okuma.id,
                islem_anahtari=self._anahtar("ot"),
                aktor=COWORK,
                tamlik=_tamlik(satir_sayisi),
                simdi=SIMDI,
            ).belge

    def bakiye(
        self, nesne_id: int | None = None, tarih: date | None = None
    ) -> hs.Bakiye:
        with self.db.okuma_islemi() as oturum:
            return hs.etkin_bakiye(oturum, nesne_id=nesne_id or self.hesap, tarih=tarih)

    def hareketler(self, **filtre: object) -> list[hs.HareketOzeti]:
        with self.db.okuma_islemi() as oturum:
            return hs.hareketleri_listele(oturum, nesne_id=self.hesap, **filtre)  # pyright: ignore[reportArgumentType]

    def sql(self, komut: str) -> None:
        with self.db.yazma_islemi() as oturum:
            oturum.execute(text(komut))


@pytest.fixture
def ortam(tmp_path: Path) -> Iterator[Ortam]:
    o = Ortam(tmp_path)
    yield o
    o.kapat()


def test_bos_hesabin_bakiyesi_sifir(ortam: Ortam) -> None:
    b = ortam.bakiye()
    assert (b.arttir_kurus, b.azalt_kurus, b.bakiye_kurus, b.bekleyen_kayit_sayisi) == (
        0,
        0,
        0,
        0,
    )


def test_yazilmis_ama_kayitsiz_belge_bakiyeye_girmez_kayitli_olunca_girer(
    ortam: Ortam,
) -> None:
    okuma = ortam.okuma_ac()
    ortam.hareket(okuma, "ARTTIR", 50_000)
    ortam.hareket(okuma, "AZALT", 12_500)

    once = ortam.bakiye()
    assert once.bakiye_kurus == 0 and once.bekleyen_kayit_sayisi == 2
    assert [h.kayitli for h in ortam.hareketler()] == [False, False]

    assert ortam.kaydet(okuma).durum is sz.BelgeDurumu.KAYITLI

    sonra = ortam.bakiye()
    assert (sonra.arttir_kurus, sonra.azalt_kurus, sonra.bakiye_kurus) == (
        50_000,
        12_500,
        37_500,
    )
    assert sonra.bekleyen_kayit_sayisi == 0
    assert [h.kayitli for h in ortam.hareketler()] == [True, True]


def test_iki_belge_ayri_ayri_kayitli_olur(ortam: Ortam) -> None:
    agustos = ortam.okuma_ac()
    eylul = ortam.okuma_ac()
    ortam.hareket(agustos, "ARTTIR", 1_000, date(2026, 8, 5))
    ortam.hareket(eylul, "ARTTIR", 2_000, date(2026, 9, 5))
    ortam.hareket(eylul, "AZALT", 500, date(2026, 9, 6))
    ortam.kaydet(agustos)

    b = ortam.bakiye()
    assert b.bakiye_kurus == 1_000 and b.bekleyen_kayit_sayisi == 2

    ortam.kaydet(eylul)
    assert ortam.bakiye().bakiye_kurus == 2_500
    assert ortam.bakiye(tarih=date(2026, 9, 5)).bakiye_kurus == 3_000
    assert ortam.bakiye(tarih=date(2026, 8, 31)).bakiye_kurus == 1_000


def test_baska_nesne_ve_baska_eksen_karismaz(ortam: Ortam) -> None:
    gk = ortam.nesne_ac("GK")
    okuma = ortam.okuma_ac()
    ortam.hareket(okuma, "ARTTIR", 700)
    ortam.hareket(okuma, "ARTTIR", 300, nesne_id=gk)
    ortam.kaydet(okuma)

    assert ortam.bakiye().bakiye_kurus == 700
    assert ortam.bakiye(nesne_id=gk).bakiye_kurus == 300
    with ortam.db.okuma_islemi() as oturum:
        borc = hs.etkin_bakiye(oturum, nesne_id=ortam.hesap, eksen=sz.Eksen.BORC)
    assert borc.bakiye_kurus == 0 and borc.bekleyen_kayit_sayisi == 0


def test_gecersiz_kayit_ve_gecersiz_belge_toplanmaz(ortam: Ortam) -> None:
    """Aşama 8'in durumları şemada; hesaplama şimdiden onları dışarıda tutar."""
    okuma = ortam.okuma_ac()
    ortam.hareket(okuma, "ARTTIR", 100)
    k2 = ortam.hareket(okuma, "ARTTIR", 200).kayit.kayit.id
    ortam.kaydet(okuma)
    assert ortam.bakiye().bakiye_kurus == 300

    ortam.sql(f"UPDATE kayit SET durum = 'GECERSIZ' WHERE id = {k2}")
    assert ortam.bakiye().bakiye_kurus == 100
    assert [h.kayit_id for h in ortam.hareketler()] != [k2]

    ortam.sql(f"UPDATE kayit SET durum = 'AKTIF' WHERE id = {k2}")
    ortam.sql(f"UPDATE kayit_kaynak SET durum = 'KALDIRILDI' WHERE kayit_id = {k2}")
    assert ortam.bakiye().bakiye_kurus == 100  # desteği kalkan etki bekler
    assert ortam.bakiye().bekleyen_kayit_sayisi == 1

    ortam.sql("UPDATE kayit_kaynak SET durum = 'AKTIF'")
    ortam.sql("UPDATE belge SET durum = 'GECERSIZ'")
    assert ortam.bakiye().bakiye_kurus == 0


def test_etkin_olmayan_okuma_surumu_sayilmaz(ortam: Ortam) -> None:
    """Belge KAYITLI ama etkin okuma başka sürümse eski sürümün etkileri girmez."""
    okuma = ortam.okuma_ac()
    ortam.hareket(okuma, "ARTTIR", 100)
    ortam.kaydet(okuma)
    ortam.sql("UPDATE belge SET etkin_okuma_id = NULL")
    assert (
        ortam.bakiye().bakiye_kurus == 0 and ortam.bakiye().bekleyen_kayit_sayisi == 1
    )


def test_hareket_listesi_sirali_filtreli_sayfali(ortam: Ortam) -> None:
    okuma = ortam.okuma_ac()
    ortam.hareket(okuma, "AZALT", 30, date(2026, 8, 3))
    ortam.hareket(okuma, "ARTTIR", 10, date(2026, 8, 1))
    ortam.hareket(okuma, "ARTTIR", 20, date(2026, 8, 2))

    hepsi = ortam.hareketler()
    assert [(h.islem_tarihi.day, h.yon, h.tutar_kurus) for h in hepsi] == [
        (1, sz.Yon.ARTTIR, 10),
        (2, sz.Yon.ARTTIR, 20),
        (3, sz.Yon.AZALT, 30),
    ]
    assert [h.tutar_kurus for h in ortam.hareketler(baslangic=date(2026, 8, 2))] == [
        20,
        30,
    ]
    assert [h.tutar_kurus for h in ortam.hareketler(bitis=date(2026, 8, 2))] == [10, 20]
    sayfa = ortam.hareketler(sayfalama=sz.Sayfalama(sinir=1, baslangic=1))
    assert [h.tutar_kurus for h in sayfa] == [20]
    assert hepsi[0].para_birimi is sz.ParaBirimi.TRY and hepsi[0].kayitli is False


# --- Hypothesis değişmezleri ------------------------------------------------------


@settings(max_examples=15, deadline=None)
@given(
    st.lists(
        st.tuples(st.sampled_from(["ARTTIR", "AZALT"]), st.integers(1, 10**9)),
        min_size=1,
        max_size=8,
    )
)
def test_bakiye_arttir_eksi_azalt_ve_kayit_gecisi(
    tmp_path_factory: pytest.TempPathFactory, hareketler: list[tuple[str, int]]
) -> None:
    ortam = Ortam(tmp_path_factory.mktemp("hyp"))
    try:
        okuma = ortam.okuma_ac()
        for yon, tutar in hareketler:
            ortam.hareket(okuma, yon, tutar)
        beklenen_arttir = sum(t for y, t in hareketler if y == "ARTTIR")
        beklenen_azalt = sum(t for y, t in hareketler if y == "AZALT")

        once = ortam.bakiye()
        assert once.bakiye_kurus == 0
        assert once.bekleyen_kayit_sayisi == len(hareketler)

        ortam.kaydet(okuma)
        sonra = ortam.bakiye()
        assert (sonra.arttir_kurus, sonra.azalt_kurus) == (
            beklenen_arttir,
            beklenen_azalt,
        )
        assert sonra.bakiye_kurus == beklenen_arttir - beklenen_azalt
        assert sonra.bekleyen_kayit_sayisi == 0
        assert len(ortam.hareketler()) == len(hareketler)
    finally:
        ortam.kapat()

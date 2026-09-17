"""Aşama 4 kapısı: uçtan uca işlev testi.

Gerçek başlangıç akışıyla (``ortami_hazirla`` şemayı kurar) bir Garanti BBVA
ekstresi senaryosu: banka ve hesap nesnesi şart seçimiyle onaylanır → dosya
gelen dizinine bırakılır ve arşivlenir → okuma açılır → hareketler yazılır
(bakiye henüz sıfır, bekleyen üç) → okuma tamamlanır, uygulama belge kaydını
tanımlar → bakiye hesaplara girer. Ekran ve MCP aracı yok; her adım işlev
düzeyinde. Sentetik veri.
"""

from collections.abc import Iterator
from datetime import date, datetime
from pathlib import Path

import pytest
from sqlalchemy import func, select

from defteriki import ayarlar as ay
from defteriki import baslangic, gunluk, mcp_kapisi, sema
from defteriki import belgeler as bl
from defteriki import finansal_kurallar as fk
from defteriki import hesaplamalar as hs
from defteriki import kayitlar as ky
from defteriki import nesneler as ns
from defteriki import onaylar as on
from defteriki import sozlesmeler as sz
from defteriki import veritabani as vt

SIMDI = datetime(2026, 9, 17, 13, 0)
COWORK = sz.DenetimAktoru.COWORK
EKSTRE = b"%PDF-1.7\n%Garanti BBVA ME 2026-08 sentetik\n"


@pytest.fixture
def hazirlik(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[baslangic.Hazirlik]:
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
    yield baslangic.ortami_hazirla()
    gunluk.gunlugu_kapat()


@pytest.fixture
def db(hazirlik: baslangic.Hazirlik) -> Iterator[vt.Veritabani]:
    veritabani = vt.veritabani_ac(hazirlik.ayarlar)
    yield veritabani
    veritabani.kapat()


def _nesne_onayla(
    db: vt.Veritabani,
    ozellikler: list[ns.OzellikGirdisi],
    *,
    anahtar: str,
    ustler: tuple[int, ...] = (),
    sart_alani: str | None = None,
) -> ns.Nesne:
    with db.yazma_islemi() as oturum:
        sonuc = ns.nesne_tanimla(
            oturum,
            ozellikler=ozellikler,
            islem_anahtari=anahtar,
            aktor=COWORK,
            ust_idleri=ustler,
            simdi=SIMDI,
        )
        sartlar = tuple(
            o.id
            for o in ns.nesne_getir(oturum, sonuc.nesne.id).ozellikler
            if o.alan_adi == sart_alani
        )
    assert sonuc.nesne.durum is sz.NesneDurumu.ONAY_BEKLIYOR
    with db.yazma_islemi() as oturum:  # kullanıcı ekranda şart seçip onaylar
        on.karar_uygula(
            oturum,
            talep_id=sonuc.onay_talebi.id,
            gorulen_hedef_surumu=sonuc.nesne.surum,
            karar=on.Karar(onaylandi=True, secilen_sartlar=sartlar),
            simdi=SIMDI,
        )
    with db.okuma_islemi() as oturum:
        ayrinti = ns.nesne_getir(oturum, sonuc.nesne.id)
    assert ayrinti.nesne.durum is sz.NesneDurumu.AKTIF
    assert [o.alan_adi for o in ayrinti.ozellikler if o.sart] == (
        [sart_alani] if sart_alani else []
    )
    return ayrinti.nesne


def _hareket(
    db: vt.Veritabani,
    okuma_id: int,
    hesap_id: int,
    n: int,
    yon: str,
    tutar: int,
    gun: int,
) -> ky.HareketSonucu:
    with db.yazma_islemi() as oturum:
        return ky.hareket_yaz(
            oturum,
            okuma_id=okuma_id,
            satir=bl.SatirGirdisi(f"satir-{n}", n, {"ham": f"{gun}.08.2026 {tutar}"}),
            hareket=fk.HesapHareketi(
                nesne_id=hesap_id,
                yon=yon,
                tutar_kurus=tutar,
                islem_tarihi=date(2026, 8, gun),
                aciklama=f"hareket {n}",
            ),
            islem_anahtari=f"hareket-{n}",
            aktor=COWORK,
            simdi=SIMDI,
        )


def test_ucta_uca_nesneden_bakiyeye(
    hazirlik: baslangic.Hazirlik, db: vt.Veritabani
) -> None:
    ayarlar = hazirlik.ayarlar
    # 0. Başlangıç şemayı kurdu; MCP durumu gerçek sürümü söyler.
    assert hazirlik.sema_surumu == sema.BEKLENEN_SEMA_SURUMU
    assert ayarlar.veritabani_yolu.is_file()
    assert mcp_kapisi.sistem_durumu(ayarlar, hazirlik.sema_surumu).sema_surumu == "0001"

    # 1. Garanti BBVA ME ekstresi geldi: banka ve yalnız ME hesabı, şart seçimiyle onay.
    banka = _nesne_onayla(
        db,
        [ns.OzellikGirdisi("ad", "Garanti BBVA")],
        anahtar="n-banka",
        sart_alani="ad",
    )
    hesap = _nesne_onayla(
        db,
        [
            ns.OzellikGirdisi("ad", "ME"),
            ns.OzellikGirdisi("iban", "TR000000000000000000000001"),
        ],
        anahtar="n-me",
        ustler=(banka.id,),
        sart_alani="iban",
    )
    assert hesap.seviye == 1

    # 2. Dosya gelen dizinine bırakılır, arşivlenir, belge ARSIVLENDI.
    dosya = ayarlar.gelen_dizini / "garanti_me_agustos.pdf"
    dosya.write_bytes(EKSTRE)
    alinan = bl.belge_al(
        db,
        yol=str(dosya),
        gelen_dizini=ayarlar.gelen_dizini,
        belge_dizini=ayarlar.belge_dizini,
        islem_anahtari="belge-1",
        aktor=COWORK,
        simdi=SIMDI,
    )
    assert alinan.belge.durum is sz.BelgeDurumu.ARSIVLENDI
    assert (ayarlar.belge_dizini / alinan.dosya.goreli_yol).read_bytes() == EKSTRE
    assert alinan.dosya.kaynak_adi == "garanti_me_agustos.pdf"

    # 3. Okuma açılır; belge OKUNUYOR.
    with db.yazma_islemi() as oturum:
        okuma = bl.okuma_baslat(
            oturum,
            belge_id=alinan.belge.id,
            sema_surumu="cowork-0.1",
            belge_dizini=ayarlar.belge_dizini,
            islem_anahtari="okuma-1",
            aktor=COWORK,
            icerik={"donem": "2026-08", "hesap": "ME"},
            tamlik=bl.Tamlik(
                beklenen_satir_sayisi=bl.TamlikAlani.sayi(4),
                acilis_bakiyesi_kurus=bl.BELGEDE_YOK,
                kapanis_bakiyesi_kurus=bl.TamlikAlani.sayi(1_250_00),
                toplam_giris_kurus=bl.TamlikAlani.sayi(2_000_00),
                toplam_cikis_kurus=bl.TamlikAlani.sayi(750_00),
            ),
            simdi=SIMDI,
        )
    assert okuma.durum is sz.OkumaDurumu.ACIK

    # 4. Hareketler yazılır: maaş, kira, market; bir de başlık satırı (kapsam dışı).
    _hareket(db, okuma.id, hesap.id, 1, "ARTTIR", 2_000_00, 1)
    _hareket(db, okuma.id, hesap.id, 2, "AZALT", 600_00, 5)
    _hareket(db, okuma.id, hesap.id, 3, "AZALT", 150_00, 9)
    with db.yazma_islemi() as oturum:
        bl.satir_gonder(
            oturum,
            okuma_id=okuma.id,
            satirlar=[
                bl.SatirGirdisi(
                    "baslik", 0, {"metin": "Dönem: Ağustos"}, sz.SatirDurumu.KAPSAM_DISI
                )
            ],
            islem_anahtari="baslik-1",
            aktor=COWORK,
            simdi=SIMDI,
        )
    # Yazıldı ama kayıtlı değil: bakiye sıfır, üç hareket bekliyor (K19).
    with db.okuma_islemi() as oturum:
        once = hs.etkin_bakiye(oturum, nesne_id=hesap.id)
        liste = hs.hareketleri_listele(oturum, nesne_id=hesap.id)
    assert once.bakiye_kurus == 0 and once.bekleyen_kayit_sayisi == 3
    assert [h.kayitli for h in liste] == [False, False, False]

    # 5. Cowork "bitti" der; uygulama koşulları denetler ve belge kaydını tanımlar.
    with db.yazma_islemi() as oturum:
        sonuc = bl.okuma_tamamla(
            oturum,
            okuma_id=okuma.id,
            islem_anahtari="tamam-1",
            aktor=COWORK,
            simdi=SIMDI,
        )
    assert sonuc.belge.durum is sz.BelgeDurumu.KAYITLI
    assert sonuc.belge.etkin_okuma_id == okuma.id

    # 6. Bakiye hesaplara girdi.
    with db.okuma_islemi() as oturum:
        sonra = hs.etkin_bakiye(oturum, nesne_id=hesap.id)
        liste = hs.hareketleri_listele(oturum, nesne_id=hesap.id)
        agustos_5 = hs.etkin_bakiye(oturum, nesne_id=hesap.id, tarih=date(2026, 8, 5))
        banka_bakiyesi = hs.etkin_bakiye(oturum, nesne_id=banka.id)
    assert (sonra.arttir_kurus, sonra.azalt_kurus, sonra.bakiye_kurus) == (
        2_000_00,
        750_00,
        1_250_00,
    )
    assert sonra.bakiye_kurus == 1_250_00  # tamlıktaki kapanış bakiyesiyle aynı
    assert sonra.bekleyen_kayit_sayisi == 0
    assert [(h.islem_tarihi.day, h.kayitli) for h in liste] == [
        (1, True),
        (5, True),
        (9, True),
    ]
    assert agustos_5.bakiye_kurus == 1_400_00
    assert banka_bakiyesi.bakiye_kurus == 0  # hareket hesapta, bankada değil

    # 7. Aynı ekstre ikinci kez gelirse: aynı belge, ikinci etki yok (K18).
    (ayarlar.gelen_dizini / "kopya.pdf").write_bytes(EKSTRE)
    tekrar = bl.belge_al(
        db,
        yol=str(ayarlar.gelen_dizini / "kopya.pdf"),
        gelen_dizini=ayarlar.gelen_dizini,
        belge_dizini=ayarlar.belge_dizini,
        islem_anahtari="belge-2",
        aktor=COWORK,
        simdi=SIMDI,
    )
    assert tekrar.zaten_vardi and tekrar.belge.id == alinan.belge.id
    with db.okuma_islemi() as oturum:
        assert hs.etkin_bakiye(oturum, nesne_id=hesap.id).bakiye_kurus == 1_250_00
        sayilar = {
            tablo.name: int(
                oturum.execute(select(func.count()).select_from(tablo)).scalar_one()
            )
            for tablo in (
                sema.nesne,
                sema.belge,
                sema.arsiv_dosya,
                sema.okuma,
                sema.okuma_satir,
                sema.kayit,
                sema.etki,
                sema.kayit_kaynak,
                sema.onay_talep,
                sema.islem_anahtari,
            )
        }
    assert sayilar == {
        "nesne": 2,
        "belge": 1,
        "arsiv_dosya": 1,
        "okuma": 1,
        "okuma_satir": 4,
        "kayit": 3,
        "etki": 3,
        "kayit_kaynak": 3,
        "onay_talep": 2,
        "islem_anahtari": 10,  # 2 nesne + 2 belge + okuma + 3 hareket + başlık + tamam
    }
    assert (ayarlar.log_dizini / gunluk.GUNLUK_DOSYA_ADI).is_file()


def test_ikinci_baslangic_ayni_veriyi_bulur(
    hazirlik: baslangic.Hazirlik, db: vt.Veritabani
) -> None:
    """Uygulama kapanıp açılınca yazılmış veri kaybolmaz, şema yeniden kurulmaz."""
    _nesne_onayla(db, [ns.OzellikGirdisi("ad", "QNB")], anahtar="n-qnb")
    db.kapat()

    yeniden = baslangic.ortami_hazirla()

    assert yeniden.sema_surumu == hazirlik.sema_surumu
    db2 = vt.veritabani_ac(yeniden.ayarlar)
    try:
        with db2.okuma_islemi() as oturum:
            (bulunan,) = ns.nesne_bul(oturum, alan_adi="ad", deger="QNB")
    finally:
        db2.kapat()
    assert bulunan.durum is sz.NesneDurumu.AKTIF

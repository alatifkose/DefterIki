"""Finansal kayıt yazma (Teslim 4.6): hareket → kayıt + etki + kaynak bağı.

Sözlük "Yazmak ve kayıt etmek": burada yapılan **yazmaktır**. Hareket,
belgenin açık okumasındaki bir satıra dayanarak ``kayit``, ``etki`` ve
``kayit_kaynak`` satırlarına kalıcı yazılır; satır ``YAZILDI`` olur. Belge
``KAYITLI`` olana kadar bu etki bakiyeye girmez (``hesaplamalar``).

Kurallar:

* **Kaynak satırı zorunlu (K06, S10).** Hareket ancak ``ACIK`` bir okumanın
  satırıyla yazılır; belgesiz, okumasız ya da kapalı okumaya hareket yoktur.
  Satır ``belgeler.satirlari_kabul_et`` ile aynı gönderimde kabul edilir
  (K07: biçim hatası paketi düşürür).
* **Nesne AKTIF olmalı.** ``ONAY_BEKLIYOR``, ``PASIF``, ``SILINDI`` nesneye
  yazılmaz; ``ENGELLI`` nesne ``NESNE_ENGELLI`` verir (K16).
* **İşlem anahtarı zorunlu (K08, S18).** Aynı anahtar aynı içerik saklı
  sonucu döndürür, ikinci etki üretmez; farklı içerik
  ``ANAHTAR_ICERIK_CAKISMASI``.
* **Aynı satıra ikinci hareket (Tam Plan 8.5.1).** Satır anahtarı aynı
  içerikle daha önce gelmiş ve bir kayda ``ASIL`` kaynak olmuşsa: yeni
  hareket o kayıtla aynıysa tekrar gönderimdir, mevcut kayıt döner; tutar,
  yön ya da para birimi farklıysa ``KAYNAK_CAKISMASI``. Kaydı olmayan mevcut
  satıra (4.5 gönderimiyle yazılmış) kayıt bağlanır.
* Denetim olayı, kayıt ve etkiler tek yazma işleminde; commit çağıranındır.

Bu teslimde yalnız ``HESAP_HAREKETI`` (``finansal_kurallar``); hareket
mükerrerliği karşılaştırması (referans, tarih + tutar + yön) Aşama 8.2'de.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from defteriki import belgeler, denetim, islem_anahtarlari, nesneler, sema
from defteriki import finansal_kurallar as fk
from defteriki import sozlesmeler as sz

ARAC_HAREKET_YAZ = "hareket_yaz"
EYLEM_HAREKET_YAZ = "hareket_yaz"


@dataclass(frozen=True, slots=True)
class Kayit:
    id: int
    asil_nesne_id: int
    islem_tarihi: date
    valor_tarihi: date | None
    aciklama: str | None
    durum: sz.KayitDurumu
    olusturma_zamani: datetime


@dataclass(frozen=True, slots=True)
class Etki:
    id: int
    kayit_id: int
    nesne_id: int
    eksen: sz.Eksen
    yon: sz.Yon
    tutar_kurus: int
    para_birimi: sz.ParaBirimi


@dataclass(frozen=True, slots=True)
class KayitKaynagi:
    id: int
    kayit_id: int
    okuma_satir_id: int
    rol: sz.KaynakRolu
    durum: sz.KaynakDurumu


@dataclass(frozen=True, slots=True)
class KayitAyrinti:
    kayit: Kayit
    etkiler: tuple[Etki, ...]
    kaynaklar: tuple[KayitKaynagi, ...]


@dataclass(frozen=True, slots=True)
class HareketSonucu:
    kayit: KayitAyrinti
    satir: belgeler.OkumaSatiri
    zaten_vardi: bool
    """Aynı satır ve aynı hareket daha önce yazılmıştı; ikinci etki üretilmedi."""


def hareket_yaz(
    oturum: Session,
    *,
    okuma_id: int,
    satir: belgeler.SatirGirdisi,
    hareket: fk.HesapHareketi,
    islem_anahtari: str,
    aktor: sz.DenetimAktoru,
    simdi: datetime | None = None,
) -> HareketSonucu:
    """Bir satırı kabul eder ve ona dayanan HESAP_HAREKETI kaydını yazar.

    Satır ``YAZILDI`` durumuyla verilmelidir (``KAPSAM_DISI`` satıra hareket
    bağlanmaz). Girdi önce saf kurallarla doğrulanır; veritabanına ancak her
    şey geçerliyse dokunulur.
    """
    simdi = simdi or sz.simdi_utc()
    taslak = fk.hesap_hareketi_dogrula(hareket)
    if satir.durum is not sz.SatirDurumu.YAZILDI:
        raise sz.GirdiGecersiz(
            f"hareket satırı YAZILDI durumuyla gönderilmeli ({satir.durum.value})",
            alan="satir.durum",
        )
    istek: dict[str, Any] = {
        "okuma_id": okuma_id,
        "satir": {
            "satir_anahtari": satir.satir_anahtari,
            "konum": satir.konum,
            "ham": dict(satir.ham),
        },
        "hareket": _taslak_icerigi(taslak),
    }

    def yaz(islem_id: int) -> islem_anahtarlari.Sonuc:
        nesneler.aktif_nesneyi_getir(oturum, taslak.asil_nesne_id)
        kabul = belgeler.satirlari_kabul_et(oturum, okuma_id=okuma_id, satirlar=[satir])
        satir_id = (kabul.yazilan_idleri or kabul.mevcut_idleri)[0]

        mevcut = _asil_kaydi_bul(oturum, satir_id)
        if mevcut is not None:
            if not _ayni_hareket(mevcut, taslak):
                raise sz.KaynakCakismasi(
                    "bu satır daha önce farklı tutar, yön ya da para birimiyle "
                    "yazılmış; aynı olay iddiasını incele",
                    alan="satir_anahtari",
                )
            return {"kayit_id": mevcut.kayit.id, "satir_id": satir_id, "yeni": False}

        kayit_id = int(
            oturum.execute(
                sema.kayit.insert()
                .values(
                    asil_nesne_id=taslak.asil_nesne_id,
                    islem_tarihi=taslak.islem_tarihi,
                    valor_tarihi=taslak.valor_tarihi,
                    aciklama=taslak.aciklama,
                    durum=sz.KayitDurumu.AKTIF.value,
                    olusturma_zamani=simdi,
                )
                .returning(sema.kayit.c.id)
            ).scalar_one()
        )
        oturum.execute(
            sema.etki.insert(),
            [
                {
                    "kayit_id": kayit_id,
                    "nesne_id": e.nesne_id,
                    "eksen": e.eksen.value,
                    "yon": e.yon.value,
                    "tutar_kurus": e.tutar_kurus,
                    "para_birimi": e.para_birimi.value,
                }
                for e in taslak.etkiler
            ],
        )
        oturum.execute(
            sema.kayit_kaynak.insert().values(
                kayit_id=kayit_id,
                okuma_satir_id=satir_id,
                rol=sz.KaynakRolu.ASIL.value,
                durum=sz.KaynakDurumu.AKTIF.value,
            )
        )
        etki = taslak.etkiler[0]
        denetim.olay_yaz(
            oturum,
            aktor=aktor,
            eylem=EYLEM_HAREKET_YAZ,
            hedef=denetim.hedef_adi("kayit", kayit_id),
            simdi=simdi,
            islem_id=islem_id,
            gerekce=(
                f"{taslak.islem_turu.value} nesne {etki.nesne_id} "
                f"{etki.yon.value} {etki.tutar_kurus} {etki.para_birimi.value}; "
                f"kaynak okuma_satir {satir_id}"
            ),
            sonraki_durum=sz.KayitDurumu.AKTIF.value,
        )
        return {"kayit_id": kayit_id, "satir_id": satir_id, "yeni": True}

    sonuc, anahtar_tekrari = islem_anahtarlari.anahtarla_calistir(
        oturum,
        arac_adi=ARAC_HAREKET_YAZ,
        anahtar=islem_anahtari,
        icerik=istek,
        simdi=simdi,
        islev=yaz,
    )
    return HareketSonucu(
        kayit=kayit_getir(oturum, int(sonuc["kayit_id"])),
        satir=belgeler.satirlari_getir(oturum, [int(sonuc["satir_id"])])[0],
        zaten_vardi=anahtar_tekrari or not bool(sonuc["yeni"]),
    )


def kayit_getir(oturum: Session, kayit_id: int) -> KayitAyrinti:
    satir = oturum.execute(
        select(sema.kayit).where(sema.kayit.c.id == kayit_id)
    ).one_or_none()
    if satir is None:
        raise sz.HedefBulunamadi("kayıt bulunamadı", alan="kayit_id")
    etkiler = tuple(
        _etki(e._mapping)  # pyright: ignore[reportPrivateUsage]
        for e in oturum.execute(
            select(sema.etki)
            .where(sema.etki.c.kayit_id == kayit_id)
            .order_by(sema.etki.c.id)
        ).all()
    )
    kaynaklar = tuple(
        _kaynak(k._mapping)  # pyright: ignore[reportPrivateUsage]
        for k in oturum.execute(
            select(sema.kayit_kaynak)
            .where(sema.kayit_kaynak.c.kayit_id == kayit_id)
            .order_by(sema.kayit_kaynak.c.id)
        ).all()
    )
    return KayitAyrinti(_kayit(satir._mapping), etkiler, kaynaklar)  # pyright: ignore[reportPrivateUsage]


def _asil_kaydi_bul(oturum: Session, satir_id: int) -> KayitAyrinti | None:
    kayit_id = oturum.execute(
        select(sema.kayit_kaynak.c.kayit_id).where(
            sema.kayit_kaynak.c.okuma_satir_id == satir_id,
            sema.kayit_kaynak.c.rol == sz.KaynakRolu.ASIL.value,
            sema.kayit_kaynak.c.durum == sz.KaynakDurumu.AKTIF.value,
        )
    ).scalar_one_or_none()
    return kayit_getir(oturum, int(kayit_id)) if kayit_id is not None else None


def _ayni_hareket(mevcut: KayitAyrinti, taslak: fk.HareketTaslagi) -> bool:
    if mevcut.kayit.asil_nesne_id != taslak.asil_nesne_id:
        return False
    if (mevcut.kayit.islem_tarihi, mevcut.kayit.valor_tarihi) != (
        taslak.islem_tarihi,
        taslak.valor_tarihi,
    ):
        return False
    mevcut_etkiler = {
        (e.nesne_id, e.eksen, e.yon, e.tutar_kurus, e.para_birimi)
        for e in mevcut.etkiler
    }
    yeni_etkiler = {
        (e.nesne_id, e.eksen, e.yon, e.tutar_kurus, e.para_birimi)
        for e in taslak.etkiler
    }
    return mevcut_etkiler == yeni_etkiler


def _taslak_icerigi(taslak: fk.HareketTaslagi) -> dict[str, Any]:
    return {
        "islem_turu": taslak.islem_turu.value,
        "asil_nesne_id": taslak.asil_nesne_id,
        "islem_tarihi": taslak.islem_tarihi.isoformat(),
        "valor_tarihi": (
            taslak.valor_tarihi.isoformat() if taslak.valor_tarihi else None
        ),
        "aciklama": taslak.aciklama,
        "etkiler": [
            {
                "nesne_id": e.nesne_id,
                "eksen": e.eksen.value,
                "yon": e.yon.value,
                "tutar_kurus": e.tutar_kurus,
                "para_birimi": e.para_birimi.value,
            }
            for e in taslak.etkiler
        ],
    }


def _kayit(satir: RowMapping) -> Kayit:
    return Kayit(
        id=int(satir["id"]),
        asil_nesne_id=int(satir["asil_nesne_id"]),
        islem_tarihi=satir["islem_tarihi"],
        valor_tarihi=satir["valor_tarihi"],
        aciklama=satir["aciklama"],
        durum=sz.KayitDurumu(satir["durum"]),
        olusturma_zamani=satir["olusturma_zamani"],
    )


def _etki(satir: RowMapping) -> Etki:
    return Etki(
        id=int(satir["id"]),
        kayit_id=int(satir["kayit_id"]),
        nesne_id=int(satir["nesne_id"]),
        eksen=sz.Eksen(satir["eksen"]),
        yon=sz.Yon(satir["yon"]),
        tutar_kurus=int(satir["tutar_kurus"]),
        para_birimi=sz.ParaBirimi(satir["para_birimi"]),
    )


def _kaynak(satir: RowMapping) -> KayitKaynagi:
    return KayitKaynagi(
        id=int(satir["id"]),
        kayit_id=int(satir["kayit_id"]),
        okuma_satir_id=int(satir["okuma_satir_id"]),
        rol=sz.KaynakRolu(satir["rol"]),
        durum=sz.KaynakDurumu(satir["durum"]),
    )

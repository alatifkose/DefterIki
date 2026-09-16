"""Nesne: dış dünyadaki bir varlığın yapılandırılmış kaydı (sözlük: Nesne).

Kurum, banka, hesap, kart gibi şeylerin hepsi **nesne**dir; tür sütunu yoktur.
Nesnenin ne olduğunu Cowork'un yazdığı serbest özellikler ve seviyeli
hiyerarşideki yeri anlatır (K11, K12).

Açılış akışı (Yürütme Planı 4.4; karar 2026-09-16 "birinci yol"):

1. **FORM**: ``tanitma_formu()`` boş formu ve kuralları açıklar; hiçbir alan
   önceden gelmez (K12). Veritabanına dokunmaz.
2. **GONDER**: ``nesne_tanimla`` üstleri, özellikleri ve varsa kaynak belgeyi
   alır. Seviye Cowork'tan gelmez, üstlerden hesaplanır (üst yoksa 0, varsa
   üst seviye + 1; üstler aynı seviyede olmalı, K11). Nesne ``ONAY_BEKLIYOR``
   durumunda yazılır; özellikler, üst bağlantıları ve kaynak aynı işlemde;
   ``NESNE_ACILISI`` onay talebi açılır. İşlem anahtarı zorunlu (K08).
3. **Karar** (yalnız ekran, ``onaylar.karar_uygula``): kullanıcı özelliklerden
   0..n şart seçer (K14); şartlar yazılır, nesne ``AKTIF`` olur, sürüm artar.
   Red: nesne ``SILINDI`` (kimlik saklı, yeniden kullanılmaz). Eşleşme
   taraması ve şüphe Aşama 7'de; burada şart yalnız saklanır.

Kurallar: en az bir özellik (C13); alan adında normalizasyon yok, boş ad ve
aynı nesnede aynı ad iki kez reddedilir (C05); özellik sayısı ve uzunluk
sınırları (C18); özellik ve şart güncelleme işlevi yoktur (K13). Değer türü
Cowork verebilir, vermezse Python türünden çıkarılır; ``eslesme_degeri``
türüyle kararlı seri hâldir ("123" metni ile 123 tam sayısı eşit değildir,
boş değer eşleşme üretmez).

Hiçbir nesne belgesiz, toplu ya da önceden açılmaz: her nesne kendi
kanıtı geldiğinde, Cowork'un teklifiyle, tek tek açılır. Bu modül commit
yapmaz; işlem sahibi çağırandır.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from defteriki import denetim, islem_anahtarlari, onaylar, sema
from defteriki import sozlesmeler as sz

ARAC_NESNE_TANIMLA = "nesne_tanimla"
EYLEM_NESNE_TANIMLA = "nesne_tanimla"
EYLEM_NESNE_ONAYI = "nesne_onayi"

AZAMI_OZELLIK_SAYISI = 200
AZAMI_ALAN_ADI_UZUNLUGU = 128
AZAMI_DEGER_UZUNLUGU = 4096
"""C18 gönderim sınırları; aşılırsa açık hata, veri kesilmez."""

FORM_KURALLARI: tuple[str, ...] = (
    "Form boştur; alan adlarını ve değerlerini sen yazarsın, hiçbir alan hazır gelmez.",
    "Mevcut nesnenin alan adlarını aynen kullan; eşanlamlı alan icat etme, biçim "
    "değiştirme.",
    "En az bir özellik zorunlu. Alan adı boş olamaz; aynı nesnede aynı ad iki kez "
    "olamaz.",
    f"En çok {AZAMI_OZELLIK_SAYISI} özellik; alan adı {AZAMI_ALAN_ADI_UZUNLUGU}, "
    f"değer {AZAMI_DEGER_UZUNLUGU} karakter.",
    "Seviye gönderme: üst nesne yoksa seviye 0, varsa üstlerin seviyesi + 1. "
    "Bütün üstler aynı seviyede olmalı; seviye atlanamaz.",
    "Hiçbir nesneyi belgesiz ya da önceden açma; kanıtı gelen nesneyi tek tek öner, "
    "önce mevcut nesneyi ara.",
    "Gönderim nesneyi aktif yapmaz: ONAY_BEKLIYOR yazılır, kullanıcı ekranda şart "
    "seçip onaylar. BEKLIYOR dönerse aynı işlem anahtarıyla durumu sor.",
)


# --- girdi ve çıktı tipleri ---------------------------------------------------


@dataclass(frozen=True, slots=True)
class OzellikGirdisi:
    alan_adi: str
    deger: object
    deger_turu: sz.DegerTuru | None = None
    """Verilmezse Python türünden çıkarılır; TARIH yalnız açıkça verilirse."""


@dataclass(frozen=True, slots=True)
class NesneKaynagi:
    belge_id: int
    okuma_id: int | None = None
    konum: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class Ozellik:
    id: int
    alan_adi: str
    deger_turu: sz.DegerTuru
    deger: object
    eslesme_degeri: str | None
    sart: bool = False


@dataclass(frozen=True, slots=True)
class Nesne:
    id: int
    seviye: int
    durum: sz.NesneDurumu
    surum: int
    olusturma_zamani: datetime


@dataclass(frozen=True, slots=True)
class NesneAyrinti:
    nesne: Nesne
    ozellikler: tuple[Ozellik, ...]
    ust_idleri: tuple[int, ...]
    alt_idleri: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class NesneTanimlamaSonucu:
    nesne: Nesne
    onay_talebi: onaylar.OnayTalebi
    zaten_vardi: bool


@dataclass(frozen=True, slots=True)
class TanitmaFormu:
    kurallar: tuple[str, ...]
    satir_sablonu: dict[str, object] = field(
        default_factory=lambda: {"alan_adi": "", "deger": None, "deger_turu": None}
    )
    deger_turleri: tuple[str, ...] = tuple(t.value for t in sz.DegerTuru)


def tanitma_formu() -> TanitmaFormu:
    """FORM adımı: boş form ve kurallar (K12). Veritabanına dokunmaz."""
    return TanitmaFormu(kurallar=FORM_KURALLARI)


# --- değer türü ve eşleşme değeri ---------------------------------------------


def deger_turunu_cikar(deger: object) -> sz.DegerTuru:
    """Python türünden değer türü; TARIH çıkarılmaz, açıkça verilmelidir."""
    if isinstance(deger, bool):
        return sz.DegerTuru.MANTIKSAL
    if isinstance(deger, int):
        return sz.DegerTuru.TAMSAYI
    if isinstance(deger, (float, Decimal)):
        return sz.DegerTuru.ONDALIK
    if isinstance(deger, date):
        return sz.DegerTuru.TARIH
    if isinstance(deger, str) or deger is None:
        return sz.DegerTuru.METIN
    return sz.DegerTuru.JSON


def degeri_dogrula(deger: object, tur: sz.DegerTuru, alan: str) -> object:
    """Değeri türüne göre doğrular ve JSON'a yazılacak biçime çevirir."""
    if deger is None or deger == "":
        return None
    match tur:
        case sz.DegerTuru.METIN:
            if not isinstance(deger, str):
                raise sz.GirdiGecersiz("METIN türünde değer metin olmalı", alan=alan)
            return deger
        case sz.DegerTuru.TAMSAYI:
            if isinstance(deger, bool) or not isinstance(deger, int):
                raise sz.GirdiGecersiz(
                    "TAMSAYI türünde değer tam sayı olmalı", alan=alan
                )
            return deger
        case sz.DegerTuru.ONDALIK:
            if isinstance(deger, bool):
                raise sz.GirdiGecersiz("ONDALIK türünde değer sayı olmalı", alan=alan)
            try:
                ondalik = (
                    Decimal(str(deger))
                    if isinstance(deger, (int, float, str))
                    else None
                )
            except InvalidOperation:
                ondalik = None
            if ondalik is None or not ondalik.is_finite():
                raise sz.GirdiGecersiz("ONDALIK türünde değer sayı olmalı", alan=alan)
            return str(ondalik)
        case sz.DegerTuru.TARIH:
            if isinstance(deger, date):
                return deger.isoformat()
            if isinstance(deger, str):
                try:
                    return date.fromisoformat(deger).isoformat()
                except ValueError:
                    pass
            raise sz.GirdiGecersiz("TARIH türünde değer YYYY-AA-GG olmalı", alan=alan)
        case sz.DegerTuru.MANTIKSAL:
            if not isinstance(deger, bool):
                raise sz.GirdiGecersiz(
                    "MANTIKSAL türünde değer doğru/yanlış olmalı", alan=alan
                )
            return deger
        case sz.DegerTuru.JSON:
            try:
                json.dumps(deger)
            except (TypeError, ValueError):
                raise sz.GirdiGecersiz(
                    "JSON türünde değer serileştirilemedi", alan=alan
                ) from None
            return deger


def eslesme_degeri(deger: object, tur: sz.DegerTuru) -> str | None:
    """Türüyle kararlı seri hâl; boş değer ``None`` (eşleşme üretmez)."""
    if deger is None or deger == "" or deger == [] or deger == {}:
        return None
    match tur:
        case sz.DegerTuru.ONDALIK:
            govde = format(Decimal(str(deger)).normalize(), "f")
        case sz.DegerTuru.MANTIKSAL:
            govde = "true" if deger else "false"
        case sz.DegerTuru.JSON:
            govde = json.dumps(
                deger, sort_keys=True, ensure_ascii=False, separators=(",", ":")
            )
        case _:
            govde = str(deger)
    return f"{tur.value}:{govde}"


# --- doğrulama ----------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _HazirOzellik:
    alan_adi: str
    deger_turu: sz.DegerTuru
    deger: object
    eslesme: str | None


def _ozellikleri_hazirla(girdiler: Sequence[OzellikGirdisi]) -> list[_HazirOzellik]:
    if not girdiler:
        raise sz.GirdiGecersiz("en az bir özellik zorunlu", alan="ozellikler")
    if len(girdiler) > AZAMI_OZELLIK_SAYISI:
        raise sz.GirdiGecersiz(
            f"nesne başına en çok {AZAMI_OZELLIK_SAYISI} özellik", alan="ozellikler"
        )
    hazir: list[_HazirOzellik] = []
    gorulen: set[str] = set()
    for konum, girdi in enumerate(girdiler):
        ad = girdi.alan_adi  # C05: normalizasyon yok, olduğu gibi
        if not ad or not ad.strip():
            raise sz.GirdiGecersiz("alan adı boş olamaz", alan="alan_adi", konum=konum)
        if len(ad) > AZAMI_ALAN_ADI_UZUNLUGU:
            raise sz.GirdiGecersiz(
                f"alan adı en çok {AZAMI_ALAN_ADI_UZUNLUGU} karakter",
                alan="alan_adi",
                konum=konum,
            )
        if ad in gorulen:
            raise sz.GirdiGecersiz(
                f"aynı nesnede aynı alan adı iki kez: {ad!r}",
                alan="alan_adi",
                konum=konum,
            )
        gorulen.add(ad)
        tur = girdi.deger_turu or deger_turunu_cikar(girdi.deger)
        deger = degeri_dogrula(girdi.deger, tur, alan=ad)
        if (
            len(json.dumps(deger, ensure_ascii=False, default=str))
            > AZAMI_DEGER_UZUNLUGU
        ):
            raise sz.GirdiGecersiz(
                f"değer en çok {AZAMI_DEGER_UZUNLUGU} karakter", alan=ad, konum=konum
            )
        hazir.append(_HazirOzellik(ad, tur, deger, eslesme_degeri(deger, tur)))
    return hazir


def _ustleri_dogrula(oturum: Session, ust_idleri: Sequence[int]) -> int:
    """Üstleri denetler; yeni nesnenin seviyesini döndürür (K11)."""
    if not ust_idleri:
        return 0
    if len(set(ust_idleri)) != len(ust_idleri):
        raise sz.GirdiGecersiz("aynı üst iki kez verildi", alan="ust_idleri")
    satirlar = oturum.execute(
        select(sema.nesne.c.id, sema.nesne.c.seviye, sema.nesne.c.durum).where(
            sema.nesne.c.id.in_(list(ust_idleri))
        )
    ).all()
    bulunan = {int(s.id): s for s in satirlar}
    for ust_id in ust_idleri:
        satir = bulunan.get(ust_id)
        if satir is None:
            raise sz.HedefBulunamadi(
                f"üst nesne bulunamadı: {ust_id}", alan="ust_idleri"
            )
        durum = sz.NesneDurumu(satir.durum)
        if durum is sz.NesneDurumu.ENGELLI:
            raise sz.NesneEngelli(
                f"üst nesne engelli: {ust_id}; şüphe çözülmeden altına nesne açılmaz",
                alan="ust_idleri",
            )
        if durum in (sz.NesneDurumu.PASIF, sz.NesneDurumu.SILINDI):
            raise sz.GirdiGecersiz(
                f"üst nesne {durum.value.lower()}: {ust_id}; altına nesne açılmaz",
                alan="ust_idleri",
            )
    seviyeler = {int(s.seviye) for s in satirlar}
    if len(seviyeler) != 1:
        raise sz.SeviyeCakismasi(
            "üst nesneler aynı seviyede olmalı; seviye atlanamaz", alan="ust_idleri"
        )
    return seviyeler.pop() + 1


# --- açılış -------------------------------------------------------------------


def nesne_tanimla(
    oturum: Session,
    *,
    ozellikler: Sequence[OzellikGirdisi],
    islem_anahtari: str,
    aktor: sz.DenetimAktoru,
    ust_idleri: Sequence[int] = (),
    kaynak: NesneKaynagi | None = None,
    simdi: datetime | None = None,
) -> NesneTanimlamaSonucu:
    """GONDER adımı: nesneyi ``ONAY_BEKLIYOR`` yazar, ``NESNE_ACILISI`` talebi açar.

    Aynı işlem anahtarı aynı içerikle gelirse saklı sonuç (aynı nesne, aynı
    talep) döner; farklı içerik ``ANAHTAR_ICERIK_CAKISMASI``.
    """
    simdi = simdi or sz.simdi_utc()
    hazir = _ozellikleri_hazirla(ozellikler)
    ustler = tuple(int(u) for u in ust_idleri)
    icerik: dict[str, Any] = {
        "ust_idleri": list(ustler),
        "ozellikler": [
            {"alan_adi": o.alan_adi, "deger_turu": o.deger_turu.value, "deger": o.deger}
            for o in hazir
        ],
        "kaynak": (
            {
                "belge_id": kaynak.belge_id,
                "okuma_id": kaynak.okuma_id,
                "konum": kaynak.konum,
            }
            if kaynak
            else None
        ),
    }

    def ac(islem_id: int) -> islem_anahtarlari.Sonuc:
        seviye = _ustleri_dogrula(oturum, ustler)
        nesne_id = int(
            oturum.execute(
                sema.nesne.insert()
                .values(
                    seviye=seviye,
                    durum=sz.NesneDurumu.ONAY_BEKLIYOR.value,
                    surum=1,
                    olusturma_zamani=simdi,
                )
                .returning(sema.nesne.c.id)
            ).scalar_one()
        )
        oturum.execute(
            sema.nesne_ozellik.insert(),
            [
                {
                    "nesne_id": nesne_id,
                    "alan_adi": o.alan_adi,
                    "deger_turu": o.deger_turu.value,
                    "deger": o.deger,
                    "eslesme_degeri": o.eslesme,
                }
                for o in hazir
            ],
        )
        if ustler:
            oturum.execute(
                sema.nesne_baglanti.insert(),
                [{"alt_id": nesne_id, "ust_id": ust} for ust in ustler],
            )
        if kaynak is not None:
            _kaynagi_dogrula(oturum, kaynak)
            oturum.execute(
                sema.nesne_kaynak.insert().values(
                    nesne_id=nesne_id,
                    belge_id=kaynak.belge_id,
                    okuma_id=kaynak.okuma_id,
                    konum=kaynak.konum,
                )
            )
        denetim.olay_yaz(
            oturum,
            aktor=aktor,
            eylem=EYLEM_NESNE_TANIMLA,
            hedef=denetim.hedef_adi("nesne", nesne_id),
            simdi=simdi,
            islem_id=islem_id,
            gerekce=f"seviye {seviye}, {len(hazir)} özellik, {len(ustler)} üst",
            sonraki_durum=sz.NesneDurumu.ONAY_BEKLIYOR.value,
        )
        talep = onaylar.talep_olustur(
            oturum,
            tur=sz.OnayTuru.NESNE_ACILISI,
            hedef_id=nesne_id,
            hedef_surumu=1,
            icerik={
                "seviye": seviye,
                "ust_idleri": list(ustler),
                "ozellikler": icerik["ozellikler"],
                "kaynak": icerik["kaynak"],
            },
            simdi=simdi,
            aktor=aktor,
            islem_id=islem_id,
        )
        return {"nesne_id": nesne_id, "onay_talebi_id": talep.id}

    sonuc, zaten_vardi = islem_anahtarlari.anahtarla_calistir(
        oturum,
        arac_adi=ARAC_NESNE_TANIMLA,
        anahtar=islem_anahtari,
        icerik=icerik,
        simdi=simdi,
        islev=ac,
    )
    return NesneTanimlamaSonucu(
        nesne=nesne_getir(oturum, int(sonuc["nesne_id"])).nesne,
        onay_talebi=onaylar.talep_getir(oturum, int(sonuc["onay_talebi_id"])),
        zaten_vardi=zaten_vardi,
    )


def _kaynagi_dogrula(oturum: Session, kaynak: NesneKaynagi) -> None:
    belge_var = oturum.execute(
        select(sema.belge.c.id).where(sema.belge.c.id == kaynak.belge_id)
    ).scalar_one_or_none()
    if belge_var is None:
        raise sz.HedefBulunamadi("kaynak belge bulunamadı", alan="kaynak.belge_id")
    if kaynak.okuma_id is not None:
        okuma_var = oturum.execute(
            select(sema.okuma.c.id).where(
                sema.okuma.c.id == kaynak.okuma_id,
                sema.okuma.c.belge_id == kaynak.belge_id,
            )
        ).scalar_one_or_none()
        if okuma_var is None:
            raise sz.HedefBulunamadi(
                "kaynak okuma bu belgede bulunamadı", alan="kaynak.okuma_id"
            )


# --- karar etkisi (NESNE_ACILISI) ---------------------------------------------


def _nesne_onayini_uygula(
    oturum: Session, talep: onaylar.OnayTalebi, karar: onaylar.Karar, simdi: datetime
) -> None:
    """Onay: şartlar yazılır, nesne AKTIF; red: SILINDI. Sürüm bir artar."""
    ayrinti = nesne_getir(oturum, talep.hedef_id)
    if ayrinti.nesne.durum is not sz.NesneDurumu.ONAY_BEKLIYOR:
        raise sz.GirdiGecersiz(
            f"nesne onay beklemiyor (durum {ayrinti.nesne.durum.value})",
            alan="hedef_id",
        )
    if karar.onaylandi:
        ozellik_idleri = {o.id for o in ayrinti.ozellikler}
        secilen = tuple(dict.fromkeys(karar.secilen_sartlar))
        yabanci = [s for s in secilen if s not in ozellik_idleri]
        if yabanci:
            raise sz.GirdiGecersiz(
                f"şart olarak seçilen özellik bu nesneye ait değil: {yabanci}",
                alan="secilen_sartlar",
            )
        if secilen:
            oturum.execute(
                sema.nesne_sart.insert(),
                [{"nesne_id": talep.hedef_id, "ozellik_id": s} for s in secilen],
            )
        yeni_durum = sz.NesneDurumu.AKTIF
    else:
        yeni_durum = sz.NesneDurumu.SILINDI
    oturum.execute(
        sema.nesne.update()
        .where(
            sema.nesne.c.id == talep.hedef_id, sema.nesne.c.surum == ayrinti.nesne.surum
        )
        .values(durum=yeni_durum.value, surum=ayrinti.nesne.surum + 1)
    )
    denetim.olay_yaz(
        oturum,
        aktor=sz.DenetimAktoru.KULLANICI,
        eylem=EYLEM_NESNE_ONAYI,
        hedef=denetim.hedef_adi("nesne", talep.hedef_id),
        simdi=simdi,
        gerekce=karar.gerekce,
        onceki_durum=ayrinti.nesne.durum.value,
        sonraki_durum=yeni_durum.value,
    )


onaylar.etki_kaydet(sz.OnayTuru.NESNE_ACILISI, _nesne_onayini_uygula)


# --- bulma ve getirme ---------------------------------------------------------


def nesne_getir(oturum: Session, nesne_id: int) -> NesneAyrinti:
    """Nesne, özellikleri (şart işaretli), üstleri ve altları; yoksa hata."""
    satir = oturum.execute(
        select(sema.nesne).where(sema.nesne.c.id == nesne_id)
    ).one_or_none()
    if satir is None:
        raise sz.HedefBulunamadi("nesne bulunamadı", alan="nesne_id")
    sartlar = set(
        oturum.execute(
            select(sema.nesne_sart.c.ozellik_id).where(
                sema.nesne_sart.c.nesne_id == nesne_id
            )
        ).scalars()
    )
    ozellikler = tuple(
        Ozellik(
            id=int(o.id),
            alan_adi=str(o.alan_adi),
            deger_turu=sz.DegerTuru(o.deger_turu),
            deger=o.deger,
            eslesme_degeri=o.eslesme_degeri,
            sart=int(o.id) in sartlar,
        )
        for o in oturum.execute(
            select(sema.nesne_ozellik)
            .where(sema.nesne_ozellik.c.nesne_id == nesne_id)
            .order_by(sema.nesne_ozellik.c.id)
        ).all()
    )
    ustler = tuple(
        int(u)
        for u in oturum.execute(
            select(sema.nesne_baglanti.c.ust_id)
            .where(sema.nesne_baglanti.c.alt_id == nesne_id)
            .order_by(sema.nesne_baglanti.c.ust_id)
        ).scalars()
    )
    altlar = tuple(
        int(a)
        for a in oturum.execute(
            select(sema.nesne_baglanti.c.alt_id)
            .where(sema.nesne_baglanti.c.ust_id == nesne_id)
            .order_by(sema.nesne_baglanti.c.alt_id)
        ).scalars()
    )
    return NesneAyrinti(_nesne(satir._mapping), ozellikler, ustler, altlar)  # pyright: ignore[reportPrivateUsage]


def nesne_bul(
    oturum: Session,
    *,
    alan_adi: str | None = None,
    deger: object = None,
    deger_turu: sz.DegerTuru | None = None,
    seviye: int | None = None,
    durumlar: Sequence[sz.NesneDurumu] = (
        sz.NesneDurumu.AKTIF,
        sz.NesneDurumu.ONAY_BEKLIYOR,
    ),
    sayfalama: sz.Sayfalama = sz.Sayfalama(),
) -> list[Nesne]:
    """Alan adı ve değer filtresiyle nesne arar; eşleşme türüyle yapılır (C05, 5.1).

    Cowork yeni nesne açmadan önce mevcut olanı bununla arar ("Garanti var mı?").
    Alan adı verilip değer verilmezse o alana sahip bütün nesneler; ikisi de
    verilirse değer türüyle birebir eşit olanlar. Alan adında normalizasyon yok.
    """
    sorgu = select(sema.nesne).where(
        sema.nesne.c.durum.in_([d.value for d in durumlar])
    )
    if seviye is not None:
        sorgu = sorgu.where(sema.nesne.c.seviye == seviye)
    if alan_adi is not None:
        alt = select(sema.nesne_ozellik.c.nesne_id).where(
            sema.nesne_ozellik.c.alan_adi == alan_adi
        )
        if deger is not None:
            tur = deger_turu or deger_turunu_cikar(deger)
            aranan = eslesme_degeri(degeri_dogrula(deger, tur, alan=alan_adi), tur)
            if aranan is None:
                return []  # boş değer eşleşme üretmez
            alt = alt.where(sema.nesne_ozellik.c.eslesme_degeri == aranan)
        sorgu = sorgu.where(sema.nesne.c.id.in_(alt))
    satirlar = oturum.execute(
        sorgu.order_by(sema.nesne.c.id)
        .limit(sayfalama.sinir)
        .offset(sayfalama.baslangic)
    ).all()
    return [_nesne(s._mapping) for s in satirlar]  # pyright: ignore[reportPrivateUsage]


def aktif_nesneyi_getir(oturum: Session, nesne_id: int) -> Nesne:
    """Finansal yazma için nesne: ``AKTIF`` değilse açık hata."""
    nesne = nesne_getir(oturum, nesne_id).nesne
    if nesne.durum is sz.NesneDurumu.ENGELLI:
        raise sz.NesneEngelli(
            "nesne engelli; şüphe çözülene kadar yazılmaz", alan="nesne_id"
        )
    if nesne.durum is not sz.NesneDurumu.AKTIF:
        raise sz.GirdiGecersiz(
            f"nesne yazma kabul etmiyor (durum {nesne.durum.value})", alan="nesne_id"
        )
    return nesne


def _nesne(satir: RowMapping | Mapping[str, Any]) -> Nesne:
    return Nesne(
        id=int(satir["id"]),
        seviye=int(satir["seviye"]),
        durum=sz.NesneDurumu(satir["durum"]),
        surum=int(satir["surum"]),
        olusturma_zamani=satir["olusturma_zamani"],
    )

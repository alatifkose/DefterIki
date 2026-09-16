"""Onay talepleri: kullanıcı kararı bekleyen işler (C12).

Bir iş kullanıcı onayı gerektirdiğinde çağrıyı bekletmek yerine kalıcı bir
**onay talebi** açılır (``onay_talep`` tablosu) ve iş ``BEKLIYOR`` döner.
Kullanıcı kararını ne zaman isterse verir; bu arada açık transaction ya da
kilit tutulmaz. Karar, talebin hedefine (nesne ...) uygulanır.

İki kesin sınır:

* **Karar uygulayan işlev yalnız ekrana açılır.** ``karar_uygula`` MCP
  kapısından çağrılmaz; Cowork'a "kullanıcı onayladı" diyebileceği bir
  parametre hiç sunulmaz.
* **Sürüm denetimi.** Talep, hedefin o anki sürümünü taşır. Karar
  uygulanırken hedefin güncel sürümü hem talebin sürümüyle hem kararı
  verenin gördüğü sürümle aynı olmalıdır; değilse ``HEDEF_SURUMU_DEGISTI``
  ve karar uygulanmaz.

Karar etkileri türe göre ``KARAR_ETKILERI`` tablosunda; her tür kendi
aşamasında eklenir (``NESNE_ACILISI`` 4.4'te). Bu modül commit yapmaz; işlem
sahibi çağırandır.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from defteriki import denetim, sema
from defteriki import sozlesmeler as sz

EYLEM_TALEP_OLUSTUR = "onay_talebi_olustur"
EYLEM_KARAR = "onay_karari"


@dataclass(frozen=True, slots=True)
class OnayTalebi:
    id: int
    tur: sz.OnayTuru
    hedef_id: int
    hedef_surumu: int
    icerik: dict[str, Any]
    durum: sz.OnayDurumu
    karar: dict[str, Any] | None
    olusturma_zamani: datetime
    cozum_zamani: datetime | None


@dataclass(frozen=True, slots=True)
class Karar:
    onaylandi: bool
    gerekce: str | None = None
    secilen_sartlar: tuple[int, ...] = ()
    """NESNE_ACILISI onayında kullanıcının mükerrerlik şartı seçtiği özellik
    kimlikleri (K14); boş olabilir ("şart yok"). Diğer türlerde kullanılmaz."""


type KararEtkisi = Callable[[Session, OnayTalebi, Karar, datetime], None]
"""Kararı hedefe uygular; hedefin sürümünü bir artırmak da onun işidir."""

KARAR_ETKILERI: dict[sz.OnayTuru, KararEtkisi] = {}
"""Tür → etki. İlgili modül import edilince kendini kaydeder."""

HEDEF_TABLOLARI: dict[sz.OnayTuru, sema.Table] = {
    sz.OnayTuru.NESNE_ACILISI: sema.nesne,
}
"""Tür → hedefin tablosu; sürüm denetimi ``surum`` sütunundan okur."""


def etki_kaydet(tur: sz.OnayTuru, etki: KararEtkisi) -> None:
    KARAR_ETKILERI[tur] = etki


def talep_olustur(
    oturum: Session,
    *,
    tur: sz.OnayTuru,
    hedef_id: int,
    hedef_surumu: int,
    icerik: Mapping[str, Any],
    simdi: datetime,
    aktor: sz.DenetimAktoru,
    islem_id: int | None = None,
) -> OnayTalebi:
    """``BEKLIYOR`` durumunda kalıcı talep açar ve denetim olayı yazar."""
    talep_id = int(
        oturum.execute(
            sema.onay_talep.insert()
            .values(
                tur=tur.value,
                hedef_id=hedef_id,
                hedef_surumu=hedef_surumu,
                icerik=dict(icerik),
                durum=sz.OnayDurumu.BEKLIYOR.value,
                karar=None,
                olusturma_zamani=simdi,
                cozum_zamani=None,
            )
            .returning(sema.onay_talep.c.id)
        ).scalar_one()
    )
    denetim.olay_yaz(
        oturum,
        aktor=aktor,
        eylem=EYLEM_TALEP_OLUSTUR,
        hedef=denetim.hedef_adi("onay_talep", talep_id),
        simdi=simdi,
        islem_id=islem_id,
        gerekce=tur.value,
        sonraki_durum=sz.OnayDurumu.BEKLIYOR.value,
    )
    return talep_getir(oturum, talep_id)


def talep_getir(oturum: Session, talep_id: int) -> OnayTalebi:
    """Talebi döndürür; yoksa ``HEDEF_BULUNAMADI``."""
    satir = oturum.execute(
        select(sema.onay_talep).where(sema.onay_talep.c.id == talep_id)
    ).one_or_none()
    if satir is None:
        raise sz.HedefBulunamadi("onay talebi bulunamadı", alan="talep_id")
    return _talep(satir._mapping)  # pyright: ignore[reportPrivateUsage]


def bekleyenleri_listele(
    oturum: Session, *, sayfalama: sz.Sayfalama = sz.Sayfalama()
) -> list[OnayTalebi]:
    """``BEKLIYOR`` talepler, eskiden yeniye."""
    satirlar = oturum.execute(
        select(sema.onay_talep)
        .where(sema.onay_talep.c.durum == sz.OnayDurumu.BEKLIYOR.value)
        .order_by(sema.onay_talep.c.id)
        .limit(sayfalama.sinir)
        .offset(sayfalama.baslangic)
    ).all()
    return [_talep(s._mapping) for s in satirlar]  # pyright: ignore[reportPrivateUsage]


def karar_uygula(
    oturum: Session,
    *,
    talep_id: int,
    gorulen_hedef_surumu: int,
    karar: Karar,
    simdi: datetime,
    aktor: sz.DenetimAktoru = sz.DenetimAktoru.KULLANICI,
) -> OnayTalebi:
    """Kullanıcı kararını talebe ve hedefine uygular. **Yalnız ekran çağırır.**

    ``gorulen_hedef_surumu`` kararı verenin ekranda gördüğü sürümdür; talebin
    sürümü ve hedefin güncel sürümüyle aynı değilse ``HEDEF_SURUMU_DEGISTI``
    ve hiçbir şey yazılmaz. Sonuçlanmış talebe yeniden karar verilemez.
    """
    talep = talep_getir(oturum, talep_id)
    if talep.durum is not sz.OnayDurumu.BEKLIYOR:
        raise sz.GirdiGecersiz(
            f"onay talebi zaten sonuçlanmış ({talep.durum.value})", alan="talep_id"
        )
    etki = KARAR_ETKILERI.get(talep.tur)
    if etki is None:
        raise sz.GirdiGecersiz(
            f"{talep.tur.value} türü için karar uygulaması henüz yok", alan="tur"
        )
    guncel_surum = _hedef_surumu(oturum, talep)
    if not (talep.hedef_surumu == gorulen_hedef_surumu == guncel_surum):
        raise sz.HedefSurumuDegisti(
            "hedef karar beklerken değişti; güncel hâlini al, eski onayı yeni "
            "içeriğe uygulama",
            alan="hedef_surumu",
        )

    etki(oturum, talep, karar, simdi)

    yeni_durum = (
        sz.OnayDurumu.ONAYLANDI if karar.onaylandi else sz.OnayDurumu.REDDEDILDI
    )
    oturum.execute(
        sema.onay_talep.update()
        .where(sema.onay_talep.c.id == talep.id)
        .values(
            durum=yeni_durum.value,
            karar={
                "onaylandi": karar.onaylandi,
                "gerekce": karar.gerekce,
                "aktor": aktor.value,
                "gorulen_hedef_surumu": gorulen_hedef_surumu,
                "secilen_sartlar": list(karar.secilen_sartlar),
            },
            cozum_zamani=simdi,
        )
    )
    denetim.olay_yaz(
        oturum,
        aktor=aktor,
        eylem=EYLEM_KARAR,
        hedef=denetim.hedef_adi("onay_talep", talep.id),
        simdi=simdi,
        gerekce=karar.gerekce,
        onceki_durum=sz.OnayDurumu.BEKLIYOR.value,
        sonraki_durum=yeni_durum.value,
    )
    return talep_getir(oturum, talep.id)


def _hedef_surumu(oturum: Session, talep: OnayTalebi) -> int:
    tablo = HEDEF_TABLOLARI[talep.tur]
    surum = oturum.execute(
        select(tablo.c.surum).where(tablo.c.id == talep.hedef_id)
    ).scalar_one_or_none()
    if surum is None:
        raise sz.HedefBulunamadi("onay talebinin hedefi bulunamadı", alan="hedef_id")
    return int(surum)


def _talep(satir: RowMapping) -> OnayTalebi:
    return OnayTalebi(
        id=int(satir["id"]),
        tur=sz.OnayTuru(satir["tur"]),
        hedef_id=int(satir["hedef_id"]),
        hedef_surumu=int(satir["hedef_surumu"]),
        icerik=dict(satir["icerik"] or {}),
        durum=sz.OnayDurumu(satir["durum"]),
        karar=dict(satir["karar"]) if satir["karar"] is not None else None,
        olusturma_zamani=satir["olusturma_zamani"],
        cozum_zamani=satir["cozum_zamani"],
    )

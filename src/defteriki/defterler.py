"""Defter: kayıtların ait olduğu bağımsız hesap alanı (C01, C12).

Defter tanımlanır ama hemen kullanılamaz: ``ONAY_BEKLIYOR`` durumunda doğar ve
bir ``DEFTER_TANIMLAMA`` onay talebi açılır. Kullanıcı ekrandan onaylayınca
``AKTIF`` olur; reddederse ``PASIF`` kalır (kimlik yeniden kullanılmaz,
kayıt silinmez). Yalnız ``AKTIF`` defter yazma kabul eder.

İlk defter açılırken henüz defter olmadığından işlem anahtarı ``SISTEM``
kapsamındadır. Aynı anahtarla aynı içerik ikinci kez gelirse saklı sonuç
döner, yeni defter açılmaz; farklı içerik ``ANAHTAR_ICERIK_CAKISMASI``.

Kapsam denetimi: bir kimliğin verilen deftere ait olduğunu doğrulayan
``defterde_oldugunu_dogrula`` başka defterin kaydına erişimi
``DEFTER_UYUSMAZLIGI`` ile keser. Şema bunu bileşik dış anahtarla zaten
imkânsız kılar; işlev düzeyi denetim anlaşılır hata için vardır.

Bu modül commit yapmaz; işlem sahibi çağırandır.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Table, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from defteriki import denetim, islem_anahtarlari, onaylar, sema
from defteriki import sozlesmeler as sz

ARAC_DEFTER_TANIMLA = "defter_tanimla"
EYLEM_DEFTER_TANIMLA = "defter_tanimla"
EYLEM_DEFTER_ONAYI = "defter_onayi"


@dataclass(frozen=True, slots=True)
class Defter:
    id: int
    ad: str
    durum: sz.DefterDurumu
    surum: int
    olusturma_zamani: datetime
    sahip_bilgisi: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class DefterTanimlamaSonucu:
    defter: Defter
    onay_talebi: onaylar.OnayTalebi
    zaten_vardi: bool
    """Aynı işlem anahtarıyla daha önce açılmıştı; yeni yazma yapılmadı."""


def defter_tanimla(
    oturum: Session,
    *,
    ad: str,
    islem_anahtari: str,
    aktor: sz.DenetimAktoru,
    sahip_bilgisi: Mapping[str, Any] | None = None,
    simdi: datetime | None = None,
) -> DefterTanimlamaSonucu:
    """Defteri ``ONAY_BEKLIYOR`` durumunda açar ve onay talebi üretir.

    ``SISTEM`` kapsamlı işlem anahtarıyla korunur. Defter, talep, anahtar
    kaydı ve denetim olayı aynı işlemde yazılır.
    """
    ad = ad.strip()
    if not ad:
        raise sz.GirdiGecersiz("defter adı boş olamaz", alan="ad")
    simdi = simdi or sz.simdi_utc()
    icerik: dict[str, Any] = {
        "ad": ad,
        "sahip_bilgisi": dict(sahip_bilgisi) if sahip_bilgisi else None,
    }

    def ac(islem_id: int) -> islem_anahtarlari.Sonuc:
        defter_id = int(
            oturum.execute(
                sema.defter.insert()
                .values(
                    ad=ad,
                    sahip_bilgisi=icerik["sahip_bilgisi"],
                    durum=sz.DefterDurumu.ONAY_BEKLIYOR.value,
                    surum=1,
                    olusturma_zamani=simdi,
                )
                .returning(sema.defter.c.id)
            ).scalar_one()
        )
        denetim.olay_yaz(
            oturum,
            defter_id=defter_id,
            aktor=aktor,
            eylem=EYLEM_DEFTER_TANIMLA,
            hedef=denetim.hedef_adi("defter", defter_id),
            simdi=simdi,
            islem_id=islem_id,
            sonraki_durum=sz.DefterDurumu.ONAY_BEKLIYOR.value,
        )
        talep = onaylar.talep_olustur(
            oturum,
            defter_id=defter_id,
            tur=sz.OnayTuru.DEFTER_TANIMLAMA,
            hedef_id=defter_id,
            hedef_surumu=1,
            icerik={"ad": ad},
            simdi=simdi,
            aktor=aktor,
            islem_id=islem_id,
        )
        return {"defter_id": defter_id, "onay_talebi_id": talep.id}

    sonuc, zaten_vardi = islem_anahtarlari.anahtarla_calistir(
        oturum,
        kapsam_turu=sz.IslemAnahtariKapsami.SISTEM,
        kapsam_id=islem_anahtarlari.SISTEM_KAPSAM_ID,
        arac_adi=ARAC_DEFTER_TANIMLA,
        anahtar=islem_anahtari,
        icerik=icerik,
        simdi=simdi,
        islev=ac,
    )
    defter_id = int(sonuc["defter_id"])
    return DefterTanimlamaSonucu(
        defter=defter_getir(oturum, defter_id),
        onay_talebi=onaylar.talep_getir(
            oturum, defter_id=defter_id, talep_id=int(sonuc["onay_talebi_id"])
        ),
        zaten_vardi=zaten_vardi,
    )


def defter_getir(oturum: Session, defter_id: int) -> Defter:
    """Defteri döndürür; yoksa ``DEFTER_UYUSMAZLIGI``."""
    satir = oturum.execute(
        select(sema.defter).where(sema.defter.c.id == defter_id)
    ).one_or_none()
    if satir is None:
        raise sz.DefterUyusmazligi("defter bulunamadı", alan="defter_id")
    return _defter(satir._mapping)  # pyright: ignore[reportPrivateUsage]


def aktif_defteri_getir(oturum: Session, defter_id: int) -> Defter:
    """Yazma için defter: ``AKTIF`` değilse ``DEFTER_UYUSMAZLIGI``."""
    defter = defter_getir(oturum, defter_id)
    if defter.durum is not sz.DefterDurumu.AKTIF:
        raise sz.DefterUyusmazligi(
            f"defter yazma kabul etmiyor (durum {defter.durum.value})", alan="defter_id"
        )
    return defter


def defter_listele(
    oturum: Session, *, sayfalama: sz.Sayfalama = sz.Sayfalama()
) -> list[Defter]:
    satirlar = oturum.execute(
        select(sema.defter)
        .order_by(sema.defter.c.id)
        .limit(sayfalama.sinir)
        .offset(sayfalama.baslangic)
    ).all()
    return [_defter(s._mapping) for s in satirlar]  # pyright: ignore[reportPrivateUsage]


def defterde_oldugunu_dogrula(
    oturum: Session, *, defter_id: int, tablo: Table, kimlik: int, alan: str
) -> None:
    """``tablo`` içindeki ``kimlik`` bu deftere ait değilse ``DEFTER_UYUSMAZLIGI``."""
    sahip = oturum.execute(
        select(tablo.c.defter_id).where(tablo.c.id == kimlik)
    ).scalar_one_or_none()
    if sahip is None or int(sahip) != defter_id:
        raise sz.DefterUyusmazligi(
            f"{tablo.name} kaydı bu defterde bulunamadı", alan=alan
        )


def _defter_onayini_uygula(
    oturum: Session, talep: onaylar.OnayTalebi, karar: onaylar.Karar, simdi: datetime
) -> None:
    """``DEFTER_TANIMLAMA`` kararı: onay → AKTIF, red → PASIF; sürüm bir artar."""
    yeni_durum = sz.DefterDurumu.AKTIF if karar.onaylandi else sz.DefterDurumu.PASIF
    onceki = defter_getir(oturum, talep.hedef_id)
    oturum.execute(
        sema.defter.update()
        .where(sema.defter.c.id == talep.hedef_id, sema.defter.c.surum == onceki.surum)
        .values(durum=yeni_durum.value, surum=onceki.surum + 1)
    )
    denetim.olay_yaz(
        oturum,
        defter_id=talep.defter_id,
        aktor=sz.DenetimAktoru.KULLANICI,
        eylem=EYLEM_DEFTER_ONAYI,
        hedef=denetim.hedef_adi("defter", talep.hedef_id),
        simdi=simdi,
        gerekce=karar.gerekce,
        onceki_durum=onceki.durum.value,
        sonraki_durum=yeni_durum.value,
    )


onaylar.etki_kaydet(sz.OnayTuru.DEFTER_TANIMLAMA, _defter_onayini_uygula)


def _defter(satir: RowMapping) -> Defter:
    return Defter(
        id=int(satir["id"]),
        ad=str(satir["ad"]),
        durum=sz.DefterDurumu(satir["durum"]),
        surum=int(satir["surum"]),
        olusturma_zamani=satir["olusturma_zamani"],
        sahip_bilgisi=dict(satir["sahip_bilgisi"])
        if satir["sahip_bilgisi"] is not None
        else None,
    )

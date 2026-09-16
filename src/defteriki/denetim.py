"""Denetim olayı: kim, neyi, ne zaman, hangi durumdan hangi duruma.

Her yazma işlevi yaptığı değişikliği aynı yazma işleminde ``denetim_olay``
tablosuna yazar; işlem geri alınırsa olay da gider. Olay kişisel veri
taşımaz: hedef ``tablo:kimlik`` biçiminde, gerekçe kısa metin.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from defteriki import sema
from defteriki import sozlesmeler as sz


def olay_yaz(
    oturum: Session,
    *,
    defter_id: int,
    aktor: sz.DenetimAktoru,
    eylem: str,
    hedef: str,
    simdi: datetime,
    islem_id: int | None = None,
    gerekce: str | None = None,
    onceki_durum: str | None = None,
    sonraki_durum: str | None = None,
) -> int:
    """Denetim olayını yazar; olay kimliğini döndürür. Commit yapmaz."""
    return int(
        oturum.execute(
            sema.denetim_olay.insert()
            .values(
                defter_id=defter_id,
                islem_id=islem_id,
                aktor=aktor.value,
                eylem=eylem,
                hedef=hedef,
                gerekce=gerekce,
                onceki_durum=onceki_durum,
                sonraki_durum=sonraki_durum,
                zaman=simdi,
            )
            .returning(sema.denetim_olay.c.id)
        ).scalar_one()
    )


def hedef_adi(tablo: str, kimlik: int) -> str:
    return f"{tablo}:{kimlik}"

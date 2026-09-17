"""İşlem anahtarı: aynı isteğin ikinci kez uygulanmasını önler (K08).

Her yazma işlevi bir ``islem_anahtari`` alır. Anahtar araç adıyla birlikte
benzersizdir: ``(arac_adi, anahtar)``. Aynı anahtar ikinci kez gelirse:

* istek içeriği aynıysa saklı sonuç döndürülür, hiçbir şey yeniden yazılmaz;
* içerik farklıysa ``ANAHTAR_ICERIK_CAKISMASI`` verilir (Tam Plan 11.2).

İçerik karşılaştırması ``istek_ozeti`` ile yapılır: isteğin kanonik JSON'unun
SHA-256'sı. Ham istek saklanmaz.

Anahtar kaydı, işin sonucu ve denetim olayı aynı yazma işleminde yazılır;
işlem sahibi çağırandır (``Veritabani.yazma_islemi``). Bu modül commit yapmaz.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from defteriki import sema
from defteriki import sozlesmeler as sz

type IstekIcerigi = Mapping[str, object]
type Sonuc = dict[str, Any]


@dataclass(frozen=True, slots=True)
class AnahtarKaydi:
    id: int
    arac_adi: str
    anahtar: str
    sonuc: Sonuc | None
    """İş bittiyse saklı sonuç; ``None`` ise anahtar açıldı ama iş tamamlanmadı."""
    olusturma_zamani: datetime


def anahtar_kayitlarini_getir(
    oturum: Session, *, arac_adi: str, anahtar: str
) -> list[AnahtarKaydi]:
    """Anahtarın kayıtları: birebir eşleşen ve ``<anahtar>#<n>`` türevleri.

    Kesintiden sonra Cowork "bu anahtarla ne oldu?" diye sorar (K08). Paket
    araçları satır anahtarlarını paket anahtarına ``#sıra`` ekleyerek üretir;
    hepsi birlikte döner. Hiç kayıt yoksa iş hiç uygulanmamıştır.
    """
    temiz = anahtari_dogrula(anahtar)
    onek = temiz.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "#%"
    satirlar = oturum.execute(
        select(sema.islem_anahtari)
        .where(
            sema.islem_anahtari.c.arac_adi == arac_adi,
            (sema.islem_anahtari.c.anahtar == temiz)
            | sema.islem_anahtari.c.anahtar.like(onek, escape="\\"),
        )
        .order_by(sema.islem_anahtari.c.id)
    ).all()
    return [
        AnahtarKaydi(
            id=int(s.id),
            arac_adi=str(s.arac_adi),
            anahtar=str(s.anahtar),
            sonuc=dict(s.sonuc) if s.sonuc is not None else None,
            olusturma_zamani=s.olusturma_zamani,
        )
        for s in satirlar
    ]


def istek_ozeti(icerik: IstekIcerigi) -> str:
    """İsteğin kanonik JSON'unun SHA-256 özeti (hex)."""
    metin = json.dumps(
        icerik, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str
    )
    return hashlib.sha256(metin.encode("utf-8")).hexdigest()


def anahtari_dogrula(anahtar: str) -> str:
    """Boş ya da yalnız boşluktan oluşan anahtarı reddeder."""
    temiz = anahtar.strip()
    if not temiz:
        raise sz.GirdiGecersiz("işlem anahtarı boş olamaz", alan="islem_anahtari")
    return temiz


def anahtarla_calistir(
    oturum: Session,
    *,
    arac_adi: str,
    anahtar: str,
    icerik: IstekIcerigi,
    simdi: datetime,
    islev: Callable[[int], Sonuc],
) -> tuple[Sonuc, bool]:
    """İşi anahtar korumasıyla çalıştırır.

    Anahtar daha önce aynı içerikle kullanılmışsa ``(saklı sonuç, True)``
    döner ve ``islev`` çağrılmaz. Farklı içerikle kullanılmışsa
    ``AnahtarIcerikCakismasi``. Yeni anahtarda kayıt açılır, ``islev`` anahtar
    kaydının kimliğiyle çağrılır (denetim olayına bağlamak için), sonucu
    kayda yazılır ve ``(sonuç, False)`` döner.
    """
    anahtar = anahtari_dogrula(anahtar)
    ozet = istek_ozeti(icerik)
    mevcut = oturum.execute(
        select(
            sema.islem_anahtari.c.id,
            sema.islem_anahtari.c.istek_ozeti,
            sema.islem_anahtari.c.sonuc,
        ).where(
            sema.islem_anahtari.c.arac_adi == arac_adi,
            sema.islem_anahtari.c.anahtar == anahtar,
        )
    ).one_or_none()

    if mevcut is not None:
        if mevcut.istek_ozeti != ozet:
            raise sz.AnahtarIcerikCakismasi(
                "aynı işlem anahtarı farklı içerikle kullanılmış; eski işi sorgula, "
                "farklı içerik için yeni anahtar üret",
                alan="islem_anahtari",
            )
        sakli: Sonuc = dict(mevcut.sonuc or {})
        return sakli, True

    kayit_id = oturum.execute(
        sema.islem_anahtari.insert()
        .values(
            arac_adi=arac_adi,
            anahtar=anahtar,
            istek_ozeti=ozet,
            sonuc=None,
            olusturma_zamani=simdi,
        )
        .returning(sema.islem_anahtari.c.id)
    ).scalar_one()

    sonuc = islev(int(kayit_id))
    oturum.execute(
        sema.islem_anahtari.update()
        .where(sema.islem_anahtari.c.id == kayit_id)
        .values(sonuc=sonuc)
    )
    return sonuc, False

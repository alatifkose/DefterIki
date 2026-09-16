"""Hesaplamalar (Teslim 4.6): etkin bakiye ve hareket listesi.

Tam Plan 10.3: ``etkin(etki)`` = en az bir **KAYITLI ve geçerli** kaynak
desteği. Bakiye yalnız etkin etkileri toplar: ARTTIR toplamı − AZALT
toplamı; tarih sınırı iki uç dahil; para birimleri ayrı. Yazılmış ama
belgesi henüz ``KAYITLI`` olmayan kayıt bakiyeye girmez, "bekleyen" olarak
ayrıca sayılır (K19, C08). Hesaplamalar SQL'de yapılır; GUI ve MCP aynı
işlevden aynı sonucu alır.

Etkin kaynak desteği: ``kayit_kaynak`` ``AKTIF``, kaynak satırının okuması
belgenin **etkin okuması** (``belge.etkin_okuma_id``), belge ``KAYITLI``,
kayıt ``AKTIF``. Çifte toplama engeli (8.5.5): her etki için destek
``EXISTS`` ile seçilir, sonra her etki bir kez toplanır; üç belgeye bağlı
etki üçe katlanmaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import Select, and_, case, exists, func, select
from sqlalchemy.orm import Session

from defteriki import sema
from defteriki import sozlesmeler as sz


@dataclass(frozen=True, slots=True)
class Bakiye:
    nesne_id: int
    eksen: sz.Eksen
    para_birimi: sz.ParaBirimi
    tarih: date | None
    """Verilmişse bu tarih dahil olmak üzere işlem tarihi sınırı."""
    arttir_kurus: int
    azalt_kurus: int
    bekleyen_kayit_sayisi: int
    """Yazılmış ama belgesi KAYITLI olmadığı için bakiyeye girmeyen kayıtlar."""

    @property
    def bakiye_kurus(self) -> int:
        return self.arttir_kurus - self.azalt_kurus


@dataclass(frozen=True, slots=True)
class HareketOzeti:
    kayit_id: int
    etki_id: int
    islem_tarihi: date
    valor_tarihi: date | None
    aciklama: str | None
    yon: sz.Yon
    tutar_kurus: int
    para_birimi: sz.ParaBirimi
    kayitli: bool
    """Etki en az bir KAYITLI belgeye dayanıyor; yoksa yazılmış ama bekliyor."""


def _etkin_destek_var() -> Select[tuple[int]]:
    """``etki.kayit_id`` için KAYITLI ve geçerli kaynak desteği (EXISTS gövdesi)."""
    kk, os_, ok, b = (
        sema.kayit_kaynak,
        sema.okuma_satir,
        sema.okuma,
        sema.belge,
    )
    return (
        select(kk.c.id)
        .join(os_, os_.c.id == kk.c.okuma_satir_id)
        .join(ok, ok.c.id == os_.c.okuma_id)
        .join(b, b.c.id == ok.c.belge_id)
        .where(
            kk.c.kayit_id == sema.etki.c.kayit_id,
            kk.c.durum == sz.KaynakDurumu.AKTIF.value,
            b.c.durum == sz.BelgeDurumu.KAYITLI.value,
            b.c.etkin_okuma_id == ok.c.id,
        )
    )


def etkin_bakiye(
    oturum: Session,
    *,
    nesne_id: int,
    eksen: sz.Eksen = sz.Eksen.VARLIK,
    para_birimi: sz.ParaBirimi = sz.ParaBirimi.TRY,
    tarih: date | None = None,
) -> Bakiye:
    """Nesnenin bir eksendeki etkin bakiyesi; her etki bir kez (EXISTS)."""
    e, k = sema.etki, sema.kayit
    kosullar = [
        e.c.nesne_id == nesne_id,
        e.c.eksen == eksen.value,
        e.c.para_birimi == para_birimi.value,
        k.c.durum == sz.KayitDurumu.AKTIF.value,
    ]
    if tarih is not None:
        kosullar.append(k.c.islem_tarihi <= tarih)
    etkin = exists(_etkin_destek_var())
    arttir = func.coalesce(
        func.sum(case((e.c.yon == sz.Yon.ARTTIR.value, e.c.tutar_kurus), else_=0)), 0
    )
    azalt = func.coalesce(
        func.sum(case((e.c.yon == sz.Yon.AZALT.value, e.c.tutar_kurus), else_=0)), 0
    )
    satir = oturum.execute(
        select(arttir, azalt)
        .select_from(e.join(k, k.c.id == e.c.kayit_id))
        .where(and_(*kosullar), etkin)
    ).one()
    bekleyen = oturum.execute(
        select(func.count(func.distinct(e.c.kayit_id)))
        .select_from(e.join(k, k.c.id == e.c.kayit_id))
        .where(and_(*kosullar), ~etkin)
    ).scalar_one()
    return Bakiye(
        nesne_id=nesne_id,
        eksen=eksen,
        para_birimi=para_birimi,
        tarih=tarih,
        arttir_kurus=int(satir[0]),
        azalt_kurus=int(satir[1]),
        bekleyen_kayit_sayisi=int(bekleyen),
    )


def hareketleri_listele(
    oturum: Session,
    *,
    nesne_id: int,
    eksen: sz.Eksen = sz.Eksen.VARLIK,
    baslangic: date | None = None,
    bitis: date | None = None,
    sayfalama: sz.Sayfalama = sz.Sayfalama(),
) -> list[HareketOzeti]:
    """Nesnenin hareketleri, tarih ve kimlik sırasıyla; her satır kayıtlı mı söyler.

    Geçersiz (``GECERSIZ``) kayıtlar listeye girmez; geçmiş görünümü Aşama 8'de.
    """
    e, k = sema.etki, sema.kayit
    sorgu = (
        select(
            k.c.id,
            e.c.id,
            k.c.islem_tarihi,
            k.c.valor_tarihi,
            k.c.aciklama,
            e.c.yon,
            e.c.tutar_kurus,
            e.c.para_birimi,
            exists(_etkin_destek_var()).label("kayitli"),
        )
        .select_from(e.join(k, k.c.id == e.c.kayit_id))
        .where(
            e.c.nesne_id == nesne_id,
            e.c.eksen == eksen.value,
            k.c.durum == sz.KayitDurumu.AKTIF.value,
        )
    )
    if baslangic is not None:
        sorgu = sorgu.where(k.c.islem_tarihi >= baslangic)
    if bitis is not None:
        sorgu = sorgu.where(k.c.islem_tarihi <= bitis)
    satirlar = oturum.execute(
        sorgu.order_by(k.c.islem_tarihi, k.c.id, e.c.id)
        .limit(sayfalama.sinir)
        .offset(sayfalama.baslangic)
    ).all()
    return [
        HareketOzeti(
            kayit_id=int(s[0]),
            etki_id=int(s[1]),
            islem_tarihi=s[2],
            valor_tarihi=s[3],
            aciklama=s[4],
            yon=sz.Yon(s[5]),
            tutar_kurus=int(s[6]),
            para_birimi=sz.ParaBirimi(s[7]),
            kayitli=bool(s[8]),
        )
        for s in satirlar
    ]

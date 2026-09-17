"""Pencerenin çağırdığı işlevler (Aşama 6; K20).

Katman sırası: pencere → bu modül → Aşama 4 işlevleri ve veritabanı. Pencere
``veritabani`` modülünü import etmez, oturum açmaz, SQL bilmez; buradaki
işlevlere düz sorular sorar ("veri değişti mi?", "bekleyenler kim?", "şu
talebe şu kararı ver") ve düz cevaplar alır. Veritabanı nesnesini bu modül
tutar ve kapatır; işlem sahibi de bu modüldür.

Bu modül kural koymaz: ``onaylar.karar_uygula`` sürüm denetimini,
``nesneler`` şart ve durum etkilerini uygular; buradaki işlevler onları
çağırır ve sonucu pencerenin göstereceği düz değerlere çevirir. Zamanlar
pencereye yerel saat olarak verilir (veritabanında UTC).

Teslim 6.1: ``degisti_mi``. Teslim 6.2: ``bekleyenler``, ``talep_ayrintisi``,
``karar_ver``. 6.3 bakiye ve hareket listesi buraya eklenir.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from defteriki import nesneler, onaylar
from defteriki import sozlesmeler as sz
from defteriki.ayarlar import Ayarlar
from defteriki.veritabani import Veritabani, veritabani_ac

OZET_OZELLIK_SAYISI = 3
"""Listede bir nesneyi tanıtan en fazla özellik sayısı."""


@dataclass(frozen=True, slots=True)
class TalepOzeti:
    """Bekleyenler listesinin bir satırı."""

    talep_id: int
    tur: str
    hedef_id: int
    hedef_surumu: int
    olusturma_zamani: datetime
    """Yerel saat, dilim bilgisiyle."""
    hedef_ozeti: str
    """Hedef nesnenin ilk özellikleri: ``ad=Akbank; tür=banka``."""


@dataclass(frozen=True, slots=True)
class OzellikSatiri:
    ozellik_id: int
    alan_adi: str
    deger: str
    deger_turu: str
    sart: bool
    """Daha önce şart seçilmiş mi (onaylı nesnelerde)."""


@dataclass(frozen=True, slots=True)
class TalepAyrintisi:
    """Karar kutusunun sağ tarafı: talep, hedef nesne, üstleri, özellikleri."""

    talep: TalepOzeti
    nesne_id: int
    seviye: int
    nesne_durumu: str
    nesne_surumu: int
    """Kararda ``gorulen_surum`` olarak geri verilir."""
    ustler: tuple[str, ...]
    """Üst nesnelerin özetleri: ``nesne 1: ad=Akbank; tür=banka``."""
    ozellikler: tuple[OzellikSatiri, ...]


@dataclass(frozen=True, slots=True)
class KararSonucu:
    talep_id: int
    talep_durumu: str
    nesne_id: int
    nesne_durumu: str
    nesne_surumu: int


class PencereIslevleri:
    """Tek pencereye ait bağlam; ``pencere_islevleri_ac`` ile kurulur."""

    def __init__(self, veritabani: Veritabani) -> None:
        self._veritabani = veritabani
        self._son_sayac: int | None = None

    # --- değişiklik (6.1) -------------------------------------------------------------

    def degisti_mi(self) -> bool:
        """Son sorudan bu yana başka bir süreç ya da bağlantı yazdı mı?

        İlk soru başlangıç noktasını alır ve ``False`` döndürür. Yazma kilidi
        tutmaz; Cowork'un ya da onay komutunun yazmasını geciktirmez.
        """
        sayac = self._veritabani.degisiklik_sayaci()
        degisti = self._son_sayac is not None and sayac != self._son_sayac
        self._son_sayac = sayac
        return degisti

    # --- karar kutusu (6.2) -----------------------------------------------------------

    def bekleyenler(self) -> list[TalepOzeti]:
        """Kullanıcı kararı bekleyen talepler, eskiden yeniye, hedef özetiyle."""
        with self._veritabani.okuma_islemi() as oturum:
            talepler = onaylar.bekleyenleri_listele(oturum)
            ozellikler = nesneler.ozellikleri_getir(
                oturum, [t.hedef_id for t in talepler]
            )
            return [
                _talep_ozeti(t, _ozet(ozellikler.get(t.hedef_id, ()))) for t in talepler
            ]

    def talep_ayrintisi(self, talep_id: int) -> TalepAyrintisi:
        """Talep, hedef nesne, üst özetleri ve şart seçimi için özellikler.

        Talep yoksa ``HEDEF_BULUNAMADI``.
        """
        with self._veritabani.okuma_islemi() as oturum:
            talep = onaylar.talep_getir(oturum, talep_id)
            ayrinti = nesneler.nesne_getir(oturum, talep.hedef_id)
            ust_ozellikleri = nesneler.ozellikleri_getir(oturum, ayrinti.ust_idleri)
            return TalepAyrintisi(
                talep=_talep_ozeti(talep, _ozet(ayrinti.ozellikler)),
                nesne_id=ayrinti.nesne.id,
                seviye=ayrinti.nesne.seviye,
                nesne_durumu=ayrinti.nesne.durum.value,
                nesne_surumu=ayrinti.nesne.surum,
                ustler=tuple(
                    f"nesne {u}: {_ozet(ust_ozellikleri.get(u, ()))}"
                    for u in ayrinti.ust_idleri
                ),
                ozellikler=tuple(
                    OzellikSatiri(
                        ozellik_id=o.id,
                        alan_adi=o.alan_adi,
                        deger="" if o.deger is None else str(o.deger),
                        deger_turu=o.deger_turu.value,
                        sart=o.sart,
                    )
                    for o in ayrinti.ozellikler
                ),
            )

    def karar_ver(
        self,
        talep_id: int,
        gorulen_surum: int,
        *,
        onaylandi: bool,
        secilen_sartlar: Sequence[int] = (),
        gerekce: str | None = None,
    ) -> KararSonucu:
        """Kullanıcı kararını uygular (``onaylar.karar_uygula``, aktör KULLANICI).

        ``gorulen_surum`` pencerede gösterilen nesne sürümüdür; hedef bu arada
        değiştiyse ``HEDEF_SURUMU_DEGISTI`` ve hiçbir şey yazılmaz. Erteleme
        için işlev yoktur: karar verilmeyen talep ``BEKLIYOR`` kalır.
        """
        karar = onaylar.Karar(
            onaylandi=onaylandi,
            gerekce=gerekce or None,
            secilen_sartlar=tuple(secilen_sartlar),
        )
        with self._veritabani.yazma_islemi() as oturum:
            talep = onaylar.karar_uygula(
                oturum,
                talep_id=talep_id,
                gorulen_hedef_surumu=gorulen_surum,
                karar=karar,
                simdi=sz.simdi_utc(),
                aktor=sz.DenetimAktoru.KULLANICI,
            )
            return _karar_sonucu(oturum, talep)

    def kapat(self) -> None:
        self._veritabani.kapat()


def pencere_islevleri_ac(ayarlar: Ayarlar) -> PencereIslevleri:
    """Ayarlardaki veritabanı için pencere işlevlerini kurar; dosya oluşturmaz."""
    return PencereIslevleri(veritabani_ac(ayarlar))


# --- çeviriler ------------------------------------------------------------------------


def yerel_saat(utc_zaman: datetime) -> datetime:
    """Veritabanındaki dilimsiz UTC zamanı yerel saate çevirir (dilim bilgisiyle)."""
    return utc_zaman.replace(tzinfo=UTC).astimezone()


def _ozet(ozellikler: Sequence[nesneler.Ozellik]) -> str:
    return "; ".join(
        f"{o.alan_adi}={o.deger}" for o in ozellikler[:OZET_OZELLIK_SAYISI]
    )


def _talep_ozeti(talep: onaylar.OnayTalebi, hedef_ozeti: str) -> TalepOzeti:
    return TalepOzeti(
        talep_id=talep.id,
        tur=talep.tur.value,
        hedef_id=talep.hedef_id,
        hedef_surumu=talep.hedef_surumu,
        olusturma_zamani=yerel_saat(talep.olusturma_zamani),
        hedef_ozeti=hedef_ozeti,
    )


def _karar_sonucu(oturum: Session, talep: onaylar.OnayTalebi) -> KararSonucu:
    nesne = nesneler.nesne_getir(oturum, talep.hedef_id).nesne
    return KararSonucu(
        talep_id=talep.id,
        talep_durumu=talep.durum.value,
        nesne_id=nesne.id,
        nesne_durumu=nesne.durum.value,
        nesne_surumu=nesne.surum,
    )

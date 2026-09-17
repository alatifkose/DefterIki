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
``karar_ver``. Teslim 6.3: ``hesaplar``, ``bakiye``, ``hareketler``,
``belgeler``, ``belge_dosya_yolu``; para ``tutar_metni`` ile gösterilir.
``bakiye`` para birimi başına ayrı döner; kodda para birimi yoktur.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

from sqlalchemy.orm import Session

from defteriki import arsiv, belgeler, hesaplamalar, nesneler, onaylar
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


@dataclass(frozen=True, slots=True)
class HesapSecenegi:
    """Hareket görünümünde seçilebilen AKTIF nesne."""

    nesne_id: int
    seviye: int
    ozet: str


@dataclass(frozen=True, slots=True)
class BakiyeOzeti:
    nesne_id: int
    para_birimi: str
    arttir_kurus: int
    azalt_kurus: int
    bakiye_kurus: int
    bekleyen_kayit_sayisi: int
    """Yazılmış ama belgesi KAYITLI olmadığı için bakiyeye girmeyenler."""


@dataclass(frozen=True, slots=True)
class HareketSatiri:
    kayit_id: int
    islem_tarihi: date
    valor_tarihi: date | None
    aciklama: str
    yon: str
    tutar_kurus: int
    para_birimi: str
    kayitli: bool
    belge_idleri: tuple[int, ...]
    """Kaydı destekleyen belgeler; kaynak belgeyi açmak için."""


@dataclass(frozen=True, slots=True)
class BelgeSatiri:
    belge_id: int
    durum: str
    surum: int
    kaynak_adi: str
    boyut: int
    mime: str
    olusturma_zamani: datetime
    """Yerel saat, dilim bilgisiyle."""


class PencereIslevleri:
    """Tek pencereye ait bağlam; ``pencere_islevleri_ac`` ile kurulur."""

    def __init__(self, veritabani: Veritabani, belge_dizini: Path) -> None:
        self._veritabani = veritabani
        self._belge_dizini = belge_dizini
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

    # --- bakiye ve hareketler (6.3) ---------------------------------------------------

    def hesaplar(self) -> list[HesapSecenegi]:
        """Seçilebilen AKTIF nesneler, kimlik sırasıyla, özetiyle."""
        with self._veritabani.okuma_islemi() as oturum:
            nesneler_ = nesneler.nesne_bul(
                oturum,
                durumlar=(sz.NesneDurumu.AKTIF,),
                sayfalama=sz.Sayfalama(sinir=sz.AZAMI_SAYFA_BOYUTU),
            )
            ozellikler = nesneler.ozellikleri_getir(oturum, [n.id for n in nesneler_])
            return [
                HesapSecenegi(n.id, n.seviye, _ozet(ozellikler.get(n.id, ())))
                for n in nesneler_
            ]

    def bakiyeler(self, nesne_id: int) -> list[BakiyeOzeti]:
        """Etkin bakiye, para birimi başına (yalnız KAYITLI belgeler;
        ``hesaplamalar.etkin_bakiyeler``). Hareket yoksa boş liste."""
        with self._veritabani.okuma_islemi() as oturum:
            liste = hesaplamalar.etkin_bakiyeler(oturum, nesne_id=nesne_id)
        return [
            BakiyeOzeti(
                nesne_id=b.nesne_id,
                para_birimi=b.para_birimi,
                arttir_kurus=b.arttir_kurus,
                azalt_kurus=b.azalt_kurus,
                bakiye_kurus=b.bakiye_kurus,
                bekleyen_kayit_sayisi=b.bekleyen_kayit_sayisi,
            )
            for b in liste
        ]

    def hareketler(self, nesne_id: int) -> list[HareketSatiri]:
        """Nesnenin hareketleri tarih sırasıyla; kayıtlı bayrağı ve belgeleriyle."""
        with self._veritabani.okuma_islemi() as oturum:
            satirlar = hesaplamalar.hareketleri_listele(
                oturum,
                nesne_id=nesne_id,
                sayfalama=sz.Sayfalama(sinir=sz.AZAMI_SAYFA_BOYUTU),
            )
            return [
                HareketSatiri(
                    kayit_id=h.kayit_id,
                    islem_tarihi=h.islem_tarihi,
                    valor_tarihi=h.valor_tarihi,
                    aciklama=h.aciklama or "",
                    yon=h.yon.value,
                    tutar_kurus=h.tutar_kurus,
                    para_birimi=h.para_birimi,
                    kayitli=h.kayitli,
                    belge_idleri=belgeler.kaydin_belge_idleri(oturum, h.kayit_id),
                )
                for h in satirlar
            ]

    def belgeler(self) -> list[BelgeSatiri]:
        """Belgeler yeniden eskiye, durumuyla."""
        with self._veritabani.okuma_islemi() as oturum:
            liste = belgeler.belgeleri_listele(
                oturum, sayfalama=sz.Sayfalama(sinir=sz.AZAMI_SAYFA_BOYUTU)
            )
        return [
            BelgeSatiri(
                belge_id=b.belge.id,
                durum=b.belge.durum.value,
                surum=b.belge.surum,
                kaynak_adi=b.dosya.kaynak_adi,
                boyut=b.dosya.boyut,
                mime=b.dosya.mime,
                olusturma_zamani=yerel_saat(b.belge.olusturma_zamani),
            )
            for b in liste
        ]

    def belge_dosya_yolu(self, belge_id: int) -> Path:
        """Belgenin arşivdeki dosyası; pencere işletim sistemine açtırır.

        Belge yoksa ``BELGE_YOK``, dosya arşivde yerinde değilse ``ARSIV_EKSIK``.
        """
        with self._veritabani.okuma_islemi() as oturum:
            dosya = belgeler.belge_getir(oturum, belge_id).dosya
        yol = arsiv.arsiv_yolu(self._belge_dizini, dosya.goreli_yol)
        if not arsiv.arsivde_var_mi(self._belge_dizini, dosya.goreli_yol, dosya.boyut):
            raise sz.ArsivEksik("belgenin dosyası arşivde yok", alan="belge_id")
        return yol

    def kapat(self) -> None:
        self._veritabani.kapat()


def pencere_islevleri_ac(ayarlar: Ayarlar) -> PencereIslevleri:
    """Ayarlardaki veritabanı için pencere işlevlerini kurar; dosya oluşturmaz."""
    return PencereIslevleri(veritabani_ac(ayarlar), ayarlar.belge_dizini)


# --- çeviriler ------------------------------------------------------------------------


def yerel_saat(utc_zaman: datetime) -> datetime:
    """Veritabanındaki dilimsiz UTC zamanı yerel saate çevirir (dilim bilgisiyle)."""
    return utc_zaman.replace(tzinfo=UTC).astimezone()


def tutar_metni(kurus: int, para_birimi: str) -> str:
    """Kuruşu Türkçe sayı biçimine çevirir ve para birimi kodunu olduğu gibi
    ekler: ``-2635`` → ``-26,35 <kod>``. Kodda para birimi ya da simge eşlemesi yok."""
    isaret = "-" if kurus < 0 else ""
    lira, kalan = divmod(abs(kurus), 100)
    lira_metni = f"{lira:,}".replace(",", ".")
    return f"{isaret}{lira_metni},{kalan:02d} {para_birimi}"


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

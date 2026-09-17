"""MCP araçlarının gövdeleri (Teslim 5.1'den itibaren).

Araç kodu kural içermez (K01): girdi modelini alır, işlem sahibi olarak
yazma ya da okuma işlemini açar, Aşama 4 işlevini çağırır, sonucu zarfa
koyar. Her işlev ``AracBaglami`` (veritabanı + ayarlar) ve doğrulanmış
girdiyle çağrılır; MCP sunucusundan bağımsız test edilir. Kayıt/protokol
işi ``mcp_kapisi``dedir.

Girdi modelleri Pydantic'tir; SDK bunlardan JSON Schema üretir ve çağrıdan
önce doğrular. Şema reddi ``mcp_kapisi`` tarafından güvenli zarfa çevrilir.
İşlem anahtarı her değişiklik yapan araçta zorunludur (K08); eksikse araç
kendi ``GIRDI_GECERSIZ`` hatasını verir. Okuma araçları salt okunur işlemde
çalışır ve anahtar istemez.

Araçlar: 5.1 ``nesne_tanimla`` (FORM / GONDER); 5.2/1 ``nesne_bul``,
``nesne_getir``, ``oturum_baglami`` (C16); 5.2/2 ``belge_al``,
``belge_getir``, ``okuma_baslat``, ``hareket_yaz`` (yalnız HESAP_HAREKETI,
paket hâlinde; K07 paket atomik), ``okuma_tamamla`` (uygulama belge kaydını
tanımlar, C07), ``belge_kaydet``. Zarfın ``belge_kaydi`` alanı her belge
aracında "yazıldı ama kayıtlı değil" ayrımını taşır (K19). 5.2/3
``islem_durumu`` (talep ya da işlem anahtarıyla kalıcı durum; kesintide önce
bu sorulur), ``bekleyen_isler``, ``sorgu`` (yalnız ``bakiye`` ve
``hareketler`` raporları; serbest SQL yok).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from defteriki import belgeler, islem_anahtarlari, kayitlar, nesneler, onaylar, zarf
from defteriki import finansal_kurallar as fk
from defteriki import hesaplamalar as hs
from defteriki import sozlesmeler as sz
from defteriki.ayarlar import Ayarlar
from defteriki.veritabani import Veritabani

AKTOR = sz.DenetimAktoru.COWORK
"""MCP kapısından gelen her yazma Cowork'a aittir."""

AZAMI_PAKET_HAREKETI = belgeler.AZAMI_GONDERIM_SATIRI
"""Bir hareket_yaz paketinde en çok satır (C18)."""

SONRAKI_ONAY_BEKLE = (
    "Kullanıcı kararı bekleniyor. Bekleme; talep kimliğiyle islem_durumu aracını "
    "sonra çağır. Kendi kendine onay üretme."
)
SONRAKI_OKUMA_AC = (
    "okuma_baslat ile okumayı aç, sonra hareket_yaz ile satırları gönder."
)
SONRAKI_SATIR_GONDER = (
    "hareket_yaz ile satırları paket paket gönder; hepsi bitince okuma_tamamla çağır. "
    "Yazılanlar belge KAYITLI olana kadar hesaba girmez."
)
SONRAKI_KAYITLI = "Belge kayıtlı; etkileri hesaba girdi. Aynı belgeyi yeniden işleme."


@dataclass(frozen=True, slots=True)
class AracBaglami:
    """Araçların ortak bağlamı: veritabanı ve dizin ayarları (gelen, belge)."""

    veritabani: Veritabani
    ayarlar: Ayarlar


# --- nesne araçları -------------------------------------------------------------------


class OzellikGirdi(BaseModel):
    model_config = ConfigDict(frozen=True)

    alan_adi: str = Field(
        description="Serbest alan adı; mevcut nesnelerin adlarını aynen kullan."
    )
    deger: Any = Field(default=None, description="Değer; boş bırakılabilir.")
    deger_turu: sz.DegerTuru | None = Field(
        default=None,
        description="Verilmezse değerin türünden çıkarılır; TARIH için zorunlu.",
    )


class KaynakGirdi(BaseModel):
    model_config = ConfigDict(frozen=True)

    belge_id: int = Field(strict=True, gt=0)
    okuma_id: int | None = Field(default=None, strict=True, gt=0)
    konum: dict[str, Any] | None = Field(
        default=None, description="Belgede nerede görüldüğü (sayfa, satır ...)."
    )


class NesneTanimlaGirdisi(BaseModel):
    """FORM: boş formu ve kuralları al. GONDER: nesneyi öner; onay talebi açılır."""

    model_config = ConfigDict(frozen=True)

    adim: Literal["FORM", "GONDER"]
    islem_anahtari: str | None = Field(
        default=None,
        description="GONDER için zorunlu; aynı anahtar aynı içerik tek nesne.",
    )
    ozellikler: list[OzellikGirdi] = []
    ust_idleri: list[int] = Field(
        default=[],
        description="Üst nesne kimlikleri; seviye bunlardan hesaplanır.",
    )
    kaynak: KaynakGirdi | None = None


class NesneBulGirdisi(BaseModel):
    """Alan adı ve değerle nesne ara; yeni nesne önermeden önce bununla bak."""

    model_config = ConfigDict(frozen=True)

    alan_adi: str | None = Field(
        default=None, description="Aranan alan adı; normalizasyon yok, aynen yaz."
    )
    deger: Any = Field(
        default=None, description="Değer; türüyle birebir karşılaştırılır."
    )
    deger_turu: sz.DegerTuru | None = None
    seviye: int | None = Field(default=None, strict=True, ge=0)
    durumlar: list[sz.NesneDurumu] = Field(
        default=[sz.NesneDurumu.AKTIF, sz.NesneDurumu.ONAY_BEKLIYOR]
    )
    sayfa_siniri: int = Field(default=sz.VARSAYILAN_SAYFA_BOYUTU, strict=True)
    sayfa_baslangici: int = Field(default=0, strict=True)


class NesneGetirGirdisi(BaseModel):
    model_config = ConfigDict(frozen=True)

    nesne_id: int = Field(strict=True, gt=0)


class OturumBaglamiGirdisi(BaseModel):
    """Oturum başında bir kez: son nesneler, alan adları, bekleyen işler (C16)."""

    model_config = ConfigDict(frozen=True)

    son_nesne_sayisi: int = Field(default=20, strict=True, ge=1, le=100)


def nesne_tanimla(
    baglam: AracBaglami, girdi: NesneTanimlaGirdisi, islem_kimligi: str
) -> zarf.Zarf:
    """FORM veritabanına dokunmaz; GONDER nesneyi ONAY_BEKLIYOR yazar → BEKLIYOR."""
    if girdi.adim == "FORM":
        form = nesneler.tanitma_formu()
        return zarf.Zarf(
            durum=zarf.YanitDurumu.TAMAMLANDI,
            islem_kimligi=islem_kimligi,
            icerik={
                "kurallar": list(form.kurallar),
                "satir_sablonu": form.satir_sablonu,
                "deger_turleri": list(form.deger_turleri),
            },
            sonraki_adim=(
                "Formu doldur; önce nesne_bul ile mevcut nesneyi ara, sonra GONDER."
            ),
        )

    anahtar = _anahtar_zorunlu(girdi.islem_anahtari)
    with baglam.veritabani.yazma_islemi() as oturum:
        sonuc = nesneler.nesne_tanimla(
            oturum,
            ozellikler=[
                nesneler.OzellikGirdisi(o.alan_adi, o.deger, o.deger_turu)
                for o in girdi.ozellikler
            ],
            islem_anahtari=anahtar,
            aktor=AKTOR,
            ust_idleri=girdi.ust_idleri,
            kaynak=(
                nesneler.NesneKaynagi(
                    girdi.kaynak.belge_id, girdi.kaynak.okuma_id, girdi.kaynak.konum
                )
                if girdi.kaynak
                else None
            ),
        )
    nesne = sonuc.nesne
    return zarf.Zarf(
        durum=_nesne_durumundan(nesne.durum),
        islem_kimligi=islem_kimligi,
        nesne_id=nesne.id,
        talep_id=sonuc.onay_talebi.id,
        hedef_surumu=nesne.surum,
        zaten_mevcut=1 if sonuc.zaten_vardi else 0,
        yazilan=0 if sonuc.zaten_vardi else 1,
        bekleyen=1 if nesne.durum is sz.NesneDurumu.ONAY_BEKLIYOR else 0,
        icerik={
            "nesne": {
                "id": nesne.id,
                "seviye": nesne.seviye,
                "durum": nesne.durum.value,
            },
            "onay_talebi": {
                "id": sonuc.onay_talebi.id,
                "durum": sonuc.onay_talebi.durum.value,
            },
        },
        sonraki_adim=_nesne_sonraki_adimi(nesne.durum),
    )


def nesne_bul(
    baglam: AracBaglami, girdi: NesneBulGirdisi, islem_kimligi: str
) -> zarf.Zarf:
    """Filtreye uyan nesneler ve özellikleri; eşleşme türüyle yapılır (C05)."""
    sayfalama = sz.Sayfalama(girdi.sayfa_siniri, girdi.sayfa_baslangici)
    with baglam.veritabani.okuma_islemi() as oturum:
        nesneler_ = nesneler.nesne_bul(
            oturum,
            alan_adi=girdi.alan_adi,
            deger=girdi.deger,
            deger_turu=girdi.deger_turu,
            seviye=girdi.seviye,
            durumlar=girdi.durumlar,
            sayfalama=sayfalama,
        )
        ozellikler = nesneler.ozellikleri_getir(oturum, [n.id for n in nesneler_])
    return zarf.Zarf(
        durum=zarf.YanitDurumu.TAMAMLANDI,
        islem_kimligi=islem_kimligi,
        icerik={
            "nesneler": [_nesne_ozeti(n, ozellikler.get(n.id, ())) for n in nesneler_],
            "sayfa": {
                "sinir": sayfalama.sinir,
                "baslangic": sayfalama.baslangic,
                "donen": len(nesneler_),
            },
        },
        sonraki_adim=(
            "Mevcut nesnenin kimliğini kullan; aynı nesneyi yeniden önerme."
            if nesneler_
            else "Eşleşen nesne yok; belgede kanıtı varsa nesne_tanimla ile öner."
        ),
    )


def nesne_getir(
    baglam: AracBaglami, girdi: NesneGetirGirdisi, islem_kimligi: str
) -> zarf.Zarf:
    """Nesne, özellikleri (şart işaretli), üstleri ve altları."""
    with baglam.veritabani.okuma_islemi() as oturum:
        ayrinti = nesneler.nesne_getir(oturum, girdi.nesne_id)
    return zarf.Zarf(
        durum=zarf.YanitDurumu.TAMAMLANDI,
        islem_kimligi=islem_kimligi,
        nesne_id=ayrinti.nesne.id,
        hedef_surumu=ayrinti.nesne.surum,
        icerik={
            **_nesne_ozeti(ayrinti.nesne, ayrinti.ozellikler),
            "ust_idleri": list(ayrinti.ust_idleri),
            "alt_idleri": list(ayrinti.alt_idleri),
        },
        sonraki_adim=_nesne_sonraki_adimi(ayrinti.nesne.durum),
    )


def oturum_baglami(
    baglam: AracBaglami, girdi: OturumBaglamiGirdisi, islem_kimligi: str
) -> zarf.Zarf:
    """C16: kalıcı kimlikler DEFTERIKI'dedir; Cowork oturum başında bunları alır."""
    with baglam.veritabani.okuma_islemi() as oturum:
        son = nesneler.son_nesneleri_listele(oturum, sinir=girdi.son_nesne_sayisi)
        ozellikler = nesneler.ozellikleri_getir(oturum, [n.id for n in son])
        alan_adlari = nesneler.alan_adlarini_listele(oturum)
        bekleyenler = onaylar.bekleyenleri_listele(oturum)
    return zarf.Zarf(
        durum=zarf.YanitDurumu.TAMAMLANDI,
        islem_kimligi=islem_kimligi,
        bekleyen=len(bekleyenler),
        icerik={
            "son_nesneler": [_nesne_ozeti(n, ozellikler.get(n.id, ())) for n in son],
            "alan_adlari": [
                {"alan_adi": ad, "kullanim": sayi} for ad, sayi in alan_adlari
            ],
            "bekleyen_isler": [
                {
                    "talep_id": t.id,
                    "tur": t.tur.value,
                    "hedef_id": t.hedef_id,
                    "hedef_surumu": t.hedef_surumu,
                    "olusturma_zamani": t.olusturma_zamani.isoformat(),
                }
                for t in bekleyenler
            ],
        },
        sonraki_adim=(
            "Bilinen kimlikleri doğrudan kullan; alan adlarını aynen kullan, eş "
            "anlamlı ad icat etme; bekleyen işler kullanıcı kararı bekliyor, "
            "onları yeniden önerme."
        ),
    )


# --- belge ve hareket araçları --------------------------------------------------------


class BelgeAlGirdisi(BaseModel):
    """Gelen dizinine bırakılan dosyayı arşivle ve belge olarak tanıt (C10)."""

    model_config = ConfigDict(frozen=True)

    yol: str = Field(description="Gelen dizinindeki dosyanın mutlak yolu.")
    islem_anahtari: str | None = None


class BelgeGetirGirdisi(BaseModel):
    model_config = ConfigDict(frozen=True)

    belge_id: int = Field(strict=True, gt=0)


class TamlikGirdi(BaseModel):
    """Belge hakkında bildirilen tamlık; verilmeyen alan bilinmiyor demektir."""

    model_config = ConfigDict(frozen=True)

    beklenen_satir_sayisi: int | None = Field(default=None, strict=True)
    acilis_bakiyesi_kurus: int | None = Field(default=None, strict=True)
    kapanis_bakiyesi_kurus: int | None = Field(default=None, strict=True)
    toplam_giris_kurus: int | None = Field(default=None, strict=True)
    toplam_cikis_kurus: int | None = Field(default=None, strict=True)


class OkumaBaslatGirdisi(BaseModel):
    model_config = ConfigDict(frozen=True)

    belge_id: int = Field(strict=True, gt=0)
    islem_anahtari: str | None = None
    talimat_surumu: str = Field(
        default=zarf.TALIMAT_SURUMU,
        description="Uyduğun Cowork talimatının sürümü; okumayla birlikte saklanır.",
    )
    icerik: dict[str, Any] | None = Field(
        default=None, description="Belge düzeyi bilgi (dönem, hesap ...)."
    )
    tamlik: TamlikGirdi | None = None


class SatirGirdi(BaseModel):
    model_config = ConfigDict(frozen=True)

    satir_anahtari: str = Field(description="Okuma içinde benzersiz istemci anahtarı.")
    konum: int = Field(strict=True, ge=0, description="Belgedeki sıra; 0'dan başlar.")
    ham: dict[str, Any] = Field(description="Satırın ham içeriği; olduğu gibi.")


class HesapHareketiGirdi(BaseModel):
    """HESAP_HAREKETI (C02): belirlenen hesapta VARLIK ARTTIR ya da AZALT."""

    model_config = ConfigDict(frozen=True)

    nesne_id: int = Field(strict=True, gt=0, description="AKTIF hesap nesnesi.")
    yon: sz.Yon
    tutar_kurus: Any = Field(
        description="Kuruş cinsinden pozitif tam sayı; ondalık, metin, yuvarlama yok.",
        json_schema_extra={"type": "integer"},
    )
    islem_tarihi: str = Field(description="YYYY-AA-GG")
    valor_tarihi: str | None = None
    aciklama: str | None = None
    para_birimi: str = "TRY"


class HareketGirdi(BaseModel):
    model_config = ConfigDict(frozen=True)

    satir: SatirGirdi
    hareket: HesapHareketiGirdi


class HareketYazGirdisi(BaseModel):
    """Bir paket: ACIK okumaya satırlar ve hareketleri. Ya hepsi ya hiçbiri (K07)."""

    model_config = ConfigDict(frozen=True)

    okuma_id: int = Field(strict=True, gt=0)
    islem_anahtari: str | None = Field(
        default=None, description="Paket anahtarı; satır anahtarları buna eklenir."
    )
    hareketler: list[HareketGirdi] = Field(
        min_length=1, max_length=AZAMI_PAKET_HAREKETI
    )


class OkumaTamamlaGirdisi(BaseModel):
    model_config = ConfigDict(frozen=True)

    okuma_id: int = Field(strict=True, gt=0)
    islem_anahtari: str | None = None
    tamlik: TamlikGirdi | None = None


class BelgeKaydetGirdisi(BaseModel):
    model_config = ConfigDict(frozen=True)

    belge_id: int = Field(strict=True, gt=0)
    gorulen_surum: int = Field(strict=True, ge=1)
    islem_anahtari: str | None = None


def belge_al(
    baglam: AracBaglami, girdi: BelgeAlGirdisi, islem_kimligi: str
) -> zarf.Zarf:
    """Dosyayı arşivler, belgeyi ARSIVLENDI tanımlar; aynı içerik mevcut belgeyi
    verir."""
    anahtar = _anahtar_zorunlu(girdi.islem_anahtari)
    sonuc = belgeler.belge_al(
        baglam.veritabani,
        yol=girdi.yol,
        gelen_dizini=baglam.ayarlar.gelen_dizini,
        belge_dizini=baglam.ayarlar.belge_dizini,
        islem_anahtari=anahtar,
        aktor=AKTOR,
    )
    belge = sonuc.belge
    return zarf.Zarf(
        durum=zarf.YanitDurumu.TAMAMLANDI,
        islem_kimligi=islem_kimligi,
        belge_id=belge.id,
        hedef_surumu=belge.surum,
        yazilan=0 if sonuc.zaten_vardi else 1,
        zaten_mevcut=1 if sonuc.zaten_vardi else 0,
        belge_kaydi=_belge_kaydi(belge.durum),
        icerik={"belge": _belge_ozeti(belge), "dosya": _dosya_ozeti(sonuc.dosya)},
        sonraki_adim=_belge_sonraki_adimi(belge.durum, sonuc.zaten_vardi),
    )


def belge_getir(
    baglam: AracBaglami, girdi: BelgeGetirGirdisi, islem_kimligi: str
) -> zarf.Zarf:
    """Belge, arşiv dosyası bilgisi ve okuma sürümleri."""
    with baglam.veritabani.okuma_islemi() as oturum:
        ayrinti = belgeler.belge_getir(oturum, girdi.belge_id)
    belge = ayrinti.belge
    return zarf.Zarf(
        durum=zarf.YanitDurumu.TAMAMLANDI,
        islem_kimligi=islem_kimligi,
        belge_id=belge.id,
        okuma_id=belge.etkin_okuma_id,
        hedef_surumu=belge.surum,
        belge_kaydi=_belge_kaydi(belge.durum),
        icerik={
            "belge": _belge_ozeti(belge),
            "dosya": _dosya_ozeti(ayrinti.dosya),
            "okumalar": [_okuma_ozeti(o) for o in ayrinti.okumalar],
        },
        sonraki_adim=_belge_sonraki_adimi(belge.durum, True),
    )


def okuma_baslat(
    baglam: AracBaglami, girdi: OkumaBaslatGirdisi, islem_kimligi: str
) -> zarf.Zarf:
    """ARSIVLENDI belgede okumayı açar; belge OKUNUYOR."""
    anahtar = _anahtar_zorunlu(girdi.islem_anahtari)
    with baglam.veritabani.yazma_islemi() as oturum:
        okuma = belgeler.okuma_baslat(
            oturum,
            belge_id=girdi.belge_id,
            sema_surumu=girdi.talimat_surumu,
            belge_dizini=baglam.ayarlar.belge_dizini,
            islem_anahtari=anahtar,
            aktor=AKTOR,
            icerik=girdi.icerik,
            tamlik=_tamlik(girdi.tamlik),
        )
        belge = belgeler.belge_getir(oturum, okuma.belge_id).belge
    return zarf.Zarf(
        durum=zarf.YanitDurumu.TAMAMLANDI,
        islem_kimligi=islem_kimligi,
        belge_id=belge.id,
        okuma_id=okuma.id,
        hedef_surumu=belge.surum,
        belge_kaydi=zarf.BelgeKaydiDurumu.TANIMLANMADI,
        icerik={"okuma": _okuma_ozeti(okuma), "belge": _belge_ozeti(belge)},
        sonraki_adim=SONRAKI_SATIR_GONDER,
    )


def hareket_yaz(
    baglam: AracBaglami, girdi: HareketYazGirdisi, islem_kimligi: str
) -> zarf.Zarf:
    """Paketteki her satırı ve hareketini tek işlemde yazar; ya hepsi ya hiçbiri.

    Her satırın işlem anahtarı ``<paket anahtarı>#<sıra>``dır: aynı paket
    yeniden gelirse her satır saklı sonucunu döndürür (yazılmaz), içerik
    değiştiyse ``ANAHTAR_ICERIK_CAKISMASI``. Bir satırdaki hata paketin
    tamamını düşürür ve ``konum`` satırın paketteki sırasını söyler.
    """
    anahtar = _anahtar_zorunlu(girdi.islem_anahtari)
    sonuclar: list[kayitlar.HareketSonucu] = []
    with baglam.veritabani.yazma_islemi() as oturum:
        for sira, h in enumerate(girdi.hareketler):
            try:
                sonuclar.append(
                    kayitlar.hareket_yaz(
                        oturum,
                        okuma_id=girdi.okuma_id,
                        satir=belgeler.SatirGirdisi(
                            h.satir.satir_anahtari, h.satir.konum, h.satir.ham
                        ),
                        hareket=fk.HesapHareketi(
                            nesne_id=h.hareket.nesne_id,
                            yon=h.hareket.yon,
                            tutar_kurus=h.hareket.tutar_kurus,
                            islem_tarihi=h.hareket.islem_tarihi,
                            valor_tarihi=h.hareket.valor_tarihi,
                            aciklama=h.hareket.aciklama,
                            para_birimi=h.hareket.para_birimi,
                        ),
                        islem_anahtari=f"{anahtar}#{sira}",
                        aktor=AKTOR,
                    )
                )
            except sz.DefterikiHatasi as hata:
                raise type(hata)(hata.mesaj, alan=hata.alan, konum=sira) from hata
        belge = belgeler.belge_getir(
            oturum, belgeler.okuma_getir(oturum, girdi.okuma_id).belge_id
        ).belge
    yazilan = sum(1 for s in sonuclar if not s.zaten_vardi)
    return zarf.Zarf(
        durum=zarf.YanitDurumu.TAMAMLANDI,
        islem_kimligi=islem_kimligi,
        belge_id=belge.id,
        okuma_id=girdi.okuma_id,
        hedef_surumu=belge.surum,
        yazilan=yazilan,
        zaten_mevcut=len(sonuclar) - yazilan,
        belge_kaydi=_belge_kaydi(belge.durum),
        icerik={
            "satirlar": [
                {
                    "satir_anahtari": s.satir.satir_anahtari,
                    "okuma_satir_id": s.satir.id,
                    "kayit_id": s.kayit.kayit.id,
                    "zaten_vardi": s.zaten_vardi,
                }
                for s in sonuclar
            ]
        },
        sonraki_adim=SONRAKI_SATIR_GONDER,
    )


def okuma_tamamla(
    baglam: AracBaglami, girdi: OkumaTamamlaGirdisi, islem_kimligi: str
) -> zarf.Zarf:
    """Cowork'un "bitti" bildirimi; koşullar sağlanırsa uygulama belge kaydını
    tanımlar."""
    anahtar = _anahtar_zorunlu(girdi.islem_anahtari)
    with baglam.veritabani.yazma_islemi() as oturum:
        sonuc = belgeler.okuma_tamamla(
            oturum,
            okuma_id=girdi.okuma_id,
            islem_anahtari=anahtar,
            aktor=AKTOR,
            tamlik=_tamlik(girdi.tamlik),
        )
    return _kayitli_zarf(sonuc.belge, sonuc.okuma, islem_kimligi)


def belge_kaydet(
    baglam: AracBaglami, girdi: BelgeKaydetGirdisi, islem_kimligi: str
) -> zarf.Zarf:
    """HAZIR kalmış belgeyi koşulları yeniden denetleyerek KAYITLI yapar."""
    anahtar = _anahtar_zorunlu(girdi.islem_anahtari)
    with baglam.veritabani.yazma_islemi() as oturum:
        belge = belgeler.belge_kaydet(
            oturum,
            belge_id=girdi.belge_id,
            gorulen_surum=girdi.gorulen_surum,
            islem_anahtari=anahtar,
        )
        okuma = (
            belgeler.okuma_getir(oturum, belge.etkin_okuma_id)
            if belge.etkin_okuma_id is not None
            else None
        )
    return _kayitli_zarf(belge, okuma, islem_kimligi)


# --- durum ve sorgu araçları ----------------------------------------------------------


class IslemDurumuGirdisi(BaseModel):
    """Ya onay talebi kimliği ya da (araç adı + işlem anahtarı); ikisi birden değil."""

    model_config = ConfigDict(frozen=True)

    talep_id: int | None = Field(default=None, strict=True, gt=0)
    arac_adi: str | None = Field(
        default=None,
        description="Sorulan anahtarın kullanıldığı araç (hareket_yaz ...).",
    )
    islem_anahtari: str | None = None


class BekleyenIslerGirdisi(BaseModel):
    model_config = ConfigDict(frozen=True)

    sayfa_siniri: int = Field(default=sz.VARSAYILAN_SAYFA_BOYUTU, strict=True)
    sayfa_baslangici: int = Field(default=0, strict=True)


class SorguGirdisi(BaseModel):
    """İzinli raporlar: bakiye, hareketler. Serbest SQL yok."""

    model_config = ConfigDict(frozen=True)

    rapor: Literal["bakiye", "hareketler"]
    nesne_id: int = Field(strict=True, gt=0)
    eksen: sz.Eksen = sz.Eksen.VARLIK
    para_birimi: sz.ParaBirimi = sz.ParaBirimi.TRY
    tarih: str | None = Field(default=None, description="bakiye: bu tarih dahil sınır.")
    baslangic: str | None = Field(
        default=None, description="hareketler: ilk gün dahil."
    )
    bitis: str | None = Field(default=None, description="hareketler: son gün dahil.")
    sayfa_siniri: int = Field(default=sz.VARSAYILAN_SAYFA_BOYUTU, strict=True)
    sayfa_baslangici: int = Field(default=0, strict=True)


def islem_durumu(
    baglam: AracBaglami, girdi: IslemDurumuGirdisi, islem_kimligi: str
) -> zarf.Zarf:
    """Kalıcı durum: talep (karar verildi mi) ya da anahtar (iş uygulandı mı)."""
    talep_soruldu = girdi.talep_id is not None
    anahtar_soruldu = girdi.islem_anahtari is not None or girdi.arac_adi is not None
    if talep_soruldu == anahtar_soruldu:
        raise sz.GirdiGecersiz(
            "ya talep_id ya da arac_adi + islem_anahtari ver; ikisi birden değil",
            alan="talep_id",
        )
    if talep_soruldu:
        assert girdi.talep_id is not None
        return _talep_durumu(baglam, girdi.talep_id, islem_kimligi)
    if girdi.arac_adi is None or girdi.islem_anahtari is None:
        raise sz.GirdiGecersiz(
            "anahtar sorgusu için arac_adi ve islem_anahtari birlikte gerekli",
            alan="islem_anahtari",
        )
    with baglam.veritabani.okuma_islemi() as oturum:
        kayitlar_ = islem_anahtarlari.anahtar_kayitlarini_getir(
            oturum, arac_adi=girdi.arac_adi, anahtar=girdi.islem_anahtari
        )
    return zarf.Zarf(
        durum=zarf.YanitDurumu.TAMAMLANDI,
        islem_kimligi=islem_kimligi,
        icerik={
            "kayitlar": [
                {
                    "anahtar": k.anahtar,
                    "sonuc": k.sonuc,
                    "olusturma_zamani": k.olusturma_zamani.isoformat(),
                }
                for k in kayitlar_
            ]
        },
        sonraki_adim=(
            "İş daha önce uygulanmış; saklı sonucu kullan, isteği yeniden gönderme."
            if kayitlar_
            else "Bu anahtar hiç kullanılmamış; isteği aynı anahtarla gönder."
        ),
    )


def _talep_durumu(baglam: AracBaglami, talep_id: int, islem_kimligi: str) -> zarf.Zarf:
    with baglam.veritabani.okuma_islemi() as oturum:
        talep = onaylar.talep_getir(oturum, talep_id)
        hedef = (
            nesneler.nesne_getir(oturum, talep.hedef_id)
            if talep.tur is sz.OnayTuru.NESNE_ACILISI
            else None
        )
    durum = {
        sz.OnayDurumu.BEKLIYOR: zarf.YanitDurumu.BEKLIYOR,
        sz.OnayDurumu.ONAYLANDI: zarf.YanitDurumu.TAMAMLANDI,
        sz.OnayDurumu.REDDEDILDI: zarf.YanitDurumu.REDDEDILDI,
    }[talep.durum]
    return zarf.Zarf(
        durum=durum,
        islem_kimligi=islem_kimligi,
        talep_id=talep.id,
        nesne_id=hedef.nesne.id if hedef else None,
        hedef_surumu=hedef.nesne.surum if hedef else talep.hedef_surumu,
        bekleyen=1 if talep.durum is sz.OnayDurumu.BEKLIYOR else 0,
        icerik={
            "talep": _talep_ozeti(talep),
            "hedef": _nesne_ozeti(hedef.nesne, hedef.ozellikler) if hedef else None,
        },
        sonraki_adim=(
            _nesne_sonraki_adimi(hedef.nesne.durum)
            if hedef
            else "Talep sonucunu kullan."
        ),
    )


def bekleyen_isler(
    baglam: AracBaglami, girdi: BekleyenIslerGirdisi, islem_kimligi: str
) -> zarf.Zarf:
    """Kullanıcı kararı bekleyen talepler, hedefleriyle; sayfalı."""
    sayfalama = sz.Sayfalama(girdi.sayfa_siniri, girdi.sayfa_baslangici)
    with baglam.veritabani.okuma_islemi() as oturum:
        talepler = onaylar.bekleyenleri_listele(oturum, sayfalama=sayfalama)
        hedefler = nesneler.ozellikleri_getir(
            oturum,
            [t.hedef_id for t in talepler if t.tur is sz.OnayTuru.NESNE_ACILISI],
        )
        nesneler_ = {
            t.hedef_id: nesneler.nesne_getir(oturum, t.hedef_id).nesne
            for t in talepler
            if t.tur is sz.OnayTuru.NESNE_ACILISI
        }
    return zarf.Zarf(
        durum=zarf.YanitDurumu.TAMAMLANDI,
        islem_kimligi=islem_kimligi,
        bekleyen=len(talepler),
        icerik={
            "talepler": [
                {
                    **_talep_ozeti(t),
                    "hedef": (
                        _nesne_ozeti(
                            nesneler_[t.hedef_id], hedefler.get(t.hedef_id, ())
                        )
                        if t.hedef_id in nesneler_
                        else None
                    ),
                }
                for t in talepler
            ],
            "sayfa": {
                "sinir": sayfalama.sinir,
                "baslangic": sayfalama.baslangic,
                "donen": len(talepler),
            },
        },
        sonraki_adim=(
            "Bunlar kullanıcı kararı bekliyor; yeniden önerme, onay üretme."
            if talepler
            else "Bekleyen iş yok."
        ),
    )


def sorgu(baglam: AracBaglami, girdi: SorguGirdisi, islem_kimligi: str) -> zarf.Zarf:
    """``bakiye``: etkin bakiye (yalnız KAYITLI belge); ``hareketler``: kayıtlı
    bayrağıyla."""
    sayfalama = sz.Sayfalama(girdi.sayfa_siniri, girdi.sayfa_baslangici)
    tarih = fk.tarih_dogrula(girdi.tarih, alan="tarih") if girdi.tarih else None
    baslangic = (
        fk.tarih_dogrula(girdi.baslangic, alan="baslangic") if girdi.baslangic else None
    )
    bitis = fk.tarih_dogrula(girdi.bitis, alan="bitis") if girdi.bitis else None
    with baglam.veritabani.okuma_islemi() as oturum:
        nesne = nesneler.nesne_getir(oturum, girdi.nesne_id).nesne
        if girdi.rapor == "bakiye":
            b = hs.etkin_bakiye(
                oturum,
                nesne_id=nesne.id,
                eksen=girdi.eksen,
                para_birimi=girdi.para_birimi,
                tarih=tarih,
            )
            icerik: dict[str, Any] = {
                "bakiye": {
                    "nesne_id": b.nesne_id,
                    "eksen": b.eksen.value,
                    "para_birimi": b.para_birimi.value,
                    "tarih": b.tarih.isoformat() if b.tarih else None,
                    "arttir_kurus": b.arttir_kurus,
                    "azalt_kurus": b.azalt_kurus,
                    "bakiye_kurus": b.bakiye_kurus,
                    "bekleyen_kayit_sayisi": b.bekleyen_kayit_sayisi,
                }
            }
            bekleyen = b.bekleyen_kayit_sayisi
        else:
            hareketler = hs.hareketleri_listele(
                oturum,
                nesne_id=nesne.id,
                eksen=girdi.eksen,
                baslangic=baslangic,
                bitis=bitis,
                sayfalama=sayfalama,
            )
            icerik = {
                "hareketler": [
                    {
                        "kayit_id": h.kayit_id,
                        "etki_id": h.etki_id,
                        "islem_tarihi": h.islem_tarihi.isoformat(),
                        "valor_tarihi": (
                            h.valor_tarihi.isoformat() if h.valor_tarihi else None
                        ),
                        "aciklama": h.aciklama,
                        "yon": h.yon.value,
                        "tutar_kurus": h.tutar_kurus,
                        "para_birimi": h.para_birimi.value,
                        "kayitli": h.kayitli,
                    }
                    for h in hareketler
                ],
                "sayfa": {
                    "sinir": sayfalama.sinir,
                    "baslangic": sayfalama.baslangic,
                    "donen": len(hareketler),
                },
            }
            bekleyen = sum(1 for h in hareketler if not h.kayitli)
    return zarf.Zarf(
        durum=zarf.YanitDurumu.TAMAMLANDI,
        islem_kimligi=islem_kimligi,
        nesne_id=nesne.id,
        bekleyen=bekleyen,
        icerik=icerik,
        sonraki_adim=(
            "Bakiye yalnız KAYITLI belgelere dayanır; bekleyen kayıtlar toplamda yok."
            if bekleyen
            else "Rapor tamam."
        ),
    )


def _talep_ozeti(talep: onaylar.OnayTalebi) -> dict[str, Any]:
    return {
        "id": talep.id,
        "tur": talep.tur.value,
        "durum": talep.durum.value,
        "hedef_id": talep.hedef_id,
        "hedef_surumu": talep.hedef_surumu,
        "karar": talep.karar,
        "olusturma_zamani": talep.olusturma_zamani.isoformat(),
        "cozum_zamani": talep.cozum_zamani.isoformat() if talep.cozum_zamani else None,
    }


# --- yardımcılar ----------------------------------------------------------------------


def _kayitli_zarf(
    belge: belgeler.Belge, okuma: belgeler.Okuma | None, islem_kimligi: str
) -> zarf.Zarf:
    return zarf.Zarf(
        durum=zarf.YanitDurumu.TAMAMLANDI,
        islem_kimligi=islem_kimligi,
        belge_id=belge.id,
        okuma_id=okuma.id if okuma else None,
        hedef_surumu=belge.surum,
        belge_kaydi=_belge_kaydi(belge.durum),
        icerik={
            "belge": _belge_ozeti(belge),
            "okuma": _okuma_ozeti(okuma) if okuma else None,
        },
        sonraki_adim=SONRAKI_KAYITLI,
    )


def _belge_kaydi(durum: sz.BelgeDurumu) -> zarf.BelgeKaydiDurumu:
    return (
        zarf.BelgeKaydiDurumu.KAYITLI
        if durum is sz.BelgeDurumu.KAYITLI
        else zarf.BelgeKaydiDurumu.TANIMLANMADI
    )


def _belge_sonraki_adimi(durum: sz.BelgeDurumu, zaten_vardi: bool) -> str:
    if durum is sz.BelgeDurumu.ARSIVLENDI:
        onek = "Belge zaten arşivdeydi. " if zaten_vardi else ""
        return onek + SONRAKI_OKUMA_AC
    if durum is sz.BelgeDurumu.OKUNUYOR:
        return "Belgenin okuması açık; " + SONRAKI_SATIR_GONDER
    if durum is sz.BelgeDurumu.HAZIR:
        return "Belge hazır; belge_kaydet ile kaydı tanımla."
    if durum is sz.BelgeDurumu.KAYITLI:
        return SONRAKI_KAYITLI
    return f"Belge durumu {durum.value}; bu belgeye yazma."


def _belge_ozeti(belge: belgeler.Belge) -> dict[str, Any]:
    return {
        "id": belge.id,
        "durum": belge.durum.value,
        "surum": belge.surum,
        "etkin_okuma_id": belge.etkin_okuma_id,
    }


def _dosya_ozeti(dosya: belgeler.ArsivDosyasi) -> dict[str, Any]:
    return {
        "sha256": dosya.sha256,
        "boyut": dosya.boyut,
        "mime": dosya.mime,
        "uzanti": dosya.uzanti,
        "kaynak_adi": dosya.kaynak_adi,
    }


def _okuma_ozeti(okuma: belgeler.Okuma) -> dict[str, Any]:
    return {
        "id": okuma.id,
        "surum_no": okuma.surum_no,
        "durum": okuma.durum.value,
        "talimat_surumu": okuma.sema_surumu,
        "tamlik": (
            {
                "beklenen_satir_sayisi": okuma.tamlik.beklenen_satir_sayisi,
                "acilis_bakiyesi_kurus": okuma.tamlik.acilis_bakiyesi_kurus,
                "kapanis_bakiyesi_kurus": okuma.tamlik.kapanis_bakiyesi_kurus,
                "toplam_giris_kurus": okuma.tamlik.toplam_giris_kurus,
                "toplam_cikis_kurus": okuma.tamlik.toplam_cikis_kurus,
            }
            if okuma.tamlik
            else None
        ),
    }


def _tamlik(girdi: TamlikGirdi | None) -> belgeler.Tamlik | None:
    if girdi is None:
        return None
    return belgeler.Tamlik(
        beklenen_satir_sayisi=girdi.beklenen_satir_sayisi,
        acilis_bakiyesi_kurus=girdi.acilis_bakiyesi_kurus,
        kapanis_bakiyesi_kurus=girdi.kapanis_bakiyesi_kurus,
        toplam_giris_kurus=girdi.toplam_giris_kurus,
        toplam_cikis_kurus=girdi.toplam_cikis_kurus,
    )


def _nesne_durumundan(durum: sz.NesneDurumu) -> zarf.YanitDurumu:
    if durum is sz.NesneDurumu.ONAY_BEKLIYOR:
        return zarf.YanitDurumu.BEKLIYOR
    if durum is sz.NesneDurumu.AKTIF:
        return zarf.YanitDurumu.TAMAMLANDI
    return zarf.YanitDurumu.REDDEDILDI


def _nesne_sonraki_adimi(durum: sz.NesneDurumu) -> str:
    if durum is sz.NesneDurumu.ONAY_BEKLIYOR:
        return SONRAKI_ONAY_BEKLE
    if durum is sz.NesneDurumu.AKTIF:
        return "Nesne aktif; kimliğini kullan."
    return (
        f"Nesne önerisi {durum.value.lower()}; bu kimliği kullanma, gerekirse yeni "
        "öneri."
    )


def _nesne_ozeti(
    nesne: nesneler.Nesne, ozellikler: tuple[nesneler.Ozellik, ...]
) -> dict[str, Any]:
    return {
        "id": nesne.id,
        "seviye": nesne.seviye,
        "durum": nesne.durum.value,
        "surum": nesne.surum,
        "ozellikler": [
            {
                "id": o.id,
                "alan_adi": o.alan_adi,
                "deger": o.deger,
                "deger_turu": o.deger_turu.value,
                "sart": o.sart,
            }
            for o in ozellikler
        ],
    }


def _anahtar_zorunlu(anahtar: str | None) -> str:
    if anahtar is None or not anahtar.strip():
        raise sz.GirdiGecersiz(
            "değişiklik yapan araçta işlem anahtarı zorunlu", alan="islem_anahtari"
        )
    return anahtar.strip()

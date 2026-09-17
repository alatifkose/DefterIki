"""MCP araçlarının gövdeleri (Teslim 5.1'den itibaren).

Araç kodu kural içermez (K01): girdi modelini alır, işlem sahibi olarak
yazma ya da okuma işlemini açar, Aşama 4 işlevini çağırır, sonucu zarfa
koyar. Her işlev ``Veritabani`` ve doğrulanmış girdiyle çağrılır; MCP
sunucusundan bağımsız test edilir. Kayıt/protokol işi ``mcp_kapisi``dedir.

Girdi modelleri Pydantic'tir; SDK bunlardan JSON Schema üretir ve çağrıdan
önce doğrular. Şema reddi ``mcp_kapisi`` tarafından güvenli zarfa çevrilir.
İşlem anahtarı her değişiklik yapan araçta zorunludur (K08); eksikse araç
kendi ``GIRDI_GECERSIZ`` hatasını verir.

Araçlar: 5.1 ``nesne_tanimla`` (FORM / GONDER); 5.2/1 ``nesne_bul``,
``nesne_getir``, ``oturum_baglami`` (C16: son nesneler, mevcut alan adları,
bekleyen işler; Cowork bildiği kimliği doğrudan kullanır). Okuma araçları
salt okunur işlemde çalışır ve anahtar istemez.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from defteriki import nesneler, onaylar, zarf
from defteriki import sozlesmeler as sz
from defteriki.veritabani import Veritabani

AKTOR = sz.DenetimAktoru.COWORK
"""MCP kapısından gelen her yazma Cowork'a aittir."""

SONRAKI_ONAY_BEKLE = (
    "Kullanıcı kararı bekleniyor. Bekleme; talep kimliğiyle islem_durumu aracını "
    "sonra çağır. Kendi kendine onay üretme."
)
SONRAKI_YENI_ANAHTAR = (
    "Değişiklik yapılmadı; farklı içerik için yeni işlem anahtarı üret."
)


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


def nesne_tanimla(
    veritabani: Veritabani, girdi: NesneTanimlaGirdisi, islem_kimligi: str
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
    with veritabani.yazma_islemi() as oturum:
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


# --- okuma araçları ------------------------------------------------------------


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


def nesne_bul(
    veritabani: Veritabani, girdi: NesneBulGirdisi, islem_kimligi: str
) -> zarf.Zarf:
    """Filtreye uyan nesneler ve özellikleri; eşleşme türüyle yapılır (C05)."""
    sayfalama = sz.Sayfalama(girdi.sayfa_siniri, girdi.sayfa_baslangici)
    with veritabani.okuma_islemi() as oturum:
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
    veritabani: Veritabani, girdi: NesneGetirGirdisi, islem_kimligi: str
) -> zarf.Zarf:
    """Nesne, özellikleri (şart işaretli), üstleri ve altları."""
    with veritabani.okuma_islemi() as oturum:
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
    veritabani: Veritabani, girdi: OturumBaglamiGirdisi, islem_kimligi: str
) -> zarf.Zarf:
    """C16: kalıcı kimlikler DEFTERIKI'dedir; Cowork oturum başında bunları alır."""
    with veritabani.okuma_islemi() as oturum:
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

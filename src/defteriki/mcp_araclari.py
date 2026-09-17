"""MCP araçlarının gövdeleri (Teslim 5.1'den itibaren).

Araç kodu kural içermez (K01): girdi modelini alır, işlem sahibi olarak
yazma ya da okuma işlemini açar, Aşama 4 işlevini çağırır, sonucu zarfa
koyar. Her işlev ``Veritabani`` ve doğrulanmış girdiyle çağrılır; MCP
sunucusundan bağımsız test edilir. Kayıt/protokol işi ``mcp_kapisi``dedir.

Girdi modelleri Pydantic'tir; SDK bunlardan JSON Schema üretir ve çağrıdan
önce doğrular. Şema reddi ``mcp_kapisi`` tarafından güvenli zarfa çevrilir.
İşlem anahtarı her değişiklik yapan araçta zorunludur (K08); eksikse araç
kendi ``GIRDI_GECERSIZ`` hatasını verir.

5.1'de tek değişiklik aracı: ``nesne_tanimla`` (FORM / GONDER). Diğerleri
5.2'nin üç parçasında gelir.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from defteriki import nesneler, zarf
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


def _anahtar_zorunlu(anahtar: str | None) -> str:
    if anahtar is None or not anahtar.strip():
        raise sz.GirdiGecersiz(
            "değişiklik yapan araçta işlem anahtarı zorunlu", alan="islem_anahtari"
        )
    return anahtar.strip()

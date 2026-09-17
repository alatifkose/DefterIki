"""MCP yanıt zarfı ve güvenli hata çevirisi (Teslim 5.1; Tam Plan 11.2).

Her MCP aracı aynı zarfı döndürür. Zarf Cowork'a **ne oldu** sorusunun
cevabını verir, hiçbir yorum yapmaz:

* ``durum``: ``TAMAMLANDI`` (iş bitti), ``BEKLIYOR`` (kullanıcı kararı
  bekleniyor; talep kimliğiyle sonra sorulur), ``REDDEDILDI`` (girdi ya da
  kural hatası; değişiklik yok), ``YENIDEN_DENE`` (geçici: veritabanı
  meşgul; aynı anahtarla tekrar denenebilir).
* ``islem_kimligi``: bu çağrının korelasyon kimliği; günlükteki satırla
  eşleşir, hata bildirirken kullanılır.
* Kimlikler ve sayılar: belge, okuma, nesne, onay talebi, hedef sürümü;
  yazılan / zaten mevcut / bekleyen satır sayıları; belge kaydı durumu.
  **"Başarılı" tek başına "kayıtlı" demek değildir**: yazılan satır
  ``belge_kaydi`` ``KAYITLI`` olana kadar hesaba girmez (K19).
* ``sonraki_adim``: Cowork'un ne yapması gerektiği (kısa Türkçe).
* ``icerik``: aracın kendi yapılandırılmış sonucu (form, nesne özeti ...).
* ``hata``: kod, güvenli açıklama, alan, satır konumu, tekrar denenebilirlik.
  Yığın izi, dosya içeriği, yol ya da ham yük yoktur.
* ``talimat_surumu``: Cowork talimatının (``docs/cowork.md``) sürümü.

Hata çevirisi: ürün hataları (``DefterikiHatasi``) kodlarıyla ``REDDEDILDI``;
``VeritabaniMesgul`` ``YENIDEN_DENE``; beklenmeyen hata ``BEKLENMEYEN_HATA``
koduyla, türü günlüğe, mesajı asla zarfa. SDK'nın girdi doğrulama hatası
alan yollarını ve hata türlerini taşır, değerleri taşımaz (Pydantic
``ValidationError.errors`` girdisiz okunur).
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from defteriki import sozlesmeler as sz

TALIMAT_SURUMU = "0.2"
"""``docs/cowork.md`` sürümü; Cowork zarftan okur, talimatı buna göre seçer."""

KOD_BEKLENMEYEN = "BEKLENMEYEN_HATA"
MESAJ_BEKLENMEYEN = (
    "uygulamada beklenmeyen bir hata oluştu; işlem kimliğiyle günlüğe bakılmalı"
)
MESAJ_SEMA_REDDI = "girdi araç şemasına uymuyor"


class YanitDurumu(StrEnum):
    TAMAMLANDI = "TAMAMLANDI"
    BEKLIYOR = "BEKLIYOR"
    REDDEDILDI = "REDDEDILDI"
    YENIDEN_DENE = "YENIDEN_DENE"


class BelgeKaydiDurumu(StrEnum):
    TANIMLANMADI = "TANIMLANMADI"
    KAYITLI = "KAYITLI"


class Hata(BaseModel):
    model_config = ConfigDict(frozen=True)

    kod: str
    mesaj: str
    alan: str | None = None
    konum: int | None = None
    tekrar_denenebilir: bool = False


class Zarf(BaseModel):
    """Bütün araçların ortak yanıtı."""

    model_config = ConfigDict(frozen=True)

    durum: YanitDurumu
    islem_kimligi: str = Field(
        description="Çağrının korelasyon kimliği; günlükle eşleşir."
    )
    talimat_surumu: str = TALIMAT_SURUMU
    belge_id: int | None = None
    okuma_id: int | None = None
    nesne_id: int | None = None
    talep_id: int | None = Field(
        default=None, description="Kullanıcı kararı bekleyen onay talebinin kimliği."
    )
    hedef_surumu: int | None = None
    yazilan: int = 0
    zaten_mevcut: int = 0
    bekleyen: int = 0
    belge_kaydi: BelgeKaydiDurumu | None = Field(
        default=None,
        description=(
            "KAYITLI değilse yazılanlar hesaba girmez; yazmak kayıt etmek değildir."
        ),
    )
    sonraki_adim: str | None = None
    icerik: dict[str, Any] | None = None
    hata: Hata | None = None


SONRAKI_ADIMLAR: dict[str, str] = {
    "BELGE_YOK": "Kaynağı tamamla (belge_al); finansal yazmayı tekrar deneme.",
    "ARSIV_EKSIK": (
        "Kaynağı tamamla (dosyayı yeniden al); finansal yazmayı tekrar deneme."
    ),
    "HEDEF_BULUNAMADI": (
        "Yanlış kimlik bağlantısını düzelt; kimlikleri nesne_bul ya da belge_getir "
        "ile doğrula."
    ),
    "SEVIYE_CAKISMASI": "Üst bağlantılarını incele; seviyeyi zorlama.",
    "NESNE_ENGELLI": "Vakayı ve izinli işlemi izle; yeni kimlikle engeli aşma.",
    "YENI_NESNE_ENGELI": "Şüphe çözülene kadar yeni nesne önerme; engeli aşma.",
    "TUTAR_GECERSIZ": "Kaynağa dön; yuvarlama ya da kur uydurma.",
    "PARA_BIRIMI_DESTEKLENMIYOR": "Kaynağa dön; kur uydurma.",
    "ANAHTAR_ICERIK_CAKISMASI": (
        "Eski işi sorgula; farklı içerik için yeni işlem anahtarı üret."
    ),
    "HEDEF_SURUMU_DEGISTI": "Güncel hedefi al; eski onayı yeni içeriğe uygulama.",
    "BELGE_HAZIR_DEGIL": (
        "Eksik satır ya da kararı çöz; belgeyi kayıtlı gibi raporlama."
    ),
    "MUTABAKAT_FARKI": (
        "Eksik ya da fazla satırı çöz, sonra yeniden tamamla; kayıtlı gibi raporlama."
    ),
    "KAYNAK_CAKISMASI": (
        "Aynı olay iddiasındaki tutar, yön, para birimi farkını incele."
    ),
    "VERITABANI_MESGUL": (
        "Aynı işlem anahtarıyla kısa süre sonra tekrar dene; yeni anahtar üretme."
    ),
    "GIRDI_GECERSIZ": "Girdiyi düzelt; değişiklik yapılmadı.",
}
"""Tam Plan 11.2: hata koduna göre Cowork'un beklenen tepkisi."""


def islem_kimligi_uret() -> str:
    return uuid.uuid4().hex[:12]


def hata_zarfi(hata: sz.DefterikiHatasi, islem_kimligi: str) -> Zarf:
    """Ürün hatasını zarfa çevirir; meşgul ise YENIDEN_DENE, değilse REDDEDILDI."""
    durum = (
        YanitDurumu.YENIDEN_DENE if hata.tekrar_denenebilir else YanitDurumu.REDDEDILDI
    )
    return Zarf(
        durum=durum,
        islem_kimligi=islem_kimligi,
        hata=Hata(
            kod=hata.kod,
            mesaj=hata.mesaj,
            alan=hata.alan,
            konum=hata.konum,
            tekrar_denenebilir=hata.tekrar_denenebilir,
        ),
        sonraki_adim=SONRAKI_ADIMLAR.get(
            hata.kod, "Hatayı gider; değişiklik yapılmadı."
        ),
    )


def beklenmeyen_hata_zarfi(islem_kimligi: str) -> Zarf:
    """Beklenmeyen hata: mesaj zarfa girmez, yalnız kod ve korelasyon kimliği."""
    return Zarf(
        durum=YanitDurumu.REDDEDILDI,
        islem_kimligi=islem_kimligi,
        hata=Hata(kod=KOD_BEKLENMEYEN, mesaj=MESAJ_BEKLENMEYEN),
        sonraki_adim="Aynı isteği tekrarlama; işlem kimliğini bildir.",
    )


def sema_reddi_zarfi(alanlar: list[tuple[str, str]], islem_kimligi: str) -> Zarf:
    """SDK girdi doğrulaması düştü: yalnız alan yolları ve hata türleri (değer yok)."""
    ayrinti = ", ".join(f"{alan} ({tur})" for alan, tur in alanlar) or "alan bilinmiyor"
    return Zarf(
        durum=YanitDurumu.REDDEDILDI,
        islem_kimligi=islem_kimligi,
        hata=Hata(
            kod=sz.GirdiGecersiz.kod,
            mesaj=f"{MESAJ_SEMA_REDDI}: {ayrinti}",
            alan=alanlar[0][0] if alanlar else None,
        ),
        sonraki_adim="Alan adlarını ve türleri araç şemasıyla karşılaştır.",
    )


def dogrulama_hatasini_ozetle(hata: ValidationError) -> list[tuple[str, str]]:
    """Pydantic hatasından (alan yolu, hata türü) çiftleri; değerler alınmaz."""
    return [
        (".".join(str(parca) for parca in h["loc"]), str(h["type"]))
        for h in hata.errors(include_url=False, include_input=False)
    ]

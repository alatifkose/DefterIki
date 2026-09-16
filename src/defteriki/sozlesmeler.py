"""DEFTERIKI ortak sözleşmeleri.

Bütün modüllerin paylaştığı temel türler, durum sabitleri, hata sınıfları ve
sayfalama. Ürün mantığı yoktur: burada hiçbir kural "ne zaman" sorusuna
cevap vermez, yalnız "ne" sorusuna.

* **Kimlik**: pozitif tam sayı. **KurusTutar**: kuruş cinsinden, sıfır ya da
  pozitif tam sayı (K05). İkisi de katıdır: ``float`` ve ``bool`` açık hatayla
  reddedilir, sessiz dönüşüm yoktur.
* **Yön** ARTTIR / AZALT, **eksen** VARLIK / BORC / GIDER, **para birimi**
  yalnız TRY (C09; alan şemada vardır, TRY dışı değer açık hata).
* **Durumlar** (C08): belge, satır ve nesne durum adları tek yerde. Tam
  Plan'ın açık bıraktığı listeler (defter, kayıt, okuma, kaynak rolü ve durumu,
  onay türü ve durumu, değer türü, işlem anahtarı kapsamı, denetim aktörü)
  Teslim 4.2'de Abdüllatif'in onayıyla sabitlendi.
* **Hatalar**: Tam Plan bölüm 11.2'deki kodlarla bir sınıf ailesi. Her
  hatanın kodu, güvenli açıklaması, tekrar denenebilirliği ve isteğe bağlı
  alan/konum bilgisi vardır. Yığın izi, dosya içeriği ya da ham yük mesaja
  girmez. ``GIRDI_GECERSIZ`` 11.2'de yok; kimlik ve sayfalama gibi genel
  girdi hataları için teknik kod olarak eklendi (bkz. README).
* **Sayfalama**: sunucu tarafı; varsayılan 100, en çok 500 satır.

Modül import edildiğinde diske dokunulmaz.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Annotated, ClassVar

from pydantic import Field, TypeAdapter, ValidationError

# --- temel türler ------------------------------------------------------------

Kimlik = Annotated[int, Field(strict=True, gt=0)]
"""Veritabanı kimliği: pozitif tam sayı; ``float`` ve ``bool`` reddedilir."""

KurusTutar = Annotated[int, Field(strict=True, ge=0)]
"""Kuruş cinsinden tutar: 0 ya da pozitif tam sayı (K05); yön ayrı alandır."""

_KIMLIK_DOGRULAYICI: TypeAdapter[int] = TypeAdapter(Kimlik)
_KURUS_DOGRULAYICI: TypeAdapter[int] = TypeAdapter(KurusTutar)


class Yon(StrEnum):
    ARTTIR = "ARTTIR"
    AZALT = "AZALT"


class Eksen(StrEnum):
    VARLIK = "VARLIK"
    BORC = "BORC"
    GIDER = "GIDER"


class ParaBirimi(StrEnum):
    """Desteklenen para birimleri; bu sürümde yalnız TRY (C09)."""

    TRY = "TRY"


# --- durumlar (C08) ----------------------------------------------------------


class BelgeDurumu(StrEnum):
    ARSIVLENDI = "ARSIVLENDI"
    """Dosya var, finansal etkisi yok; okuma başlatılabilir."""
    OKUNUYOR = "OKUNUYOR"
    KARAR_BEKLIYOR = "KARAR_BEKLIYOR"
    HAZIR = "HAZIR"
    KAYITLI = "KAYITLI"
    """Belge kaydı tanımlandı; etkileri hesaplara girer."""
    GECERSIZ = "GECERSIZ"
    YERINE_GECILDI = "YERINE_GECILDI"


class SatirDurumu(StrEnum):
    YAZILDI = "YAZILDI"
    """Kayıt, etki ve kaynak bağı saklandı; belge kayıtlı değilse hesaba girmez."""
    KARAR_BEKLIYOR = "KARAR_BEKLIYOR"
    MEVCUDA_BAGLANDI = "MEVCUDA_BAGLANDI"
    KAPSAM_DISI = "KAPSAM_DISI"


class NesneDurumu(StrEnum):
    AKTIF = "AKTIF"
    ENGELLI = "ENGELLI"
    PASIF = "PASIF"
    SILINDI = "SILINDI"


# Aşağıdaki listeler Tam Plan'da açık bırakılmıştı; 2026-09-16'da Claude önerdi,
# Abdüllatif "öneriler tamam" dedi (Teslim 4.2).


class DefterDurumu(StrEnum):
    ONAY_BEKLIYOR = "ONAY_BEKLIYOR"
    """Tanımlandı, onay uygulanmadı; yazma kabul etmez (C12)."""
    AKTIF = "AKTIF"
    PASIF = "PASIF"


class KayitDurumu(StrEnum):
    AKTIF = "AKTIF"
    GECERSIZ = "GECERSIZ"
    """Geçersizleştirme Aşama 8'de gelir; ad şemada hazır."""


class OkumaDurumu(StrEnum):
    ACIK = "ACIK"
    TAMAMLANDI = "TAMAMLANDI"
    IPTAL = "IPTAL"


class KaynakRolu(StrEnum):
    """Bir kaydı destekleyen satırın rolü (C11: iki kaynaklıda yalnız destek kalkar)."""

    ASIL = "ASIL"
    DESTEK = "DESTEK"


class KaynakDurumu(StrEnum):
    AKTIF = "AKTIF"
    KALDIRILDI = "KALDIRILDI"


class OnayTuru(StrEnum):
    """Onay talebi türleri; diğerleri (ayrı tutma, pasifleştirme) kendi aşamalarında."""

    DEFTER_TANIMLAMA = "DEFTER_TANIMLAMA"
    NESNE_ACILISI = "NESNE_ACILISI"


class OnayDurumu(StrEnum):
    BEKLIYOR = "BEKLIYOR"
    ONAYLANDI = "ONAYLANDI"
    REDDEDILDI = "REDDEDILDI"


class DegerTuru(StrEnum):
    """Nesne özelliği değer türü; eşleşme türüyle karşılaştırılır (Tam Plan 5.1)."""

    METIN = "METIN"
    TAMSAYI = "TAMSAYI"
    ONDALIK = "ONDALIK"
    TARIH = "TARIH"
    MANTIKSAL = "MANTIKSAL"
    JSON = "JSON"


class IslemAnahtariKapsami(StrEnum):
    SISTEM = "SISTEM"
    """Defter henüz yokken (ilk defter) kullanılan kapsam; kapsam_id 0."""
    DEFTER = "DEFTER"


class DenetimAktoru(StrEnum):
    COWORK = "COWORK"
    KULLANICI = "KULLANICI"
    UYGULAMA = "UYGULAMA"


# --- hatalar (Tam Plan 11.2) -------------------------------------------------


class DefterikiHatasi(Exception):
    """Ürün hatalarının kökü.

    ``kod`` Cowork'a ve ekrana giden kısa sabit; ``mesaj`` güvenli açıklama
    (kişisel veri, belge içeriği, yol ya da ham yük taşımaz); ``alan`` ve
    ``konum`` hatanın hangi girdide olduğunu söyler; ``tekrar_denenebilir``
    aynı isteğin değişiklik yapılmadan yeniden denenebileceğini bildirir.
    """

    kod: ClassVar[str] = "DEFTERIKI_HATASI"
    tekrar_denenebilir: ClassVar[bool] = False

    def __init__(
        self, mesaj: str, *, alan: str | None = None, konum: int | None = None
    ) -> None:
        super().__init__(mesaj)
        self.mesaj = mesaj
        self.alan = alan
        self.konum = konum

    def __str__(self) -> str:
        yer = ""
        if self.alan is not None:
            yer = (
                f" [{self.alan}]"
                if self.konum is None
                else f" [{self.alan}#{self.konum}]"
            )
        return f"{self.kod}{yer}: {self.mesaj}"


class GirdiGecersiz(DefterikiHatasi):
    """Genel girdi hatası (kimlik, sayfalama); 11.2 dışı teknik kod."""

    kod = "GIRDI_GECERSIZ"


class BelgeYok(DefterikiHatasi):
    kod = "BELGE_YOK"


class ArsivEksik(DefterikiHatasi):
    kod = "ARSIV_EKSIK"


class DefterUyusmazligi(DefterikiHatasi):
    kod = "DEFTER_UYUSMAZLIGI"


class SeviyeCakismasi(DefterikiHatasi):
    kod = "SEVIYE_CAKISMASI"


class NesneEngelli(DefterikiHatasi):
    kod = "NESNE_ENGELLI"


class YeniNesneEngeli(DefterikiHatasi):
    kod = "YENI_NESNE_ENGELI"


class TutarGecersiz(DefterikiHatasi):
    kod = "TUTAR_GECERSIZ"


class ParaBirimiDesteklenmiyor(DefterikiHatasi):
    kod = "PARA_BIRIMI_DESTEKLENMIYOR"


class AnahtarIcerikCakismasi(DefterikiHatasi):
    kod = "ANAHTAR_ICERIK_CAKISMASI"


class HedefSurumuDegisti(DefterikiHatasi):
    kod = "HEDEF_SURUMU_DEGISTI"


class BelgeHazirDegil(DefterikiHatasi):
    kod = "BELGE_HAZIR_DEGIL"


class MutabakatFarki(DefterikiHatasi):
    kod = "MUTABAKAT_FARKI"


class KaynakCakismasi(DefterikiHatasi):
    kod = "KAYNAK_CAKISMASI"


class VeritabaniMesgul(DefterikiHatasi):
    """Yazma kilidi alınamadı; aynı istek değişiklik yapılmadan tekrar denenebilir."""

    kod = "VERITABANI_MESGUL"
    tekrar_denenebilir = True


HATA_KODLARI: tuple[type[DefterikiHatasi], ...] = (
    GirdiGecersiz,
    BelgeYok,
    ArsivEksik,
    DefterUyusmazligi,
    SeviyeCakismasi,
    NesneEngelli,
    YeniNesneEngeli,
    TutarGecersiz,
    ParaBirimiDesteklenmiyor,
    AnahtarIcerikCakismasi,
    HedefSurumuDegisti,
    BelgeHazirDegil,
    MutabakatFarki,
    KaynakCakismasi,
    VeritabaniMesgul,
)
"""Bütün hata sınıfları; kodların benzersizliği testle doğrulanır."""


# --- doğrulayıcılar ----------------------------------------------------------


def kimlik_dogrula(deger: object, alan: str = "kimlik") -> int:
    """Pozitif tam sayı kimlik döndürür; aksi hâlde ``GirdiGecersiz``."""
    try:
        return _KIMLIK_DOGRULAYICI.validate_python(deger)
    except ValidationError:
        raise GirdiGecersiz("kimlik pozitif bir tam sayı olmalı", alan=alan) from None


def kurus_tutar_dogrula(deger: object, alan: str = "tutar") -> int:
    """Kuruş tutarı döndürür (K05); aksi hâlde ``TutarGecersiz``.

    Katı doğrulama: ``12.0`` ya da ``True`` gibi değerler tam sayıya
    çevrilmez, reddedilir. Yuvarlama yoktur.
    """
    try:
        return _KURUS_DOGRULAYICI.validate_python(deger)
    except ValidationError:
        raise TutarGecersiz(
            "tutar kuruş cinsinden sıfır ya da pozitif bir tam sayı olmalı", alan=alan
        ) from None


def para_birimi_dogrula(deger: object, alan: str = "para_birimi") -> ParaBirimi:
    """Desteklenen para birimini döndürür; aksi hâlde ``ParaBirimiDesteklenmiyor``."""
    if isinstance(deger, ParaBirimi):
        return deger
    if isinstance(deger, str):
        try:
            return ParaBirimi(deger)
        except ValueError:
            pass
    desteklenen = ", ".join(birim.value for birim in ParaBirimi)
    raise ParaBirimiDesteklenmiyor(
        f"desteklenen para birimleri: {desteklenen}", alan=alan
    )


# --- sayfalama ---------------------------------------------------------------

VARSAYILAN_SAYFA_BOYUTU = 100
AZAMI_SAYFA_BOYUTU = 500


@dataclass(frozen=True, slots=True)
class Sayfalama:
    """Sunucu tarafı sayfalama: ``sinir`` satır, ``baslangic`` kadar atla."""

    sinir: int = VARSAYILAN_SAYFA_BOYUTU
    baslangic: int = 0

    def __post_init__(self) -> None:
        # Tür ipucu int olsa da çağıran float ya da bool geçirebilir; bool int'in
        # alt türü olduğundan type() ile tam eşleşme aranır.
        if type(self.sinir) is not int:
            raise GirdiGecersiz("sayfa sınırı tam sayı olmalı", alan="sinir")
        if not 1 <= self.sinir <= AZAMI_SAYFA_BOYUTU:
            raise GirdiGecersiz(
                f"sayfa sınırı 1 ile {AZAMI_SAYFA_BOYUTU} arasında olmalı", alan="sinir"
            )
        if type(self.baslangic) is not int or self.baslangic < 0:
            raise GirdiGecersiz(
                "sayfa başlangıcı sıfır ya da pozitif tam sayı olmalı", alan="baslangic"
            )

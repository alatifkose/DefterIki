"""Finansal işlem sözleşmeleri (Tam Plan bölüm 10, C02) — saf kurallar.

Finansal davranış nesne türüyle değil **işlem sözleşmesiyle** belirlenir:
Cowork her satırda işlem türünü gönderir, uygulama o türün zorunlu
alanlarını, tutar denkliklerini ve izinli etkilerini doğrular. Bu modül
veritabanına dokunmaz; girdiyi alır, ya doğrulanmış bir **hareket taslağı**
döndürür ya da açık hata verir. Yazma ``kayitlar.hareket_yaz``ın işidir.

Teslim 4.6 kapsamı tek sözleşmedir: ``HESAP_HAREKETI`` — belirlenen nesnede
``VARLIK`` ekseninde ``ARTTIR`` ya da ``AZALT``. Gelen para gelir, çıkan para
gider sayılmaz; gider anlamı ayrı sözleşmelerle (HARCAMA, MALIYET ...) gelir,
onlar Aşama 8'de yazılır. Tek nesne, tek etki.

Tutar kuralları (K05, C09, S20): kuruş cinsinden pozitif tam sayı; ``float``,
``bool`` ve metin reddedilir, sessiz yuvarlama yoktur; sıfır hareket
değildir; SQLite'ın 64 bit tam sayı sınırını aşan tutar taşma sayılır ve
reddedilir. Para birimi belgeden gelir, listeyle karşılaştırılmaz. İşlem tarihi
zorunlu, valör isteğe bağlı; ikisi de ``date`` ya da ``YYYY-AA-GG`` metni.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from enum import StrEnum

from defteriki import sozlesmeler as sz

AZAMI_TUTAR_KURUS = 2**63 - 1
"""SQLite INTEGER üst sınırı; aşan tutar taşmadır, açık hata (S20)."""

AZAMI_ACIKLAMA_UZUNLUGU = 512


class IslemTuru(StrEnum):
    """İşlem sözleşmeleri; bu teslimde yalnız hesap hareketi."""

    HESAP_HAREKETI = "HESAP_HAREKETI"


@dataclass(frozen=True, slots=True)
class HesapHareketi:
    """Cowork'un gönderdiği hesap hareketi girdisi; doğrulanmamış."""

    nesne_id: object
    yon: object
    tutar_kurus: object
    islem_tarihi: object
    para_birimi: object
    """Belgedeki para birimi; zorunlu, varsayılanı yok (koda gömülü tanım yok)."""
    valor_tarihi: object = None
    aciklama: object = None


@dataclass(frozen=True, slots=True)
class EtkiTaslagi:
    nesne_id: int
    eksen: sz.Eksen
    yon: sz.Yon
    tutar_kurus: int
    para_birimi: str


@dataclass(frozen=True, slots=True)
class HareketTaslagi:
    """Doğrulanmış hareket: kayıt alanları ve izinli etkiler."""

    islem_turu: IslemTuru
    asil_nesne_id: int
    islem_tarihi: date
    valor_tarihi: date | None
    aciklama: str | None
    etkiler: tuple[EtkiTaslagi, ...]


def hesap_hareketi_dogrula(girdi: HesapHareketi) -> HareketTaslagi:
    """HESAP_HAREKETI sözleşmesi: tek nesne, VARLIK ekseni, yön, kuruş tutar.

    Her alan katı doğrulanır; ilk hata açık kodla döner. Veritabanına
    dokunmaz: nesnenin varlığı ve durumu yazma anında denetlenir.
    """
    nesne_id = sz.kimlik_dogrula(girdi.nesne_id, alan="nesne_id")
    yon = _yon_dogrula(girdi.yon)
    tutar = tutar_dogrula(girdi.tutar_kurus)
    para_birimi = sz.para_birimi_dogrula(girdi.para_birimi)
    islem_tarihi = tarih_dogrula(girdi.islem_tarihi, alan="islem_tarihi")
    valor = (
        tarih_dogrula(girdi.valor_tarihi, alan="valor_tarihi")
        if girdi.valor_tarihi is not None
        else None
    )
    aciklama = _aciklama_dogrula(girdi.aciklama)
    return HareketTaslagi(
        islem_turu=IslemTuru.HESAP_HAREKETI,
        asil_nesne_id=nesne_id,
        islem_tarihi=islem_tarihi,
        valor_tarihi=valor,
        aciklama=aciklama,
        etkiler=(EtkiTaslagi(nesne_id, sz.Eksen.VARLIK, yon, tutar, para_birimi),),
    )


def tutar_dogrula(deger: object, alan: str = "tutar_kurus") -> int:
    """Pozitif kuruş tutarı; float/bool/metin, sıfır ve taşma reddedilir."""
    tutar = sz.kurus_tutar_dogrula(deger, alan=alan)
    if tutar == 0:
        raise sz.TutarGecersiz("sıfır tutarlı hareket olmaz", alan=alan)
    if tutar > AZAMI_TUTAR_KURUS:
        raise sz.TutarGecersiz("tutar tam sayı sınırını aşıyor (taşma)", alan=alan)
    return tutar


def tarih_dogrula(deger: object, *, alan: str) -> date:
    """``date`` ya da ``YYYY-AA-GG`` metni; ``datetime`` ve başka biçim reddedilir."""
    if type(deger) is date:
        return deger
    if isinstance(deger, str):
        try:
            return date.fromisoformat(deger.strip())
        except ValueError:
            pass
    raise sz.GirdiGecersiz("tarih YYYY-AA-GG biçiminde olmalı", alan=alan)


def _yon_dogrula(deger: object) -> sz.Yon:
    if isinstance(deger, sz.Yon):
        return deger
    if isinstance(deger, str):
        try:
            return sz.Yon(deger)
        except ValueError:
            pass
    secenekler = ", ".join(y.value for y in sz.Yon)
    raise sz.GirdiGecersiz(f"yön {secenekler} olmalı", alan="yon")


def _aciklama_dogrula(deger: object) -> str | None:
    if deger is None:
        return None
    if not isinstance(deger, str):
        raise sz.GirdiGecersiz("açıklama metin olmalı", alan="aciklama")
    temiz = deger.strip()
    if not temiz:
        return None
    if len(temiz) > AZAMI_ACIKLAMA_UZUNLUGU:
        raise sz.GirdiGecersiz(
            f"açıklama en çok {AZAMI_ACIKLAMA_UZUNLUGU} karakter", alan="aciklama"
        )
    return temiz

"""Belge arşivi: gelen dizinindeki dosyayı değişmez baytlar olarak saklar.

Cowork belgeyi izinli **gelen dizinine** bırakır ve yolunu verir (C10; Aşama
3.3'te doğrulanan yöntem). Bu modül dosyayı denetler, akışla kopyalar,
SHA-256 ve boyutunu kendisi hesaplar, içerik adresli kalıcı yola atomik
taşır (Tam Plan 8.1). Veritabanına dokunmaz; ``arsiv_dosya`` ve ``belge``
satırlarını ``belgeler.belge_tanimla`` yazar. Dosya ve veritabanı tek
işlem değildir: önce dosya arşive girer, sonra kısa bir yazma işlemi
kaydı açar; veritabanı düşerse kaynaksız kayıt oluşmaz, sahipsiz dosya
başlangıç uzlaştırmasında raporlanır (Aşama 9).

Yol denetimi (3.3'teki ``dosya_dene`` sırası): mutlak yol → ``..`` yok →
gerçek yol izinli dizinin gerçek yolunun altında → simgesel bağlantı ya da
takma yol değil → sıradan dosya. Red, kategorik gerekçeyle ``GIRDI_GECERSIZ``
verir; mesajda yol yoktur.

Kopya: önce ``<belge dizini>/gecici/<rastgele>.tmp`` adına akışla yazılır,
yazarken özet ve boyut hesaplanır ve 50 MiB sınırı (C18) aşılınca kesilir;
sonra ``fsync`` ve aynı dosya sisteminde ``os.replace`` ile
``<ilk iki hex>/<sha256><uzantı>`` yoluna taşınır. Herhangi bir adım
düşerse geçici dosya silinir; yarım kopya arşivde kalmaz. Aynı içerik daha
önce arşivlenmişse hedef zaten vardır: ikinci dosya üretilmez, kopya atılır.

MIME: ilk baytlardaki imzadan (PDF, PNG, JPEG) belirlenir; imza biliniyorsa
uzantı onunla uyuşmalıdır, bilinmiyorsa uzantıdan tahmin edilir, o da yoksa
``application/octet-stream``. Boş dosya belge olamaz.
"""

from __future__ import annotations

import hashlib
import mimetypes
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from defteriki import sozlesmeler as sz

AZAMI_DOSYA_BOYUTU = 50 * 1024 * 1024
"""C18: dosya en çok 50 MiB; aşılırsa açık hata, veri kesilmez."""

OKUMA_PARCA_BOYUTU = 1024 * 1024
GECICI_DIZIN_ADI = "gecici"
AZAMI_UZANTI_UZUNLUGU = 10
VARSAYILAN_MIME = "application/octet-stream"

GEREKCE_MUTLAK_DEGIL = "yol mutlak değil"
GEREKCE_UST_DIZIN = "yolda üst dizin parçası (..) var"
GEREKCE_BULUNAMADI = "dosya bulunamadı"
GEREKCE_DIZIN_DISI = "izinli gelen dizininin dışında"
GEREKCE_BAGLANTI = "simgesel bağlantı ya da takma yol"
GEREKCE_DOSYA_DEGIL = "sıradan bir dosya değil"
GEREKCE_OKUNAMADI = "dosya okunamadı"
GEREKCE_BOS = "boş dosya belge olamaz"
GEREKCE_COK_BUYUK = f"dosya {AZAMI_DOSYA_BOYUTU // (1024 * 1024)} MiB sınırını aşıyor"
GEREKCE_UZANTI_UYUSMUYOR = "dosya uzantısı içerikle uyuşmuyor"

_IMZALAR: tuple[tuple[bytes, str, frozenset[str]], ...] = (
    (b"%PDF-", "application/pdf", frozenset({".pdf"})),
    (b"\x89PNG\r\n\x1a\n", "image/png", frozenset({".png"})),
    (b"\xff\xd8\xff", "image/jpeg", frozenset({".jpg", ".jpeg"})),
)
_IMZALI_UZANTILAR: frozenset[str] = frozenset(
    uzanti for _, _, uzantilar in _IMZALAR for uzanti in uzantilar
)
_IMZA_UZUNLUGU = max(len(imza) for imza, _, _ in _IMZALAR)


@dataclass(frozen=True, slots=True)
class ArsivlenenDosya:
    """Arşive giren dosyanın kimliği; ``belgeler.belge_tanimla`` bunu kaydeder."""

    sha256: str
    boyut: int
    mime: str
    goreli_yol: str
    """Belge dizinine göre POSIX yol: ``<ilk iki hex>/<sha256><uzantı>``."""
    diskte_zaten_vardi: bool
    """Aynı içerik daha önce arşivlenmişti; yeni dosya yazılmadı."""


# --- gelen dizini denetimi ----------------------------------------------------


def gelen_dosyayi_dogrula(yol_metni: str, gelen_dizini: Path) -> Path:
    """Yolu denetler; izinliyse dosyanın gerçek yolunu döndürür.

    Her red ``GirdiGecersiz`` (alan ``yol``) ve kategorik gerekçedir; mesaja
    yol yazılmaz.
    """
    yol = Path(yol_metni)
    if not yol_metni.strip() or not yol.is_absolute():
        raise _red(GEREKCE_MUTLAK_DEGIL)
    if ".." in yol.parts:
        raise _red(GEREKCE_UST_DIZIN)

    gelen_gercek = gelen_dizini.resolve()
    try:
        hedef = yol.resolve(strict=True)
    except FileNotFoundError:
        raise _red(GEREKCE_BULUNAMADI) from None
    except (OSError, RuntimeError):
        raise _red(GEREKCE_OKUNAMADI) from None

    if not hedef.is_relative_to(gelen_gercek):
        raise _red(GEREKCE_DIZIN_DISI)
    if yol.is_symlink() or _takma_yol_mu(yol, hedef):
        raise _red(GEREKCE_BAGLANTI)
    if not hedef.is_file():
        raise _red(GEREKCE_DOSYA_DEGIL)
    return hedef


def _takma_yol_mu(verilen: Path, gercek: Path) -> bool:
    """Sadeleştirilen yol gerçek yoldan farklıysa arada bağlantı ya da kavşak var."""
    sade = os.path.normcase(os.path.normpath(str(verilen)))
    return sade != os.path.normcase(str(gercek))


def _red(gerekce: str) -> sz.GirdiGecersiz:
    return sz.GirdiGecersiz(gerekce, alan="yol")


# --- arşivleme ----------------------------------------------------------------


def dosyayi_arsivle(
    yol_metni: str, *, gelen_dizini: Path, belge_dizini: Path
) -> ArsivlenenDosya:
    """Gelen dizinindeki dosyayı denetler ve içerik adresli yola arşivler.

    Dönen değer veritabanına henüz yazılmamıştır; çağıran kısa bir yazma
    işleminde ``belgeler.belge_tanimla`` çağırır.
    """
    kaynak = gelen_dosyayi_dogrula(yol_metni, gelen_dizini)
    uzanti = _uzanti(kaynak)
    gecici_dizin = belge_dizini / GECICI_DIZIN_ADI
    gecici_dizin.mkdir(parents=True, exist_ok=True)
    gecici = gecici_dizin / f"{uuid.uuid4().hex}.tmp"

    try:
        ozet, boyut, bas = _akisla_kopyala(kaynak, gecici)
        mime = _mime_belirle(bas, uzanti)
        hedef = belge_dizini / ozet[:2] / f"{ozet}{uzanti}"
        hedef.parent.mkdir(parents=True, exist_ok=True)
        if hedef.exists():
            gecici.unlink()
            zaten_vardi = True
        else:
            os.replace(gecici, hedef)
            zaten_vardi = False
    except BaseException:
        gecici.unlink(missing_ok=True)
        raise

    return ArsivlenenDosya(
        sha256=ozet,
        boyut=boyut,
        mime=mime,
        goreli_yol=hedef.relative_to(belge_dizini).as_posix(),
        diskte_zaten_vardi=zaten_vardi,
    )


def arsiv_yolu(belge_dizini: Path, goreli_yol: str) -> Path:
    return belge_dizini / Path(goreli_yol)


def arsivde_var_mi(belge_dizini: Path, goreli_yol: str, boyut: int) -> bool:
    """Arşiv dosyası yerinde ve kayıtlı boyutta mı (okuma başlatma ön şartı, S10)."""
    yol = arsiv_yolu(belge_dizini, goreli_yol)
    try:
        return yol.is_file() and yol.stat().st_size == boyut
    except OSError:
        return False


def _uzanti(dosya: Path) -> str:
    uzanti = dosya.suffix.lower()
    govde = uzanti[1:]
    if not govde or len(govde) > AZAMI_UZANTI_UZUNLUGU or not govde.isalnum():
        return ""
    return uzanti


def _akisla_kopyala(kaynak: Path, hedef: Path) -> tuple[str, int, bytes]:
    """Akışla kopyalar; (sha256, boyut, ilk baytlar) döndürür. Sınır aşımı hata."""
    ozet = hashlib.sha256()
    boyut = 0
    bas = b""
    try:
        with kaynak.open("rb") as girdi, hedef.open("wb") as cikti:
            while parca := girdi.read(OKUMA_PARCA_BOYUTU):
                if not bas:
                    bas = parca[:_IMZA_UZUNLUGU]
                boyut += len(parca)
                if boyut > AZAMI_DOSYA_BOYUTU:
                    raise _red(GEREKCE_COK_BUYUK)
                ozet.update(parca)
                cikti.write(parca)
            cikti.flush()
            os.fsync(cikti.fileno())
    except OSError:
        raise _red(GEREKCE_OKUNAMADI) from None
    if boyut == 0:
        raise _red(GEREKCE_BOS)
    return ozet.hexdigest(), boyut, bas


def _mime_belirle(bas: bytes, uzanti: str) -> str:
    for imza, mime, uzantilar in _IMZALAR:
        if bas.startswith(imza):
            if uzanti and uzanti not in uzantilar:
                raise _red(GEREKCE_UZANTI_UYUSMUYOR)
            return mime
    if uzanti in _IMZALI_UZANTILAR:
        raise _red(GEREKCE_UZANTI_UYUSMUYOR)
    tahmin, _ = mimetypes.guess_type(f"dosya{uzanti}") if uzanti else (None, None)
    return tahmin or VARSAYILAN_MIME

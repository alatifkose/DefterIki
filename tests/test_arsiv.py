"""Belge arşivi (Teslim 4.5): gelen dizini denetimi, akışla kopya, atomik taşıma.

Sentetik dosyalar; gerçek belge yok. Simgesel bağlantı testleri Windows'ta
bağlantı yetkisi yoksa atlanır (3.3'teki kalıp).
"""

import hashlib
import os
from pathlib import Path

import pytest

from defteriki import arsiv
from defteriki import sozlesmeler as sz

PDF = b"%PDF-1.7\n%sentetik ekstre\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


@pytest.fixture
def gelen(tmp_path: Path) -> Path:
    dizin = tmp_path / "gelen"
    dizin.mkdir()
    return dizin


@pytest.fixture
def belgeler(tmp_path: Path) -> Path:
    dizin = tmp_path / "belgeler"
    dizin.mkdir()
    return dizin


def _yaz(yol: Path, icerik: bytes) -> Path:
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_bytes(icerik)
    return yol


def _baglanti_kur(baglanti: Path, hedef: Path) -> None:
    try:
        baglanti.symlink_to(hedef)
    except (OSError, NotImplementedError) as hata:
        pytest.skip(f"simgesel bağlantı oluşturulamadı: {type(hata).__name__}")


def _arsivle(yol: Path, gelen: Path, belgeler: Path) -> arsiv.ArsivlenenDosya:
    return arsiv.dosyayi_arsivle(str(yol), gelen_dizini=gelen, belge_dizini=belgeler)


def _dosyalar(dizin: Path) -> set[str]:
    return {p.relative_to(dizin).as_posix() for p in dizin.rglob("*") if p.is_file()}


# --- arşivleme ----------------------------------------------------------------


def test_dosya_icerik_adresli_yola_atomik_tasinir(gelen: Path, belgeler: Path) -> None:
    kaynak = _yaz(gelen / "Ekstre.PDF", PDF)
    beklenen = hashlib.sha256(PDF).hexdigest()

    sonuc = _arsivle(kaynak, gelen, belgeler)

    assert sonuc == arsiv.ArsivlenenDosya(
        sha256=beklenen,
        boyut=len(PDF),
        mime="application/pdf",
        uzanti=".pdf",
        kaynak_adi="Ekstre.PDF",
        goreli_yol=f"{beklenen[:2]}/{beklenen}",
        diskte_zaten_vardi=False,
    )
    assert arsiv.arsiv_yolu(belgeler, sonuc.goreli_yol).read_bytes() == PDF
    assert _dosyalar(belgeler) == {sonuc.goreli_yol}  # geçici dosya kalmadı
    assert kaynak.exists()  # gelen dizinindeki dosya silinmez, kopyalanır
    assert arsiv.arsivde_var_mi(belgeler, sonuc.goreli_yol, sonuc.boyut)


METIN = b"tarih;aciklama;tutar\n2026-08-01;sentetik;100\n"


@pytest.mark.parametrize(
    ("icerik", "ilk_ad", "ikinci_ad"),
    [
        (PDF, "a.pdf", "alt/b.pdf"),  # farklı ad, aynı uzantı
        (PDF, "a.pdf", "a.pdf"),  # aynı ad (gelen dizininde üzerine yazıldı)
        (PDF, "a.pdf", "ekstre"),  # uzantısız
        (PDF, "ekstre", "a.pdf"),  # önce uzantısız, sonra uzantılı
        (
            METIN,
            "hareketler.csv",
            "hareketler.xyz",
        ),  # imzasız içerik, bilinmeyen uzantı
        (METIN, "hareketler.csv", "hareketler"),  # imzasız içerik, uzantısız
        (METIN, "hareketler.xyz", "hareketler.txt"),  # bilinmeyen → bilinen uzantı
    ],
)
def test_ayni_icerik_hangi_adla_gelirse_gelsin_tek_fiziksel_dosya(
    gelen: Path, belgeler: Path, icerik: bytes, ilk_ad: str, ikinci_ad: str
) -> None:
    """Fiziksel kimlik yalnız SHA-256: yol uzantı taşımaz, ad ve uzantı metadata'dır."""
    ilk = _arsivle(_yaz(gelen / ilk_ad, icerik), gelen, belgeler)
    ikinci = _arsivle(_yaz(gelen / ikinci_ad, icerik), gelen, belgeler)

    assert ikinci.sha256 == ilk.sha256 and ikinci.goreli_yol == ilk.goreli_yol
    assert ikinci.diskte_zaten_vardi is True
    assert ikinci.kaynak_adi == Path(ikinci_ad).name
    assert ikinci.uzanti == Path(ikinci_ad).suffix.lower()
    assert _dosyalar(belgeler) == {ilk.goreli_yol}
    assert ilk.goreli_yol == f"{ilk.sha256[:2]}/{ilk.sha256}"


def test_imzali_icerik_bilinmeyen_uzantiyla_kapida_reddedilir(
    gelen: Path, belgeler: Path
) -> None:
    """Giriş kapısı denetimi aynen durur: PDF içerik .xyz adıyla arşive giremez."""
    ilk = _arsivle(_yaz(gelen / "a.pdf", PDF), gelen, belgeler)

    with pytest.raises(sz.GirdiGecersiz, match=arsiv.GEREKCE_UZANTI_UYUSMUYOR):
        _arsivle(_yaz(gelen / "a.xyz", PDF), gelen, belgeler)

    assert _dosyalar(belgeler) == {ilk.goreli_yol}


def test_buyuk_dosya_parcali_okunur_ve_ozet_dogru(gelen: Path, belgeler: Path) -> None:
    icerik = PNG + os.urandom(3 * arsiv.OKUMA_PARCA_BOYUTU + 17)
    kaynak = _yaz(gelen / "foto.png", icerik)

    sonuc = _arsivle(kaynak, gelen, belgeler)

    assert sonuc.sha256 == hashlib.sha256(icerik).hexdigest()
    assert sonuc.boyut == len(icerik) and sonuc.mime == "image/png"


def test_sinir_asan_dosya_reddedilir_yarim_kopya_kalmaz(
    gelen: Path, belgeler: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(arsiv, "AZAMI_DOSYA_BOYUTU", 100)
    kaynak = _yaz(gelen / "buyuk.pdf", PDF + b"x" * 200)

    with pytest.raises(sz.GirdiGecersiz, match="MiB"):
        _arsivle(kaynak, gelen, belgeler)

    assert _dosyalar(belgeler) == set()


def test_kopya_ortasinda_hata_gecici_dosyayi_siler(
    gelen: Path, belgeler: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    kaynak = _yaz(gelen / "a.pdf", PDF)

    def patlayan(*_: object) -> str:
        raise RuntimeError("mime patladı")

    monkeypatch.setattr(arsiv, "_mime_belirle", patlayan)
    with pytest.raises(RuntimeError, match="mime patladı"):
        _arsivle(kaynak, gelen, belgeler)

    assert _dosyalar(belgeler) == set()


def test_bos_dosya_belge_olamaz(gelen: Path, belgeler: Path) -> None:
    with pytest.raises(sz.GirdiGecersiz, match=arsiv.GEREKCE_BOS):
        _arsivle(_yaz(gelen / "bos.pdf", b""), gelen, belgeler)
    assert _dosyalar(belgeler) == set()


def test_arsivde_var_mi_boyut_uyusmazsa_eksik(gelen: Path, belgeler: Path) -> None:
    sonuc = _arsivle(_yaz(gelen / "a.pdf", PDF), gelen, belgeler)
    arsiv.arsiv_yolu(belgeler, sonuc.goreli_yol).write_bytes(b"bozuk")

    assert not arsiv.arsivde_var_mi(belgeler, sonuc.goreli_yol, sonuc.boyut)
    assert not arsiv.arsivde_var_mi(belgeler, "yok/yok.pdf", 1)


# --- MIME ---------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ad", "icerik", "mime"),
    [
        ("a.pdf", PDF, "application/pdf"),
        ("a.png", PNG, "image/png"),
        ("a.jpeg", b"\xff\xd8\xff\xe0" + b"\x00" * 8, "image/jpeg"),
        ("uzantisiz", PDF, "application/pdf"),
        ("notlar.txt", b"duz metin", "text/plain"),
        ("veri.bin", b"\x00\x01\x02", "application/octet-stream"),
        ("garip.%%%", b"icerik", "application/octet-stream"),
    ],
)
def test_mime_imzadan_ya_da_uzantidan(
    gelen: Path, belgeler: Path, ad: str, icerik: bytes, mime: str
) -> None:
    sonuc = _arsivle(_yaz(gelen / ad, icerik), gelen, belgeler)
    assert sonuc.mime == mime


@pytest.mark.parametrize(
    ("ad", "icerik"),
    [("sahte.pdf", PNG), ("sahte.png", PDF), ("sahte.jpg", b"duz metin")],
)
def test_uzanti_icerikle_uyusmazsa_reddedilir(
    gelen: Path, belgeler: Path, ad: str, icerik: bytes
) -> None:
    with pytest.raises(sz.GirdiGecersiz, match=arsiv.GEREKCE_UZANTI_UYUSMUYOR):
        _arsivle(_yaz(gelen / ad, icerik), gelen, belgeler)
    assert _dosyalar(belgeler) == set()


# --- gelen dizini denetimi (3.3 kuralları) ----------------------------------------


@pytest.mark.parametrize(
    ("yol", "gerekce"),
    [
        ("", arsiv.GEREKCE_MUTLAK_DEGIL),
        ("goreli/ekstre.pdf", arsiv.GEREKCE_MUTLAK_DEGIL),
    ],
)
def test_mutlak_olmayan_yol(gelen: Path, yol: str, gerekce: str) -> None:
    with pytest.raises(sz.GirdiGecersiz, match=gerekce):
        arsiv.gelen_dosyayi_dogrula(yol, gelen)


def test_ust_dizin_parcasi(gelen: Path) -> None:
    _yaz(gelen / "a.pdf", PDF)
    with pytest.raises(sz.GirdiGecersiz, match=r"\.\."):
        arsiv.gelen_dosyayi_dogrula(str(gelen / "alt" / ".." / "a.pdf"), gelen)


def test_olmayan_dosya(gelen: Path) -> None:
    with pytest.raises(sz.GirdiGecersiz, match=arsiv.GEREKCE_BULUNAMADI):
        arsiv.gelen_dosyayi_dogrula(str(gelen / "yok.pdf"), gelen)


def test_dizin_disi_dosya(tmp_path: Path, gelen: Path) -> None:
    disari = _yaz(tmp_path / "disari" / "sir.pdf", PDF)
    with pytest.raises(sz.GirdiGecersiz, match=arsiv.GEREKCE_DIZIN_DISI) as hata:
        arsiv.gelen_dosyayi_dogrula(str(disari), gelen)
    assert str(tmp_path) not in str(hata.value)  # mesajda yol yok


def test_dizin_dosya_degil(gelen: Path) -> None:
    (gelen / "klasor").mkdir()
    with pytest.raises(sz.GirdiGecersiz, match=arsiv.GEREKCE_DOSYA_DEGIL):
        arsiv.gelen_dosyayi_dogrula(str(gelen / "klasor"), gelen)


def test_disariya_giden_baglanti_reddedilir(tmp_path: Path, gelen: Path) -> None:
    hedef = _yaz(tmp_path / "disari" / "sir.pdf", PDF)
    baglanti = gelen / "masum.pdf"
    _baglanti_kur(baglanti, hedef)

    with pytest.raises(sz.GirdiGecersiz, match=arsiv.GEREKCE_DIZIN_DISI):
        arsiv.gelen_dosyayi_dogrula(str(baglanti), gelen)


def test_icerideki_baglanti_da_reddedilir(gelen: Path) -> None:
    hedef = _yaz(gelen / "gercek.pdf", PDF)
    baglanti = gelen / "kisayol.pdf"
    _baglanti_kur(baglanti, hedef)

    with pytest.raises(sz.GirdiGecersiz, match=arsiv.GEREKCE_BAGLANTI):
        arsiv.gelen_dosyayi_dogrula(str(baglanti), gelen)


def test_gecerli_dosya_gercek_yolunu_dondurur(gelen: Path) -> None:
    kaynak = _yaz(gelen / "alt" / "a.pdf", PDF)
    assert arsiv.gelen_dosyayi_dogrula(str(kaynak), gelen) == kaynak.resolve()

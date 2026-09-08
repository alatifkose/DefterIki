"""K-008: bağımlılık tek yöne akar; kural burada zorlanır.

`src/defteriki` altındaki her modülün importları taranır. Bir modül yalnız kendi
katından **daha aşağıdaki** katları içe alabilir. Aynı katta yalnız kendi birimi
içinde kalır (ürünler birbirini, `mcp` ile `arayuz` birbirini tanımaz). Fonksiyon ve
sınıf gövdesinde `import` yasaktır: Defter'de 247 fonksiyon-içi import döngülerden
kaçmak için yazılmıştı; burada döngü olmayınca gerek de kalmaz.

Yeni bir paket açıldığında `KATLAR`a eklenmelidir; eklenmezse test kırılır.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

KAYNAK = Path(__file__).resolve().parent.parent / "src" / "defteriki"
PAKET = "defteriki"

# Yalnız alt paketleri taşıyan kapsayıcılar; kendileri bir kata ait değildir ve
# hiçbir şeyi içe almazlar (aksi `test_kapsayicilar_bos` ile yakalanır).
KAPSAYICILAR = {"defteriki", "defteriki.cekirdek"}

# Paket öneki -> kat numarası. Küçük numara alttadır. Uzun önek önce eşleşir.
KATLAR: dict[str, int] = {
    "defteriki.ayarlar": 0,
    "defteriki.cekirdek.temel": 1,
    "defteriki.cekirdek.urunler": 2,
    "defteriki.cekirdek.yorum": 3,
    "defteriki.mcp": 4,
    "defteriki.arayuz": 4,
}

# Aynı katta "birim" sınırı: bu öneklerin hemen altındaki ilk alt paket ayrı birimdir.
# Örn. defteriki.cekirdek.urunler.hesaplar ile ...urunler.kartlar birbirini göremez.
BIRIM_KOKLERI = ("defteriki.cekirdek.urunler", "defteriki.cekirdek.yorum")


def _moduller() -> list[tuple[str, Path]]:
    sonuc: list[tuple[str, Path]] = []
    for yol in sorted(KAYNAK.rglob("*.py")):
        parcalar = yol.relative_to(KAYNAK.parent).with_suffix("").parts
        if parcalar[-1] == "__init__":
            parcalar = parcalar[:-1]
        sonuc.append((".".join(parcalar), yol))
    return sonuc


def _kat(modul: str) -> int | None:
    for onek in sorted(KATLAR, key=len, reverse=True):
        if modul == onek or modul.startswith(onek + "."):
            return KATLAR[onek]
    return None


def _birim(modul: str) -> str:
    """Aynı kat içinde kimin kiminle konuşabileceğini belirleyen öbek adı."""
    for kok in BIRIM_KOKLERI:
        if modul.startswith(kok + "."):
            return ".".join(modul.split(".")[: len(kok.split(".")) + 1])
    for onek in sorted(KATLAR, key=len, reverse=True):
        if modul == onek or modul.startswith(onek + "."):
            return onek
    return modul


def _ic_importlar(agac: ast.Module, modul: str) -> list[tuple[int, str]]:
    """(satır, hedef modül) çiftleri; yalnız `defteriki` içi hedefler."""
    sonuc: list[tuple[int, str]] = []
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.Import):
            for ad in dugum.names:
                if ad.name == PAKET or ad.name.startswith(PAKET + "."):
                    sonuc.append((dugum.lineno, ad.name))
        elif isinstance(dugum, ast.ImportFrom):
            if dugum.level:
                taban = modul.rsplit(".", dugum.level)[0]
                hedef = f"{taban}.{dugum.module}" if dugum.module else taban
            else:
                hedef = dugum.module or ""
            if hedef == PAKET or hedef.startswith(PAKET + "."):
                # "from defteriki.cekirdek.temel import veritabani": alt modül de hedeftir.
                for ad in dugum.names:
                    sonuc.append((dugum.lineno, f"{hedef}.{ad.name}"))
    return sonuc


def _govde_ici_importlar(agac: ast.Module) -> list[int]:
    satirlar: set[int] = set()
    for dugum in ast.walk(agac):
        if isinstance(dugum, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            for ic in ast.walk(dugum):
                if isinstance(ic, ast.Import | ast.ImportFrom):
                    satirlar.add(ic.lineno)
    return sorted(satirlar)


MODULLER = _moduller()


def test_her_modulun_kati_belli() -> None:
    katsiz = [m for m, _ in MODULLER if m not in KAPSAYICILAR and _kat(m) is None]
    assert katsiz == [], f"KATLAR'a ekle: {katsiz}"


@pytest.mark.parametrize("modul", sorted(KAPSAYICILAR))
def test_kapsayicilar_bos(modul: str) -> None:
    """Kapsayıcı paket kat kuralının dışında; bu yüzden içinde kod da olmamalı."""
    yol = dict(MODULLER).get(modul)
    if yol is None:
        return
    agac = ast.parse(yol.read_text(encoding="utf-8"))
    assert _ic_importlar(agac, modul) == [], f"{modul} kapsayıcıdır, import taşıyamaz"


@pytest.mark.parametrize(("modul", "yol"), MODULLER, ids=[m for m, _ in MODULLER])
def test_bagimlilik_tek_yone_akar(modul: str, yol: Path) -> None:
    if modul in KAPSAYICILAR:
        return
    agac = ast.parse(yol.read_text(encoding="utf-8"))
    kendi_kat = _kat(modul)
    assert kendi_kat is not None
    ihlaller: list[str] = []
    for satir, hedef in _ic_importlar(agac, modul):
        hedef_kat = _kat(hedef)
        if hedef_kat is None:
            # "from defteriki import ayarlar" gibi: hedef bir ad olabilir, üst paketi dene.
            hedef_kat = _kat(hedef.rsplit(".", 1)[0])
        if hedef_kat is None:
            ihlaller.append(f"{yol.name}:{satir} katsız hedef {hedef}")
        elif hedef_kat > kendi_kat:
            ihlaller.append(f"{yol.name}:{satir} yukarı bakıyor: {hedef}")
        elif hedef_kat == kendi_kat and _birim(hedef) != _birim(modul):
            ihlaller.append(f"{yol.name}:{satir} aynı katta yan birime uzanıyor: {hedef}")
    assert ihlaller == []


@pytest.mark.parametrize(("modul", "yol"), MODULLER, ids=[m for m, _ in MODULLER])
def test_govde_icinde_import_yok(modul: str, yol: Path) -> None:
    agac = ast.parse(yol.read_text(encoding="utf-8"))
    assert _govde_ici_importlar(agac) == [], f"{modul}: fonksiyon/sınıf içinde import"


def test_kural_ihlali_yakalanir() -> None:
    """Testin kendisini sına: ihlaller gerçekten ihlal sayılıyor mu."""
    agac = ast.parse("from defteriki.cekirdek.yorum import raporlar\n")
    hedefler = _ic_importlar(agac, "defteriki.cekirdek.temel.veritabani")
    assert hedefler == [(1, "defteriki.cekirdek.yorum.raporlar")]
    assert _kat("defteriki.cekirdek.yorum.raporlar") == 3 > 1

    agac = ast.parse("from defteriki.cekirdek.urunler.kartlar import servis\n")
    (_, hedef), *_ = _ic_importlar(agac, "defteriki.cekirdek.urunler.hesaplar.servis")
    assert _birim(hedef) != _birim("defteriki.cekirdek.urunler.hesaplar.servis")

    agac = ast.parse("def f():\n    import defteriki.ayarlar\n")
    assert _govde_ici_importlar(agac) == [2]

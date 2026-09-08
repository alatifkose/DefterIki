"""Test fikstürlerinin gerçek kullanıcı klasörüne dokunmadığını sınar (B-008).

`conftest.veri_dizini` autouse olduğundan buradaki testler fikstür istemeden de geçici
dizinde koşmalıdır. Yalnız veritabanı yönlendirilip arşiv unutulursa ilk belge testi
gerçek `%LOCALAPPDATA%\\DefterIki\\belgeler` içine yazardı.
"""

from __future__ import annotations

from pathlib import Path

from defteriki import ayarlar


def test_veritabani_gecici_dizindedir(veri_dizini: Path, tmp_path: Path) -> None:
    yol = ayarlar.veritabani_yolu()
    assert yol.is_relative_to(tmp_path)
    assert yol.parent == veri_dizini.resolve()


def test_belge_arsivi_gecici_dizindedir(veri_dizini: Path, tmp_path: Path) -> None:
    yol = ayarlar.belge_arsivi_yolu()
    assert yol.is_relative_to(tmp_path)
    assert yol.parent == veri_dizini.resolve()


def test_fikstur_istemeyen_test_de_gecici_dizindedir(tmp_path: Path) -> None:
    """Autouse olmasaydı bu test varsayılan (gerçek) yolu görürdü."""
    assert ayarlar.veritabani_yolu().is_relative_to(tmp_path)
    assert ayarlar.belge_arsivi_yolu().is_relative_to(tmp_path)


def test_arsiv_hazirlama_gecici_dizinde_acar(tmp_path: Path) -> None:
    dizin = ayarlar.belge_arsivini_hazirla()
    assert dizin.is_dir()
    assert dizin.is_relative_to(tmp_path)


def test_gocler_gecici_veritabanina_yazar(veritabani_yolu: Path, tmp_path: Path) -> None:
    assert veritabani_yolu.is_file()
    assert veritabani_yolu.is_relative_to(tmp_path)

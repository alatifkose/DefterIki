"""Veritabanı ve belge arşivi yollarının tek kaynaktan gelmesini sınar (K-004, K-011)."""

from pathlib import Path

import pytest

from defteriki import ayarlar


def _ortami_temizle(monkeypatch: pytest.MonkeyPatch) -> None:
    for degisken in (
        ayarlar.VERITABANI_DEGISKENI,
        ayarlar.BELGE_ARSIVI_DEGISKENI,
        "LOCALAPPDATA",
        "XDG_DATA_HOME",
    ):
        monkeypatch.delenv(degisken, raising=False)


def test_ozel_degisken_yolu_ezer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ortami_temizle(monkeypatch)
    hedef = tmp_path / "baska" / "defter.sqlite3"
    monkeypatch.setenv(ayarlar.VERITABANI_DEGISKENI, str(hedef))

    assert ayarlar.veritabani_yolu() == hedef.resolve()


def test_degisken_yoksa_localappdata_altina_duser(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _ortami_temizle(monkeypatch)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    yol = ayarlar.veritabani_yolu()

    assert yol.parent == (tmp_path / ayarlar.UYGULAMA_ADI).resolve()
    assert yol.name == ayarlar.VERITABANI_DOSYA_ADI


def test_localappdata_yoksa_ev_dizinine_duser(monkeypatch: pytest.MonkeyPatch) -> None:
    """Windows disi ortamda (CI, Linux kabugu) testler yine kosabilmelidir."""
    _ortami_temizle(monkeypatch)

    yol = ayarlar.veritabani_yolu()

    assert yol.is_absolute()
    assert ayarlar.UYGULAMA_ADI in yol.parts


def test_yol_her_zaman_mutlaktir(monkeypatch: pytest.MonkeyPatch) -> None:
    """Goreli yol calisma dizinine gore cozulur; sureclere gore ayrisir."""
    _ortami_temizle(monkeypatch)
    monkeypatch.setenv(ayarlar.VERITABANI_DEGISKENI, "goreli.sqlite3")

    assert ayarlar.veritabani_yolu().is_absolute()


def test_url_posix_ayracli_ve_mutlak(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ortami_temizle(monkeypatch)
    hedef = tmp_path / "bosluklu dizin" / "Masaüstü" / "defter.sqlite3"
    monkeypatch.setenv(ayarlar.VERITABANI_DEGISKENI, str(hedef))

    url = ayarlar.veritabani_url()

    assert url.startswith("sqlite:///")
    assert "\\" not in url
    assert url.endswith("/bosluklu dizin/Masaüstü/defter.sqlite3")


def test_veri_dizinini_hazirla_dizini_olusturur(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _ortami_temizle(monkeypatch)
    hedef = tmp_path / "henuz" / "yok" / "defter.sqlite3"
    monkeypatch.setenv(ayarlar.VERITABANI_DEGISKENI, str(hedef))

    dizin = ayarlar.veri_dizinini_hazirla()

    assert dizin.is_dir()
    assert dizin == hedef.parent.resolve()


def test_ayni_dizin_iki_kez_hazirlanabilir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ortami_temizle(monkeypatch)
    monkeypatch.setenv(ayarlar.VERITABANI_DEGISKENI, str(tmp_path / "a" / "defter.sqlite3"))

    assert ayarlar.veri_dizinini_hazirla() == ayarlar.veri_dizinini_hazirla()


def test_sonuc_onbelleklenmez(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Yol onbelleklenirse ortam degiskeni degisince eski deger dondurulurdu."""
    _ortami_temizle(monkeypatch)
    monkeypatch.setenv(ayarlar.VERITABANI_DEGISKENI, str(tmp_path / "bir.sqlite3"))
    birinci = ayarlar.veritabani_yolu()

    monkeypatch.setenv(ayarlar.VERITABANI_DEGISKENI, str(tmp_path / "iki.sqlite3"))
    ikinci = ayarlar.veritabani_yolu()

    assert birinci != ikinci


def test_bos_degisken_varsayilani_bozmaz(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Bos deger 'tanimsiz' sayilir; yoksa yol dizinin kendisine cozulurdu."""
    _ortami_temizle(monkeypatch)
    monkeypatch.setenv(ayarlar.VERITABANI_DEGISKENI, "")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert ayarlar.veritabani_yolu().name == ayarlar.VERITABANI_DOSYA_ADI


# --- Belge arşivi (K-011) ---


def test_arsiv_degiskeni_yolu_ezer(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _ortami_temizle(monkeypatch)
    hedef = tmp_path / "baska" / "arsiv"
    monkeypatch.setenv(ayarlar.BELGE_ARSIVI_DEGISKENI, str(hedef))

    assert ayarlar.belge_arsivi_yolu() == hedef.resolve()


def test_arsiv_varsayilani_veri_dizininin_altindadir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Veritabani ile arsiv ayni kokte durur; yedek tek klasordur."""
    _ortami_temizle(monkeypatch)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    arsiv = ayarlar.belge_arsivi_yolu()

    assert arsiv.parent == ayarlar.veritabani_yolu().parent
    assert arsiv.name == ayarlar.BELGE_ARSIVI_DIZIN_ADI


def test_arsiv_yolu_her_zaman_mutlaktir(monkeypatch: pytest.MonkeyPatch) -> None:
    _ortami_temizle(monkeypatch)
    monkeypatch.setenv(ayarlar.BELGE_ARSIVI_DEGISKENI, "goreli/arsiv")

    assert ayarlar.belge_arsivi_yolu().is_absolute()


def test_arsiv_bos_degisken_varsayilani_bozmaz(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _ortami_temizle(monkeypatch)
    monkeypatch.setenv(ayarlar.BELGE_ARSIVI_DEGISKENI, "")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))

    assert ayarlar.belge_arsivi_yolu().name == ayarlar.BELGE_ARSIVI_DIZIN_ADI


def test_arsiv_ve_veritabani_birbirinden_bagimsiz_ezilir(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Yalniz veritabani ezilirse arsiv varsayilan yerinde kalir; iki yol birbirine bagli degil."""
    _ortami_temizle(monkeypatch)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv(ayarlar.VERITABANI_DEGISKENI, str(tmp_path / "ayri" / "db.sqlite3"))

    assert ayarlar.belge_arsivi_yolu() == (tmp_path / ayarlar.UYGULAMA_ADI / "belgeler").resolve()


def test_belge_arsivini_hazirla_dizini_olusturur(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _ortami_temizle(monkeypatch)
    hedef = tmp_path / "henuz" / "yok" / "arsiv"
    monkeypatch.setenv(ayarlar.BELGE_ARSIVI_DEGISKENI, str(hedef))

    dizin = ayarlar.belge_arsivini_hazirla()

    assert dizin.is_dir()
    assert dizin == hedef.resolve()
    assert ayarlar.belge_arsivini_hazirla() == dizin

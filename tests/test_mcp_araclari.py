"""MCP zarfı, hata çevirisi ve işlem anahtarı (Teslim 5.1).

Araç gövdeleri sunucudan bağımsız çağrılır; şema reddi ve beklenmeyen hata
için sunucu süreç içinde (``call_tool``) kullanılır. Gerçek stdio testi
``test_mcp_kapisi.py``de.
"""

import contextlib
import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import anyio
import pytest
from sqlalchemy import func, select, text

from defteriki import ayarlar as ay
from defteriki import gunluk, mcp_araclari, mcp_kapisi, nesneler, sema, zarf
from defteriki import sozlesmeler as sz
from defteriki import veritabani as vt

Girdi = mcp_araclari.NesneTanimlaGirdisi
Oz = mcp_araclari.OzellikGirdi


@pytest.fixture
def db(tmp_path: Path) -> Iterator[vt.Veritabani]:
    yol = tmp_path / "vt" / "mcp.sqlite3"
    yol.parent.mkdir()
    veritabani = vt.Veritabani(yol, mesgul_bekleme_ms=200)
    sema.semayi_yukselt(veritabani)
    yield veritabani
    veritabani.kapat()


@pytest.fixture
def ayarlar(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[ay.Ayarlar]:
    for degisken in (
        ay.ORTAM_DEGISKENI,
        ay.VERI_KOKU_DEGISKENI,
        ay.VERITABANI_YOLU_DEGISKENI,
        ay.BELGE_DIZINI_DEGISKENI,
        ay.LOG_DIZINI_DEGISKENI,
        ay.GELEN_DIZINI_DEGISKENI,
    ):
        monkeypatch.delenv(degisken, raising=False)
    monkeypatch.setenv(ay.ORTAM_DEGISKENI, "test")
    monkeypatch.setenv(ay.VERI_KOKU_DEGISKENI, str(tmp_path / "kok"))
    ayar = ay.ayarlari_yukle()
    ay.dizinleri_hazirla(ayar)
    gunluk.gunlugu_kapat()
    gunluk.gunlugu_kur(ayar.log_dizini)
    yield ayar
    gunluk.gunlugu_kapat()


def _log(ayarlar: ay.Ayarlar) -> str:
    return (ayarlar.log_dizini / gunluk.GUNLUK_DOSYA_ADI).read_text(encoding="utf-8")


def _gonder(
    db: vt.Veritabani, anahtar: str | None, *ozellikler: Oz, ustler: list[int] = []
) -> zarf.Zarf:
    girdi = Girdi(
        adim="GONDER",
        islem_anahtari=anahtar,
        ozellikler=list(ozellikler) or [Oz(alan_adi="ad", deger="QNB")],
        ust_idleri=ustler,
    )
    return mcp_kapisi.araci_calistir(
        mcp_kapisi.ARAC_NESNE_TANIMLA, mcp_araclari.nesne_tanimla, db, girdi
    )


def _sayi(db: vt.Veritabani, tablo: sema.Table) -> int:
    with db.okuma_islemi() as oturum:
        return int(oturum.execute(select(func.count()).select_from(tablo)).scalar_one())


# --- zarf: FORM ve GONDER --------------------------------------------------------


def test_form_zarfi_veritabanina_dokunmaz(
    db: vt.Veritabani, ayarlar: ay.Ayarlar
) -> None:
    sonuc = mcp_kapisi.araci_calistir(
        mcp_kapisi.ARAC_NESNE_TANIMLA,
        mcp_araclari.nesne_tanimla,
        db,
        Girdi(adim="FORM"),
    )

    assert sonuc.durum is zarf.YanitDurumu.TAMAMLANDI
    assert sonuc.hata is None and sonuc.nesne_id is None
    assert sonuc.talimat_surumu == zarf.TALIMAT_SURUMU
    assert sonuc.icerik is not None
    assert sonuc.icerik["kurallar"] == list(nesneler.FORM_KURALLARI)
    assert sonuc.icerik["deger_turleri"] == [t.value for t in sz.DegerTuru]
    assert _sayi(db, sema.nesne) == 0 and _sayi(db, sema.islem_anahtari) == 0
    assert f"arac=nesne_tanimla islem={sonuc.islem_kimligi} durum=TAMAMLANDI" in _log(
        ayarlar
    )


def test_gonder_bekliyor_ve_talep_kimligi_doner(
    db: vt.Veritabani, ayarlar: ay.Ayarlar
) -> None:
    sonuc = _gonder(
        db, "n-1", Oz(alan_adi="ad", deger="QNB"), Oz(alan_adi="tür", deger="banka")
    )

    assert sonuc.durum is zarf.YanitDurumu.BEKLIYOR
    assert sonuc.nesne_id == 1 and sonuc.talep_id == 1 and sonuc.hedef_surumu == 1
    assert (sonuc.yazilan, sonuc.zaten_mevcut, sonuc.bekleyen) == (1, 0, 1)
    assert sonuc.belge_kaydi is None and sonuc.hata is None
    assert sonuc.sonraki_adim == mcp_araclari.SONRAKI_ONAY_BEKLE
    assert sonuc.icerik == {
        "nesne": {"id": 1, "seviye": 0, "durum": "ONAY_BEKLIYOR"},
        "onay_talebi": {"id": 1, "durum": "BEKLIYOR"},
    }
    with db.okuma_islemi() as oturum:
        nesne = nesneler.nesne_getir(oturum, 1)
    assert nesne.nesne.durum is sz.NesneDurumu.ONAY_BEKLIYOR
    assert [o.alan_adi for o in nesne.ozellikler] == ["ad", "tür"]


def test_anahtarsiz_gonder_reddedilir(db: vt.Veritabani, ayarlar: ay.Ayarlar) -> None:
    for anahtar in (None, "", "   "):
        sonuc = _gonder(db, anahtar)
        assert sonuc.durum is zarf.YanitDurumu.REDDEDILDI
        assert sonuc.hata is not None
        assert sonuc.hata.kod == "GIRDI_GECERSIZ"
        assert sonuc.hata.alan == "islem_anahtari"
        assert sonuc.hata.tekrar_denenebilir is False
    assert _sayi(db, sema.nesne) == 0
    assert _log(ayarlar).count("durum=REDDEDILDI hata=GIRDI_GECERSIZ") == 3


def test_ayni_anahtar_ayni_sonuc_farkli_icerik_cakisma(
    db: vt.Veritabani, ayarlar: ay.Ayarlar
) -> None:
    ilk = _gonder(db, "n-1")
    tekrar = _gonder(db, "n-1")

    assert tekrar.durum is zarf.YanitDurumu.BEKLIYOR
    assert (tekrar.nesne_id, tekrar.talep_id) == (ilk.nesne_id, ilk.talep_id)
    assert (tekrar.yazilan, tekrar.zaten_mevcut) == (0, 1)
    assert tekrar.islem_kimligi != ilk.islem_kimligi  # korelasyon çağrı başına
    assert _sayi(db, sema.nesne) == 1

    farkli = _gonder(db, "n-1", Oz(alan_adi="ad", deger="Akbank"))
    assert farkli.durum is zarf.YanitDurumu.REDDEDILDI
    assert farkli.hata is not None and farkli.hata.kod == "ANAHTAR_ICERIK_CAKISMASI"
    assert _sayi(db, sema.nesne) == 1


def test_urun_hatasi_kodu_ve_alaniyla_zarfa_girer(
    db: vt.Veritabani, ayarlar: ay.Ayarlar
) -> None:
    sonuc = _gonder(db, "n-1", ustler=[999])

    assert sonuc.durum is zarf.YanitDurumu.REDDEDILDI
    assert sonuc.hata is not None
    assert (sonuc.hata.kod, sonuc.hata.alan) == ("HEDEF_BULUNAMADI", "ust_idleri")
    assert sonuc.sonraki_adim == "Hatayı gider; değişiklik yapılmadı."
    assert _sayi(db, sema.nesne) == 0 and _sayi(db, sema.islem_anahtari) == 0


def test_veritabani_mesgul_yeniden_dene(db: vt.Veritabani, ayarlar: ay.Ayarlar) -> None:
    kilit = vt.Veritabani(db.yol, mesgul_bekleme_ms=200)
    try:
        with contextlib.ExitStack() as yigin:
            tutan = yigin.enter_context(kilit.yazma_islemi())
            tutan.execute(text("SELECT 1"))  # BEGIN IMMEDIATE: yazma kilidi tutulur
            sonuc = _gonder(db, "n-1")
    finally:
        kilit.kapat()

    assert sonuc.durum is zarf.YanitDurumu.YENIDEN_DENE
    assert sonuc.hata is not None
    assert sonuc.hata.kod == "VERITABANI_MESGUL"
    assert sonuc.hata.tekrar_denenebilir is True
    assert "aynı işlem anahtarıyla" in (sonuc.sonraki_adim or "").lower()


def test_beklenmeyen_hata_mesaji_zarfa_girmez_turu_gunluge_gider(
    db: vt.Veritabani, ayarlar: ay.Ayarlar, monkeypatch: pytest.MonkeyPatch
) -> None:
    hassas = "IBAN TR00 0000 0000 0000 0000 0000 00 KISI ALFA"

    def patlat(*_: object, **__: object) -> object:
        raise RuntimeError(hassas)

    monkeypatch.setattr(nesneler, "nesne_tanimla", patlat)
    sonuc = _gonder(db, "n-1")

    assert sonuc.durum is zarf.YanitDurumu.REDDEDILDI
    assert sonuc.hata is not None and sonuc.hata.kod == zarf.KOD_BEKLENMEYEN
    metin = sonuc.model_dump_json()
    assert "IBAN" not in metin and "ALFA" not in metin
    gunlukte = _log(ayarlar)
    assert "builtins.RuntimeError" in gunlukte and "ALFA" not in gunlukte
    assert (
        f"islem={sonuc.islem_kimligi} durum=REDDEDILDI hata=BEKLENMEYEN_HATA"
        in gunlukte
    )


def test_zarf_yol_ve_ortam_degiskeni_icermez(
    db: vt.Veritabani, ayarlar: ay.Ayarlar, tmp_path: Path
) -> None:
    sonuc = _gonder(db, "n-1")
    metin = sonuc.model_dump_json()
    assert str(tmp_path) not in metin and "DEFTERIKI_" not in metin


# --- sunucu: şema reddi ve araç listesi ------------------------------------------


def _cagir(sunucu: Any, ad: str, args: dict[str, Any]) -> dict[str, Any]:
    sonuc = anyio.run(sunucu.call_tool, ad, args)
    assert sonuc.is_error is False
    return sonuc.structured_content


def test_sema_reddi_degerleri_disari_vermez(
    db: vt.Veritabani, ayarlar: ay.Ayarlar
) -> None:
    sunucu = mcp_kapisi.sunucu_kur(ayarlar, "0001", db)
    gizli = "GIZLI-DEGER-123"

    yanit = _cagir(
        sunucu,
        mcp_kapisi.ARAC_NESNE_TANIMLA,
        {"girdi": {"adim": "GONDER", "ust_idleri": [gizli], "ozellikler": "x"}},
    )

    assert yanit["durum"] == "REDDEDILDI"
    assert yanit["hata"]["kod"] == "GIRDI_GECERSIZ"
    mesaj = yanit["hata"]["mesaj"]
    assert "girdi.ust_idleri.0" in mesaj and "girdi.ozellikler" in mesaj
    assert gizli not in json.dumps(yanit) and gizli not in _log(ayarlar)
    assert yanit["hata"]["alan"] == "girdi.ozellikler"
    assert _sayi(db, sema.nesne) == 0


def test_bilinmeyen_arac_sdk_hatasiyla_doner(
    db: vt.Veritabani, ayarlar: ay.Ayarlar
) -> None:
    sunucu = mcp_kapisi.sunucu_kur(ayarlar, "0001", db)
    bos: dict[str, Any] = {}
    with pytest.raises(Exception, match="Unknown tool"):
        anyio.run(sunucu.call_tool, "yok_boyle_arac", bos)


def test_sunucu_araclari_ve_semalari(db: vt.Veritabani, ayarlar: ay.Ayarlar) -> None:
    sunucu = mcp_kapisi.sunucu_kur(ayarlar, "0001", db)
    araclar = {a.name: a for a in anyio.run(sunucu.list_tools)}

    assert set(araclar) == set(mcp_kapisi.YETENEKLER)
    nesne = araclar[mcp_kapisi.ARAC_NESNE_TANIMLA]
    girdi_semasi = nesne.input_schema["$defs"]["NesneTanimlaGirdisi"]
    assert girdi_semasi["required"] == ["adim"]
    assert set(girdi_semasi["properties"]) == {
        "adim",
        "islem_anahtari",
        "ozellikler",
        "ust_idleri",
        "kaynak",
    }
    assert nesne.output_schema is not None
    assert set(nesne.output_schema["required"]) >= {"durum", "islem_kimligi"}
    assert nesne.output_schema["properties"]["durum"]["$ref"].endswith("YanitDurumu")
    durum = mcp_kapisi.sistem_durumu(ayarlar, "0001")
    assert durum.yetenekler == list(mcp_kapisi.YETENEKLER)
    assert durum.talimat_surumu == zarf.TALIMAT_SURUMU


def test_sunucu_uzerinden_gonder_zarf_doner(
    db: vt.Veritabani, ayarlar: ay.Ayarlar
) -> None:
    sunucu = mcp_kapisi.sunucu_kur(ayarlar, "0001", db)
    yanit = _cagir(
        sunucu,
        mcp_kapisi.ARAC_NESNE_TANIMLA,
        {
            "girdi": {
                "adim": "GONDER",
                "islem_anahtari": "n-1",
                "ozellikler": [{"alan_adi": "ad", "deger": "QNB"}],
            }
        },
    )
    assert yanit["durum"] == "BEKLIYOR" and yanit["talep_id"] == 1
    assert yanit["talimat_surumu"] == zarf.TALIMAT_SURUMU

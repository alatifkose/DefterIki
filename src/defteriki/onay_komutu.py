"""Geçici kullanıcı onayı komutu: ``uv run defteriki-onay`` (Aşama 6 ekranına kadar).

Karar (2026-09-17, Abdüllatif): kullanıcı onayı Aşama 6'daki ekran gelene
kadar bu komut satırından verilir. İki kesin sınır:

* **MCP'ye açılmaz.** Bu modül ``mcp_kapisi``de kayıtlı değildir; Cowork
  buraya ulaşamaz, kendi kendine onay üretemez. Aktör her zaman
  ``KULLANICI``dır.
* **Onay mekanizması terminale bağlanmaz.** Karar mantığı, sürüm denetimi
  ve etkiler ``onaylar`` ve ``nesneler``dedir; bu modül yalnız o işlevleri
  çağıran geçici bir arayüzdür. Ekran geldiğinde bu dosya silinir, çağırdığı
  işlevler olduğu gibi kalır.

Alt komutlar: ``bekleyenler`` (BEKLIYOR talepler), ``goster TALEP`` (talep ve
hedef nesnenin özellikleri, şart seçimi için özellik kimlikleriyle),
``onayla TALEP --surum N [--sart ID ...] [--gerekce ...]``, ``reddet TALEP
--surum N [--gerekce ...]``. ``--surum`` kullanıcının ``goster``de gördüğü
hedef sürümüdür; değişmişse karar uygulanmaz (``HEDEF_SURUMU_DEGISTI``).
Çıktı stdout'a düz metindir; bu bir terminal arayüzüdür.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from sqlalchemy.orm import Session

from defteriki import nesneler, onaylar
from defteriki import sozlesmeler as sz
from defteriki.baslangic import (
    CIKIS_BASARILI,
    CIKIS_HATALI,
    BaslangicHatasi,
    ortami_hazirla,
)
from defteriki.veritabani import veritabani_ac

KOMUT_BEKLEYENLER = "bekleyenler"
KOMUT_GOSTER = "goster"
KOMUT_ONAYLA = "onayla"
KOMUT_REDDET = "reddet"


def main(argv: Sequence[str] | None = None) -> int:
    """Komutu çalıştırır; çıkış kodunu döndürür."""
    args = _ayristirici().parse_args(argv)
    try:
        hazirlik = ortami_hazirla()
    except BaslangicHatasi as hata:
        _hata_yaz(str(hata))
        return CIKIS_HATALI

    veritabani = veritabani_ac(hazirlik.ayarlar)
    try:
        if args.komut == KOMUT_BEKLEYENLER:
            with veritabani.okuma_islemi() as oturum:
                _bekleyenleri_yaz(oturum)
        elif args.komut == KOMUT_GOSTER:
            with veritabani.okuma_islemi() as oturum:
                _talebi_goster(oturum, args.talep)
        else:
            karar = onaylar.Karar(
                onaylandi=args.komut == KOMUT_ONAYLA,
                gerekce=args.gerekce,
                secilen_sartlar=tuple(getattr(args, "sart", None) or ()),
            )
            with veritabani.yazma_islemi() as oturum:
                _karari_uygula(oturum, args.talep, args.surum, karar)
    except sz.DefterikiHatasi as hata:
        _hata_yaz(f"Karar uygulanamadı: {hata}")
        return CIKIS_HATALI
    finally:
        veritabani.kapat()
    return CIKIS_BASARILI


def _ayristirici() -> argparse.ArgumentParser:
    ayristirici = argparse.ArgumentParser(
        prog="defteriki-onay",
        description=(
            "Geçici kullanıcı onayı (Aşama 6 ekranına kadar). MCP'ye açık değildir."
        ),
    )
    alt = ayristirici.add_subparsers(dest="komut", required=True)
    alt.add_parser(KOMUT_BEKLEYENLER, help="karar bekleyen talepleri listele")
    goster = alt.add_parser(KOMUT_GOSTER, help="talebi ve hedef nesneyi göster")
    goster.add_argument("talep", type=int)
    for ad, yardim in (
        (KOMUT_ONAYLA, "talebi onayla; şartları özellik kimliğiyle seç"),
        (KOMUT_REDDET, "talebi reddet"),
    ):
        p = alt.add_parser(ad, help=yardim)
        p.add_argument("talep", type=int)
        p.add_argument(
            "--surum",
            type=int,
            required=True,
            help="goster'de görülen hedef sürümü; değişmişse karar uygulanmaz",
        )
        p.add_argument("--gerekce", default=None)
        if ad == KOMUT_ONAYLA:
            p.add_argument(
                "--sart",
                type=int,
                action="append",
                help=(
                    "mükerrerlik şartı olarak seçilen özellik kimliği (tekrarlanabilir)"
                ),
            )
    return ayristirici


def _bekleyenleri_yaz(oturum: Session) -> None:
    talepler = onaylar.bekleyenleri_listele(oturum)
    if not talepler:
        print("Karar bekleyen talep yok.")
        return
    for t in talepler:
        print(
            f"talep {t.id} | {t.tur.value} | hedef {t.hedef_id} | "
            f"sürüm {t.hedef_surumu} | {t.olusturma_zamani.isoformat(sep=' ')}"
        )


def _talebi_goster(oturum: Session, talep_id: int) -> None:
    talep = onaylar.talep_getir(oturum, talep_id)
    print(
        f"talep {talep.id} | {talep.tur.value} | durum {talep.durum.value} | "
        f"hedef {talep.hedef_id} | sürüm {talep.hedef_surumu}"
    )
    if talep.tur is sz.OnayTuru.NESNE_ACILISI:
        ayrinti = nesneler.nesne_getir(oturum, talep.hedef_id)
        nesne = ayrinti.nesne
        print(
            f"nesne {nesne.id} | seviye {nesne.seviye} | durum {nesne.durum.value} | "
            f"sürüm {nesne.surum} | üstler {list(ayrinti.ust_idleri)}"
        )
        for o in ayrinti.ozellikler:
            isaret = " [şart]" if o.sart else ""
            print(
                f"  [{o.id}] {o.alan_adi} = {o.deger!r} ({o.deger_turu.value}){isaret}"
            )
        print(
            f"Onaylamak için: defteriki-onay onayla {talep.id} --surum {nesne.surum} "
            "[--sart ÖZELLİK_ID ...]"
        )


def _karari_uygula(
    oturum: Session, talep_id: int, gorulen_surum: int, karar: onaylar.Karar
) -> None:
    sonuc = onaylar.karar_uygula(
        oturum,
        talep_id=talep_id,
        gorulen_hedef_surumu=gorulen_surum,
        karar=karar,
        simdi=sz.simdi_utc(),
        aktor=sz.DenetimAktoru.KULLANICI,
    )
    print(f"talep {sonuc.id} {sonuc.durum.value}")
    if sonuc.tur is sz.OnayTuru.NESNE_ACILISI:
        nesne = nesneler.nesne_getir(oturum, sonuc.hedef_id).nesne
        print(
            f"nesne {nesne.id} {nesne.durum.value} | sürüm {nesne.surum} | "
            f"şartlar {list(karar.secilen_sartlar)}"
        )


def _hata_yaz(mesaj: str) -> None:
    print(f"defteriki-onay: {mesaj}", file=sys.stderr, flush=True)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())

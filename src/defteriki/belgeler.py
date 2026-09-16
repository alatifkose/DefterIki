"""Belge, okuma, satır gönderimi ve belge kaydı (Teslim 4.5).

Kavramlar (Tam Plan bölüm 3 ve 8; sözlük "Yazmak ve kayıt etmek"):

* **Belge dosyası** arşivdeki değişmez baytlardır (``arsiv``); **belge** o
  dosyanın kaynak kimliğidir. Aynı dosya ikinci kez gelirse mevcut belge
  döner, ikinci belge ve ikinci mali etki üretilmez (K18,
  ``UNIQUE(belge.dosya_id)``).
* **Okuma** Cowork'un belgeden çıkardığı yapılandırılmış içeriktir;
  sürümlüdür. Uygulama okuma yapmaz, saklar ve denetler.
* **Gönderim** tek yazma çağrısındaki satır paketidir: biçim hatası varsa
  paketin tamamı reddedilir, hiçbir satır yazılmaz (K07). Aynı okumada aynı
  satır anahtarı aynı içerikle yeniden gelirse tekrar gönderimdir, satır
  "zaten mevcut" döner; içerik farklıysa ``ANAHTAR_ICERIK_CAKISMASI``.
* **Kayıt etmek** yazmaktan ayrıdır (K19): Cowork ``okuma_tamamla`` ile
  bitişi ve tamlık bilgisini bildirir; uygulama koşulları denetler (bütün
  satırlar sonuçlanmış, mutabakat farkı yok; açık şüphe koşulu Aşama 7'de)
  ve belge kaydını **kendisi** tanımlar (C07): tek işlemde ``KAYITLI`` olur
  ya da hiçbir durum değişmez.

Belge durumları bu teslimde ``ARSIVLENDI → OKUNUYOR → HAZIR → KAYITLI``
(C08). ``KARAR_BEKLIYOR``, ``GECERSIZ`` ve ``YERINE_GECILDI`` geçişleri
Aşama 7 ve 8'de yazılır; bu yüzden okuma yalnız ``ARSIVLENDI`` belgede
başlatılır (sürüm 1) ve yeni okuma sürümü henüz açılmaz.

Satır durumu 4.5'te gönderimle gelir (``YAZILDI`` ya da ``KAPSAM_DISI``).
Kayıt ve etki üretimi 4.6'da ``kayitlar.hareket_yaz`` ile gelir; C08 listesinde
kabul ile kayıt arasında ara durum yoktur, bu yüzden 4.5 gönderimi satırı
doğrudan sonuç durumuyla yazar. Tamlıktaki bakiye ve toplam alanları
saklanır; etki toplamlarıyla karşılaştırma 4.6'da ``hesaplamalar`` gelince
eklenir. Bu teslimde mutabakat = beklenen satır sayısı ile yazılan satır
sayısı.

Her yazma işlevi işlem anahtarı ister (K08), denetim olayı yazar ve commit
yapmaz; işlem sahibi çağırandır. Tek istisna ``belge_al``: dosya işlemi ile
veritabanı işlemi tek transaction olamayacağından (Tam Plan 8.1) önce
arşivler, sonra kısa yazma işlemini kendisi açar.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.orm import Session

from defteriki import arsiv, denetim, islem_anahtarlari, sema
from defteriki import sozlesmeler as sz
from defteriki.veritabani import Veritabani

ARAC_BELGE_AL = "belge_al"
ARAC_OKUMA_BASLAT = "okuma_baslat"
ARAC_SATIR_GONDER = "satir_gonder"
ARAC_OKUMA_TAMAMLA = "okuma_tamamla"
ARAC_BELGE_KAYDET = "belge_kaydet"

EYLEM_BELGE_AL = "belge_al"
EYLEM_OKUMA_BASLAT = "okuma_baslat"
EYLEM_SATIR_GONDER = "satir_gonder"
EYLEM_OKUMA_TAMAMLA = "okuma_tamamla"
EYLEM_BELGE_HAZIR = "belge_hazir"
EYLEM_BELGE_KAYDET = "belge_kaydet"

AZAMI_GONDERIM_SATIRI = 500
AZAMI_GONDERIM_BOYUTU = 2 * 1024 * 1024
AZAMI_SATIR_ANAHTARI_UZUNLUGU = 128
AZAMI_HAM_UZUNLUGU = 4096
AZAMI_ICERIK_UZUNLUGU = 64 * 1024
AZAMI_SEMA_SURUMU_UZUNLUGU = 32
"""C18 gönderim sınırları: 500 satır ve 2 MiB; aşılırsa açık hata, veri kesilmez."""

GONDERILEBILIR_SATIR_DURUMLARI = frozenset(
    {sz.SatirDurumu.YAZILDI, sz.SatirDurumu.KAPSAM_DISI}
)
"""4.5'te gönderimle gelebilen satır durumları; diğerleri Aşama 7 ve 8'de."""

SONUCLANMIS_SATIR_DURUMLARI = frozenset(
    {
        sz.SatirDurumu.YAZILDI,
        sz.SatirDurumu.MEVCUDA_BAGLANDI,
        sz.SatirDurumu.KAPSAM_DISI,
    }
)
"""C07: belge kaydı için her satır bunlardan birinde olmalı."""


# --- tipler --------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ArsivDosyasi:
    id: int
    sha256: str
    boyut: int
    mime: str
    goreli_yol: str
    olusturma_zamani: datetime


@dataclass(frozen=True, slots=True)
class Belge:
    id: int
    dosya_id: int
    durum: sz.BelgeDurumu
    etkin_okuma_id: int | None
    surum: int
    olusturma_zamani: datetime


@dataclass(frozen=True, slots=True)
class Tamlik:
    """Cowork'un belge hakkında bildirdiği tamlık bilgisi (Tam Plan 5.2).

    Verilmeyen alan "bilinmiyor" demektir; "belgenin tamamı okundu" iddiası
    üretilmez. Bakiye alanları negatif olabilir (KMH); toplamlar ve satır
    sayısı sıfır ya da pozitif.
    """

    beklenen_satir_sayisi: int | None = None
    acilis_bakiyesi_kurus: int | None = None
    kapanis_bakiyesi_kurus: int | None = None
    toplam_giris_kurus: int | None = None
    toplam_cikis_kurus: int | None = None


@dataclass(frozen=True, slots=True)
class Okuma:
    id: int
    belge_id: int
    surum_no: int
    sema_surumu: str
    icerik: dict[str, Any] | None
    tamlik: Tamlik | None
    durum: sz.OkumaDurumu
    olusturma_zamani: datetime


@dataclass(frozen=True, slots=True)
class SatirGirdisi:
    satir_anahtari: str
    """Cowork'un ürettiği, okuma içinde benzersiz istemci anahtarı."""
    konum: int
    """Belgedeki sıra (0'dan başlar); izlenebilirlik içindir."""
    ham: Mapping[str, Any]
    """Satırın ham içeriği; uygulama yorumlamaz, saklar."""
    durum: sz.SatirDurumu = sz.SatirDurumu.YAZILDI


@dataclass(frozen=True, slots=True)
class OkumaSatiri:
    id: int
    okuma_id: int
    satir_anahtari: str
    konum: int
    ham: dict[str, Any]
    durum: sz.SatirDurumu


@dataclass(frozen=True, slots=True)
class BelgeTanimlamaSonucu:
    belge: Belge
    dosya: ArsivDosyasi
    zaten_vardi: bool
    """Aynı içerik daha önce belge olmuştu; ikinci belge açılmadı (K18)."""


@dataclass(frozen=True, slots=True)
class BelgeAyrinti:
    belge: Belge
    dosya: ArsivDosyasi
    okumalar: tuple[Okuma, ...]


@dataclass(frozen=True, slots=True)
class GonderimSonucu:
    okuma: Okuma
    yazilan: tuple[OkumaSatiri, ...]
    zaten_mevcut: tuple[OkumaSatiri, ...]
    """Aynı anahtar ve içerikle daha önce yazılmış satırlar (tekrar gönderim)."""


@dataclass(frozen=True, slots=True)
class OkumaTamamlamaSonucu:
    okuma: Okuma
    belge: Belge


# --- belge alma ------------------------------------------------------------------


def belge_al(
    veritabani: Veritabani,
    *,
    yol: str,
    gelen_dizini: Path,
    belge_dizini: Path,
    islem_anahtari: str,
    aktor: sz.DenetimAktoru,
    simdi: datetime | None = None,
) -> BelgeTanimlamaSonucu:
    """C10 akışı: dosyayı arşivler, sonra kısa yazma işleminde belgeyi tanımlar.

    Dosya ve veritabanı tek işlem değildir; veritabanı düşerse dosya arşivde
    sahipsiz kalır, kaynaksız kayıt oluşmaz.
    """
    dosya = arsiv.dosyayi_arsivle(
        yol, gelen_dizini=gelen_dizini, belge_dizini=belge_dizini
    )
    with veritabani.yazma_islemi() as oturum:
        return belge_tanimla(
            oturum, dosya=dosya, islem_anahtari=islem_anahtari, aktor=aktor, simdi=simdi
        )


def belge_tanimla(
    oturum: Session,
    *,
    dosya: arsiv.ArsivlenenDosya,
    islem_anahtari: str,
    aktor: sz.DenetimAktoru,
    simdi: datetime | None = None,
) -> BelgeTanimlamaSonucu:
    """Arşivlenmiş dosya için ``arsiv_dosya`` ve ``ARSIVLENDI`` belge yazar.

    Aynı içerik (sha256) daha önce belge olduysa o belge döner (K18);
    ``zaten_vardi`` True olur, hiçbir şey yazılmaz.
    """
    simdi = simdi or sz.simdi_utc()
    icerik = {"sha256": dosya.sha256, "boyut": dosya.boyut, "mime": dosya.mime}

    def ac(islem_id: int) -> islem_anahtarlari.Sonuc:
        mevcut = oturum.execute(
            select(sema.arsiv_dosya.c.id).where(
                sema.arsiv_dosya.c.sha256 == dosya.sha256
            )
        ).scalar_one_or_none()
        if mevcut is not None:
            belge_id = oturum.execute(
                select(sema.belge.c.id).where(sema.belge.c.dosya_id == mevcut)
            ).scalar_one()
            return {"belge_id": int(belge_id), "dosya_id": int(mevcut), "yeni": False}

        dosya_id = int(
            oturum.execute(
                sema.arsiv_dosya.insert()
                .values(
                    sha256=dosya.sha256,
                    boyut=dosya.boyut,
                    mime=dosya.mime,
                    goreli_yol=dosya.goreli_yol,
                    olusturma_zamani=simdi,
                )
                .returning(sema.arsiv_dosya.c.id)
            ).scalar_one()
        )
        belge_id = int(
            oturum.execute(
                sema.belge.insert()
                .values(
                    dosya_id=dosya_id,
                    durum=sz.BelgeDurumu.ARSIVLENDI.value,
                    etkin_okuma_id=None,
                    surum=1,
                    olusturma_zamani=simdi,
                )
                .returning(sema.belge.c.id)
            ).scalar_one()
        )
        denetim.olay_yaz(
            oturum,
            aktor=aktor,
            eylem=EYLEM_BELGE_AL,
            hedef=denetim.hedef_adi("belge", belge_id),
            simdi=simdi,
            islem_id=islem_id,
            gerekce=f"{dosya.mime}, {dosya.boyut} bayt",
            sonraki_durum=sz.BelgeDurumu.ARSIVLENDI.value,
        )
        return {"belge_id": belge_id, "dosya_id": dosya_id, "yeni": True}

    sonuc, _ = islem_anahtarlari.anahtarla_calistir(
        oturum,
        arac_adi=ARAC_BELGE_AL,
        anahtar=islem_anahtari,
        icerik=icerik,
        simdi=simdi,
        islev=ac,
    )
    ayrinti = belge_getir(oturum, int(sonuc["belge_id"]))
    return BelgeTanimlamaSonucu(
        belge=ayrinti.belge, dosya=ayrinti.dosya, zaten_vardi=not bool(sonuc["yeni"])
    )


def belge_getir(oturum: Session, belge_id: int) -> BelgeAyrinti:
    """Belge, arşiv dosyası ve okuma sürümleri; yoksa ``BELGE_YOK``."""
    satir = oturum.execute(
        select(sema.belge).where(sema.belge.c.id == belge_id)
    ).one_or_none()
    if satir is None:
        raise sz.BelgeYok("belge bulunamadı", alan="belge_id")
    belge = _belge(satir._mapping)  # pyright: ignore[reportPrivateUsage]
    dosya = oturum.execute(
        select(sema.arsiv_dosya).where(sema.arsiv_dosya.c.id == belge.dosya_id)
    ).one()
    okumalar = tuple(
        _okuma(o._mapping)  # pyright: ignore[reportPrivateUsage]
        for o in oturum.execute(
            select(sema.okuma)
            .where(sema.okuma.c.belge_id == belge_id)
            .order_by(sema.okuma.c.surum_no)
        ).all()
    )
    return BelgeAyrinti(belge, _dosya(dosya._mapping), okumalar)  # pyright: ignore[reportPrivateUsage]


# --- okuma ---------------------------------------------------------------------


def okuma_baslat(
    oturum: Session,
    *,
    belge_id: int,
    sema_surumu: str,
    belge_dizini: Path,
    islem_anahtari: str,
    aktor: sz.DenetimAktoru,
    icerik: Mapping[str, Any] | None = None,
    tamlik: Tamlik | None = None,
    simdi: datetime | None = None,
) -> Okuma:
    """``ARSIVLENDI`` belgede sürüm 1 okumayı ``ACIK`` açar; belge ``OKUNUYOR``.

    Arşiv dosyası diskte yerinde değilse ``ARSIV_EKSIK`` (S10): dosyasız
    belgeye okuma başlamaz. ``sema_surumu`` Cowork'un uyduğu okuma
    sözleşmesinin sürümüdür (Aşama 5'te ``docs/cowork.md`` ile sabitlenir);
    burada yalnız boş olmayan kısa metin olarak saklanır.
    """
    simdi = simdi or sz.simdi_utc()
    sema_surumu = _sema_surumunu_dogrula(sema_surumu)
    icerik_json = _icerigi_dogrula(icerik)
    tamlik_json = _tamligi_dogrula(tamlik)
    istek = {
        "belge_id": belge_id,
        "sema_surumu": sema_surumu,
        "icerik": icerik_json,
        "tamlik": tamlik_json,
    }

    def ac(islem_id: int) -> islem_anahtarlari.Sonuc:
        ayrinti = belge_getir(oturum, belge_id)
        belge = ayrinti.belge
        if belge.durum is not sz.BelgeDurumu.ARSIVLENDI:
            raise sz.GirdiGecersiz(
                f"belge okumaya açık değil (durum {belge.durum.value}); yeni okuma "
                "sürümü düzeltme akışıyla açılır",
                alan="belge_id",
            )
        if not arsiv.arsivde_var_mi(
            belge_dizini, ayrinti.dosya.goreli_yol, ayrinti.dosya.boyut
        ):
            raise sz.ArsivEksik(
                "belgenin arşiv dosyası yerinde değil; dosyayı yeniden al",
                alan="belge_id",
            )
        surum_no = (
            int(
                oturum.execute(
                    select(func.coalesce(func.max(sema.okuma.c.surum_no), 0)).where(
                        sema.okuma.c.belge_id == belge_id
                    )
                ).scalar_one()
            )
            + 1
        )
        okuma_id = int(
            oturum.execute(
                sema.okuma.insert()
                .values(
                    belge_id=belge_id,
                    surum_no=surum_no,
                    sema_surumu=sema_surumu,
                    icerik=icerik_json,
                    tamlik=tamlik_json,
                    durum=sz.OkumaDurumu.ACIK.value,
                    olusturma_zamani=simdi,
                )
                .returning(sema.okuma.c.id)
            ).scalar_one()
        )
        _belge_durumunu_degistir(
            oturum,
            belge,
            sz.BelgeDurumu.OKUNUYOR,
            eylem=EYLEM_OKUMA_BASLAT,
            aktor=aktor,
            simdi=simdi,
            islem_id=islem_id,
            gerekce=f"okuma {okuma_id}, sürüm {surum_no}",
        )
        return {"okuma_id": okuma_id}

    sonuc, _ = islem_anahtarlari.anahtarla_calistir(
        oturum,
        arac_adi=ARAC_OKUMA_BASLAT,
        anahtar=islem_anahtari,
        icerik=istek,
        simdi=simdi,
        islev=ac,
    )
    return okuma_getir(oturum, int(sonuc["okuma_id"]))


def okuma_getir(oturum: Session, okuma_id: int) -> Okuma:
    satir = oturum.execute(
        select(sema.okuma).where(sema.okuma.c.id == okuma_id)
    ).one_or_none()
    if satir is None:
        raise sz.HedefBulunamadi("okuma bulunamadı", alan="okuma_id")
    return _okuma(satir._mapping)  # pyright: ignore[reportPrivateUsage]


def satirlari_listele(
    oturum: Session, okuma_id: int, *, sayfalama: sz.Sayfalama = sz.Sayfalama()
) -> list[OkumaSatiri]:
    """Okumanın satırları, konum sırasıyla."""
    satirlar = oturum.execute(
        select(sema.okuma_satir)
        .where(sema.okuma_satir.c.okuma_id == okuma_id)
        .order_by(sema.okuma_satir.c.konum, sema.okuma_satir.c.id)
        .limit(sayfalama.sinir)
        .offset(sayfalama.baslangic)
    ).all()
    return [_satir(s._mapping) for s in satirlar]  # pyright: ignore[reportPrivateUsage]


# --- gönderim ----------------------------------------------------------------


def satir_gonder(
    oturum: Session,
    *,
    okuma_id: int,
    satirlar: Sequence[SatirGirdisi],
    islem_anahtari: str,
    aktor: sz.DenetimAktoru,
    simdi: datetime | None = None,
) -> GonderimSonucu:
    """Bir gönderim paketini ``ACIK`` okumaya yazar; ya tamamı ya hiçbiri (K07).

    Paket önce baştan sona doğrulanır; tek satırda bile biçim hatası varsa
    hiçbir satır yazılmaz ve hata satırın konumunu söyler. Aynı anahtar
    aynı içerikle daha önce yazılmışsa satır ``zaten_mevcut`` listesine
    girer; farklı içerikle yazılmışsa ``ANAHTAR_ICERIK_CAKISMASI``.
    """
    simdi = simdi or sz.simdi_utc()
    hazir = _satirlari_dogrula(satirlar)
    istek = {"okuma_id": okuma_id, "satirlar": [asdict(h) for h in hazir]}

    def yaz(islem_id: int) -> islem_anahtarlari.Sonuc:
        okuma = okuma_getir(oturum, okuma_id)
        if okuma.durum is not sz.OkumaDurumu.ACIK:
            raise sz.GirdiGecersiz(
                f"okuma satır kabul etmiyor (durum {okuma.durum.value})",
                alan="okuma_id",
            )
        mevcutlar = {
            str(m.satir_anahtari): m
            for m in oturum.execute(
                select(sema.okuma_satir).where(
                    sema.okuma_satir.c.okuma_id == okuma_id,
                    sema.okuma_satir.c.satir_anahtari.in_(
                        [h.satir_anahtari for h in hazir]
                    ),
                )
            ).all()
        }
        yeni: list[dict[str, Any]] = []
        mevcut_idleri: list[int] = []
        for konum, h in enumerate(hazir):
            mevcut = mevcutlar.get(h.satir_anahtari)
            if mevcut is None:
                yeni.append(
                    {
                        "okuma_id": okuma_id,
                        "satir_anahtari": h.satir_anahtari,
                        "konum": h.konum,
                        "ham": h.ham,
                        "durum": h.durum,
                        "aday_grup_id": None,
                    }
                )
                continue
            ayni = (
                int(mevcut.konum) == h.konum
                and str(mevcut.durum) == h.durum
                and _kanonik(mevcut.ham) == _kanonik(h.ham)
            )
            if not ayni:
                raise sz.AnahtarIcerikCakismasi(
                    "aynı okumada aynı satır anahtarı farklı içerikle yazılmış; "
                    "düzeltme için yeni okuma sürümü gerekir",
                    alan="satir_anahtari",
                    konum=konum,
                )
            mevcut_idleri.append(int(mevcut.id))
        yazilan_idleri: list[int] = []
        if yeni:
            yazilan_idleri = [
                int(k)
                for k in oturum.execute(
                    sema.okuma_satir.insert().returning(sema.okuma_satir.c.id), yeni
                ).scalars()
            ]
        denetim.olay_yaz(
            oturum,
            aktor=aktor,
            eylem=EYLEM_SATIR_GONDER,
            hedef=denetim.hedef_adi("okuma", okuma_id),
            simdi=simdi,
            islem_id=islem_id,
            gerekce=f"{len(yazilan_idleri)} yazıldı, {len(mevcut_idleri)} mevcut",
        )
        return {"yazilan_idleri": yazilan_idleri, "mevcut_idleri": mevcut_idleri}

    sonuc, _ = islem_anahtarlari.anahtarla_calistir(
        oturum,
        arac_adi=ARAC_SATIR_GONDER,
        anahtar=islem_anahtari,
        icerik=istek,
        simdi=simdi,
        islev=yaz,
    )
    return GonderimSonucu(
        okuma=okuma_getir(oturum, okuma_id),
        yazilan=_satirlari_getir(oturum, [int(k) for k in sonuc["yazilan_idleri"]]),
        zaten_mevcut=_satirlari_getir(oturum, [int(k) for k in sonuc["mevcut_idleri"]]),
    )


# --- tamamlama ve belge kaydı ---------------------------------------------------


def okuma_tamamla(
    oturum: Session,
    *,
    okuma_id: int,
    islem_anahtari: str,
    aktor: sz.DenetimAktoru,
    tamlik: Tamlik | None = None,
    simdi: datetime | None = None,
) -> OkumaTamamlamaSonucu:
    """Cowork'un "bitti" bildirimi: okuma ``TAMAMLANDI``, belge ``HAZIR`` ve
    ardından uygulama belge kaydını tanımlar, belge ``KAYITLI`` (C07).

    Koşullar sağlanmazsa (satır sonuçlanmamış → ``BELGE_HAZIR_DEGIL``, satır
    sayısı beklenenden farklı → ``MUTABAKAT_FARKI``) hata verilir ve hiçbir
    durum değişmez: okuma ``ACIK`` kalır, eksik satırlar gönderilebilir.
    ``tamlik`` verilirse okumadakinin yerine geçer.
    """
    simdi = simdi or sz.simdi_utc()
    tamlik_json = _tamligi_dogrula(tamlik)
    istek = {"okuma_id": okuma_id, "tamlik": tamlik_json}

    def tamamla(islem_id: int) -> islem_anahtarlari.Sonuc:
        okuma = okuma_getir(oturum, okuma_id)
        if okuma.durum is not sz.OkumaDurumu.ACIK:
            raise sz.GirdiGecersiz(
                f"okuma zaten sonuçlanmış ({okuma.durum.value})", alan="okuma_id"
            )
        belge = belge_getir(oturum, okuma.belge_id).belge
        if belge.durum is not sz.BelgeDurumu.OKUNUYOR:
            raise sz.BelgeHazirDegil(
                f"belge okunuyor durumunda değil ({belge.durum.value})",
                alan="belge_id",
            )
        etkin_tamlik = tamlik if tamlik is not None else okuma.tamlik
        _kayit_kosullarini_denetle(oturum, okuma_id, etkin_tamlik)

        degerler: dict[str, Any] = {"durum": sz.OkumaDurumu.TAMAMLANDI.value}
        if tamlik is not None:
            degerler["tamlik"] = tamlik_json
        oturum.execute(
            sema.okuma.update().where(sema.okuma.c.id == okuma_id).values(**degerler)
        )
        denetim.olay_yaz(
            oturum,
            aktor=aktor,
            eylem=EYLEM_OKUMA_TAMAMLA,
            hedef=denetim.hedef_adi("okuma", okuma_id),
            simdi=simdi,
            islem_id=islem_id,
            onceki_durum=sz.OkumaDurumu.ACIK.value,
            sonraki_durum=sz.OkumaDurumu.TAMAMLANDI.value,
        )
        hazir = _belge_durumunu_degistir(
            oturum,
            belge,
            sz.BelgeDurumu.HAZIR,
            eylem=EYLEM_BELGE_HAZIR,
            aktor=aktor,
            simdi=simdi,
            islem_id=islem_id,
            gerekce=f"okuma {okuma_id} tamamlandı",
        )
        _belge_kaydini_tanimla(oturum, hazir, okuma_id, simdi=simdi, islem_id=islem_id)
        return {"okuma_id": okuma_id, "belge_id": belge.id}

    sonuc, _ = islem_anahtarlari.anahtarla_calistir(
        oturum,
        arac_adi=ARAC_OKUMA_TAMAMLA,
        anahtar=islem_anahtari,
        icerik=istek,
        simdi=simdi,
        islev=tamamla,
    )
    return OkumaTamamlamaSonucu(
        okuma=okuma_getir(oturum, int(sonuc["okuma_id"])),
        belge=belge_getir(oturum, int(sonuc["belge_id"])).belge,
    )


def belge_kaydet(
    oturum: Session,
    *,
    belge_id: int,
    gorulen_surum: int,
    islem_anahtari: str,
    simdi: datetime | None = None,
) -> Belge:
    """``HAZIR`` belgeyi koşulları yeniden denetleyerek ``KAYITLI`` yapar.

    ``okuma_tamamla`` bunu kendisi çağırır; bu işlev ``HAZIR`` kalmış bir
    belgeyi (Aşama 7'de karar sonrası) kaydetmek içindir. ``gorulen_surum``
    belgenin güncel sürümüyle aynı değilse ``HEDEF_SURUMU_DEGISTI``.
    """
    simdi = simdi or sz.simdi_utc()
    istek = {"belge_id": belge_id, "gorulen_surum": gorulen_surum}

    def kaydet(islem_id: int) -> islem_anahtarlari.Sonuc:
        belge = belge_getir(oturum, belge_id).belge
        if belge.surum != gorulen_surum:
            raise sz.HedefSurumuDegisti(
                "belge bu arada değişti; güncel hâlini al", alan="gorulen_surum"
            )
        if belge.durum is not sz.BelgeDurumu.HAZIR:
            raise sz.BelgeHazirDegil(
                f"belge kayda hazır değil (durum {belge.durum.value})",
                alan="belge_id",
            )
        okuma_id = int(
            oturum.execute(
                select(sema.okuma.c.id).where(
                    sema.okuma.c.belge_id == belge_id,
                    sema.okuma.c.durum == sz.OkumaDurumu.TAMAMLANDI.value,
                )
            ).scalar_one()
        )
        _belge_kaydini_tanimla(oturum, belge, okuma_id, simdi=simdi, islem_id=islem_id)
        return {"belge_id": belge_id}

    islem_anahtarlari.anahtarla_calistir(
        oturum,
        arac_adi=ARAC_BELGE_KAYDET,
        anahtar=islem_anahtari,
        icerik=istek,
        simdi=simdi,
        islev=kaydet,
    )
    return belge_getir(oturum, belge_id).belge


def _belge_kaydini_tanimla(
    oturum: Session, belge: Belge, okuma_id: int, *, simdi: datetime, islem_id: int
) -> Belge:
    """C07: koşullar yeniden denetlenir, belge ``KAYITLI`` ve etkin okuma bu."""
    okuma = okuma_getir(oturum, okuma_id)
    if okuma.durum is not sz.OkumaDurumu.TAMAMLANDI:
        raise sz.BelgeHazirDegil("okuma tamamlanmamış", alan="okuma_id")
    _kayit_kosullarini_denetle(oturum, okuma_id, okuma.tamlik)
    return _belge_durumunu_degistir(
        oturum,
        belge,
        sz.BelgeDurumu.KAYITLI,
        eylem=EYLEM_BELGE_KAYDET,
        aktor=sz.DenetimAktoru.UYGULAMA,
        simdi=simdi,
        islem_id=islem_id,
        gerekce=f"etkin okuma {okuma_id}",
        etkin_okuma_id=okuma_id,
    )


def _kayit_kosullarini_denetle(
    oturum: Session, okuma_id: int, tamlik: Tamlik | None
) -> None:
    """Bütün satırlar sonuçlanmış ve satır sayısı beklenenle aynı (C07, 4.5 hâli)."""
    sayimlar = oturum.execute(
        select(sema.okuma_satir.c.durum, func.count())
        .where(sema.okuma_satir.c.okuma_id == okuma_id)
        .group_by(sema.okuma_satir.c.durum)
    ).all()
    toplam = 0
    for durum, sayi in sayimlar:
        toplam += int(sayi)
        if sz.SatirDurumu(durum) not in SONUCLANMIS_SATIR_DURUMLARI:
            raise sz.BelgeHazirDegil(
                f"{sayi} satır {durum} durumunda; hepsi sonuçlanmadan belge "
                "kaydedilmez",
                alan="okuma_id",
            )
    if tamlik is not None and tamlik.beklenen_satir_sayisi is not None:
        if tamlik.beklenen_satir_sayisi != toplam:
            raise sz.MutabakatFarki(
                f"beklenen satır sayısı {tamlik.beklenen_satir_sayisi}, yazılan "
                f"{toplam}; eksik ya da fazla satırı çöz",
                alan="beklenen_satir_sayisi",
            )


def _belge_durumunu_degistir(
    oturum: Session,
    belge: Belge,
    yeni: sz.BelgeDurumu,
    *,
    eylem: str,
    aktor: sz.DenetimAktoru,
    simdi: datetime,
    islem_id: int,
    gerekce: str,
    etkin_okuma_id: int | None = None,
) -> Belge:
    """Belge durumunu değiştirir, sürümü bir artırır, denetim olayı yazar."""
    degerler: dict[str, Any] = {"durum": yeni.value, "surum": belge.surum + 1}
    if etkin_okuma_id is not None:
        degerler["etkin_okuma_id"] = etkin_okuma_id
    guncellenen = oturum.execute(
        sema.belge.update()
        .where(sema.belge.c.id == belge.id, sema.belge.c.surum == belge.surum)
        .values(**degerler)
        .returning(sema.belge.c.id)
    ).all()
    if len(guncellenen) != 1:
        raise sz.HedefSurumuDegisti(
            "belge bu arada değişti; güncel hâlini al", alan="belge_id"
        )
    denetim.olay_yaz(
        oturum,
        aktor=aktor,
        eylem=eylem,
        hedef=denetim.hedef_adi("belge", belge.id),
        simdi=simdi,
        islem_id=islem_id,
        gerekce=gerekce,
        onceki_durum=belge.durum.value,
        sonraki_durum=yeni.value,
    )
    return belge_getir(oturum, belge.id).belge


# --- doğrulama -------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _HazirSatir:
    satir_anahtari: str
    konum: int
    ham: dict[str, Any]
    durum: str


def _satirlari_dogrula(satirlar: Sequence[SatirGirdisi]) -> list[_HazirSatir]:
    if not satirlar:
        raise sz.GirdiGecersiz("gönderim en az bir satır içermeli", alan="satirlar")
    if len(satirlar) > AZAMI_GONDERIM_SATIRI:
        raise sz.GirdiGecersiz(
            f"gönderim en çok {AZAMI_GONDERIM_SATIRI} satır", alan="satirlar"
        )
    hazir: list[_HazirSatir] = []
    gorulen: set[str] = set()
    toplam_boyut = 0
    for konum, satir in enumerate(satirlar):
        anahtar = satir.satir_anahtari
        if not isinstance(anahtar, str) or not anahtar.strip():  # pyright: ignore[reportUnnecessaryIsInstance]
            raise sz.GirdiGecersiz(
                "satır anahtarı boş olamaz", alan="satir_anahtari", konum=konum
            )
        if len(anahtar) > AZAMI_SATIR_ANAHTARI_UZUNLUGU:
            raise sz.GirdiGecersiz(
                f"satır anahtarı en çok {AZAMI_SATIR_ANAHTARI_UZUNLUGU} karakter",
                alan="satir_anahtari",
                konum=konum,
            )
        if anahtar in gorulen:
            raise sz.GirdiGecersiz(
                "aynı gönderimde aynı satır anahtarı iki kez",
                alan="satir_anahtari",
                konum=konum,
            )
        gorulen.add(anahtar)
        if type(satir.konum) is not int or satir.konum < 0:
            raise sz.GirdiGecersiz(
                "konum sıfır ya da pozitif tam sayı olmalı", alan="konum", konum=konum
            )
        if not isinstance(satir.ham, Mapping) or not satir.ham:  # pyright: ignore[reportUnnecessaryIsInstance]
            raise sz.GirdiGecersiz(
                "ham içerik boş olmayan bir nesne olmalı", alan="ham", konum=konum
            )
        try:
            ham_metni = _kanonik(satir.ham)
        except (TypeError, ValueError):
            raise sz.GirdiGecersiz(
                "ham içerik JSON'a çevrilemedi", alan="ham", konum=konum
            ) from None
        if len(ham_metni) > AZAMI_HAM_UZUNLUGU:
            raise sz.GirdiGecersiz(
                f"ham içerik en çok {AZAMI_HAM_UZUNLUGU} karakter",
                alan="ham",
                konum=konum,
            )
        toplam_boyut += len(ham_metni.encode("utf-8"))
        if toplam_boyut > AZAMI_GONDERIM_BOYUTU:
            raise sz.GirdiGecersiz(
                f"gönderim {AZAMI_GONDERIM_BOYUTU // (1024 * 1024)} MiB sınırını aşar",
                alan="satirlar",
                konum=konum,
            )
        if satir.durum not in GONDERILEBILIR_SATIR_DURUMLARI:
            raise sz.GirdiGecersiz(
                f"satır durumu {satir.durum.value} gönderimle verilemez",
                alan="durum",
                konum=konum,
            )
        hazir.append(
            _HazirSatir(anahtar, satir.konum, dict(satir.ham), satir.durum.value)
        )
    return hazir


def _sema_surumunu_dogrula(deger: str) -> str:
    if not isinstance(deger, str) or not deger.strip():  # pyright: ignore[reportUnnecessaryIsInstance]
        raise sz.GirdiGecersiz("şema sürümü boş olamaz", alan="sema_surumu")
    if len(deger) > AZAMI_SEMA_SURUMU_UZUNLUGU:
        raise sz.GirdiGecersiz(
            f"şema sürümü en çok {AZAMI_SEMA_SURUMU_UZUNLUGU} karakter",
            alan="sema_surumu",
        )
    return deger.strip()


def _icerigi_dogrula(icerik: Mapping[str, Any] | None) -> dict[str, Any] | None:
    if icerik is None:
        return None
    if not isinstance(icerik, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise sz.GirdiGecersiz("okuma içeriği bir nesne olmalı", alan="icerik")
    try:
        metin = _kanonik(icerik)
    except (TypeError, ValueError):
        raise sz.GirdiGecersiz(
            "okuma içeriği JSON'a çevrilemedi", alan="icerik"
        ) from None
    if len(metin) > AZAMI_ICERIK_UZUNLUGU:
        raise sz.GirdiGecersiz(
            f"okuma içeriği en çok {AZAMI_ICERIK_UZUNLUGU} karakter", alan="icerik"
        )
    return dict(icerik)


def _tamligi_dogrula(tamlik: Tamlik | None) -> dict[str, int | None] | None:
    if tamlik is None:
        return None
    for alan, negatif_olabilir in (
        ("beklenen_satir_sayisi", False),
        ("acilis_bakiyesi_kurus", True),
        ("kapanis_bakiyesi_kurus", True),
        ("toplam_giris_kurus", False),
        ("toplam_cikis_kurus", False),
    ):
        deger = getattr(tamlik, alan)
        if deger is None:
            continue
        if type(deger) is not int or (deger < 0 and not negatif_olabilir):
            raise sz.GirdiGecersiz(
                "tamlık alanı tam sayı olmalı"
                + ("" if negatif_olabilir else " ve negatif olamaz"),
                alan=alan,
            )
    return asdict(tamlik)


def _kanonik(deger: Any) -> str:
    return json.dumps(deger, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


# --- satır dönüştürücüler ------------------------------------------------------


def _satirlari_getir(oturum: Session, idler: Sequence[int]) -> tuple[OkumaSatiri, ...]:
    if not idler:
        return ()
    satirlar = oturum.execute(
        select(sema.okuma_satir)
        .where(sema.okuma_satir.c.id.in_(list(idler)))
        .order_by(sema.okuma_satir.c.konum, sema.okuma_satir.c.id)
    ).all()
    return tuple(_satir(s._mapping) for s in satirlar)  # pyright: ignore[reportPrivateUsage]


def _belge(satir: RowMapping) -> Belge:
    return Belge(
        id=int(satir["id"]),
        dosya_id=int(satir["dosya_id"]),
        durum=sz.BelgeDurumu(satir["durum"]),
        etkin_okuma_id=(
            int(satir["etkin_okuma_id"])
            if satir["etkin_okuma_id"] is not None
            else None
        ),
        surum=int(satir["surum"]),
        olusturma_zamani=satir["olusturma_zamani"],
    )


def _dosya(satir: RowMapping) -> ArsivDosyasi:
    return ArsivDosyasi(
        id=int(satir["id"]),
        sha256=str(satir["sha256"]),
        boyut=int(satir["boyut"]),
        mime=str(satir["mime"]),
        goreli_yol=str(satir["goreli_yol"]),
        olusturma_zamani=satir["olusturma_zamani"],
    )


def _okuma(satir: RowMapping) -> Okuma:
    tamlik = satir["tamlik"]
    return Okuma(
        id=int(satir["id"]),
        belge_id=int(satir["belge_id"]),
        surum_no=int(satir["surum_no"]),
        sema_surumu=str(satir["sema_surumu"]),
        icerik=dict(satir["icerik"]) if satir["icerik"] is not None else None,
        tamlik=Tamlik(**tamlik) if tamlik is not None else None,
        durum=sz.OkumaDurumu(satir["durum"]),
        olusturma_zamani=satir["olusturma_zamani"],
    )


def _satir(satir: RowMapping) -> OkumaSatiri:
    return OkumaSatiri(
        id=int(satir["id"]),
        okuma_id=int(satir["okuma_id"]),
        satir_anahtari=str(satir["satir_anahtari"]),
        konum=int(satir["konum"]),
        ham=dict(satir["ham"]),
        durum=sz.SatirDurumu(satir["durum"]),
    )

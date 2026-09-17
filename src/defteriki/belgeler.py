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

Satır durumu gönderimle gelir (``YAZILDI`` ya da ``KAPSAM_DISI``). Finansal
satır için kayıt, etki ve kaynak bağını ``kayitlar.hareket_yaz`` aynı
gönderimde üretir ve satırı ``YAZILDI`` yazar; ``satir_gonder`` kayıtsız
satır (başlık, bilgi) içindir. C08 listesinde kabul ile kayıt arasında ara
durum yoktur. Tamlıktaki bakiye ve toplam alanları saklanır ve tamamlama
anında yazılan satırlarla karşılaştırılır (karar 2026-09-17,
``_toplamlari_denetle``): beklenen satır sayısı, toplam giriş, toplam
çıkış ve açılış + giriş − çıkış = kapanış; verilmeyen alan denetlenmez.

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

from sqlalchemy import case, func, select
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
    uzanti: str
    kaynak_adi: str
    """İlk gelişteki dosya adı ve uzantısı (metadata); aynı içerik sonra başka
    adla gelirse bu alanlar değişmez."""
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
class TamlikAlani:
    """Bir tamlık alanı: durum ve (yalnız ``DEGER`` ise) sayı."""

    durum: sz.TamlikDurumu
    deger: int | None = None

    @staticmethod
    def sayi(deger: int) -> TamlikAlani:
        return TamlikAlani(sz.TamlikDurumu.DEGER, deger)


BELGEDE_YOK = TamlikAlani(sz.TamlikDurumu.BELGEDE_YOK)
OKUNAMADI = TamlikAlani(sz.TamlikDurumu.OKUNAMADI)


@dataclass(frozen=True, slots=True)
class Tamlik:
    """Cowork'un belge hakkında bildirdiği tamlık bilgisi (Tam Plan 5.2).

    Karar 2026-09-17: beş alanın her biri her okumada zorunlu bildirilir
    (``DEGER`` / ``BELGEDE_YOK`` / ``OKUNAMADI``); alanın hiç gönderilmemesi
    ``GIRDI_GECERSIZ``. Satır sayısı için ``BELGEDE_YOK`` yasaktır: Cowork
    gördüğü hareketleri sayar, sayamıyorsa ``OKUNAMADI`` der. Bakiye alanları
    negatif olabilir (KMH); toplamlar ve satır sayısı sıfır ya da pozitif.
    """

    beklenen_satir_sayisi: TamlikAlani
    acilis_bakiyesi_kurus: TamlikAlani
    kapanis_bakiyesi_kurus: TamlikAlani
    toplam_giris_kurus: TamlikAlani
    toplam_cikis_kurus: TamlikAlani


TAMLIK_ALANLARI: tuple[tuple[str, bool], ...] = (
    ("beklenen_satir_sayisi", False),
    ("acilis_bakiyesi_kurus", True),
    ("kapanis_bakiyesi_kurus", True),
    ("toplam_giris_kurus", False),
    ("toplam_cikis_kurus", False),
)
"""Tamlık alanları ve negatif olabilir mi."""


@dataclass(frozen=True, slots=True)
class Okuma:
    id: int
    belge_id: int
    surum_no: int
    sema_surumu: str
    icerik: dict[str, Any] | None
    tamlik: Tamlik
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
                    uzanti=dosya.uzanti,
                    kaynak_adi=dosya.kaynak_adi,
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


@dataclass(frozen=True, slots=True)
class BelgeVeDosya:
    belge: Belge
    dosya: ArsivDosyasi


def belgeleri_listele(
    oturum: Session, *, sayfalama: sz.Sayfalama = sz.Sayfalama()
) -> list[BelgeVeDosya]:
    """Belgeler arşiv dosyasıyla, yeniden eskiye (pencere belge listesi)."""
    satirlar = oturum.execute(
        select(sema.belge, sema.arsiv_dosya)
        .join(sema.arsiv_dosya, sema.arsiv_dosya.c.id == sema.belge.c.dosya_id)
        .order_by(sema.belge.c.id.desc())
        .limit(sayfalama.sinir)
        .offset(sayfalama.baslangic)
    ).all()
    sonuc: list[BelgeVeDosya] = []
    for s in satirlar:
        m = s._mapping  # pyright: ignore[reportPrivateUsage]
        sonuc.append(
            BelgeVeDosya(
                belge=Belge(
                    id=int(m[sema.belge.c.id]),
                    dosya_id=int(m[sema.belge.c.dosya_id]),
                    durum=sz.BelgeDurumu(m[sema.belge.c.durum]),
                    etkin_okuma_id=m[sema.belge.c.etkin_okuma_id],
                    surum=int(m[sema.belge.c.surum]),
                    olusturma_zamani=m[sema.belge.c.olusturma_zamani],
                ),
                dosya=ArsivDosyasi(
                    id=int(m[sema.arsiv_dosya.c.id]),
                    sha256=str(m[sema.arsiv_dosya.c.sha256]),
                    boyut=int(m[sema.arsiv_dosya.c.boyut]),
                    mime=str(m[sema.arsiv_dosya.c.mime]),
                    uzanti=str(m[sema.arsiv_dosya.c.uzanti]),
                    kaynak_adi=str(m[sema.arsiv_dosya.c.kaynak_adi]),
                    goreli_yol=str(m[sema.arsiv_dosya.c.goreli_yol]),
                    olusturma_zamani=m[sema.arsiv_dosya.c.olusturma_zamani],
                ),
            )
        )
    return sonuc


def kaydin_belge_idleri(oturum: Session, kayit_id: int) -> tuple[int, ...]:
    """Kaydı destekleyen (AKTIF kaynak) satırların belgeleri, artan kimlikle."""
    kk, os_, ok = sema.kayit_kaynak, sema.okuma_satir, sema.okuma
    idler = oturum.execute(
        select(ok.c.belge_id)
        .distinct()
        .select_from(
            kk.join(os_, os_.c.id == kk.c.okuma_satir_id).join(
                ok, ok.c.id == os_.c.okuma_id
            )
        )
        .where(
            kk.c.kayit_id == kayit_id,
            kk.c.durum == sz.KaynakDurumu.AKTIF.value,
        )
        .order_by(ok.c.belge_id)
    ).scalars()
    return tuple(int(i) for i in idler)


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
    burada yalnız boş olmayan kısa metin olarak saklanır. ``tamlik`` zorunlu
    (karar 2026-09-17); eksikse ``GIRDI_GECERSIZ`` ve okuma açılmaz.
    """
    simdi = simdi or sz.simdi_utc()
    sema_surumu = _sema_surumunu_dogrula(sema_surumu)
    icerik_json = _icerigi_dogrula(icerik)
    if tamlik is None:
        raise sz.GirdiGecersiz(
            "tamlık zorunlu: beş alanın her biri DEGER, BELGEDE_YOK ya da "
            "OKUNAMADI olarak bildirilmeli",
            alan="tamlik",
        )
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
        yazilan_idleri, mevcut_idleri = _satirlari_kabul_et(oturum, okuma_id, hazir)
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
        yazilan=satirlari_getir(oturum, [int(k) for k in sonuc["yazilan_idleri"]]),
        zaten_mevcut=satirlari_getir(oturum, [int(k) for k in sonuc["mevcut_idleri"]]),
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

    Koşullar sağlanmazsa (satır sonuçlanmamış ya da tamlık alanı OKUNAMADI →
    ``BELGE_HAZIR_DEGIL``, satır sayısı ya da toplamlar tutmuyor →
    ``MUTABAKAT_FARKI``) hata verilir ve hiçbir durum değişmez: okuma ``ACIK``
    kalır, eksik satırlar gönderilebilir. ``tamlik`` isteğe bağlıdır;
    verilirse beş alanın tamamı yeniden verilir ve okumadakinin yerine geçer.
    """
    simdi = simdi or sz.simdi_utc()
    tamlik_json = _tamligi_dogrula(tamlik) if tamlik is not None else None
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
    atlanan = _kayit_kosullarini_denetle(oturum, okuma_id, okuma.tamlik)
    gerekce = f"etkin okuma {okuma_id}"
    if atlanan:
        gerekce += "; atlanan denetimler: " + "; ".join(atlanan)
    return _belge_durumunu_degistir(
        oturum,
        belge,
        sz.BelgeDurumu.KAYITLI,
        eylem=EYLEM_BELGE_KAYDET,
        aktor=sz.DenetimAktoru.UYGULAMA,
        simdi=simdi,
        islem_id=islem_id,
        gerekce=gerekce,
        etkin_okuma_id=okuma_id,
    )


def _kayit_kosullarini_denetle(
    oturum: Session, okuma_id: int, tamlik: Tamlik
) -> list[str]:
    """C07 koşulları; döndürdüğü liste BELGEDE_YOK yüzünden atlanan denetimlerdir.

    Sıra: her satır sonuçlanmış; hiçbir tamlık alanı ``OKUNAMADI`` değil
    (belge kayıtlı olamaz); satır sayısı ``DEGER`` ise yazılanla aynı; sonra
    toplamlar (``_toplamlari_denetle``).
    """
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
    for alan, _ in TAMLIK_ALANLARI:
        if getattr(tamlik, alan).durum is sz.TamlikDurumu.OKUNAMADI:
            raise sz.BelgeHazirDegil(
                f"{alan} belgede var ama güvenle okunamadı; belgeyi yeniden oku "
                "ve tamlığı yeniden bildir",
                alan=alan,
            )
    satir_sayisi = tamlik.beklenen_satir_sayisi
    if satir_sayisi.durum is sz.TamlikDurumu.DEGER and satir_sayisi.deger != toplam:
        raise sz.MutabakatFarki(
            f"beklenen satır sayısı {satir_sayisi.deger}, yazılan {toplam}; eksik "
            "ya da fazla satırı çöz",
            alan="beklenen_satir_sayisi",
        )
    return _toplamlari_denetle(oturum, okuma_id, tamlik)


def _toplamlari_denetle(oturum: Session, okuma_id: int, tamlik: Tamlik) -> list[str]:
    """Tamlıkta verilen toplamlar yazılan satırlarla tutmalı (karar 2026-09-17).

    Üç denetim: toplam giriş = yazılan ARTTIR toplamı; toplam çıkış = yazılan
    AZALT toplamı; açılış + giriş − çıkış = kapanış (giriş/çıkış yazılan
    satırlardan). ``DEGER`` olmayan alanın denetimi atlanır ve döndürülen
    listeye yazılır (``OKUNAMADI`` buraya gelmez, önce reddedilir). Belgenin
    söylediği yazılır, aritmetiği uygulama denetler; tutmuyorsa
    ``MUTABAKAT_FARKI`` ve belge kayıtlı olmaz.
    """
    e, k, kk, os_ = sema.etki, sema.kayit, sema.kayit_kaynak, sema.okuma_satir
    bu_okumadan = (
        select(kk.c.id)
        .select_from(kk.join(os_, os_.c.id == kk.c.okuma_satir_id))
        .where(
            kk.c.kayit_id == e.c.kayit_id,
            kk.c.durum == sz.KaynakDurumu.AKTIF.value,
            os_.c.okuma_id == okuma_id,
        )
        .exists()
    )
    arttir = func.coalesce(
        func.sum(case((e.c.yon == sz.Yon.ARTTIR.value, e.c.tutar_kurus), else_=0)), 0
    )
    azalt = func.coalesce(
        func.sum(case((e.c.yon == sz.Yon.AZALT.value, e.c.tutar_kurus), else_=0)), 0
    )
    satir = oturum.execute(
        select(arttir, azalt)
        .select_from(e.join(k, k.c.id == e.c.kayit_id))
        .where(k.c.durum == sz.KayitDurumu.AKTIF.value, bu_okumadan)
    ).one()
    giris, cikis = int(satir[0]), int(satir[1])
    atlanan: list[str] = []
    deger = sz.TamlikDurumu.DEGER

    t_giris, t_cikis = tamlik.toplam_giris_kurus, tamlik.toplam_cikis_kurus
    if t_giris.durum is deger:
        if t_giris.deger != giris:
            raise sz.MutabakatFarki(
                f"verilen toplam giriş {t_giris.deger} kuruş, yazılan satırların "
                f"girişi {giris}; toplamı belgeden aynen al ya da eksik satırı çöz",
                alan="toplam_giris_kurus",
            )
    else:
        atlanan.append(f"toplam_giris_kurus {t_giris.durum.value}")
    if t_cikis.durum is deger:
        if t_cikis.deger != cikis:
            raise sz.MutabakatFarki(
                f"verilen toplam çıkış {t_cikis.deger} kuruş, yazılan satırların "
                f"çıkışı {cikis}; toplamı belgeden aynen al ya da eksik satırı çöz",
                alan="toplam_cikis_kurus",
            )
    else:
        atlanan.append(f"toplam_cikis_kurus {t_cikis.durum.value}")

    acilis, kapanis = tamlik.acilis_bakiyesi_kurus, tamlik.kapanis_bakiyesi_kurus
    if acilis.durum is deger and kapanis.durum is deger:
        beklenen_kapanis = (acilis.deger or 0) + giris - cikis
        if beklenen_kapanis != kapanis.deger:
            raise sz.MutabakatFarki(
                f"açılış {acilis.deger} + giriş {giris} − çıkış {cikis} = "
                f"{beklenen_kapanis} kuruş, verilen kapanış {kapanis.deger}; eksik "
                "ya da fazla satırı çöz",
                alan="kapanis_bakiyesi_kurus",
            )
    else:
        eksikler = ", ".join(
            f"{ad} {a.durum.value}"
            for ad, a in (
                ("acilis_bakiyesi_kurus", acilis),
                ("kapanis_bakiyesi_kurus", kapanis),
            )
            if a.durum is not deger
        )
        atlanan.append(f"kapanış eşitliği ({eksikler})")
    return atlanan


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


# --- satır kabulü (çekirdek) ------------------------------------------------------


@dataclass(frozen=True, slots=True)
class KabulSonucu:
    yazilan_idleri: tuple[int, ...]
    mevcut_idleri: tuple[int, ...]


def satirlari_kabul_et(
    oturum: Session, *, okuma_id: int, satirlar: Sequence[SatirGirdisi]
) -> KabulSonucu:
    """Gönderim çekirdeği: paket doğrulanır ve ``ACIK`` okumaya yazılır (K07).

    İşlem anahtarı ve denetim olayı çağıranındır (``satir_gonder`` ya da
    ``kayitlar.hareket_yaz``); bu işlev yalnız satırları yazar. Aynı anahtar
    aynı içerikle varsa kimliği ``mevcut_idleri``ne girer, farklı içerik
    ``ANAHTAR_ICERIK_CAKISMASI``.
    """
    hazir = _satirlari_dogrula(satirlar)
    yazilan, mevcut = _satirlari_kabul_et(oturum, okuma_id, hazir)
    return KabulSonucu(tuple(yazilan), tuple(mevcut))


def _satirlari_kabul_et(
    oturum: Session, okuma_id: int, hazir: Sequence[_HazirSatir]
) -> tuple[list[int], list[int]]:
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
    return yazilan_idleri, mevcut_idleri


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


def _tamligi_dogrula(tamlik: Tamlik) -> dict[str, dict[str, Any]]:
    """Beş alanın her biri var, durumu geçerli, değeri durumuyla tutarlı.

    ``DEGER`` → tam sayı (bool değil), negatif yalnız bakiyelerde;
    ``BELGEDE_YOK`` / ``OKUNAMADI`` → değer verilemez; satır sayısı
    ``BELGEDE_YOK`` olamaz. JSON'a yazılacak biçimi döndürür.
    """
    sonuc: dict[str, dict[str, Any]] = {}
    for alan, negatif_olabilir in TAMLIK_ALANLARI:
        a = getattr(tamlik, alan, None)
        if not isinstance(a, TamlikAlani):
            raise sz.GirdiGecersiz(
                "tamlık alanı eksik; DEGER, BELGEDE_YOK ya da OKUNAMADI bildir",
                alan=alan,
            )
        try:
            durum = sz.TamlikDurumu(a.durum)
        except ValueError:
            raise sz.GirdiGecersiz(
                "tamlık durumu DEGER, BELGEDE_YOK ya da OKUNAMADI olmalı", alan=alan
            ) from None
        if durum is sz.TamlikDurumu.DEGER:
            deger = a.deger
            if type(deger) is not int or (deger < 0 and not negatif_olabilir):
                raise sz.GirdiGecersiz(
                    "tamlık alanı DEGER ise tam sayı olmalı"
                    + ("" if negatif_olabilir else " ve negatif olamaz"),
                    alan=alan,
                )
            sonuc[alan] = {"durum": durum.value, "deger": deger}
            continue
        if a.deger is not None:
            raise sz.GirdiGecersiz(
                f"{durum.value} ile değer verilemez; sayı biliniyorsa DEGER de",
                alan=alan,
            )
        if alan == "beklenen_satir_sayisi" and durum is sz.TamlikDurumu.BELGEDE_YOK:
            raise sz.GirdiGecersiz(
                "satır sayısı belgede yok olamaz: gördüğün hareketleri say; "
                "sayamıyorsan OKUNAMADI bildir",
                alan=alan,
            )
        sonuc[alan] = {"durum": durum.value, "deger": None}
    return sonuc


def _kanonik(deger: Any) -> str:
    return json.dumps(deger, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


# --- satır dönüştürücüler ------------------------------------------------------


def satirlari_getir(oturum: Session, idler: Sequence[int]) -> tuple[OkumaSatiri, ...]:
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
        uzanti=str(satir["uzanti"]),
        kaynak_adi=str(satir["kaynak_adi"]),
        goreli_yol=str(satir["goreli_yol"]),
        olusturma_zamani=satir["olusturma_zamani"],
    )


def _okuma(satir: RowMapping) -> Okuma:
    ham: dict[str, dict[str, Any]] = dict(satir["tamlik"])
    tamlik = Tamlik(
        **{
            alan: TamlikAlani(sz.TamlikDurumu(ham[alan]["durum"]), ham[alan]["deger"])
            for alan, _ in TAMLIK_ALANLARI
        }
    )
    return Okuma(
        id=int(satir["id"]),
        belge_id=int(satir["belge_id"]),
        surum_no=int(satir["surum_no"]),
        sema_surumu=str(satir["sema_surumu"]),
        icerik=dict(satir["icerik"]) if satir["icerik"] is not None else None,
        tamlik=tamlik,
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

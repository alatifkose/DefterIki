"""Pencerenin çağırdığı işlevler (Aşama 6; K20).

Katman sırası: pencere → bu modül → Aşama 4 işlevleri ve veritabanı. Pencere
``veritabani`` modülünü import etmez, oturum açmaz, SQL bilmez; buradaki
işlevlere düz sorular sorar ("veri değişti mi?") ve düz cevaplar alır.
Veritabanı nesnesini bu modül tutar ve kapatır.

Teslim 6.1: değişiklik algılama. 6.2 karar kutusu (bekleyen talepler, talep
ayrıntısı, karar), 6.3 bakiye ve hareket listesi işlevleri buraya eklenir;
hepsi ``onaylar``, ``nesneler``, ``hesaplamalar`` gibi mevcut işlevleri
çağırır, kural koymaz.
"""

from __future__ import annotations

from defteriki.ayarlar import Ayarlar
from defteriki.veritabani import Veritabani, veritabani_ac


class PencereIslevleri:
    """Tek pencereye ait bağlam; ``pencere_islevleri_ac`` ile kurulur."""

    def __init__(self, veritabani: Veritabani) -> None:
        self._veritabani = veritabani
        self._son_sayac: int | None = None

    def degisti_mi(self) -> bool:
        """Son sorudan bu yana başka bir süreç ya da bağlantı yazdı mı?

        İlk soru başlangıç noktasını alır ve ``False`` döndürür. Yazma kilidi
        tutmaz; Cowork'un ya da onay komutunun yazmasını geciktirmez.
        """
        sayac = self._veritabani.degisiklik_sayaci()
        degisti = self._son_sayac is not None and sayac != self._son_sayac
        self._son_sayac = sayac
        return degisti

    def kapat(self) -> None:
        self._veritabani.kapat()


def pencere_islevleri_ac(ayarlar: Ayarlar) -> PencereIslevleri:
    """Ayarlardaki veritabanı için pencere işlevlerini kurar; dosya oluşturmaz."""
    return PencereIslevleri(veritabani_ac(ayarlar))

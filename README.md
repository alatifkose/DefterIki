# DEFTERIKI

Belge tabanlı kişisel finans uygulaması. Yerel çalışır, verisi tek bir SQLite dosyasında
durur; kayıtlar arşivlenmiş bir kaynak belgeye bağlıdır.

Bugün Cowork (MCP, stdio) ve bir PySide6 masaüstü arayüzü üzerinden kullanılacak şekilde
tasarlanıyor; iş kuralları ikisinden de bağımsız bir çekirdekte toplanır.

## Durum

**İnşaya hazır iskelet.** 8 Eylül 2026'da inşadan önce verilmesi gereken kararlar
alındı (K-006..K-009): belge tek doğruluk kaynağı, veri sözleşmesi (para/tarih/kimlik/
yaşam durumu), katmanlı düzen ve başlangıç konusu olarak **hesap ekstresi**. Aynı gün
teknik hazırlık tamamlandı: veritabanı motoru tek modülde (WAL, yabancı anahtar,
meşgul bekleme, `synchronous=NORMAL`), model tabanı ve kısıt adlandırma kuralı, Alembic
batch modu, gerçek göçlerle açılan test fikstürü, "göç = model" testi ve katman kuralını
zorlayan test.
Aynı gün inceleme sonrası üç karar daha alındı: belgeyi AI okur, determinizm doğrulama ve
kayıt katmanında aranır (K-010); belge arşivi yolu da ayarların tek sahipliğinde (K-011,
kodda ve testte); her `CheckConstraint` adlıdır (K-012, testle zorlanır). Alan modeli henüz
yok; sıradaki iş hesap ekstresi (K-009). İnşa öncesi inceleme (aynı gün) kodu temiz buldu;
`uq`/`fk` kısıt adları ilk göçten önce tüm sütunlardan türeyecek biçimde sabitlendi. Açık
kararlar: A-004 (iki konuya değen kural nereye yazılır, ilk örnekte), A-006 (aynı hareketin
iki belgede görünmesi) ve A-007 (ürün modellerinin metadata kaydı, ilk modelle birlikte
çözülür). A-008 (satır bazında sahiplik) bilinçli ertelendi: ilk sürümde dosyanın sahibi
kullanıcıdır.
İkinci inşa öncesi inceleme (aynı gün) iki hata düzeltti: test fikstürü artık belge arşivini
de geçici dizine yönlendiriyor (B-008), `busy_timeout` ilk pragma (B-009). İki açık madde
daha: loglama ilk gerçek kullanımdan önce (A-009), AI okumasının saklanma biçimi ilk belge
modeliyle (A-010). Temel kat önceden doldurulmaz, hesap ekstresiyle birlikte ihtiyaç
oldukça büyür.
Üçüncü inceleme (aynı gün) kodu temiz buldu, üç küçük belge/test tutarsızlığı düzeltti ve
A-010'u kapattı: AI okuması veritabanında JSON metin sütununda saklanır (K-013), kayıtlar
okumayla aynı işlemde yazılır, arşivde yalnız orijinal belge durur; reddedilen okuma da
REDDEDILDI durumuyla saklanır, kayıt türetilmez (K-013 ek). Sıradaki adım: anonim hesap
ekstresi örneği ve okuma modeli.

Bu bölüm proje ilerledikçe güncellenir; okuyan kişi buraya bakıp nerede olunduğunu
görebilmelidir.

## Teknoloji yığını

| Alan | Seçim |
|---|---|
| Dil / paket yöneticisi | Python 3.13, uv |
| Veritabanı | SQLite (WAL), veritabanına özgü özellik kullanılmaz |
| ORM / şema göçü | SQLAlchemy 2.x, Alembic (ilk günden) |
| Belge okuma | Cowork/AI okur, program doğrular ve okumayı saklar (K-010) |
| Doğrulama | Pydantic v2 — MCP girdileri ile servis girdileri aynı modeller |
| Arayüz | FastMCP (stdio) + PySide6 masaüstü, koyu tema |
| Para | Kuruş tamsayı; girişte `Decimal`, `float` yok |
| Test | pytest + Hypothesis |
| Kalite | ruff, pyright (strict), pre-commit |

Gerekçeler ve reddedilen alternatifler `KARARLAR.md` içindedir. FastMCP ve PySide6 karar
verilmiş ama henüz bağımlılık olarak eklenmemiştir; sırası geldiğinde eklenir.

## Kurulum

```powershell
uv sync
uv run pre-commit install
```

İkinci komut commit kancasını kurar (ruff, ruff format, pyright); temiz bir klonda kanca
kendiliğinden gelmez. Depo `C:\dev\DefterIki` altında, bulut senkronu yapılan bir klasörün **dışında** tutulur;
yedek GitHub'dadır (K-005). Git ile OneDrive aynı klasörde iyi geçinmez.

## Komutlar

Test:

```powershell
uv run pytest
```

Lint ve biçim (`alembic/` dahil, pre-commit ile aynı kapsam):

```powershell
uv run ruff check .
uv run ruff format --check .
```

Tip denetimi (strict; `src`, `tests` ve `alembic`):

```powershell
uv run pyright
```

Şema göçü (henüz migration yok; veritabanını aşağıdaki "Veri konumu" yoluna kurar):

```powershell
uv run alembic upgrade head
```

## Veri konumu

| Ne | Nerede |
|---|---|
| Canlı veritabanı | `%LOCALAPPDATA%\DefterIki\defteriki.sqlite3` |
| Belge arşivi | `%LOCALAPPDATA%\DefterIki\belgeler\` |

Veritabanı yolu `DEFTERIKI_VERITABANI`, arşiv dizini `DEFTERIKI_BELGE_ARSIVI` ortam
değişkeniyle ayrı ayrı değiştirilebilir; testler bunu kullanır. Windows dışında (CI, Linux
kabuğu) XDG karşılığına düşer.

İki yolun da **tek sahibi** `src/defteriki/ayarlar.py` modülüdür (K-004, K-011);
`alembic.ini` içindeki `sqlalchemy.url` bu yüzden bilerek boştur ve `alembic/env.py`
adresi ayarlardan alır. Veri dizini OneDrive'ın içine konmaz: bulut senkronu ile SQLite'ın
WAL dosyaları birlikte veri bozulmasına yol açar.

## Klasör düzeni

| Yol | İçerik |
|---|---|
| `src/defteriki/ayarlar.py` | Yol ve ortam kararları (veritabanı, belge arşivi); en alt kat |
| `src/defteriki/cekirdek/temel/` | Veritabanı motoru (`veritabani.py`), model tabanı (`model.py`) |
| `src/defteriki/cekirdek/urunler/` | Hesaplar, kartlar, krediler... (henüz yok; her ürün ayrı alt paket) |
| `src/defteriki/cekirdek/yorum/` | Eşleştirme, giderler, işleme, raporlar (henüz yok) |
| `src/defteriki/mcp/`, `arayuz/` | Cowork kapısı ve masaüstü (henüz yok) |
| `tests/` | Testler; `conftest.py` her teste geçici veri dizini verir (veritabanı + arşiv) ve şemayı gerçek göçlerle kurar |
| `alembic/` | Şema göçleri (`versions/` bugün boş) |
| `KARARLAR.md` | Mimari karar defteri: karar, gerekçe, reddedilen alternatif |
| `BULGULAR.md` | Çalışma sırasında çıkan sorunlar ve durumları |

## Çalışma kuralları

- **Karar defteri sohbetten üstündür.** Bir mimari karar `KARARLAR.md` içinde yazılı
  değilse verilmemiş sayılır.
- **Açık madde kovasız bırakılmaz:** yapılacak / şimdilik kabul / yapılmayacak.
- **Python kodu içeren commit'ler Windows tarafından alınır.** Cowork'ün kabuğunda
  pre-commit kancası çalışmıyor (bkz. `BULGULAR.md` B-003); oradan yalnız belge/metin
  dosyaları `--no-verify` ile commit'lenir.
- Depoda ve çalışma kopyasında satır sonu **LF**, kodlama **UTF-8** (K-003).
- **Bağımlılık tek yöne akar** (K-008): ayarlar → temel → urunler → yorum → mcp/arayuz.
  Ürünler birbirini tanımaz, fonksiyon içinde `import` yok. `tests/test_katmanlar.py`
  zorlar; yeni paket açılınca oradaki `KATLAR` haritasına eklenir.
- **Model değişikliği göçüyle gelir.** Testler şemayı Alembic ile kurar, `create_all`
  kullanılmaz; `tests/test_gocler.py` head şeması ile modelleri karşılaştırır.
- **`create_engine` paket içinde yalnız `cekirdek/temel/veritabani.py`'de** çağrılır; SQLite
  pragmaları oradan gelir (WAL, `foreign_keys=ON`, `busy_timeout`, `synchronous=NORMAL`:
  WAL ile birlikte güvenli, her commit'te disk senkronu beklemez). Tek bilinçli istisna
  `alembic/env.py`: göç sırasında yabancı anahtar kapalı kalmalı, bu yüzden Alembic
  motorunu pragmasız kendisi kurar (K-004 ek). İki kural da testle korunur.
- **Her `CheckConstraint` adlıdır** (K-012): `name=` verilmeden yazılmaz; adsız kısıt
  SQLAlchemy'de tanım anında hata verir. Diğer kısıtlar adını `model.py` kuralından alır;
  `uq` ve `fk` adları kısıttaki **tüm** sütunlardan türer (`column_0_N_name`), ilk sütunu
  paylaşan iki kısıt çakışmaz.
- **Belge AI tarafından okunur, program doğrular** (K-010): okuma Pydantic ile doğrulanır,
  veritabanında JSON metin sütununda saklanır (K-013); kayıtlar saklı okumadan türer ve
  okumayla aynı işlemde yazılır. Yeniden işleme AI'ya yeniden sormak değildir.

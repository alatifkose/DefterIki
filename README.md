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
meşgul bekleme), model tabanı ve kısıt adlandırma kuralı, Alembic batch modu, gerçek
göçlerle açılan test fikstürü, "göç = model" testi ve katman kuralını zorlayan test.
Alan modeli henüz yok; sıradaki iş hesap ekstresi (K-009). Açıkta kalan tek karar
A-006 (aynı hareketin iki belgede görünmesi).

Bu bölüm proje ilerledikçe güncellenir; okuyan kişi buraya bakıp nerede olunduğunu
görebilmelidir.

## Teknoloji yığını

| Alan | Seçim |
|---|---|
| Dil / paket yöneticisi | Python 3.13, uv |
| Veritabanı | SQLite (WAL), veritabanına özgü özellik kullanılmaz |
| ORM / şema göçü | SQLAlchemy 2.x, Alembic (ilk günden) |
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
```

Depo `C:\dev\DefterIki` altında, bulut senkronu yapılan bir klasörün **dışında** tutulur;
yedek GitHub'dadır (K-005). Git ile OneDrive aynı klasörde iyi geçinmez.

## Komutlar

Test:

```powershell
uv run pytest
```

Lint ve biçim:

```powershell
uv run ruff check src tests
```

Tip denetimi (strict):

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

Yol `DEFTERIKI_VERITABANI` ortam değişkeniyle değiştirilebilir; testler bunu kullanır.
Windows dışında (CI, Linux kabuğu) XDG karşılığına düşer.

Yolun **tek sahibi** `src/defteriki/ayarlar.py` modülüdür; `alembic.ini` içindeki
`sqlalchemy.url` bu yüzden bilerek boştur ve `alembic/env.py` adresi ayarlardan alır
(K-004). Canlı veritabanı OneDrive'ın içine konmaz: bulut senkronu ile SQLite'ın WAL
dosyaları birlikte veri bozulmasına yol açar.

## Klasör düzeni

| Yol | İçerik |
|---|---|
| `src/defteriki/ayarlar.py` | Yol ve ortam kararları; en alt kat |
| `src/defteriki/cekirdek/temel/` | Veritabanı motoru (`veritabani.py`), model tabanı (`model.py`) |
| `src/defteriki/cekirdek/urunler/` | Hesaplar, kartlar, krediler... (henüz yok; her ürün ayrı alt paket) |
| `src/defteriki/cekirdek/yorum/` | Eşleştirme, giderler, işleme, raporlar (henüz yok) |
| `src/defteriki/mcp/`, `arayuz/` | Cowork kapısı ve masaüstü (henüz yok) |
| `tests/` | Testler; `conftest.py` geçici veritabanını gerçek göçlerle açar |
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
- **`create_engine` yalnız `cekirdek/temel/veritabani.py` içinde** çağrılır; SQLite
  pragmaları oradan gelir.

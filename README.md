# DEFTERIKI

Belge tabanlı kişisel finans uygulaması. Yerel çalışır, verisi tek bir SQLite dosyasında
durur; kayıtlar arşivlenmiş bir kaynak belgeye bağlıdır.

Bugün Cowork (MCP, stdio) ve bir PySide6 masaüstü arayüzü üzerinden kullanılacak şekilde
tasarlanıyor; iş kuralları ikisinden de bağımsız bir çekirdekte toplanır.

## Durum

**İskelet aşaması.** Altyapı kurulu ve kalite kapıları çalışıyor; uygulama mantığı henüz
yazılmadı. Bugün depoda olan: paket iskeleti, Alembic kurulumu (henüz migration yok),
test/lint/tip denetimi zinciri ve karar/bulgu defterleri.

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

Şema göçü (henüz migration yok):

```powershell
uv run alembic upgrade head
```

## Klasör düzeni

| Yol | İçerik |
|---|---|
| `src/defteriki/` | Uygulama paketi |
| `tests/` | Testler |
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

# DEFTERIKI

## Teknoloji

Bu projede kullanılacak teknoloji. Mutlak değil; ihtiyaç duyulması halinde değişebilir.

* Python 3.13 — ana dil
* uv — paket ve sanal ortam yönetimi
* pyproject.toml — proje/bağımlılık tanımı
* uv.lock — bağımlılık kilidi
* SQLite — ilişkisel veritabanı
* WAL — SQLite çalışma/journal modu; ayrı bir teknoloji değil
* SQLAlchemy 2.x — ORM / veritabanı erişimi
* Alembic — migration
* Pydantic 2.x — MCP giriş/çıkış ve veri doğrulama
* MCP Python SDK / FastMCP — Cowork ↔ DEFTERIKI kapısı
* PySide6 — masaüstü GUI için
* pytest — test
* Hypothesis — property-based test
* Ruff — lint + format
* Pyright strict — statik type checking
* pre-commit — commit öncesi kalite kontrolleri
* Git — sürüm kontrolü
* `.gitignore` — DB, WAL/SHM, kişisel veri, cache, secret vb. dışlama
* `.gitattributes` — LF/CRLF standardizasyonu

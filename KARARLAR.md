# DEFTERIKI — KARAR DEFTERİ

Her mimari karar burada tutulur: tarih, karar, gerekçe, reddedilen alternatif ve neden
reddedildiği. Sohbet geçmişi bu dosyadan daha güvenilir sayılmaz.

---

## K-001 — Teknoloji yığını

**Tarih:** 7 Eylül 2026

**Karar:** Python 3.13 / uv; SQLite (WAL), veritabanına özgü özellik kullanılmaz;
SQLAlchemy 2.x; ilk günden Alembic; Pydantic v2 (MCP girdileri ile servis girdileri aynı
modeller); FastMCP (stdio); arayüz PySide6 masaüstü, koyu tema; para kuruş tamsayı, girişte
Decimal, float yok; belge arşivi dosya sistemi + SHA-256; pytest + Hypothesis; ruff, pyright
strict, pre-commit; standart logging dosyaya; git + GitHub. Dağıtım şimdilik yok.

**Gerekçe:** Tek kullanıcıyla gerçek kullanımda olgunlaştırılacak, sonra ürünleştirilecek bir
finans uygulaması için: taşınabilir ve tek dosyalık veritabanı, şema değişikliklerinin ilk
günden izlenebilir olması, parada yuvarlama hatasının imkânsız olması.

**Reddedilen alternatif:** Kayıt yok — karar sohbette verildi, alternatifler yazılmadı.

---

## K-002 — Tek süreç, çekirdek/arayüz sınırı, HTTP katmanı yok

**Tarih:** 7 Eylül 2026

**Karar:** Uygulama tek süreç olarak çalışır. Ayrı bir backend süreci ve HTTP katmanı
şimdilik yoktur. Kodda çekirdek (iş kuralları) ile arayüz (MCP araçları, PySide6 ekranları)
arasında katı bir sınır bulunur; iş kuralları yalnızca çekirdekte tanımlanır ve her arayüz
aynı kapıdan geçer.

**Gerekçe:** Uygulamayı bugün Cowork (MCP, stdio) işletecek; ürünleşince Claude API
girecek. Kurallar tek yerde durursa yeni arayüz eklemek çekirdeği değiştirmez. Tek
kullanıcılı masaüstü kullanım için ağ katmanı bugün hiçbir sorunu çözmüyor.

**Reddedilen alternatif:** Ayrı backend süreci + HTTP API. Bugün ihtiyaç yok; süreç yönetimi,
kimlik doğrulama ve dağıtım maliyeti getiriyor. Çekirdek/arayüz sınırı korunduğu sürece
ileride HTTP katmanı çekirdeğin üstüne eklenebilir; bu karar o kapıyı kapatmıyor.

---

## K-003 — Satır sonu ve dosya kodlaması

**Tarih:** 8 Eylül 2026

**Karar:** Depoda ve çalışma kopyasında tüm metin dosyaları LF satır sonu kullanır.
`.gitattributes` içinde `* text=auto eol=lf`; ikili uzantılar (`.db`, `.png`, `.jpg`, `.pdf`)
binary olarak işaretlidir. Kodlama UTF-8.

**Gerekçe:** Windows'ta çalışıldığı için dosyalar CRLF'e dönüşüyor ve içerik değişmediği
hâlde git dosyanın tamamını "değişmiş" gösteriyordu. Bu hâliyle gerçek değişiklik diff'te
görünmez, gözden geçirme imkânsızlaşır.

**Reddedilen alternatif:** `core.autocrlf=true` (yerel git ayarı). Ayar makineye bağlı; depoda
saklanmadığı için başka bir makinede veya yeni kurulumda sorun geri geliyor. `.gitattributes`
depoyla birlikte taşınır.

---

## K-004 — Veritabanı yolunun tek sahibi `ayarlar` modülüdür

**Tarih:** 8 Eylül 2026

**Karar:** Canlı veritabanının yeri yalnızca `src/defteriki/ayarlar.py` içinde tanımlanır.
`alembic.ini` içindeki `sqlalchemy.url` **boş bırakılır**; `alembic/env.py` adresi
`ayarlar.veritabani_url()` ile alır ve motoru kendisi kurar. Varsayılan konum
`%LOCALAPPDATA%\DefterIki\defteriki.sqlite3`, Windows dışında XDG karşılığıdır; yol
`DEFTERIKI_VERITABANI` ortam değişkeniyle ezilebilir (testler bunu kullanır). Yol her
zaman mutlaktır ve adres POSIX ayracıyla yazılır.

**Gerekçe:** Üç ayrı sorun aynı satırdan doğuyordu (`sqlalchemy.url = sqlite:///defteriki.db`):

1. *Yol göreliydi.* Çalışma dizinine göre çözüldüğü için masaüstü kısayolu, MCP süreci ve
   `pytest` üç farklı veritabanı dosyasıyla çalışabilirdi. Defter'de tam bu nedenle MCP
   sunucusu ile uygulama ayrı yedek kümesi oluşturmuştu.
2. *İki doğruluk kaynağı doğacaktı.* `alembic.ini` bir adres, uygulama motoru başka bir
   adres bilecekti; bugün aynı olan bu iki değer ilerde ayrışır ve göç bir dosyaya,
   uygulama başka dosyaya yazar — üstelik sessizce.
3. *Dosya OneDrive'ın içindeydi.* Depo kökündeki `defteriki.db`, bulut senkronu ile
   SQLite'ın WAL dosyalarını yan yana getiriyordu; bu bilinen bir veri bozulması yoludur.

**Reddedilen alternatifler:**
- *`alembic.ini` olduğu gibi kalsın, yalnız elle `alembic` çağrıları için kullanılsın;
  uygulama kendi yolunu hesaplasın.* İki kaynak sorununu (2) doğrudan doğurur.
- *Ortam değişkeni tek kaynak olsun.* Değişken tanımsızken yine bir varsayılan gerekir ve o
  varsayılan zaten kodda olmak zorundadır; bu, seçilen çözümün daha zayıf hâlidir. Değişken
  ezme yolu olarak korundu.

**Nasıl korunuyor:** `tests/test_alembic_yolu.py` gerçek bir `alembic upgrade head` koşturur;
göçün ortam değişkeninin gösterdiği dosyaya yazdığını, çalışma dizininden bağımsız olduğunu
ve depo köküne hiçbir veritabanı dosyası düşmediğini doğrular. `alembic.ini` içindeki adresin
boş kaldığı da sınanır. Kural bozulduğunda üç test birden kırılır (mutasyonla doğrulandı).

---

## Açık maddeler

Her açık madde üç kovadan birine girer: **yapılacak / şimdilik kabul / yapılmayacak.**
Kovasız açık madde bırakılmaz.

| # | Madde | Kova | Not |
|---|-------|------|-----|
| A-001 | pre-commit kancaları Cowork'ün kabuğundan çalışmıyor | şimdilik kabul | Kod commit'leri Windows tarafından alınır; bkz. `BULGULAR.md` B-003 |

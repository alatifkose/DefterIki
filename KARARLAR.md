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
girecek. Kurallar tek yerde durursa yeni arayüz eklemek çekirdeği değiştirmez. Ürün çok
kullanıcılı hedeflense de (bireyler ve şirketler) uygulama bugün tek süreç, tek SQLite
dosyasıyla ve tek kullanıcı tarafından işletiliyor; ağ katmanı bu aşamada hiçbir sorunu
çözmüyor. *(Gerekçe 8 Eylül 2026'da düzeltildi: önceki metin "tek kullanıcılı masaüstü"
varsayımı taşıyordu; karar değişmedi.)*

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

*Not (8 Eylül 2026):* Bu makinede Git for Windows'un sistem yapılandırması
(`C:\Program Files\Git\etc\gitconfig`) `core.autocrlf=true` taşıyor. `.gitattributes`
içindeki `eol=lf` bu ayarı ezer; çalışma kopyası LF kalır (doğrulandı). Ayar bilerek
bırakıldı: sistem geneli ve bu depoya özgü değil; kaldırmak yönetici hakkı ister ve başka
depoları etkiler. Karar için gereken tek şey `.gitattributes`tır.

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

*Ek (8 Eylül 2026):* `env.py` motoru `veritabani.motor_kur` ile değil, doğrudan
`create_engine` ile ve **pragmasız** kurar; bu, "create_engine yalnız `veritabani.py`
içinde" kuralının tek bilinçli istisnasıdır. Sebep: `motor_kur` her bağlantıda
`foreign_keys=ON` açar; SQLite batch modu tabloyu düşürüp yeniden kurarken yabancı anahtar
açıksa bağlı satırlar `ON DELETE` kurallarıyla silinebilir ya da göç kısıt hatasıyla durur.
Göç, SQLite varsayılanında (yabancı anahtar kapalı) koşar; WAL ve meşgul bekleme uygulama
motoruyla gelir. İstisna `tests/test_gocler.py`, kural `tests/test_veritabani.py` ile korunur.

**Nasıl korunuyor:** `tests/test_alembic_yolu.py` gerçek bir `alembic upgrade head` koşturur;
göçün ortam değişkeninin gösterdiği dosyaya yazdığını, çalışma dizininden bağımsız olduğunu
ve depo köküne hiçbir veritabanı dosyası düşmediğini doğrular. `alembic.ini` içindeki adresin
boş kaldığı da sınanır. Kural bozulduğunda üç test birden kırılır (mutasyonla doğrulandı).

---

## K-005 — Depo OneDrive dışında, yedek GitHub'da

**Tarih:** 8 Eylül 2026

**Karar:** Depo `C:\dev\DefterIki` altında tutulur; OneDrive'ın (ve genel olarak bulut
senkronu yapılan bir klasörün) içinde bulunmaz. Yedekleme GitHub üzerinden yapılır:
`https://github.com/alatifkose/DefterIki` (public), `origin/main` izlenir.

**Gerekçe:** Depo `OneDrive\Masaüstü\DefterIki` altındaydı. Ölçüm: OneDrive'ın
senkronladığı 7.822 dosyanın (108 MB) neredeyse tamamı `.venv` ve önbelleklerdi; gerçek
proje 19 izlenen dosyaydı.

1. *`.git` bozulma riski.* Git; index, ref ve paket dosyalarını sürekli yazıp siler.
   OneDrive aynı dosyaları kilitleyip yüklerken çakışırsa git işlemleri takılır, daha
   kötüsü bulut bir dosyanın eski sürümünü geri getirip depoyu tutarsız bırakabilir.
   B-002'deki `.git` artık dosyası birikmesi bu ailedendi.
2. *Günlük maliyet.* `.gitignore` OneDrive'ı ilgilendirmez; her `uv sync` sonrası binlerce
   dosya yeniden senkronlanıyordu.
3. *Files On-Demand.* OneDrive dosyaları "yalnız çevrimiçi"ye çevirebilir; okuma anında
   indirme tetiklenir ve araçlar anlaşılmaz hatalarla düşer.
4. *ASCII olmayan yol.* `Masaüstü` içindeki `ü`, pre-commit kancasının içine bozuk
   kodlanmış olarak yazılmıştı. Yeni yolda bu sorun kendiliğinden ortadan kalktı.

Sıra önemliydi: taşımadan **önce** GitHub deposu açıldı; aksi hâlde tek yedek olan
OneDrive kopyası kaldırılınca proje yedeksiz kalırdı.

**Reddedilen alternatifler:**
- *Depo yerinde kalsın, OneDrive ayarından `.venv` senkron dışı bırakılsın.* Yalnız
  günlük maliyeti (2) çözer; asıl risk olan `.git` bozulmasını (1) olduğu gibi bırakır.
- *Yedek olarak OneDrive yeterlidir, GitHub'a gerek yok.* Git zaten sürümlü ve tarihçeli
  bir yedektir; OneDrive ise çakışma çözmeyi kullanıcıya bırakır ve `.git` ile birlikte
  çalışırken sorunun kaynağıdır.

**Not:** Taşıma sonrası `.venv` `uv sync` ile, pre-commit kancası `pre-commit install` ile
yeniden kuruldu; 13 test, ruff ve pyright yeni konumda doğrulandı.

---

## K-006 — Belge tek doğruluk kaynağıdır; kayıt belgeden türetilir

**Tarih:** 8 Eylül 2026

**Karar:** Finansal kayıtlar belgeden türetilir ve elle değiştirilmez. Bir kayıt yanlış
çıkarsa iki yol vardır: okuma kuralı düzeltilip belge **yeniden işlenir**, ya da kaydın
yanına ayrı bir düzeltme notu eklenir. Belge her zaman yeniden işlenebilir olmalıdır; aynı
belge aynı kuralla işlenince aynı kayıtlar çıkar. Aynı dosya (aynı SHA-256) ikinci kez
yüklenirse reddedilir.

*Ek (8 Eylül 2026):* Belgeyi program değil AI okuyacağı için "aynı belge aynı kuralla aynı
kayıtları çıkarır" cümlesi okuma adımı için geçerli değildir; determinizm doğrulama ve
kayıt katmanında aranır. Bkz. K-010.

**Gerekçe:** Yanlış kuralla yazılmış veriyi geri almak, kodu geri almaktan pahalıdır.
Kayıt belgeye bağlı kalırsa geri alma "belgeyi yeniden işle"ye iner; elle veri ameliyatına
gerek kalmaz. A-005 bu kararla kapanır.

**Reddedilen alternatif:** Kayıt ekrandan elle düzeltilir, belge yalnız "buradan geldi"
referansıdır. Defter bunu seçti; kayıtlar belgeden koptu, geri alma her modülün içini
tanımak zorunda kaldı (`belgeler/geri_alma.py`, 49 fonksiyon-içi import).

---

## K-007 — Veri sözleşmesi: para, tarih, kimlik, yaşam durumu

**Tarih:** 8 Eylül 2026

**Karar:**

- *Para.* Tutar kuruş tamsayıdır (K-001). Her tutarın yanında bir **varlık kodu** bulunur
  (TL, USD, gram altın; ileride hisse). Kod yalnız para birimi değil, varlık türüdür:
  yatırım hesapları gelince tabloya dokunulmaz. Giriş/çıkış yönü tutarın işaretiyle değil,
  **ayrı bir yön alanıyla** tutulur; tutar her zaman pozitiftir.
- *Tarih.* Hareketin belgedeki tarihi (gün) zorunludur; saat ayrı ve isteğe bağlı bir
  alandır. Saat, hareketin kendi belgesinde yoksa ama aynı hareketi gösteren başka bir
  belgede varsa (kart ekstresi satırı + fiş) oradan tamamlanır. Kaydın programa girdiği
  an ayrı tutulur; ikisi karıştırılmaz. Tarih ISO metin (`YYYY-MM-DD`), zaman damgaları
  UTC ISO metin olarak saklanır.
- *Kimlik.* Tablo birincil anahtarları tamsayıdır. Belgenin kimliği SHA-256'dır.
  *Ek (8 Eylül 2026):* Ürün hedefi çok kullanıcılı olsa da bu tek başına UUID gerektirmez;
  tamsayı anahtar kararı değişmez. Gerçek bir ihtiyaç doğarsa o gün ayrıca değerlendirilir.
- *Yaşam durumu.* Finansal kayıt fiziksel olarak silinmez. İptal edilebilir varlıklar bir
  yaşam durumu taşır: **AKTIF / IPTAL / YERINI_DEVRETTI**. Belge yeniden işlenince eski
  kayıtlar YERINI_DEVRETTI olur, yenileri AKTIF. Bu alan her tabloya körlemesine
  konmaz; hangi varlığın gerçekten iptal edilebileceği o varlık tanımlanırken ayrıca
  kararlaştırılır ve burada not edilir.

**Gerekçe:** Bu dördü sonradan değiştirilince her tabloya ve eldeki her satıra dokunur.
Para birimi ve yön alanı sonradan eklenemez; tarih biçimi sonradan tekleştirilemez;
"gerçekten sil"den "pasife al"a dönüş Defter'de pahalı olmuştu.

**Reddedilen alternatifler:** İşaretli tek tutar (okurken ve sorgularken hata kaynağı);
yalnız TL (döviz ve altın hesabı var); her tabloya `is_active` (körleme, anlamsız
sütunlar); fiziksel silme (finansal iz kaybolur).

---

## K-008 — Katmanlı düzen: bağımlılık tek yöne akar

**Tarih:** 8 Eylül 2026

**Karar:** Paket üç bölgeye ayrılır: `cekirdek/` (iş kuralları), `mcp/` (Cowork kapısı),
`arayuz/` (masaüstü ekranları). `mcp` ve `arayuz` çekirdeğe sorar; çekirdek onları tanımaz.
Çekirdek kendi içinde üç kata bölünür, aşağıdan yukarı:

1. **temel:** bankalar, belgeler, para/tarih tipleri, veritabanı motoru.
2. **urunler:** hesaplar, kartlar, krediler, KMH. Her ürün yalnız temeli tanır;
   ürünler **birbirini tanımaz**.
3. **yorum:** eşleştirme, giderler, işleme, raporlar. Alttaki katları tanır.

Kural: bir modül yalnız kendi katının altındakileri içe alabilir; aynı kattaki ürünler
birbirine uzanamaz; fonksiyon içi `import` yasaktır. Kural `tests/test_katmanlar.py` ile
korunur; çiğnendiğinde test kırılır. A-003 bu kararla kapanır.

Gerçek hayat ilişkileri bu düzende şöyle durur: kart bankayı tanır (temel), banka kartı
tanımaz; ödeme ile hesap hareketini bağlayan eşleştirme yorum katındadır, hesaplar da
kartlar da ödemeyi bilmez; belge modülü ürünleri tanımaz, her ürünün kendi okuyucusu
belgeyi tanır, "şu belgeyi işle" emrini yorum katındaki işleme modülü verir; gider,
hareketin üstüne yazılan etikettir, giderler kartı tanır, kartlar gideri tanımaz.

**Gerekçe:** Defter'de 12 modülün çoğu 9-12 modül tarafından içe alınıyordu ve karşılıklı
döngüler vardı; 247 fonksiyon-içi import bu döngülerden kaçmak için yazılmıştı. Tek yönlü
akış, yanlış çıkan parçanın tek başına atılabilmesini sağlar.

**Reddedilen alternatif:** "Konular birbirini hiç tanımaz." Gerçek ilişkileri (kart→banka,
gider→hareket) yasaklar; uygulanamaz. Tek yön yeterli, döngü yasak.

---

## K-009 — Başlangıç konusu: hesap ekstresi

**Tarih:** 8 Eylül 2026

**Karar:** İlk yazılacak ürün **hesap ekstresi**dir: tek belge, tek ürün. Mekanizma
(belge → kayıt → yeniden işleme) burada oturduktan sonra kredi kartı ekstresi gelir.

**Gerekçe:** En basit belge türü ve içinde hazır bir doğruluk kontrolü var: açılış
bakiyesi + hareketler = kapanış bakiyesi. Okuma yanlışsa hemen belli olur.

**Reddedilen alternatif:** Kredi kartı ekstresi ile başlamak. Acil ihtiyaca daha yakın ama
taksit, dönem ve kesim tarihi ilk denemede daha çok şeyin ters gitmesine yol açar.

---

## K-010 — Belgeyi AI okur; determinizm doğrulama ve kayıt katmanındadır

**Tarih:** 8 Eylül 2026

**Karar:** Belgeyi (hesap ekstresi, kart ekstresi...) şimdilik Cowork/AI okur ve yapılandırılmış
bir **okuma** üretir: satırlar, tarihler, tutarlar, açılış ve kapanış bakiyesi. Programın
belge okuyucusu yoktur. Determinizm okuma çıktısında **aranmaz**; doğrulama ve kayıt
katmanında aranır:

- Okuma, Pydantic modelleriyle doğrulanır (K-001: MCP girdisi ile servis girdisi aynı
  model). Doğrulama sabittir; hesap ekstresinde açılış + hareketler = kapanış tutmuyorsa
  okuma reddedilir.
- Doğrulanan okuma belgeyle birlikte saklanır. Kayıtlar belgeden değil, **saklı okumadan**
  türetilir; bu adım deterministiktir. "Belgeyi yeniden işle" saklı okumadan kayıt üretmektir,
  AI'ya yeniden sormak değildir.
- Belge yeniden okunursa yeni bir okuma sürümü doğar; eskisi YERINI_DEVRETTI olur (K-007).

Ürünleşme aşamasında okuyucu değişebilir (program, başka bir model); değişen yalnız ilk
adımdır, doğrulama ve kayıt katmanı aynı kalır.

**Gerekçe:** Bugün uygulamayı Cowork işletiyor ve belgeyi zaten okuyabiliyor; ayrı bir PDF
okuyucu yazmak ilk ürünü geciktirir. K-006'nın özü (geri alma = yeniden işleme, elle veri
ameliyatı yok) okumanın saklanmasıyla korunur.

**Reddedilen alternatif:** Programın kendi PDF okuyucusu. Deterministik ama banka başına
ayrı kural ister; ilk belge türünde bile en çok zaman alan iş olurdu. Kapı kapalı değil.

---

## K-011 — Belge arşivi yolunun tek sahibi de `ayarlar` modülüdür

**Tarih:** 8 Eylül 2026

**Karar:** Arşivlenen belgelerin dizini yalnız `src/defteriki/ayarlar.py` içinde tanımlanır
(K-004 ile aynı kalıp). Varsayılan konum `%LOCALAPPDATA%\DefterIki\belgeler`, Windows
dışında XDG karşılığıdır; yol `DEFTERIKI_BELGE_ARSIVI` ortam değişkeniyle ezilebilir.
Yol her zaman mutlaktır. Arşiv, ilk belge işlenmeden önce hazırdır.

**Gerekçe:** K-001 arşivi "dosya sistemi + SHA-256" olarak seçmişti ama yeri tanımsızdı. Yol
iki yerde tanımlanırsa veritabanı yolundaki üç sorun (göreli yol, iki kaynak, bulut senkronu)
burada da doğar. Veritabanı ile arşiv aynı kök dizinde durur; yedek tek klasördür.

**Reddedilen alternatif:** Belgeleri veritabanının içinde BLOB olarak saklamak. Tek dosya
avantajı var ama veritabanını şişirir, belgeyi dışarıdan açmayı zorlaştırır ve SHA-256 ile
dosya sisteminde doğrulama olanağını kaldırır.

---

## K-012 — Model yazım standardı: her kısıt adlandırılır

**Tarih:** 8 Eylül 2026

**Karar:** `CheckConstraint` her zaman `name=` ile yazılır; adsız kısıt yasaktır. Diğer kısıtlar
(`pk`, `fk`, `uq`, `ix`) adlarını `model.py` içindeki adlandırma kuralından otomatik alır.
Kural SQLAlchemy tarafından **tanım anında** zorlanır: adsız `CheckConstraint` tabloya
bağlanırken `InvalidRequestError` verir, model modülü import bile edilemez.
`tests/test_gocler.py` bu davranışı sınar ki kural zayıflatılırsa (token kaldırılırsa) fark
edilsin.

**Gerekçe:** Adlandırma kuralı `ck_%(table_name)s_%(constraint_name)s` biçimindedir; ad
verilmezse SQLAlchemy tablo tanımında hata verir (inceleme sırasında doğrulandı). SQLite adsız kısıtı sonradan düşüremez;
Alembic batch modu adı bilmek zorundadır.

**Reddedilen alternatif:** `ck_%(column_0_name)s` gibi sütundan türeyen ad. Çok sütunlu ve
sütunsuz (`length(x) > 0` gibi) kısıtlarda belirsiz kalır.

---

## Açık maddeler

Her açık madde üç kovadan birine girer: **yapılacak / şimdilik kabul / yapılmayacak.**
Kovasız açık madde bırakılmaz.

| # | Madde | Kova | Not |
|---|-------|------|-----|
| A-001 | pre-commit kancaları Cowork'ün kabuğundan çalışmıyor | şimdilik kabul | Kod commit'leri Windows tarafından alınır; bkz. `BULGULAR.md` B-003 |
| A-002 | Claude Desktop'ın güvenilen klasör kaydı hâlâ eski OneDrive yolunu gösteriyor | kapandı | Çalışma dizini `C:\dev\DefterIki`; Claude Code oturumları buradan açılıyor (8 Eylül 2026) |
| A-003 | Çekirdek/arayüz sınırı kodda zorlanmıyor | kapandı | K-008 ile karara bağlandı, `tests/test_katmanlar.py` koruyor |
| A-004 | İki konuya birden değen kural nereye yazılır | yapılacak | Şimdi kararlaştırılmıyor: ilk gerçek örnek çıktığında, somut vaka elde varken verilecek |
| A-005 | Her kaydın kaynak belgesine geri izlenebilir olması | kapandı | K-006 ile karara bağlandı |
| A-006 | Aynı hareket iki belgede görünürse (hesap ekstresindeki kart ödemesi + kart ekstresindeki aynı ödeme) ne olur | yapılacak | Abdüllatif kararı erteledi. Masadaki öneri: her belge kendi kaydını yazar, ikisini bağlayan ayrı bir eşleştirme katmanı olur (öneri → onay → bozulabilir). Aynı mekanizma bir belgenin eksiğini (saat) başka belgeden tamamlamak için de gerekir (K-007). Hesap ekstresi tek başına bu kararı gerektirmiyor; kart gelmeden önce verilecek |
| A-007 | Ürün modelleri Alembic metadata'sına nasıl kaydolur | yapılacak | İlk ürün modeliyle birlikte çözülür: `alembic/env.py` ve `tests/conftest.py` model modüllerini açıkça içe alır; ayrı bir kayıt mekanizması kurulmaz |
| A-008 | Kayıtların sahibi (kullanıcı/şirket) satır bazında tutulacak mı | şimdilik kabul | 8 Eylül 2026 kararı: **ilk sürümde dosyanın sahibi kullanıcıdır; satır bazında sahiplik yoktur.** Uygulama tek kullanıcı + tek SQLite dosyasıyla çalışıyor; ürün hedefi çok kullanıcılı olsa da bu bugün `user_id` sütunu gerektirmiyor. Ürünleştirme aşamasında yeniden değerlendirilir. Bilinçli erteleme; unutulmuş değil |
| A-009 | Dosyaya loglama (K-001'de vaat edildi) henüz kurulmadı | yapılacak | Hesap ekstresinin önünde engel değil; **ilk gerçek kullanımdan önce** kurulur. Log dosyasının yeri K-004 kalıbıyla `ayarlar` modülünün sahipliğinde, veri dizininin altında olur. `alembic/env.py` içindeki `disable_existing_loggers=False` bu loglamanın göçler sırasında susmaması içindir |
| A-010 | AI okuması nerede saklanır: veritabanında JSON sütunu mu, arşivde belgenin yanında dosya mı | yapılacak | K-010 "belgeyle birlikte saklanır" der ama yeri söylemez. **İlk belge modeliyle birlikte, ilk göçten önce** kararlaştırılır; sonradan taşımak göç ve arşiv dönüşümü ister. Ölçütler: yedek tek klasör (K-011), yeniden işleme saklı okumadan üretilir (K-010), okuma sürümlenir ve eskisi YERINI_DEVRETTI olur (K-007) |

---

## Tartışma notu — sınır ve kuralların keşfi (8 Eylül 2026)

Karar değil, **karara giden konuşmanın özeti**. Bir sonraki oturum buradan devam eder.

**Çıkış noktası.** Abdüllatif'in tespiti: iş kurallarının hepsi bugün bilinmiyor; bugün
kural diye bağlanan şey yarın ayağa dolanıyor. Bu yüzden kurallar baştan kararlaştırılamaz.

**Ayrım.** İki farklı şey birbirine karışıyordu:
- *İş kuralları* ("kart limiti aşılamaz", "ödeme tutarı hareketi aşamaz"): bilinmiyor,
  kullandıkça çıkacak, taahhüt edilmiyor.
- *Yerleşim kuralı* ("kod nerede durur, ne neyi tanır"): finansla ilgisi yok, iş kuralları
  bilinmeden de karara bağlanabilir.

**Üzerinde durulan iki ilke** (henüz K numarası verilmedi, A-003'te):
1. Bir iş kuralı kodda tek yerde durur; ekran da MCP de oraya sorar.
2. Konular (kartlar, hesaplar, giderler) birbirinin içine uzanmaz.

Gerekçe kuralları dondurmak değil, **fikir değiştirmeyi ucuzlatmak**: yanlış çıkan parça
tek başına atılabilsin.

**Çalışma yöntemi (Abdüllatif'in tercihi).** Projeyi çok büyütmeden, gerçek belgelerle
çalıştırarak kuralları kullanımda keşfetmek; gerekirse geri alıp öğrenilen kuralla devam
etmek. Kendi çekincesi: bu bir geri alma döngüsü yaratabilir.

**Döngüye karşı üç dayanak:**
- Kodu geri almak ucuz (git); pahalı olan yanlış kuralla yazılmış **veriyi** geri almak.
  Panzehiri A-005: kayıt kaynağına geri izlenebilirse geri alma "belgeleri yeniden işle"ye
  iner, elle veri ameliyatına değil.
- Geri almanın **birimi** küçük olmalı; parçalar ayrı değilse yanlış çıkanı tek başına
  atamazsın ve yanlış kuralla yaşamaya başlarsın.
- Sinyal: aynı şey üçüncü kez geri alınıyorsa sorun kodda değildir; cevaplanmamış bir soru
  vardır, orada durulur.

**Sonuç (8 Eylül 2026, ikinci oturum).** İki ilke K-008 oldu; başlangıç konusu K-009 ile
hesap ekstresi seçildi. Belge–kayıt yönü K-006, veri sözleşmesi K-007. Açıkta kalan tek
soru A-006 (aynı hareketin iki belgede görünmesi).

**Üçüncü oturum (8 Eylül 2026).** İnceleme sonrası altı karar: belgeyi AI okur (K-010),
arşiv yolu ayarlarda (K-011), kısıtlar adlı (K-012), tamsayı PK kalır (K-007 ek), metadata
kaydı ilk modelle çözülür (A-007), A-002 kapandı.

**Dördüncü oturum (8 Eylül 2026, inşa öncesi inceleme).** Kod ve araçlar temiz çıktı
(61 test, ruff, pyright, pre-commit). İlk göçten önce `uq`/`fk` kısıt adları tüm sütunlardan
türetilecek biçimde düzeltildi (`column_0_N_name`; yalnız ilk sütunla iki kısıt aynı adı
alabiliyordu). Sahiplik sorusu A-008 olarak açıldı ve bilinçli ertelendi. K-002 gerekçesi
ve K-011'deki yol yazımı (dosyaya sızmış backspace baytı) düzeltildi.

**Beşinci oturum (8 Eylül 2026, ikinci inşa öncesi inceleme).** İki gerçek hata düzeltildi:
test fikstürü belge arşivini geçici dizine yönlendirmiyordu (B-008), `busy_timeout`
pragması `journal_mode`'dan sonra geliyordu (B-009). İki açık madde eklendi: loglama
(A-009), AI okumasının saklanma biçimi (A-010). Abdüllatif'in yön kararı: **temel kat
önceden eksiksiz doldurulmaz; ihtiyaç oldukça büyütülür.** Hesap ekstresi için gerçekten
ortak olacak parçalar (belge modeli ve arşivi, para ve tarih tipleri) ürünle birlikte
temel kata girer; "önce bütün altyapıyı kur" yaklaşımı reddedildi. CI ve LICENSE bekler.

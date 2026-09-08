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
- *Kimlik.* Tablo birincil anahtarları tamsayıdır (tek kullanıcı, tek dosya). Belgenin
  kimliği SHA-256'dır.
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

## Açık maddeler

Her açık madde üç kovadan birine girer: **yapılacak / şimdilik kabul / yapılmayacak.**
Kovasız açık madde bırakılmaz.

| # | Madde | Kova | Not |
|---|-------|------|-----|
| A-001 | pre-commit kancaları Cowork'ün kabuğundan çalışmıyor | şimdilik kabul | Kod commit'leri Windows tarafından alınır; bkz. `BULGULAR.md` B-003 |
| A-002 | Claude Desktop'ın güvenilen klasör kaydı hâlâ eski OneDrive yolunu gösteriyor | yapılacak | Uygulamadan klasör yeniden bağlanacak: `C:\dev\DefterIki`. Kayıt `preferences.localAgentModeTrustedFolders` içinde |
| A-003 | Çekirdek/arayüz sınırı kodda zorlanmıyor | kapandı | K-008 ile karara bağlandı, `tests/test_katmanlar.py` koruyor |
| A-004 | İki konuya birden değen kural nereye yazılır | yapılacak | Şimdi kararlaştırılmıyor: ilk gerçek örnek çıktığında, somut vaka elde varken verilecek |
| A-005 | Her kaydın kaynak belgesine geri izlenebilir olması | kapandı | K-006 ile karara bağlandı |
| A-006 | Aynı hareket iki belgede görünürse (hesap ekstresindeki kart ödemesi + kart ekstresindeki aynı ödeme) ne olur | yapılacak | Abdüllatif kararı erteledi. Masadaki öneri: her belge kendi kaydını yazar, ikisini bağlayan ayrı bir eşleştirme katmanı olur (öneri → onay → bozulabilir). Aynı mekanizma bir belgenin eksiğini (saat) başka belgeden tamamlamak için de gerekir (K-007). Hesap ekstresi tek başına bu kararı gerektirmiyor; kart gelmeden önce verilecek |

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

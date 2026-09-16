# DEFTERIKI

Kişisel finans kayıt sistemi. Belgeler Cowork tarafından okunur, MCP kapısından
DEFTERIKI'ye yazılır; uygulama kayıtları tutar, denetler ve gösterir.

## Durum

Aşama 2 (proje temeli) ve Aşama 3 (gerçek Cowork MCP denemesi) tamamlandı;
Aşama 3'ün dört teslimi ve ölçümleri "Cowork entegrasyonu" bölümünde. Aşama 4
(veritabanı çekirdeği) sürüyor: Teslim 4.1, 4.2 ve 4.3 bitti, 4.4 (nesne)
sırada. Bitenler:

* uv ile paket iskeleti (`src/defteriki`)
* Merkezi ayar yönetimi (`src/defteriki/ayarlar.py`)
* Başlangıç akışı: `uv run defteriki` (`src/defteriki/baslangic.py`)
* Teknik hata günlüğü (`src/defteriki/gunluk.py`)
* Test altyapısı (pytest + Hypothesis)
* Tek komutluk kalite kontrolü (Ruff, Pyright strict, pytest)
* `.gitignore` ve `.gitattributes`; kritik dışlama kuralları testle doğrulanır
  (`tests/test_gitignore.py`)
* MCP kapısı iskeleti: `uv run defteriki-mcp`, tek araç `sistem_durumu`
  (`src/defteriki/mcp_kapisi.py`); Cowork ile bağlantı, dosya erişimi ve
  çok adımlı protokol gerçek istemciyle ölçüldü
* Ortak sözleşmeler: katı kimlik ve kuruş tutar, yön/eksen/para birimi,
  durum adları, hata ailesi, sayfalama (`src/defteriki/sozlesmeler.py`)
* Veritabanı bağlantısı ve işlem sınırları: WAL, `BEGIN IMMEDIATE`, salt
  okunur okuma, geri alma garantisi (`src/defteriki/veritabani.py`)
* Şema ve ilk migration: on altı tablo, isimli kısıtlar, bileşik dış
  anahtarlar, Alembic ile sürüm denetimi (`src/defteriki/sema.py`,
  `migrations/`)
* Defter ve onay talebi: defter `ONAY_BEKLIYOR` doğar, ekrandan onaylanınca
  `AKTIF`; işlem anahtarı koruması, sürüm denetimli karar, denetim olayı
  (`defterler.py`, `onaylar.py`, `islem_anahtarlari.py`, `denetim.py`)

Henüz yok: nesne/belge/kayıt işlevleri (4.4–4.6), GUI, ürün verisi yazan
MCP aracı. Şema kurulu ama başlangıç akışına henüz bağlı değil: `uv run
defteriki` veritabanı dosyası oluşturmaz, şema `semayi_yukselt` ile ya da
`uv run alembic upgrade head` ile kurulur (bağlama Aşama 4 kapısında).

## Kurulum

```bash
uv sync
```

Python 3.13 ve uv gerekir. `uv sync` sanal ortamı ve geliştirme
bağımlılıklarını (pytest, hypothesis, ruff, pyright, pre-commit) kurar.

Klon sonrası bir kez, commit öncesi kontrol kancasını yükle:

```bash
uv run pre-commit install
```

## Başlatma

```bash
uv run defteriki
```

Komut sırayla ayarları ortam değişkenlerinden yükler, seçilen ortamın
dizinlerini (veritabanı dizini, `belgeler/`, `logs/`) açar, teknik günlüğü
kurar ve başlangıç olayını günlüğe yazar. Başarılıysa tek satırlık bir mesaj
(ortam, veri kökü, günlük dosyası) basar ve `0` ile çıkar. Henüz veritabanı
oluşturmaz; finansal iş yapmaz.

Herhangi bir adım başarısızsa (`DEFTERIKI_ORTAM` bilinmeyen değer, test
ortamında veri kökü verilmemiş, dizin yerine dosya var, log dosyası
açılamıyor...) anlaşılır bir hata stderr'e yazılır ve çıkış kodu `1` olur.
Günlük kurulamadıysa başarılı başlangıç mesajı verilmez. Yollar
uygulamanın hangi dizinden başlatıldığına bağlı değildir; modüller import
edildiğinde dizin ya da dosya oluşturulmaz.

## MCP kapısı

Cowork'un DEFTERIKI'ye ulaştığı tek kapı. stdio taşımasıyla çalışır:

```bash
uv run defteriki-mcp
```

Komut `uv run defteriki` ile aynı hazırlığı yapar (ayarlar, dizinler, günlük),
ardından MCP sunucusunu stdin/stdout üzerinde çalıştırır. İstemci bağlantıyı
kapatınca `0` ile çıkar. Hazırlık düşerse hata stderr'e yazılır, çıkış kodu
`1` olur; stdout'a hiçbir şey yazılmaz.

Bu sürümde tek araç var: `sistem_durumu`. Uygulama sürümü, ortam adı, şema
sürümü (`yok`) ve yetenek listesini döndürür; yol, anahtar ya da ortam
değişkeni içermez. Ürün verisi yazan araç henüz yoktur. Aşama 3'te kullanılan
geçici deneme araçları (`dosya_dene`, `deneme_baslat`, `deneme_durumu`)
kapı temizliğinde kaldırıldı; ne ölçtükleri "Cowork entegrasyonu"
bölümünde. Gelen dizini ayarı (`DEFTERIKI_GELEN_DIZINI`) kaldı: Aşama 4'te
belge alımı Cowork'un bu dizine bıraktığı dosyanın yoluyla yapılır.

Kurallar:

* stdout yalnız protokolündür. SDK'nın stdio taşıması sunucu çalışırken
  dosya tanımlayıcısı 1'i stderr'e çevirir; DEFTERIKI ayrıca hiç `print`
  kullanmaz. Test, stdout'un yalnız JSON-RPC satırları taşıdığını doğrular.
* Bütün tanı çıktısı teknik günlüğe gider. SDK'nın `mcp` günlüğü de aynı
  dosyaya bağlanır (olay sütunu `-`), stderr'e düşmez.
* Modül import edildiğinde sunucu kurulmaz, dosya oluşturulmaz.
* Her araç çağrısında günlüğe `mcp_el_sikisma` satırı düşer: istemci adı ve
  sürümü, müzakere edilen protokol sürümü, istemci yetenekleri. Aşama 3'ün
  ölçümü bu satırdan okunur.

Test (`tests/test_mcp_kapisi.py`) sunucuyu ayrı süreçte başlatır; ham
JSON-RPC ile `initialize`, `tools/list` ve `tools/call` yapar, her isteğin
yanıtını bekler, sonra stdin'i kapatır.

## Cowork entegrasyonu

Aşama 3'ün dört teslimi ve ölçümleri (aşama 2026-09-16'da kapandı). Geçici
deneme araçları `dosya_dene`, `deneme_baslat`, `deneme_durumu` ve testleri
kapı temizliğinde kaldırıldı; yalnız `sistem_durumu` kaldı. Aşağıdaki satırlar
o araçların ne ölçtüğünün kalıcı kaydıdır. Kalıcı çıkarımlar: SDK `mcp` 2.2.0
kilitli; protokol 2025-11-25, istemcide elicitation ve sampling yok; belge
alımı dosya yolu yöntemiyle (gelen dizini), parça yükleme gerekmez; kullanıcı
kararı bekleyen işler için "BEKLIYOR + talep kimliği, istemci tekrar sorar"
yöntemi Cowork'la çalışır, talep durumu veritabanında tutulur.

| Teslim | Konu | Sonuç |
|---|---|---|
| 3.1 | MCP SDK ve sunucu iskeleti | Bitti. `mcp` 2.2.0 `uv.lock` ile kilitli. SDK 2.x'te `FastMCP` adı `MCPServer` oldu (`mcp.server.mcpserver`); 1.x örnekleri doğrudan çalışmaz. Araç dönüş tipi `slots=True` dataclass olamaz, SDK şemayı düşürüyor. Yerel istemciyle protokol sürümü `2025-06-18` müzakere edildi. |
| 3.2 | Gerçek Cowork bağlantısı | Bitti (2026-09-15). Ayar: Claude masaüstü `claude_desktop_config.json` → `mcpServers`, komut `uv.exe run --directory C:/dev/DefterIki defteriki-mcp`, ortam değişkeni yok, veri `%LOCALAPPDATA%/DEFTERIKI/gelistirme`. Ölçüm (`mcp_el_sikisma`): istemci `local-agent-mode-defteriki 1.0.0`; müzakere edilen protokol sürümü **2025-11-25** (sunucunun en yükseği 2026-07-28, istemci daha eskisini seçti); istemci yetenekleri `roots.listChanged=true` ve `io.modelcontextprotocol/ui` uzantısı (`text/html;profile=mcp-app`); sampling ve elicitation bildirilmedi. Uygulama açılışta sunucuyu üç kez başlatıyor: biri 10 ms içinde kapanan yoklama, ikisi kalıcı (Cowork ve Claude Code). Zaman aşımı gözlenmedi: başlatmadan araç yanıtına kadar sorun yok, uygulama kapanınca sunucular EOF ile temiz çıktı. Uygulamanın kendi MCP günlüğü boş; ölçüm sunucu günlüğünden alındı. |
| 3.3 | Dosya erişim denemesi | **Bitti (2026-09-15): dosya yolu yöntemi çalıştı, parça yükleme gerekmez.** Araç `dosya_dene` yazıldı ve testlendi (izinli dosya, boş dosya, alt dizin, dizin dışı, `..`, göreli yol, olmayan dosya, dizin, okuma hatası, stdio üzerinden okuma ve red; simgesel bağlantı testleri Windows'ta bağlantı yetkisi yoksa atlanır). Cowork ayarı: `mcpServers.defteriki.env` → `DEFTERIKI_GELEN_DIZINI=C:/dev/DefterIki-gelen`; uygulama yeniden başlayınca dizin kendiliğinden oluştu. Deneme ~402 KB'lik gerçek bir hesap özeti PDF'iyle iki senaryoda yapıldı: (a) dosya elle gelen dizinine kopyalandı, Cowork'a yol söylendi → `sonuc=okundu`; (b) PDF Cowork'a yüklendi, gelen dizinine bırakması istendi → Cowork dosyayı dizine yazdı ve `dosya_dene` ile okuttu → `sonuc=okundu`. İki dosyanın SHA-256 özeti birebir aynı; Cowork dosyayı bozmadan aktarıyor. Günlükte iki `mcp_dosya_deneme` satırı, red ya da hata yok. Aşama 4 belge alımı bu yöntemle kurulacak: Cowork dosyayı gelen dizinine bırakır, yolu MCP aracına verir. |
| 3.4 | Çok adımlı protokol denemesi | **Bitti (2026-09-16): Cowork BEKLIYOR döngüsünü kendi başına, sadakatle yürüttü.** Araç çifti `deneme_baslat` / `deneme_durumu` yazıldı ve testlendi (süreç içi sahte saatle bekle→tamamla geçişi, aynı anahtar aynı kimlik, boş anahtar reddi, bilinmeyen kimlik, yanıt ve günlükte anahtar yok; stdio üzerinden başlat→durum→bilinmeyen→tekrar başlat döngüsü). Cowork'a tek cümle verildi: "bir deneme işi başlat; bekliyor dönerse aynı anahtarla durumu sor, tamamlanınca bildir." Günlük (`mcp_deneme`): `deneme_baslat` → BEKLIYOR, talep kimliği verildi; `deneme_durumu` üç kez soruldu: 3,1 s (BEKLIYOR), 17,4 s (BEKLIYOR), 42,5 s (TAMAMLANDI). Sorgu aralıkları yaklaşık 3 s, 14 s, 25 s; Cowork bekleme süresini kendi uzattı, vazgeçmedi, kimliği doğru taşıdı, anahtarı değiştirmedi, aynı işi yeniden başlatmadı. Hiçbir çağrı açık kalmadı; durum sorguları anında döndü. Dört çağrı da aynı sunucu sürecinden (`surec` eşit) geldi: Claude masaüstü sunucuyu yine iki kalıcı süreç olarak başlattı ama tek sohbetin bütün çağrıları tek sürece gitti; BILINMIYOR görülmedi. Aşama 5 için çıkarım: BEKLIYOR + talep kimliği + istemcinin tekrar sorması çalışan bir yöntem; talep durumu yine de belleğe değil veritabanına yazılır, çünkü sohbetler ve uygulama yeniden başlatmaları arası süreç garantisi yok. |

## Veritabanı

SQLite, tek dosya, yolu yalnız ayarlardan (`DEFTERIKI_VERITABANI_YOLU` ya da
`<veri kökü>/<ortam>/defteriki.sqlite3`). `src/defteriki/veritabani.py` bu
dosyaya iki motor açar; import ve kurulum diske dokunmaz, dosya ilk yazma
işleminde oluşur.

* **Yazma**: her bağlantıda `foreign_keys=ON`, `journal_mode=WAL`,
  `busy_timeout=5000`, `synchronous=FULL`. `yazma_islemi()` tek işlemdir ve
  `BEGIN IMMEDIATE` ile açılır: yazma kilidi kapıda alınır, iki yazar ortada
  çakışmaz. Çıkışta başarı COMMIT, herhangi bir hata ROLLBACK; yarım satır
  kalmaz. İşlem sahibi en dıştaki çağrıdır, içerideki işlevler commit yapmaz.
  Kilit 5 saniyede alınamazsa `VeritabaniMesgul` (kod `VERITABANI_MESGUL`,
  tekrar denenebilir).
* **Okuma**: `okuma_islemi()` aynı PRAGMA'lar ve `query_only=ON` ile salt
  okunur oturum verir; yazma denemesini SQLite reddeder. WAL sayesinde yazma
  sürerken okuma bekletilmez ve commit edilmemiş veriyi görmez.
* Python'un `sqlite3` sürücüsünün kendi BEGIN'i kapatılır; BEGIN'i SQLAlchemy
  `begin` olayıyla biz veririz, aksi hâlde `BEGIN IMMEDIATE` uygulanamaz.

Ortak sözleşmeler `src/defteriki/sozlesmeler.py`'de; ürün mantığı içermez:

* `Kimlik` pozitif tam sayı, `KurusTutar` kuruş cinsinden 0 ya da pozitif tam
  sayı (K05). İkisi de katı: `12.0`, `True`, `"100"` reddedilir, yuvarlama
  yok. `kurus_tutar_dogrula` → `TUTAR_GECERSIZ`.
* `Yon` ARTTIR/AZALT, `Eksen` VARLIK/BORC/GIDER, `ParaBirimi` yalnız TRY
  (C09; `para_birimi_dogrula` → `PARA_BIRIMI_DESTEKLENMIYOR`).
* Durum adları (C08): belge ARSIVLENDI → OKUNUYOR → KARAR_BEKLIYOR → HAZIR →
  KAYITLI, GECERSIZ, YERINE_GECILDI; satır YAZILDI, KARAR_BEKLIYOR,
  MEVCUDA_BAGLANDI, KAPSAM_DISI; nesne AKTIF, ENGELLI, PASIF, SILINDI.
* Hata ailesi: `DefterikiHatasi` kökü; Tam Plan 11.2'deki kodların her biri
  bir sınıf (`BELGE_YOK`, `DEFTER_UYUSMAZLIGI`, `TUTAR_GECERSIZ`,
  `ANAHTAR_ICERIK_CAKISMASI`, `HEDEF_SURUMU_DEGISTI`, `VERITABANI_MESGUL`
  ...). Her hatada kod, güvenli mesaj, isteğe bağlı alan/konum ve tekrar
  denenebilirlik var; yalnız `VERITABANI_MESGUL` tekrar denenebilir.
  **Karar notu:** 11.2'de genel girdi hatası için kod yok; kimlik ve
  sayfalama için `GIRDI_GECERSIZ` teknik kod olarak eklendi. Abdüllatif
  itiraz ederse ad değişir ya da kaldırılır.
* `Sayfalama(sinir=100, baslangic=0)`: sunucu tarafı, en çok 500.

### Şema ve migration

On altı tablo `src/defteriki/sema.py`'de SQLAlchemy Core `Table` nesneleriyle
tanımlıdır (Tam Plan bölüm 5; Yürütme Planı 4.2 listesi). Veritabanında
Alembic migration'larıyla kurulur: `migrations/versions/0001_ilk_sema.py`
`METADATA`'dan autogenerate ile üretilip donduruldu; şema değişimi yalnız yeni
migration ile yapılır, `create_all` kullanılmaz. Metadata ile veritabanındaki
şema arasında fark olmaması testle doğrulanır (`compare_metadata == []`).

| Grup | Tablolar |
|---|---|
| Defter ve nesne | `defter`, `nesne`, `nesne_ozellik`, `nesne_baglanti`, `nesne_sart`, `nesne_kaynak` |
| Belge | `arsiv_dosya`, `belge`, `okuma`, `okuma_satir` |
| Para | `kayit`, `kayit_kaynak`, `etki` |
| İşletim | `onay_talep`, `islem_anahtari`, `denetim_olay` |

Kurallar:

* Kimlikler `INTEGER PRIMARY KEY AUTOINCREMENT`; silinen kimlik yeniden
  verilmez.
* Her iş tablosu `defter_id` taşır; alt tablolar üst tabloya bileşik dış
  anahtarla `(defter_id, hedef_id) → hedef(defter_id, id)` bağlanır, bunun
  için üst tablolarda `UNIQUE(defter_id, id)` vardır. Başka defterin
  nesnesine kayıt bağlamak veritabanı düzeyinde imkânsızdır (testli).
  İstisnalar: `arsiv_dosya` defterden bağımsız (aynı dosya birden fazla
  defterde belge olabilir); `islem_anahtari` kapsamı `kapsam_turu`
  (`SISTEM`/`DEFTER`) ve `kapsam_id` ile taşır.
* Bütün kısıtlar isimli (`pk_`, `fk_`, `uq_`, `ck_`, `ix_` kalıbı). Durum,
  yön, eksen, para birimi, tür sütunları izinli değerlerle CHECK'li;
  `tutar_kurus >= 0`, `seviye >= 0`, `alt_id <> ust_id`, boş alan adı ve
  boş anahtar reddedilir, `sha256` 64 karakter.
* Zaman damgaları UTC `DateTime`; kaynak tarihleri (`islem_tarihi`,
  `valor_tarihi`) ayrı `Date`.
* İndeksler Tam Plan 5.3'teki gibi: nesne (defter, seviye, id); bağlantı iki
  yönlü; özellik (defter, alan adı, değer türü, eşleşme değeri); kayıt
  (defter, asıl nesne, işlem tarihi, id); etki (defter, nesne, eksen, para
  birimi, kayıt); kaynak iki yönlü; onay (defter, durum, id). Ölçülmeden ek
  indeks eklenmez.
* Aşama 8 alanları (`kayit.olay_id`, `islem_turu`, `yerine_gecen_id`,
  `etki.borc_id`) ve Aşama 7'nin mükerrerlik tabloları bu şemada yoktur;
  `okuma_satir.aday_grup_id` yer tutucudur. Tam Plan'daki `gonderim` tablosu
  Yürütme Planı 4.2 listesinde olmadığı için kurulmadı.

**Durum listeleri (karar, 2026-09-16).** Tam Plan belge, satır ve nesne
durumlarını (C08) vermişti; şu listeler açıktı, Claude önerdi, Abdüllatif
onayladı: defter `ONAY_BEKLIYOR`/`AKTIF`/`PASIF`; kayıt `AKTIF`/`GECERSIZ`;
okuma `ACIK`/`TAMAMLANDI`/`IPTAL`; kaynak rolü `ASIL`/`DESTEK`, kaynak durumu
`AKTIF`/`KALDIRILDI`; onay türü `DEFTER_TANIMLAMA`/`NESNE_ACILISI`, onay
durumu `BEKLIYOR`/`ONAYLANDI`/`REDDEDILDI`. Ayrıca plandan: değer türü
`METIN`/`TAMSAYI`/`ONDALIK`/`TARIH`/`MANTIKSAL`/`JSON`, denetim aktörü
`COWORK`/`KULLANICI`/`UYGULAMA`. Hepsi `sozlesmeler.py`'de `StrEnum`.

Sürüm denetimi (`sema.py`): `BEKLENEN_SEMA_SURUMU = "0001"`.
`semayi_denetle` veritabanındaki Alembic sürümünü okur; kurulmamış ya da
farklıysa `SemaSurumuUyumsuz` verir, eski şemaya yazılmaz. `semayi_yukselt`
migration'ları tek yazma işleminde (`BEGIN IMMEDIATE`) uygular, ardından
`foreign_key_check` ve `integrity_check` çalıştırır. Komut satırı:
`uv run alembic upgrade head` (yol `DEFTERIKI_*` ayarlarından;
`alembic.ini`'de URL yok, yollar `%(here)s` ile ini dosyasına göre).

Test (`tests/test_sema.py`): boş veritabanına kurulum on altı tablo;
`foreign_key_check`/`integrity_check` temiz; metadata ile migration
arasında fark yok; sürüm denetimi (kurulmamış, farklı sürüm); tekrar
yükseltme; geri alma bütün tabloları kaldırır; kısıtlar veritabanında
çalışır (izinsiz durum, defterler arası bağlantı, negatif tutar, TRY dışı
para birimi, kendine bağlantı, boş alan adı, aynı alan adı iki kez,
kimlik yeniden kullanılmaz); komut satırından yükseltme başka çalışma
dizininden ayarlardaki yolu bulur.

Test (`tests/test_veritabani.py`, `tests/test_sozlesmeler.py`): PRAGMA
değerleri; iki ayrı süreç aynı ayarlarla aynı dosyayı çözer ve birbirinin
yazdığını okur; FK ihlali reddedilir; hata sonrası yarım satır kalmaz; kilit
tutulurken `BEGIN IMMEDIATE` salt SELECT'i bile bekletir ve süre dolunca
`VERITABANI_MESGUL` verir; yazar okumayı engellemez; import dosya yaratmaz;
Hypothesis ile `KurusTutar` sınırları (negatif, float, bool reddi).

## Defter ve onay talebi

Teslim 4.3. Ekran ve MCP yok; işlev ve test düzeyi. Bütün işlevler bir
`Session` alır ve **commit yapmaz**: işlem sahibi çağırandır
(`Veritabani.yazma_islemi`). Bir işlev ortada düşerse aynı işlemdeki her şey
(defter, talep, anahtar kaydı, denetim olayı) geri alınır; testli.

**Defter** (`src/defteriki/defterler.py`). `defter_tanimla(ad,
islem_anahtari, aktor)` defteri `ONAY_BEKLIYOR` durumunda açar ve
`DEFTER_TANIMLAMA` onay talebi üretir (C12). Defter onaylanmadan yazma kabul
etmez: `aktif_defteri_getir` `AKTIF` dışı durumda `DEFTER_UYUSMAZLIGI` verir.
İlk defter açılırken henüz defter yok, bu yüzden işlem anahtarı `SISTEM`
kapsamlıdır (`kapsam_id` 0). Kapsam denetimi `defterde_oldugunu_dogrula`:
başka defterin kaydına erişim `DEFTER_UYUSMAZLIGI`. `defter_getir`,
`defter_listele` (sayfalı).

**İşlem anahtarı** (`src/defteriki/islem_anahtarlari.py`, K08). Her yazma
işlevi anahtar alır; `(kapsam_turu, kapsam_id, arac_adi, anahtar)` benzersiz.
Aynı anahtar aynı içerikle gelirse saklı sonuç döner, hiçbir şey yeniden
yazılmaz (`zaten_vardi=True`); farklı içerik `ANAHTAR_ICERIK_CAKISMASI`.
İçerik karşılaştırması isteğin kanonik JSON'unun SHA-256 özetiyle yapılır,
ham istek saklanmaz. Anahtar kaydı, iş sonucu ve denetim olayı aynı işlemde.

**Onay talebi** (`src/defteriki/onaylar.py`). `talep_olustur` kalıcı
`BEKLIYOR` talep açar; kullanıcı beklerken açık transaction ya da kilit
tutulmaz (testli: talep yazıldıktan hemen sonra başka bağlantı yazma kilidi
alabilir). `bekleyenleri_listele` yalnız `BEKLIYOR` olanları verir.
`karar_uygula(defter_id, talep_id, gorulen_hedef_surumu, karar)` **yalnız
ekrana açılır**; MCP kapısına "kullanıcı onayladı" parametresi hiç
sunulmaz. Sürüm denetimi: talebin taşıdığı sürüm, kullanıcının ekranda
gördüğü sürüm ve hedefin güncel sürümü üçü aynı değilse
`HEDEF_SURUMU_DEGISTI`, hiçbir şey yazılmaz. Sonuçlanmış talebe yeniden karar
verilemez. Karar etkisi türe göre kayıtlıdır (`KARAR_ETKILERI`):
`DEFTER_TANIMLAMA` onay → defter `AKTIF`, red → `PASIF`; iki hâlde de
hedefin sürümü bir artar. `NESNE_ACILISI` etkisi 4.4'te eklenir.

**Denetim olayı** (`src/defteriki/denetim.py`). Her yazma aynı işlemde
`denetim_olay` satırı bırakır: aktör (`COWORK`/`KULLANICI`/`UYGULAMA`),
eylem, hedef (`tablo:kimlik`), önceki/sonraki durum, işlem anahtarı kaydı.
Kişisel veri taşımaz.

Test (`tests/test_defterler.py`, `tests/test_onaylar.py`): ilk defter
`SISTEM` kapsamlı anahtarla; aynı anahtar aynı içerik yeni defter açmaz;
farklı içerik çakışır ve yazmaz; boş ad/anahtar reddi; hata her şeyi geri
alır; kilit tutulmaz; onay uygulanmadan defter `AKTIF` olmaz; onay → `AKTIF`
ve sürüm 2, red → `PASIF`; eski sürümle karar reddedilir ve yazılmaz; hedef
arkadan değişirse talep eskir; sonuçlanmış talebe yeniden karar yok; başka
defterin talebine karar yok; bekleyenler ve sayfalama; karar hatası geri
alınır.

## Teknik hata günlüğü

Günlük yalnızca ayarlardaki log dizinine yazar: `<log dizini>/defteriki.log`
(varsayılan `<veri kökü>/<ortam>/logs/defteriki.log`). Standart kütüphanenin
`logging` modülü kullanılır; ek bağımlılık yoktur.

Her satır `zaman | seviye | olay | mesaj` biçimindedir; olay türleri
şimdilik `baslangic`, `baslangic_hatasi`, `mcp_baslangic`, `mcp_el_sikisma`,
`mcp_kapanis`, `mcp_hatasi`. Dosya günlüğüne bağlanan dış kütüphane
kayıtlarında olay `-` olur.

Saklama sınırı: dosya 1.000.000 baytı aşınca döndürülür, en fazla 5 eski
dosya (`defteriki.log.1` ... `.5`) tutulur; toplam en çok ~6 MB. Kurulum
tekrar çağrılırsa önceki handler kapatılıp kaldırılır, aynı olay birden
fazla yazılmaz.

Gizlilik: belge içeriği, finansal kayıt içeriği, IBAN, kimlik bilgileri,
sırlar ve ortam değişkenleri günlüğe yazılmaz. Hatalar yalnızca türüyle
(`builtins.ValueError` gibi) kaydedilir; ham hata mesajı ve traceback dosyaya
dökülmez. Kullanıcıya gösterilen hata metni stderr'e gider, dosyaya değil.

## Kalite kontrolü

Biçim kontrolü, statik kontrol, tip kontrolü ve testler tek komutla:

```bash
uv run python scripts/kontrol.py
```

Betik sırayla `ruff format --check`, `ruff check`, `pyright` ve `pytest`
çalıştırır. Bir adım düşse de diğerleri çalışır; sonunda toplu sonuç verir ve
herhangi bir adım başarısızsa sıfırdan farklı çıkış kodu döner. Kaynak
dosyalarını değiştirmez.

Yalnızca testler:

```bash
uv run pytest
```

Aynı kontrol her `git commit` öncesinde pre-commit kancasıyla otomatik
çalışır (`.pre-commit-config.yaml`, tek kanca: `scripts/kontrol.py`);
bir adım düşerse commit yapılmaz. Kanca kaynak dosyalarını değiştirmez.

## Ayarlar

Bütün yollar `defteriki.ayarlar` modülünden gelir; uygulamanın nereden
başlatıldığı yolları değiştirmez.

```python
from defteriki.ayarlar import ayarlari_yukle, dizinleri_hazirla

ayarlar = ayarlari_yukle()  # ortam değişkenlerini okur, diske yazmaz
dizinleri_hazirla(ayarlar)  # gerekli dizinleri açar, dosya oluşturmaz
```

Ortam değişkenleri (öncelik yukarıdan aşağıya):

| Değişken | Anlamı |
|---|---|
| `DEFTERIKI_VERITABANI_YOLU` | Veritabanı dosyası; türetilmiş yolun yerine geçer |
| `DEFTERIKI_BELGE_DIZINI` | Belge arşivi dizini; türetilmiş yolun yerine geçer |
| `DEFTERIKI_LOG_DIZINI` | Log dizini; türetilmiş yolun yerine geçer |
| `DEFTERIKI_GELEN_DIZINI` | Gelen dizini: Cowork'un dosya bıraktığı, MCP araçlarının okumaya izinli olduğu tek dizin; türetilmiş yolun yerine geçer |
| `DEFTERIKI_VERI_KOKU` | Ortamların ortak üst dizini; ortam adı altına eklenir |
| `DEFTERIKI_ORTAM` | `gelistirme` (varsayılan), `test`, `gercek` |

Varsayılan veri kökü Windows'ta `%LOCALAPPDATA%\DEFTERIKI\<ortam>`, Linux'ta
`$XDG_DATA_HOME/DEFTERIKI/<ortam>` (yoksa `~/.local/share/...`), macOS'ta
`~/Library/Application Support/DEFTERIKI/<ortam>`. Bu kökten
`defteriki.sqlite3`, `belgeler/`, `logs/` ve `gelen/` türetilir.

Kurallar:

* Yollar mutlak olmalı; boş veya göreli değer hata verir.
* Bilinmeyen ortam adı hata verir.
* `test` ortamı `DEFTERIKI_VERI_KOKU` ister ve tekil yolların bu kökün dışına
  çıkmasına izin vermez.
* Tekil yol değişkenleri diğer ortamlarda ortam ayrımını geçersiz kılabilir.

## Dizin düzeni

```
src/defteriki/    uygulama paketi
  ayarlar.py      merkezi ayarlar (ortam, yollar)
  baslangic.py    uv run defteriki giriş noktası; ortak hazırlık (ortami_hazirla)
  gunluk.py       teknik hata günlüğü
  mcp_kapisi.py   uv run defteriki-mcp; MCP sunucusu ve araçları
  sozlesmeler.py  ortak türler, durum adları, hata kodları, sayfalama
  veritabani.py   SQLite bağlantısı; yazma_islemi / okuma_islemi
  sema.py         on altı tablo (METADATA), şema sürümü denetimi ve yükseltme
  islem_anahtarlari.py  işlem anahtarı koruması (aynı anahtar aynı sonuç, K08)
  denetim.py      denetim olayı yazımı
  onaylar.py      onay talebi: oluştur, listele, karar uygula (yalnız ekran)
  defterler.py    defter tanımla/getir/listele; kapsam denetimi
migrations/       Alembic ortamı (env.py) ve sürümler (versions/0001_ilk_sema.py)
alembic.ini       Alembic ayarı; URL yok, yol ayarlardan
tests/            pytest testleri
scripts/          geliştirme betikleri (kontrol.py)
.pre-commit-config.yaml  commit öncesi kanca; kontrol.py'yi çalıştırır
kavramlar_sozlugu.md   ortak kavram tanımları; ekleme ve değişiklik yalnız Abdüllatif'in onayıyla
```

## Teknoloji

Bu projede kullanılacak teknoloji. Mutlak değil; ihtiyaç duyulması halinde değişebilir.

* Python 3.13 — ana dil
* uv — paket ve sanal ortam yönetimi
* pyproject.toml — proje/bağımlılık tanımı
* uv.lock — bağımlılık kilidi
* SQLite — ilişkisel veritabanı
* WAL — SQLite çalışma/journal modu; ayrı bir teknoloji değil
* SQLAlchemy 2.0 — veritabanı erişimi (kilitli: `uv.lock`)
* Alembic 1.20 — migration (Aşama 4.2'den itibaren)
* Pydantic 2.13 — katı tür doğrulama; ileride MCP giriş/çıkış şemaları
* MCP Python SDK 2.x (`mcp`, `MCPServer`) — Cowork ↔ DEFTERIKI kapısı
* PySide6 — masaüstü GUI için
* pytest — test
* Hypothesis — property-based test
* Ruff — lint + format
* Pyright strict — statik type checking
* pre-commit — commit öncesi kalite kontrolleri
* Git — sürüm kontrolü
* `.gitignore` — DB, WAL/SHM, kişisel veri, cache, secret vb. dışlama
* `.gitattributes` — LF/CRLF standardizasyonu

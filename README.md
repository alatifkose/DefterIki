# DEFTERIKI

Kişisel finans kayıt sistemi. Belgeler Cowork tarafından okunur, MCP kapısından
DEFTERIKI'ye yazılır; uygulama kayıtları tutar, denetler ve gösterir.

## Durum

Aşama 2 (proje temeli) ve Aşama 3 (gerçek Cowork MCP denemesi) tamamlandı;
Aşama 3'ün dört teslimi ve ölçümleri "Cowork entegrasyonu" bölümünde. Aşama 4
(veritabanı çekirdeği) sürüyor: Teslim 4.1–4.6 bitti, Aşama 4 kapısı
(uçtan uca test, şemanın başlangıç akışına bağlanması) sırada. **Karar (2026-09-16, Abdüllatif):** DEFTERIKI tek bütünleşik
defterdir; ayrı defter yoktur (sözlük: Defter; Tam Plan C01 iptal). Şema ve
4.3 buna göre yeniden kuruldu. Bitenler:

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
* Şema ve ilk migration: on beş tablo, isimli kısıtlar, Alembic ile sürüm
  denetimi (`src/defteriki/sema.py`, `migrations/`)
* Onay talebi, işlem anahtarı ve denetim olayı: kalıcı `BEKLIYOR` talep,
  yalnız ekrana açık sürüm denetimli karar, aynı anahtar aynı sonuç
  (`onaylar.py`, `islem_anahtarlari.py`, `denetim.py`)
* Nesne tanıtma: serbest özellikli form, üstlerden hesaplanan seviye,
  `ONAY_BEKLIYOR` ile yazılıp onayda şart seçimiyle `AKTIF`, türüyle
  eşleşme değeri, bulma (`nesneler.py`)
* Belge arşivi ve belge akışı: gelen dizininden içerik adresli arşive
  atomik kopya, belge tanımlama (aynı dosya tek belge), okuma, atomik satır
  gönderimi, okuma tamamlama ve uygulamanın tanımladığı belge kaydı
  (`arsiv.py`, `belgeler.py`)
* Tek işlem türü ve etkin bakiye: `HESAP_HAREKETI` sözleşmesi (saf
  doğrulama), hareket yazma (kaynak satırı zorunlu, aynı anahtar tek etki),
  yalnız `KAYITLI` belgeye dayanan bakiye ve hareket listesi
  (`finansal_kurallar.py`, `kayitlar.py`, `hesaplamalar.py`)

Henüz yok: diğer işlem sözleşmeleri (Aşama 8), mükerrerlik karşılaştırması
(Aşama 7), GUI, ürün verisi yazan MCP aracı. Şema kurulu ama başlangıç akışına henüz bağlı değil: `uv run
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
  bir sınıf (`BELGE_YOK`, `HEDEF_BULUNAMADI`, `TUTAR_GECERSIZ`,
  `ANAHTAR_ICERIK_CAKISMASI`, `HEDEF_SURUMU_DEGISTI`, `VERITABANI_MESGUL`
  ...). Her hatada kod, güvenli mesaj, isteğe bağlı alan/konum ve tekrar
  denenebilirlik var; yalnız `VERITABANI_MESGUL` tekrar denenebilir.
  **Karar notu:** 11.2'de genel girdi hatası için kod yok; kimlik ve
  sayfalama için `GIRDI_GECERSIZ` teknik kod olarak eklendi. Abdüllatif
  itiraz ederse ad değişir ya da kaldırılır.
* `Sayfalama(sinir=100, baslangic=0)`: sunucu tarafı, en çok 500.

### Şema ve migration

On beş tablo `src/defteriki/sema.py`'de SQLAlchemy Core `Table` nesneleriyle
tanımlıdır (Tam Plan bölüm 5; Yürütme Planı 4.2 listesi; sözlük "Defter"
kararıyla defter tablosu yok). Veritabanında Alembic migration'larıyla
kurulur: `migrations/versions/0001_ilk_sema.py` `METADATA`'dan autogenerate
ile üretilip donduruldu; şema değişimi yalnız yeni migration ile yapılır,
`create_all` kullanılmaz. Metadata ile veritabanındaki şema arasında fark
olmaması testle doğrulanır (`compare_metadata == []`).

| Grup | Tablolar |
|---|---|
| Nesne | `nesne`, `nesne_ozellik`, `nesne_baglanti`, `nesne_sart`, `nesne_kaynak` |
| Belge | `arsiv_dosya`, `belge`, `okuma`, `okuma_satir` |
| Para | `kayit`, `kayit_kaynak`, `etki` |
| İşletim | `onay_talep`, `islem_anahtari`, `denetim_olay` |

Kurallar:

* Kimlikler `INTEGER PRIMARY KEY AUTOINCREMENT`; silinen kimlik yeniden
  verilmez (testli).
* **Tek defter.** Tablolarda defter kimliği yok; dış anahtarlar doğrudan
  hedef kimliğe bağlanır (`nesne_id → nesne.id` gibi). Aynı arşiv dosyası
  yalnız bir belgeye bağlanır (`UNIQUE(belge.dosya_id)`). İşlem anahtarı
  `(arac_adi, anahtar)` ile benzersizdir.
* Bütün kısıtlar isimli (`pk_`, `fk_`, `uq_`, `ck_`, `ix_` kalıbı). Durum,
  yön, eksen, para birimi, tür sütunları izinli değerlerle CHECK'li;
  `tutar_kurus >= 0`, `seviye >= 0`, `alt_id <> ust_id`, boş alan adı ve
  boş anahtar reddedilir, `sha256` 64 karakter, `kaynak_adi` boş değil.
* Zaman damgaları UTC `DateTime`; kaynak tarihleri (`islem_tarihi`,
  `valor_tarihi`) ayrı `Date`.
* İndeksler Tam Plan 5.3'ün defter-sız hâli: nesne (seviye, id); bağlantı
  üst yönü (alt yönü UNIQUE ile kapalı); özellik (alan adı, değer türü,
  eşleşme değeri); kayıt (asıl nesne, işlem tarihi, id); etki (nesne, eksen,
  para birimi, kayıt); kaynak iki yönlü; onay (durum, id). Ölçülmeden ek
  indeks eklenmez.
* Aşama 8 alanları (`kayit.olay_id`, `islem_turu`, `yerine_gecen_id`,
  `etki.borc_id`) ve Aşama 7'nin mükerrerlik tabloları bu şemada yoktur;
  `okuma_satir.aday_grup_id` yer tutucudur. Tam Plan'daki `gonderim` tablosu
  Yürütme Planı 4.2 listesinde olmadığı için kurulmadı.

**Durum listeleri (karar, 2026-09-16).** Tam Plan belge, satır ve nesne
durumlarını (C08) vermişti; şu listeler açıktı, Claude önerdi, Abdüllatif
onayladı: nesne durumlarına `ONAY_BEKLIYOR` eklendi (C08'in nesne listesi
`AKTIF`/`ENGELLI`/`PASIF`/`SILINDI` idi; 4.4 kararı: nesne onaydan önce bu
etiketle yazılır); kayıt `AKTIF`/`GECERSIZ`; okuma `ACIK`/`TAMAMLANDI`/`IPTAL`;
kaynak rolü `ASIL`/`DESTEK`, kaynak durumu `AKTIF`/`KALDIRILDI`; onay türü
`NESNE_ACILISI` (diğerleri kendi aşamalarında), onay durumu
`BEKLIYOR`/`ONAYLANDI`/`REDDEDILDI`. Ayrıca plandan: değer türü
`METIN`/`TAMSAYI`/`ONDALIK`/`TARIH`/`MANTIKSAL`/`JSON`, denetim aktörü
`COWORK`/`KULLANICI`/`UYGULAMA`. Hepsi `sozlesmeler.py`'de `StrEnum`.
Tek defter kararıyla 11.2'deki `DEFTER_UYUSMAZLIGI` kodu `HEDEF_BULUNAMADI`
oldu (verilen kimlikte kayıt yok).

Sürüm denetimi (`sema.py`): `BEKLENEN_SEMA_SURUMU = "0001"`.
`semayi_denetle` veritabanındaki Alembic sürümünü okur; kurulmamış ya da
farklıysa `SemaSurumuUyumsuz` verir, eski şemaya yazılmaz. `semayi_yukselt`
migration'ları tek yazma işleminde (`BEGIN IMMEDIATE`) uygular, ardından
`foreign_key_check` ve `integrity_check` çalıştırır. Komut satırı:
`uv run alembic upgrade head` (yol `DEFTERIKI_*` ayarlarından;
`alembic.ini`'de URL yok, yollar `%(here)s` ile ini dosyasına göre).

Test (`tests/test_sema.py`): boş veritabanına kurulum on beş tablo, hiçbir
tabloda defter kimliği yok; `foreign_key_check`/`integrity_check` temiz;
metadata ile migration arasında fark yok; sürüm denetimi (kurulmamış, farklı
sürüm); tekrar yükseltme; geri alma bütün tabloları kaldırır; kısıtlar
veritabanında çalışır (izinsiz durum, olmayan nesneye kayıt, negatif tutar,
TRY dışı para birimi, kendine bağlantı, boş alan adı, aynı alan adı iki kez,
aynı dosya iki belge olamaz, kimlik yeniden kullanılmaz); komut satırından
yükseltme başka çalışma dizininden ayarlardaki yolu bulur.

Test (`tests/test_veritabani.py`, `tests/test_sozlesmeler.py`): PRAGMA
değerleri; iki ayrı süreç aynı ayarlarla aynı dosyayı çözer ve birbirinin
yazdığını okur; FK ihlali reddedilir; hata sonrası yarım satır kalmaz; kilit
tutulurken `BEGIN IMMEDIATE` salt SELECT'i bile bekletir ve süre dolunca
`VERITABANI_MESGUL` verir; yazar okumayı engellemez; import dosya yaratmaz;
Hypothesis ile `KurusTutar` sınırları (negatif, float, bool reddi).

## Onay talebi, işlem anahtarı, denetim olayı

Teslim 4.3. Ekran ve MCP yok; işlev ve test düzeyi. Bütün işlevler bir
`Session` alır ve **commit yapmaz**: işlem sahibi çağırandır
(`Veritabani.yazma_islemi`). Bir işlev ortada düşerse aynı işlemdeki her şey
(talep, anahtar kaydı, denetim olayı, hedef değişikliği) geri alınır; testli.

**Tek defter kararının etkisi.** 4.3'ün ilk hâli "defter tanımla + onay"
işlevini içeriyordu; Abdüllatif ayrı defter istemediğini söyleyince
(sözlük: Defter) `defterler.py` ve testleri kaldırıldı, işlem anahtarının
`SISTEM`/`DEFTER` kapsamı düştü, onay ve denetim işlevleri defter
parametresinden arındı. İlk onay türü `NESNE_ACILISI`, etkisi 4.4'te.

**İşlem anahtarı** (`src/defteriki/islem_anahtarlari.py`, K08). Her yazma
işlevi anahtar alır; `(arac_adi, anahtar)` benzersiz. Aynı anahtar aynı
içerikle gelirse saklı sonuç döner, hiçbir şey yeniden yazılmaz
(`zaten_vardi=True`); farklı içerik `ANAHTAR_ICERIK_CAKISMASI`. İçerik
karşılaştırması isteğin kanonik JSON'unun SHA-256 özetiyle yapılır, ham istek
saklanmaz. Anahtar kaydı, iş sonucu ve denetim olayı aynı işlemde; iş ortada
düşerse anahtar kaydı da gider.

**Onay talebi** (`src/defteriki/onaylar.py`, C12). `talep_olustur` kalıcı
`BEKLIYOR` talep açar; kullanıcı beklerken açık transaction ya da kilit
tutulmaz (testli: talep yazıldıktan hemen sonra başka bağlantı yazma kilidi
alabilir). `bekleyenleri_listele` yalnız `BEKLIYOR` olanları verir.
`karar_uygula(talep_id, gorulen_hedef_surumu, karar)` **yalnız ekrana
açılır**; MCP kapısına "kullanıcı onayladı" parametresi hiç sunulmaz. Sürüm
denetimi: talebin taşıdığı sürüm, kullanıcının ekranda gördüğü sürüm ve
hedefin güncel sürümü üçü aynı değilse `HEDEF_SURUMU_DEGISTI`, hiçbir şey
yazılmaz. Sonuçlanmış talebe yeniden karar verilemez; hedefi silinmiş talep
`HEDEF_BULUNAMADI`. Karar etkisi türe göre kayıtlıdır (`KARAR_ETKILERI`);
`NESNE_ACILISI` etkisini 4.4'te `nesneler.py` kaydeder, testler kendi
etkisini kaydederek mekanizmayı sınar.

**Denetim olayı** (`src/defteriki/denetim.py`). Her yazma aynı işlemde
`denetim_olay` satırı bırakır: aktör (`COWORK`/`KULLANICI`/`UYGULAMA`),
eylem, hedef (`tablo:kimlik`), önceki/sonraki durum, işlem anahtarı kaydı.
Kişisel veri taşımaz.

Test (`tests/test_islem_anahtarlari.py`, `tests/test_onaylar.py`): yeni
anahtar işlevi çalıştırır ve sonucu saklar; aynı anahtar aynı içerik saklı
sonucu verir, işlev çalışmaz; farklı içerik çakışır; aynı anahtar farklı araç
ayrı sayılır; boş anahtar reddi; işlev hatası anahtar kaydını geri alır;
talep `BEKLIYOR` doğar ve denetim olayı yazar; kilit tutulmaz; onay hedefi
`AKTIF` yapar ve sürümü artırır, red `PASIF`; eski sürümle karar reddedilir
ve yazılmaz; hedef arkadan değişirse talep eskir; sonuçlanmış talebe yeniden
karar yok; hedefi silinmiş talep; bekleyenler ve sayfalama; karar hatası
her şeyi geri alır.

## Nesne tanıtma

Teslim 4.4 (`src/defteriki/nesneler.py`). Kurum, banka, hesap, kart: hepsi
**nesne**, tür sütunu yok (sözlük: Nesne; K11, K12). Nesnenin ne olduğunu
Cowork'un yazdığı serbest özellikler ve hiyerarşideki yeri anlatır.

**Abdüllatif'in kuralı (2026-09-16).** Hiçbir nesne belgesiz, toplu ya da
önceden açılmaz. Garanti BBVA'dan ME adına ekstre geldi → banka ve yalnız
ME hesabı açılır. Ertesi gün GK ekstresi geldi → Cowork önce arar
(`nesne_bul`), Garanti zaten var, yalnız GK hesabı onun altına eklenir.
Başka isme ekstre gelmezse başka hesap açılmaz. Bu akış uçtan uca testtir
(`test_garanti_akisi_banka_ve_hesaplar_tek_tek_acilir`).

**Akış.** `tanitma_formu()` boş formu ve kuralları verir, veritabanına
dokunmaz (FORM, K12). `nesne_tanimla(ozellikler, islem_anahtari, aktor,
ust_idleri, kaynak)` GONDER adımıdır: nesne `ONAY_BEKLIYOR` durumunda
yazılır; özellikler, üst bağlantıları ve varsa kaynak belge aynı işlemde;
`NESNE_ACILISI` onay talebi açılır (içeriğinde alan/değer listesi, seviye,
üstler, kaynak). Karar (yalnız ekran, `onaylar.karar_uygula`): kullanıcı
özelliklerden 0..n şart seçer (`Karar.secilen_sartlar`, K14); şartlar
`nesne_sart`a yazılır, nesne `AKTIF`, sürüm artar. Red: nesne `SILINDI`
(kimlik saklı). Şart yalnız saklanır; eşleşme taraması ve şüphe Aşama 7'de.
Onay bekleyen üst kabul edilir: Garanti ile ME hesabı aynı anda önerilebilir.

**Seviye (K11).** Cowork seviye göndermez. Üst yoksa 0; varsa üstlerin
seviyesi + 1. Üstler aynı seviyede olmalı (`SEVIYE_CAKISMASI`); aynı üst
iki kez, olmayan üst (`HEDEF_BULUNAMADI`), engelli üst (`NESNE_ENGELLI`),
pasif ya da silinmiş üst reddedilir. Bir nesne birden fazla üste bağlanabilir
(S02: fiş hem karta hem hesaba).

**Özellikler.** En az bir özellik (C13). Alan adında normalizasyon yok:
`" IBAN"`, `"IBAN"`, `"iban"` üç ayrı alandır (C05); boş ad ve aynı nesnede
aynı ad iki kez reddedilir. Sınırlar (C18): nesne başına 200 özellik, alan
adı 128, değer 4.096 karakter; aşılırsa açık hata, veri kesilmez. Değer türü
Cowork verebilir; vermezse Python türünden çıkarılır (bool → MANTIKSAL,
int → TAMSAYI, float/Decimal → ONDALIK, str → METIN, liste/sözlük → JSON;
TARIH yalnız açıkça). Türe uymayan değer reddedilir; ONDALIK `Decimal`
olarak saklanır, TARIH ISO. `eslesme_degeri` türüyle kararlı seri hâl
(`METIN:123` ≠ `TAMSAYI:123`; `2.5` = `2.50`; boş değer `None`, eşleşme
üretmez). Özellik ve şart güncelleme işlevi yoktur (K13).

**Bulma ve getirme.** `nesne_bul(alan_adi, deger, deger_turu, seviye,
durumlar)` alan adı ve türüyle değer üzerinden arar; Cowork yeni nesne
açmadan önce mevcut olanı bununla bulur. `nesne_getir` özellikleri (şart
işaretiyle), üstleri ve altları verir. `aktif_nesneyi_getir` finansal yazma
için: `AKTIF` değilse açık hata.

**Kaynak (C13).** `NesneKaynagi(belge_id, okuma_id, konum)` verilirse
`nesne_kaynak`a yazılır; belge yoksa `HEDEF_BULUNAMADI`. Kurum belgesiz
açılabilir; kaynak zorunlu değil.

**S03 kapsam dışı.** "Başka defterdeki nesneye bağlantı" senaryosu tek
defter kararıyla anlamsızlaştı; test yok.

Test (`tests/test_nesneler.py`): Garanti akışı uçtan uca; GONDER
`ONAY_BEKLIYOR` + talep; aynı anahtar aynı nesne, farklı içerik çakışma; hata
her şeyi geri alır; seviye 0/1/2; S02 iki üst; S01 farklı seviyeli üstler
`SEVIYE_CAKISMASI`; olmayan/engelli/pasif üst; aynı üst iki kez; en az bir
özellik; boş alan adı; aynı alan adı iki kez; alan adı normalize edilmez;
sınır aşımı (201 özellik, 129 ve 4.097 karakter); tür çıkarımı ve eşleşme
değeri; türe uymayan değer; şartsız onay `AKTIF`; şart seçimi kalıcı ve
tekrarsız; başka nesnenin özelliği şart olamaz; red `SILINDI`; onay bekleyen
üst; kaynak belge kaydı ve olmayan belge reddi; kurum belgesiz; bulma
filtreleri (alan, değer türüyle, seviye, durum, boş değer); form veritabanına
dokunmaz; denetim olayları ve anahtar kaydı.

## Belge arşivi ve belge akışı

Teslim 4.5 (`src/defteriki/arsiv.py`, `src/defteriki/belgeler.py`). Ekran ve
MCP aracı yok; işlev ve test düzeyi. Cowork'un belgeyi gelen dizinine
bırakıp yolunu vermesi Aşama 3.3'te ölçülen yöntemdir (C10); parça yükleme
gerekmediği için yazılmadı.

**Arşiv (`arsiv.py`).** `dosyayi_arsivle(yol, gelen_dizini, belge_dizini)`
yolu 3.3'teki sırayla denetler (mutlak, `..` yok, gerçek yol izinli gelen
dizininin altında, simgesel bağlantı ya da takma yol değil, sıradan dosya;
red `GIRDI_GECERSIZ` + kategorik gerekçe, mesajda yol yok), dosyayı
`<belge dizini>/gecici/<rastgele>.tmp` adına akışla kopyalarken SHA-256 ve
boyutu hesaplar, 50 MiB sınırını (C18) aşınca keser, `fsync` sonrası
`os.replace` ile `<ilk iki hex>/<sha256>` yoluna atomik taşır. Herhangi bir
adım düşerse geçici dosya silinir; yarım kopya kalmaz.

**Karar (2026-09-16, Abdüllatif): fiziksel kimlik yalnız SHA-256.** Arşiv
yolu içerikten deterministik türer ve uzantı taşımaz; SHA-256 fiziksel
kimliğin tek kaynağıdır. Aynı baytlar hangi adla, hangi uzantıyla ya da
uzantısız gelirse gelsin tek fiziksel dosyaya karşılık gelir; hedef zaten
varsa kopya atılır, "aynı SHA ile başlayan dosya" araması yapılmaz. Uzantı,
MIME ve kaynak dosya adı metadata'dır; `arsiv_dosya.uzanti`, `mime`,
`kaynak_adi` sütunlarında saklanır ve ilk gelişteki değerler kalır (aynı
içerik sonra başka adla gelirse metadata değişmez). İki süreç aynı içeriği
aynı anda arşivlerse ikisi de aynı baytları aynı yola bırakır; `os.replace`
atomiktir, sonuç tek dosyadır; Windows'ta hedef o an açıksa taşıma
reddedilir, hedef yerinde ve doğru boyuttaysa "zaten vardı" sayılır.

Giriş kapısı denetimi aynen durur: MIME ilk baytların imzasından (PDF, PNG,
JPEG) belirlenir; imza biliniyorsa uzantı onunla uyuşmalı (PDF içerik
`.png` ya da `.xyz` adıyla reddedilir, uzantısız kabul edilir), imza
bilinmiyorsa uzantıdan tahmin, o da yoksa `application/octet-stream`. Boş
dosya belge olamaz. `arsivde_var_mi` dosyanın yerinde ve kayıtlı boyutta
olduğunu söyler (okuma başlatma ön şartı).

**Belge alma.** `belge_al(veritabani, yol, ...)` C10 akışıdır: önce
arşivler, sonra kısa yazma işleminde `belge_tanimla` çağırır. Dosya ve
veritabanı tek işlem değildir (Tam Plan 8.1): veritabanı düşerse dosya
arşivde sahipsiz kalır, kaynaksız kayıt oluşmaz (sahipsiz dosya uzlaştırması
Aşama 9). `belge_tanimla` `arsiv_dosya` + `ARSIVLENDI` belge yazar; aynı
sha256 daha önce belge olduysa o belge döner, `zaten_vardi=True`, hiçbir şey
yazılmaz (K18, `UNIQUE(belge.dosya_id)`). İşlem anahtarı zorunlu (araç adı
`belge_al`).

**Okuma.** `okuma_baslat(belge_id, sema_surumu, belge_dizini, icerik,
tamlik)` yalnız `ARSIVLENDI` belgede sürüm 1 okumayı `ACIK` açar, belge
`OKUNUYOR`. Arşiv dosyası diskte yerinde değilse `ARSIV_EKSIK` (S10);
belge yoksa `BELGE_YOK`. `sema_surumu` Cowork'un uyduğu okuma sözleşmesinin
sürümüdür; Aşama 5'te `docs/cowork.md` ile sabitlenir, şimdilik boş olmayan
kısa metin. `Tamlik(beklenen_satir_sayisi, acilis_bakiyesi_kurus,
kapanis_bakiyesi_kurus, toplam_giris_kurus, toplam_cikis_kurus)` isteğe
bağlıdır; verilmeyen alan "bilinmiyor", "belgenin tamamı okundu" iddiası
üretilmez. Yeni okuma sürümü (düzeltme akışı) Aşama 8.3'te.

**Gönderim (K07).** `satir_gonder(okuma_id, satirlar)` tek paketi `ACIK`
okumaya yazar: `SatirGirdisi(satir_anahtari, konum, ham, durum)`. Paket önce
baştan sona doğrulanır; tek satırda bile biçim hatası varsa (boş ya da 128
karakteri aşan anahtar, pakette aynı anahtar iki kez, negatif ya da tam sayı
olmayan konum, boş ya da JSON'a çevrilemeyen ya da 4.096 karakteri aşan ham,
gönderilemez durum) hiçbir satır yazılmaz, hata satırın konumunu söyler
(S11). Sınırlar (C18): 500 satır, 2 MiB. Aynı okumada aynı satır anahtarı
aynı içerikle yeniden gelirse tekrar gönderimdir, satır `zaten_mevcut`
listesine girer; içerik farklıysa `ANAHTAR_ICERIK_CAKISMASI` ve paket
bütünüyle düşer. Satır durumu gönderimle gelir: `YAZILDI` ya da
`KAPSAM_DISI` (başlık/bilgi satırı). Finansal satır için `satir_gonder`
değil `kayitlar.hareket_yaz` kullanılır: satırı aynı gönderimde kabul eder
(`satirlari_kabul_et` çekirdeği ortak), kayıt ve etkiyi üretir, `YAZILDI`
yazar. `satir_gonder` kayıtsız satırlar (başlık, bilgi) içindir. **Karar
notu:** C08'de kabul ile kayıt arasında ara satır durumu yok; gerekirse
listeye Abdüllatif'in onayıyla eklenir.

**Tamamlama ve belge kaydı (K19, C07).** `okuma_tamamla(okuma_id, tamlik)`
Cowork'un "bitti" bildirimidir: okuma `TAMAMLANDI`, belge `HAZIR`, ardından
**uygulama** belge kaydını tanımlar (aktör `UYGULAMA`): belge `KAYITLI`,
`etkin_okuma_id` bu okuma; ek onay yok. Koşullar: her satır sonuçlanmış
(`YAZILDI`, `MEVCUDA_BAGLANDI`, `KAPSAM_DISI`; aksi `BELGE_HAZIR_DEGIL`) ve
tamlıkta beklenen satır sayısı verildiyse yazılan satır sayısıyla aynı (aksi
`MUTABAKAT_FARKI`). Koşul sağlanmazsa hiçbir durum değişmez: okuma `ACIK`
kalır, eksik satır gönderilip yeniden tamamlanır. Bu teslimde mutabakat
yalnız satır sayısıdır; bakiye ve toplam alanları saklanır, etkilerle
karşılaştırma 4.6'da `hesaplamalar` gelince eklenir; açık şüphe koşulu
Aşama 7'de. `belge_kaydet(belge_id, gorulen_surum)` `HAZIR` kalmış belgeyi
(Aşama 7'de karar sonrası) koşulları yeniden denetleyerek `KAYITLI` yapar;
sürüm uyuşmazsa `HEDEF_SURUMU_DEGISTI`. Belge sürümü her durum
değişiminde bir artar (ARSIVLENDI 1 → OKUNUYOR 2 → HAZIR 3 → KAYITLI 4).

Her yazma işlevi işlem anahtarı ister, denetim olayı yazar, commit yapmaz.
Denetim izi: `belge_al`, `okuma_baslat`, `satir_gonder`, `okuma_tamamla`,
`belge_hazir`, `belge_kaydet`.

Test (`tests/test_arsiv.py`): içerik adresli (uzantısız) atomik taşıma ve
geçici dosya kalmaması; aynı içerik farklı ad / aynı ad / uzantısız /
bilinmeyen uzantı / bilinen uzantıyla gelince tek fiziksel dosya, ad ve
uzantı metadata; imzalı içerik bilinmeyen uzantıyla kapıda ret; parçalı
okuma ve özet; sınır
aşımı ve kopya ortasında hata sonrası yarım kopya yok; boş dosya; MIME
imzadan/uzantıdan; uzantı-içerik uyuşmazlığı; 3.3 yol kuralları (göreli,
`..`, olmayan, dizin dışı, dizin, dışarıya ve içeriye simgesel bağlantı;
bağlantı testleri Windows'ta yetki yoksa atlanır).
Test (`tests/test_belgeler.py`): uçtan uca ARSIVLENDI → KAYITLI (durumlar,
sürümler, etkin okuma, satırlar, denetim izi, kaydı uygulama tanımlar); aynı
dosya iki kez tek belge; aynı anahtar saklı sonuç / farklı dosya çakışma;
farklı içerik ayrı belge; veritabanı düşerse dosya arşivde belge yok; izinsiz
yol; S10 (belgesiz okuma, arşiv dosyası silinmiş, olmayan okumaya satır);
ikinci okuma açılmaz; şema sürümü ve tamlık doğrulama (negatif bakiye
kabul); S11 on biçim hatası paketin tamamını düşürür; boş ve 501 satırlık
paket; tekrar gönderim mevcut/çakışma; aynı işlem anahtarı; kapalı okumaya
satır; mutabakat farkı hiçbir durumu değiştirmez ve eksik satırla tamamlanır;
tamamlarken tamlık; tamlıksız sıfır satır; yeniden tamamlama; hata her şeyi
geri alır; `belge_kaydet` HAZIR → KAYITLI, eski sürüm, hazır olmayan belge;
sonuçlanmamış satır kaydı engeller; dört ayrı süreç aynı içeriği farklı
adlarla aynı anda getirir → arşivde tek dosya, tek `arsiv_dosya`, tek belge,
dört işlem anahtarı, geçici dosya yok.

## Hareket yazma ve etkin bakiye

Teslim 4.6 (`src/defteriki/finansal_kurallar.py`, `kayitlar.py`,
`hesaplamalar.py`). Ekran ve MCP aracı yok; işlev ve test düzeyi.

**Sözleşme (C02).** Finansal davranış nesne türüyle değil işlem
sözleşmesiyle belirlenir. Bu teslimde tek sözleşme: `HESAP_HAREKETI`, yani
belirlenen nesnede `VARLIK` ekseninde `ARTTIR` ya da `AZALT`; gelen para
gelir, çıkan para gider sayılmaz (gider anlamı Aşama 8'in sözleşmeleriyle).
`finansal_kurallar.hesap_hareketi_dogrula(HesapHareketi)` saf işlevdir,
veritabanına dokunmaz: nesne kimliği katı, yön `ARTTIR`/`AZALT`, tutar kuruş
cinsinden pozitif tam sayı (S20: `float`, `bool`, metin, `Decimal`, sıfır ve
64 bit taşma açık ret, sessiz yuvarlama yok), para birimi yalnız TRY, işlem
tarihi zorunlu ve valör isteğe bağlı (`date` ya da `YYYY-AA-GG`; `datetime`
reddedilir), açıklama en çok 512 karakter. Çıktı `HareketTaslagi`: kayıt
alanları + tek `VARLIK` etkisi.

**Yazma (`kayitlar.hareket_yaz`).** Sözlükteki anlamıyla *yazmaktır*, kayıt
etmek değil. `hareket_yaz(okuma_id, satir, hareket, islem_anahtari, aktor)`
satırı aynı gönderimde kabul eder (`belgeler.satirlari_kabul_et`; biçim
hatası paketi düşürür, K07), nesnenin `AKTIF` olduğunu denetler
(`ONAY_BEKLIYOR`/`PASIF`/`SILINDI` ret, `ENGELLI` → `NESNE_ENGELLI`), tek
işlemde `kayit` (AKTIF) + `etki` + `kayit_kaynak` (ASIL, AKTIF) yazar ve
denetim olayı düşer. Kaynak satırı zorunludur (K06, S10): okumasız, olmayan
ya da kapalı okumaya hareket yazılmaz; `KAPSAM_DISI` satıra hareket
bağlanmaz. İşlem anahtarı zorunlu (K08, S18 tek süreç): aynı anahtar aynı
içerik saklı sonuç, tek etki; farklı içerik `ANAHTAR_ICERIK_CAKISMASI`.
Aynı satır anahtarı başka işlem anahtarıyla yeniden gelirse (Tam Plan
8.5.1): hareket mevcut kayıtla aynıysa tekrar gönderim, mevcut kayıt döner;
tutar, yön ya da para birimi farklıysa `KAYNAK_CAKISMASI`. Kaydı olmayan
mevcut satıra (4.5 `satir_gonder` ile yazılmış) kayıt bağlanır. Hareket
mükerrerliği karşılaştırması (referans, tarih + tutar + yön) Aşama 8.2'de.

**Etkin bakiye (`hesaplamalar`).** Tam Plan 10.3: `etkin(etki)` = en az bir
KAYITLI ve geçerli kaynak desteği. `etkin_bakiye(nesne_id, eksen,
para_birimi, tarih)` yalnız etkin etkileri toplar: kaynak bağı `AKTIF`,
kaynak satırının okuması belgenin etkin okuması (`belge.etkin_okuma_id`),
belge `KAYITLI`, kayıt `AKTIF`; tarih sınırı dahil; ARTTIR − AZALT. Her
etkinin desteği `EXISTS` ile seçilir, her etki bir kez toplanır (çifte
toplama engeli, 8.5.5). Yazılmış ama belgesi henüz `KAYITLI` olmayan
kayıtlar `bekleyen_kayit_sayisi` olarak ayrıca sayılır, bakiyeye girmez
(K19). `hareketleri_listele(nesne_id, eksen, baslangic, bitis, sayfalama)`
tarih ve kimlik sırasıyla döner; her satırda `kayitli` bayrağı (yazılmış /
kayıtlı ayrımı). Toplamlar SQL'de; GUI ve MCP aynı işlevi çağıracak.

Test (`tests/test_finansal_kurallar.py`): geçerli hareket tek VARLIK
etkisi; tarih metin, valör ve açıklama isteğe bağlı; S20 tutar reddi
(`12.0`, `12.5`, `True`, `False`, `"100"`, `"12,50"`, `Decimal`, `None`,
`-1`, `0`), taşma sınırı; Hypothesis: pozitif tam sayı her zaman kabul,
sıfır/negatif/taşma ve float/bool her zaman ret; kimlik, yön, para birimi,
tarih biçimi, açıklama; saf işlev veritabanına dokunmaz.
Test (`tests/test_kayitlar.py`): kayıt + etki + kaynak + satır tek işlemde,
denetim olayı; S18 aynı anahtar iki kez tek etki, farklı içerik çakışma;
aynı satır farklı anahtar aynı hareket tekrar gönderim; aynı satıra farklı
tutar/yön `KAYNAK_CAKISMASI`; aynı satır anahtarı farklı ham paket düşer;
kaydı olmayan mevcut satıra kayıt bağlanır; S10 olmayan ve kapalı okuma;
`KAPSAM_DISI` satır; biçim hatalı satır hareketi de düşürür; geçersiz tutar
veritabanına dokunmadan ret; onay bekleyen, engelli ve olmayan nesne; hata
her şeyi geri alır; uçtan uca hareketli belge `KAYITLI`.
Test (`tests/test_hesaplamalar.py`): boş hesap sıfır; yazılmış ama kayıtsız
belge bakiyeye girmez, `KAYITLI` olunca girer (bekleyen sayısı ve `kayitli`
bayrağı); iki belge ayrı ayrı kayıtlı olur, tarih sınırı; başka nesne ve
başka eksen karışmaz; `GECERSIZ` kayıt, kaldırılmış kaynak desteği ve
`GECERSIZ` belge toplanmaz; etkin olmayan okuma sürümü sayılmaz; hareket
listesi sıralı, filtreli, sayfalı; Hypothesis: rastgele ARTTIR/AZALT dizisi
için kayıt öncesi bakiye 0, sonrası ARTTIR − AZALT, bekleyen sayısı geçişi.

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
  sema.py         on beş tablo (METADATA), şema sürümü denetimi ve yükseltme
  islem_anahtarlari.py  işlem anahtarı koruması (aynı anahtar aynı sonuç, K08)
  denetim.py      denetim olayı yazımı
  onaylar.py      onay talebi: oluştur, listele, karar uygula (yalnız ekran)
  nesneler.py     nesne tanıtma (FORM/GONDER), seviye, şart seçimi etkisi, bulma
  arsiv.py        gelen dizini denetimi, akışla kopya ve SHA-256, atomik taşıma
  belgeler.py     belge alma/tanımlama, okuma, satır gönderimi, tamamlama, belge kaydı
  finansal_kurallar.py  işlem sözleşmeleri (yalnız HESAP_HAREKETI), saf doğrulama
  kayitlar.py     hareket yazma: kayıt + etki + kaynak bağı, tek işlem
  hesaplamalar.py etkin bakiye (yalnız KAYITLI belge, EXISTS), hareket listesi
migrations/       Alembic ortamı (env.py) ve sürümler (versions/0001_ilk_sema.py)
alembic.ini       Alembic ayarı; URL yok, yol ayarlardan
tests/            pytest testleri
scripts/          geliştirme betikleri (kontrol.py)
.pre-commit-config.yaml  commit öncesi kanca; kontrol.py'yi çalıştırır
kavramlar_sozlugu.md   ortak kavram tanımları (Defter, Nesne, Mükerrerlik, Yazmak/kayıt etmek ...); değişiklik yalnız Abdüllatif'in onayıyla
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

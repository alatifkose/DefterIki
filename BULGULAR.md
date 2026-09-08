# DEFTERIKI — BULGULAR

Çalışma sırasında ortaya çıkan sorunlar, nasıl çözüldükleri ve mevcut durumları.
Mimari kararlar burada değil, `KARARLAR.md` içindedir.

Durum: **AÇIK** / **ÇÖZÜLDÜ** / **ŞİMDİLİK KABUL**

---

## B-001 — CRLF satır sonu yüzünden sahte diff

**Bulundu:** 8 Eylül 2026 · **Durum:** ÇÖZÜLDÜ (8 Eylül 2026)

**Sorun:** `git status`, `alembic.ini`, `alembic/env.py`, `pyproject.toml` ve `uv.lock`
dosyalarını değişmiş gösteriyordu; toplam 834 satır eklenmiş, 834 satır silinmiş görünüyordu.
İçerikte tek karakter fark yoktu — dosyalar depoya LF ile girmiş, Windows'ta CRLF'e dönmüştü.

**Etkisi:** Her dosyaya dokunuşta diff'in tamamı "değişti" görünür; gerçek değişiklik bu
gürültünün içinde kaybolur, kod gözden geçirmesi ve commit hijyeni imkânsızlaşır.

**Kök neden:** Depoda `.gitattributes` yok, `core.autocrlf` ayarlanmamış. Satır sonu kuralı
hiçbir yerde tanımlı değildi.

**Çözüm:** `.gitattributes` eklendi (`* text=auto eol=lf`, ikili uzantılar binary),
`git add --renormalize .` çalıştırıldı. Dört dosya artık temiz; `git status` yalnızca gerçek
değişiklikleri gösteriyor. Karar `KARARLAR.md` K-003 olarak kaydedildi.

---

## B-002 — Cowork, .git içindeki kilit ve geçici dosyaları silemiyordu

**Bulundu:** 8 Eylül 2026 · **Durum:** ÇÖZÜLDÜ (oturum bazlı — her yeni oturumda geri gelir)

**Sorun:** Cowork'ün bilgisayardaki kabuğu varsayılan olarak dosya silemiyor. Git ise normal
çalışırken `.git/index.lock` ve `.git/objects/tmp_obj_*` gibi dosyaları oluşturup siliyor.
Silinemeyince `.git` içinde artık dosyalar birikti ve kalan `index.lock` sonraki git
işlemlerini bloke edecek durumdaydı.

**Etkisi:** Commit ve index yazan git komutları takılır; `.git` klasörü çöp biriktirir.

**Çözüm:** Klasör için silme izni istendi ve verildi; artık dosyalar temizlendi.

**Not:** Bu izin oturuma özeldir. Yeni bir Cowork oturumunda git yazma işlemi takılırsa
sebebi budur; izin yeniden istenmelidir.

---

## B-003 — pre-commit kancaları Cowork'ün kabuğundan çalışmıyor

**Bulundu:** 8 Eylül 2026 · **Durum:** ŞİMDİLİK KABUL

**Sorun:** `.git/hooks/pre-commit` Windows'ta üretilmiş: satır sonları CRLF olduğu için
shebang bozuk okunuyor ve içindeki yorumlayıcı yolu Windows'a bakıyor
(`...\.venv\Scripts\python.exe`). Cowork'ün kabuğu Linux tarafında çalıştığından kanca
"No such file or directory" ile düşüyor ve commit tamamen engelleniyor.

**Etkisi:** Cowork'ten yapılan commit'lerde ruff ve pyright çalışmaz; commit ancak
`--no-verify` ile alınabilir. Python kodu bu yoldan commit'lenirse kalite kapısı atlanmış
olur.

**Şimdilik kabul, çünkü:** Klasördeki `.venv` bir Windows sanal ortamı; Linux tarafında
kullanılamıyor. Aynı klasöre ikinci bir sanal ortam kurmak iki ortamı senkron tutma yükü
getirir ve bugünkü sorunu çözmez.

**Kural:** Python kodu içeren commit'ler Windows tarafından (Claude Code veya terminal)
alınır — kalite kapısı orada çalışır. Cowork yalnızca belge/metin dosyalarını `--no-verify`
ile commit'ler; kod commit'lemez.

**Doğrulandı (8 Eylül 2026):** Kanca Claude Code'un Windows kabuğundan sorunsuz çalışıyor —
`ruff check`, `ruff format` ve `pyright` commit sırasında koşup geçti. Sorun gerçekten
Cowork'ün Linux kabuğuna özeldir; kuralın "Windows tarafı" kısmı işliyor.

---

## B-004 — Katman testi `__init__.py` içindeki göreli importu bir seviye kayık çözüyordu

**Bulundu:** 8 Eylül 2026 (proje incelemesi) · **Durum:** ÇÖZÜLDÜ (8 Eylül 2026)

**Sorun:** `tests/test_katmanlar.py` `from .x import y` biçimindeki importu modül adından
`level` kadar parça atarak çözüyordu. Python ise göreli importu modülün *paketine* göre
çözer; `__init__.py` için paket modülün kendisidir, dolayısıyla bir seviye daha az atılır.
`temel/__init__.py` içindeki `from . import veritabani`, test tarafından
`defteriki.cekirdek.veritabani` sanılıyordu.

**Etkisi:** Bugün kodda göreli import olmadığı için görünmüyordu. İlk `__init__` yeniden dışa
aktarımında test ya yanlış yerden kırılır ya da gerçek bir ihlali kaçırırdı.

**Çözüm:** `_ic_importlar` artık modülün paket olup olmadığını (`paket_mi`) biliyor; çözüm
Python kuralıyla birebir. Dört durumu (modül/paket × bir/çok seviye) sınayan test eklendi.

---

## B-005 — "create_engine yalnız veritabani.py'de" kuralı env.py ile çelişiyordu

**Bulundu:** 8 Eylül 2026 (proje incelemesi) · **Durum:** ÇÖZÜLDÜ (8 Eylül 2026)

**Sorun:** README ve `veritabani.py` docstring'i `create_engine`'in yalnız orada çağrıldığını
yazıyordu; `alembic/env.py` ise kendi motorunu pragmasız kuruyordu. Kod haklıydı, belge
eksikti: SQLite batch modu tabloyu düşürüp yeniden kurarken yabancı anahtar açık olursa
bağlı satırlar silinebilir ya da göç kısıt hatasıyla durur.

**Etkisi:** Kuralı okuyan biri env.py'yi `motor_kur`a "düzeltir", göçler yabancı anahtar
açıkken koşmaya başlar; hata ilk gerçek tablo yeniden kurulumunda ve sessizce çıkar.

**Çözüm:** İstisna K-004 ekine, README kuralına, env.py yorumuna ve `veritabani.py`
docstring'ine yazıldı. İki test eklendi: `test_gocler` env.py'nin pragmasız ve `motor_kur`suz
kaldığını, `test_veritabani` paket içinde `create_engine`'in yalnız `veritabani.py`de
geçtiğini sınar.

---

## B-006 — Göç şablonu ruff'ın UP kurallarıyla çelişiyordu

**Bulundu:** 8 Eylül 2026 (proje incelemesi) · **Durum:** ÇÖZÜLDÜ (8 Eylül 2026)

**Sorun:** `alembic/script.py.mako` Alembic'in varsayılanıydı: `typing.Union`,
`typing.Sequence`, isort'a aykırı import sırası. Üretilen ilk göç dosyasını pre-commit
`--fix` ile commit anında yeniden yazacaktı; dosya diske düşen hâliyle depoya girmeyecekti.

**Çözüm:** Şablon `collections.abc.Sequence` ve `X | Y` tiplerine çevrildi, import sırası
düzeltildi. `alembic.ini` içine `post_write_hooks` eklendi: `alembic revision` dosyayı
yazar yazmaz `ruff check --fix` ve `ruff format` koşar (`module` tipi, PATH'e bağımlı
değil). Bir deneme revizyonu üretilip ruff, pyright ve gerçek `upgrade head` ile doğrulandı,
sonra silindi.

**Not:** Boş (elle yazılacak) bir revizyonda kullanılmayan `sa` ve `op` importlarını ruff
kaldırır; elle göç yazan kişi gerekeni geri ekler. Otomatik üretilen göçte ikisi de
kullanıldığı için kalır. `alembic/` klasörü pyright kapsamındadır (strict); üretilen göç
dosyası da bu denetimden geçer. *(Not 8 Eylül 2026'da düzeltildi: önceki metin klasörü
kapsam dışı gösteriyordu, kapsama alındıktan sonra güncellenmemişti.)*

---

## B-007 — Belgelere `\b` yerine gerçek backspace baytı sızmıştı

**Bulundu:** 8 Eylül 2026 (inşa öncesi inceleme) · **Durum:** ÇÖZÜLDÜ (8 Eylül 2026)

**Sorun:** README ve K-011'de arşiv yolu `DefterIkielgeler` görünüyordu. Dosyada iki
karakterlik `\b` değil, tek bir 0x08 (backspace) baytı vardı: metin bir kabuk heredoc'u
içinden Python'a geçerken `\\b` önce `\b`ye, sonra kaçış çözümüyle backspace'e dönmüştü.
Aynı sebeple `grep DefterIkielgeler` eşleşmiyordu; bayt ancak `grep -c $'\x08'` ile görüldü.

**Etkisi:** Belge yanlış yolu gösteriyor, arama ile bulunamıyordu.

**Çözüm:** İki dosyada bayt `\b` ile değiştirildi; `git grep -c` ile depoda başka 0x08
kalmadığı doğrulandı. Kural: dosya içeriği yazan betikler heredoc'a değil ayrı bir `.py`
dosyasına yazılır ve ters bölü içeren dizgeler ham (`r"..."`) tutulur.

---

## B-008 — Test fikstürü belge arşivini geçici dizine yönlendirmiyordu

**Bulundu:** 8 Eylül 2026 (ikinci inşa öncesi inceleme) · **Durum:** ÇÖZÜLDÜ (8 Eylül 2026)

**Sorun:** `tests/conftest.py` yalnız `DEFTERIKI_VERITABANI` değişkenini geçici dosyaya
çeviriyordu; `DEFTERIKI_BELGE_ARSIVI` (K-011) dokunulmadan kalıyordu. Fikstür istemeyen bir
test ise her iki yolu da gerçek konumunda görüyordu.

**Etkisi:** Bugün belge kodu olmadığı için görünmüyordu. İlk belge kaydeden test gerçek
`%LOCALAPPDATA%\DefterIki\belgeler` klasörüne yazacak, test verisi kullanıcı verisine
karışacaktı.

**Çözüm:** `veri_dizini` autouse fikstürü her test için `tmp_path/veri` altında iki yolu
birden ayarlar; `veritabani_yolu` ona dayanır. `tests/test_fiksturler.py` fikstür isteyen ve
istemeyen testte iki yolun da geçici dizinde kaldığını sınar.

---

## B-009 — `busy_timeout` pragması `journal_mode`'dan sonra geliyordu

**Bulundu:** 8 Eylül 2026 (ikinci inşa öncesi inceleme) · **Durum:** ÇÖZÜLDÜ (8 Eylül 2026)

**Sorun:** `veritabani.PRAGMALAR` sırası `journal_mode=WAL`, `foreign_keys`, `busy_timeout`,
`synchronous` idi. `journal_mode` dosyaya kilit ister; dosya o an başka bir süreçte kilitliyse
bekleme süresi henüz tanımlı olmadığından ilk bağlantı beklemeden "database is locked" ile
düşerdi.

**Etkisi:** Bugün tek süreç olduğu için görünmüyordu. MCP süreci ile masaüstü uygulaması aynı
dosyayı açtığında ilk bağlantı ara sıra ve açıklanamaz biçimde başarısız olurdu.

**Çözüm:** `busy_timeout` ilk sıraya alındı; `tests/test_veritabani.py` sıranın korunduğunu
sınar.

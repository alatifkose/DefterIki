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

# Masterplan aktarımı ve temizlik — 8 Eylül 2026

## Aktif plan

[Masterplan v2.0](../GP_Attainability_Masterplan_TR.md) ve
[güncel öncelik](../AKTIF_ONCELIK_PROJE.md) verilen kaynaklardan aynen kopyalandı;
kaynak dosyalar korunmuştur. Eski kapsam, uygulama sırası ve tamamlanma ölçütleri
aktif değildir. Mevcut FIELDWORK v0 başlangıç kanıtıdır; SOGP, zamanlı MDP/DP, QP,
yürütme/bütçe mekanizması ve güçlü B3/P–USV değerlendirmesi henüz tamamlanmış değildir.

8 Eylül aktarım anındaki SHA-256 (kaynak = hedef):

- Masterplan: `3EAF7DB5E747BCB0DC5791EB0010C515CB9B2F05C03A09A322193109741C070B`
- Öncelik: `46090EBF05B1CB72BB65BF880F3AB3C102F4107ECED6E9C037B19A98D4E4FFF0`

9 Eylül notu: Kullanıcı isteğiyle yerel masterplana §1.1 odak eki ve ek tarihi eklendi.
Yukarıdaki masterplan hash'i aktarım anını belgeler; güncel yerel dosyanın hash'i değildir.
Dış kaynak masterplan ve öncelik belgesi değiştirilmedi; kapsam ve aşama sırası korundu.

## Uygulanan arşiv ve silme

Arşiv: [20260908-171715-172-masterplan-v2](<C:/Users/Lenovo/Documents/Codex/GP_Attainability_Archive/20260908-171715-172-masterplan-v2>).
63 dosya / 401.933 bayt kopyalandı; manifest yeniden okunup **her dosyanın hash'i
doğrulandıktan sonra** kaldırma uygulandı. Eski ana plan, kaldırılan 47 dosya ve
güncellenen belgelerin 15 önceki sürümü bu arşivden geri alınabilir.

Projeden arşiv sonrası kaldırılanlar (47 dosya / 253.835 bayt):

- `docs/proof_notes.md`, `docs/novelty_matrix.md`: ertelenen, benzersiz v1 notları.
- `configs/methods/`: kullanılmayan beş v1 yöntem taslağı; eski B0/B1/B3/O1/O2 adları
  ve G3/kalibrasyon kilitleri v2 ile çakışıyordu. Aktif kod/test/CI tüketicisi yoktu.
- `configs/sweeps/main.yaml`, `scaling.yaml`: eski slack karşılaştırması ve ölçekleme.
- `experiments/locked_splits.yaml`: kullanılmayan, dondurulmamış eski seed rezervasyonu.
- `dist/`: 37 dosyalık eski scaffold dağıtımı ve bağımsız wheel-smoke çıkarımı;
  mevcut `.venv` veya raporlanan yeni paket doğrulaması değildi.

Arşivsiz silinen yeniden üretilebilirler: `.mypy_cache`, `.pytest_cache`, `.ruff_cache`,
`.coverage`, yalnız `src`, `tests` ve diagnostic altındaki `__pycache__` dizinleri.
Toplam **84 dosya / 18.255.012 bayt (17,41 MiB)**. Bunlar yeniden üretilebilir.
Her silmede çözülmüş mutlak hedefin proje içinde olduğu ve tüm ağacın reparse point
içermediği kontrol edildi; junction/symlink izlenmedi, `.git`e dokunulmadı.

## Korunanlar ve gerekçeler

Tüm çalışan kaynak/test kodu, ortam, bağımlılık/lock dosyaları, kullanılan YAML ve
kaynak belgeleri korundu. `budget/noise/mismatch` taslakları ile genel
`final_protocol.yaml` hâlâ yararlı olabileceğinden silinmedi; ilgili dizin README'leri
bunları **pasif taslak**, yeni değerlendirmeyi **henüz dondurulmamış** olarak işaretler.
`.uv-cache` ve `.pre-commit-cache` araç/çevrimdışı ortam desteği içerdiğinden gereksiz
oldukları varsayılmadı; `.tools`, `.python` ve `.venv` değişmedi.

Hash'li handoff paketi, diagnostic ve **bütün mevcut sonuç/ham veri paketleri**,
olumsuz bulgular ve eski video taslaklarıyla birlikte korundu. Paketlerin içinden
dosya ayıklanmadı. Eski handoff içindeki talimatların tarihsel olduğu yeni
[handoff dizininde](handoffs/README.md) açıklandı. Oradaki eski diagnostic bağlantısı
kaynak klasör düzenine ait, önceden mevcut bir kırık bağlantıydı; doğru hedef yeni
dizinde gösterildi, hash-korumalı orijinal değiştirilmedi.

## Doğrulama

- 68 korunan dosya + 26 mevcut artifact manifesti değişmedi; eski transferin 23 kaydı
  ve sonuç manifestlerindeki 442 dosya hash'i geçti.
- **187 ana test** (10,04 s), **11 diagnostic testi** (0,196 s) geçti.
- Ruff lint/format ve strict mypy: geçti; mevcut 24 kaynak modülünde tip hatası yok.
- Temizlik sonrası wheel ve kaynak paketi çevrimdışı üretildi:
  `outputs/maintenance-20260908/packages/`. Kaynak paketindeki iki aktif belgenin
  hash'i de orijinallerle eşleşti; wheel'in üç dashboard dosyası mevcut.
- 28 Markdown belgesinde 61 yerel bağlantı denetlendi: aktif kırık bağlantı yok;
  yukarıda açıklanan tek tarihsel paket bağlantısı değiştirilmeden korundu.
- İki robot, 10 s, combined senaryosunda üç yöntemli uçtan uca `simulate` geçti;
  JSON/Parquet, manifest/DONE ve iki PNG paneli üretildi. Bu kısa kontrol yeni yöntem
  veya performans kanıtı değildir. [Koşu](../outputs/maintenance-20260908/smoke/20260908T142324560789Z-6f8d2b8b-bfc0eb/comparison.json).
- Önceki %91,9 kapsam bilgisi tarihsel korunmuştur; bu temizlikte yeni kapsam ölçümü
  iddia edilmez. Testler temizlenen önbellekleri yeniden doldurmadan çalıştırıldı.

İşlem listeleri, koruma/link kontrolleri ve tekrar doğrulama yardımcıları
`outputs/maintenance-20260908/` altındadır. Arşivde `manifest.json`, `VERIFIED.json`
ve uygulanan prosedür bulunur. Kod sıfırdan kurulmadı; yeni algoritma/teori eklenmedi,
Git değişiklikleri geri alınmadı ve commit/push yapılmadı.

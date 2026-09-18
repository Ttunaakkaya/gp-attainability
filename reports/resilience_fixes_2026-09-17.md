# Dayanıklılık düzeltmeleri — 17 Eylül 2026

Kapsam: incelemede yeniden üretilen hata işleme ve aday sayacı açıklarını kapatmak.
GP/kontrol denklemleri, rota seçimi, hedef/plan-koruma tercihleri, dondurulmuş
protokoller ve eski sonuç paketleri değiştirilmedi. Bu bir performans deneyi değil.

## Düzeltilenler

- **P rollout:** ilk adımda ret veya sıfır adımlı rollout için ölçülmemiş minimum
  mesafe `null`. Reddedilmiş adayın JSON kaydı artık kabul edilmiş diğer adayları
  engellemiyor. Kabul edilmiş önekin mesafe bilgisi korunuyor; bütün adaylar
  reddedildiğinde açık başarısızlık davranışı değişmedi.
- **Sayaçlar:** `candidates_evaluated = accepted + rejected`; `not_evaluated` ayrı
  sayılıyor. Yeni kayıtlar aday durumlarıyla doğrulanıyor. Eski paketler aynı kalıyor;
  demo sayıları aday durumlarından hesaplayarak eski hatalı sayaçları da doğru gösteriyor.
- **M5 batch:** başarısız koşu, eksik ilk epoch okunmadan önce ele alınıyor; çiftin
  sekiz ölçütü `false`. Ham başarısızlık, gerçekleşmiş önek ve audit korunuyor;
  sonraki çiftler çalışıyor. Gürültü eşleştirmesi boş önekte alan hesabı yapmıyor ve
  eşit olmayan uzunluklarda ortak `(epoch, robot)` anahtarlarını doğruluyor.
- **M5 sayısal ret kaydı:** sonlu olmayan `max_violation`, açıklamalı `null` olarak
  saklanıyor; bu sıfır ihlal anlamına gelmiyor. Solver durumu ve iç ret işareti korunuyor.

## Yeni doğrulama

- Ana testler: **997 geçti**, 54.41 s; önceki sayı 968 idi.
- Diagnostic: **11 test / 6 subtest geçti**.
- Ruff, format ve strict Mypy kontrolleri geçti; JavaScript sözdizimi kontrolü geçti.
- Demo sayaçları üç küçük JavaScript örneğinde kontrol edildi; eski hatalı sayaç
  içeren örnek dahil, sayılar aday durumlarıyla uyuştu.
- Regresyonlar ilk adım/önek sonrası ret, tamamen reddedilmiş aday kümesi,
  kabul+ret+atlanmış aday karışımı ve yanlış sayaç reddini kapsıyor.
- M5 küçük batch regresyonu gerçek örnekleme/audit ile kontrollü solver reddini
  birleştiriyor. Sonlu, `inf` ve `NaN` tanılarında ham kayıt ve hash korunması,
  katı JSON serileştirmesi ve bir sonraki seed'e devam test edildi.

## Çalışan davranışın korunması

Değişiklik öncesi/sonrası aynı 20 kısa koşu karşılaştırıldı: holonomik/QP ve
`usv_curvature`, exact ve SOGP-8, B0/B1/B2/B3/P; combined, seed 7, üç robot, 20 s.
Durum, bilimsel özet metrikleri, gerçekleşmiş konum/yönler, ham örnekler ve plan
hedef/forecast/seçim alanlarının hash'leri dört grubun tamamında birebir aynı.
Zamanlama ve değiştirilen tanı sayaçları bu karşılaştırmaya dahil edilmedi.

Mevcut M5 `11099e` paketindeki 40 koşu yalnız okundu: yeni `evaluate()` ile 20 çiftin
sekiz ölçütü mevcut raporla birebir aynı. Büyük deneyler yeniden koşulmadı.

## Gerçek CLI regresyonu

```powershell
.\.venv\Scripts\python.exe -m attain_sampling simulate --scenario nominal --robots 2 --seed 7 --duration 10 --controller qp --qp-max-iter 25 --methods p --output outputs/resilience-20260917
```

[Yeni sonuç paketi](../outputs/resilience-20260917/20260917T182555510140Z-fa19271c-16243f/comparison.json)
tamamlandı: 10 s, iki plan, altı alınmış ölçüm; 48 rollout kontrol çağrısında sekiz
ret, yürütmede 20 QP çözümü ve sıfır hata. Uygun bekleme adayı seçiliyor: yol 0 m.
Bu, çökme hatasının kapandığını gösterir; bilgi toplama veya görev hedefi başarısı
iddiası değildir. Paket ve şekiller yeni dizinde; eski dosyaların üzerine yazılmadı.

## Ayrı kalan işler

M5 basis-only kontrol posterioru / gerçek SOGP tutarlılığı; hedefe göre plan koruma
tercihi; kısa ECC koşularının geç-zaman takılma metriği; özel ECC ayarlarının açıklama
metni ve M8 teslim paketi bu bakımın kapsamı dışında kaldı.

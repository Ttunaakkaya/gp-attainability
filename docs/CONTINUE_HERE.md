# Devam noktası — aktif masterplan v2.0

**Yetkili plan:** [GP_Attainability_Masterplan_TR.md](../GP_Attainability_Masterplan_TR.md),
sürüm 2.0, 8 Eylül 2026. [Güncel öncelik](../AKTIF_ONCELIK_PROJE.md) onun özetidir.
Bu iki dosya 8 Eylül'de kullanıcının verdiği kaynaklardan değiştirilmeden aktarıldı.
9 Eylül'de yalnız yerel masterplana §1.1 odak eki eklendi: hedef kaybını erken öngörme
ve kalan bütçeyle toparlanmayı B3'e karşı değerlendirme. Kapsam ve M0–M8 sırası değişmedi;
dış kaynak dosyalar korunur. Ek, genel olanaksızlık kanıtı veya ECC çözümü iddiası değildir.
Eski masterplanın kapsamı, sırası ve bitiş ölçütleri artık aktif değildir.

## Mevcut durum ve sıradaki iş

**17 Eylül — dayanıklılık düzeltmesi:** P'de ilk kontrol adımında reddedilen adayın
ölçülmemiş minimum mesafesi artık `NaN` yerine `null`; başka uygulanabilir aday varken
karar JSON serileştirmesi görevi düşürmez. Değerlendirilmiş/reddedilmiş/üst sınır
nedeniyle atlanmış aday sayaçları ayrıldı ve yeni kayıtlar doğrulanıyor; demo eski
paketleri değiştirmeden aday durumlarından doğru sayıları gösteriyor. M5 doğrulayıcısı
ilk örnek öncesi veya daha geç QP reddini korur, sekiz ölçütü başarısız sayar ve sonraki
çifte devam eder; boş/eşit olmayan ölçüm önekleri güvenle karşılaştırılır. Sonlu olmayan
ECC solver tanı değeri sıfır değil, açıklamalı `null` olarak kaydedilir.

Doğrulama: **997 ana test + 11 diagnostic**, Ruff/format/Mypy; 20 kısa holonomik/USV,
exact/SOGP koşusunun bilimsel çıktı hash'leri değişiklik öncesiyle aynı. Önceden çöken
gerçek düşük-iterasyon QP örneği artık tamamlanıyor. Mevcut M5'in 20 çiftindeki ölçütler
değişmedi; dondurulmuş M6/M7 veya başka eski paket yeniden yazılmadı. Ayrıntı ve yeni
CLI kanıtı: [dayanıklılık raporu](../reports/resilience_fixes_2026-09-17.md).

Bu bakım, M5'in **basis-only kontrol posterioru ile gerçek SOGP posteriorunun
tutarlılığı** konusunu çözmez; kaynak uyumu anlatılmadan önce bu açık ayrıca ele
alınmalı. Hedefe göre plan koruma tercihi, kısa ECC koşularındaki takılma metriği,
özel ayarlardaki açıklama metinleri ve M8 sunum eksikleri de bu turda değiştirilmedi.

FIELDWORK v0 korunmuştur: exact GP, sweep/nominal greedy/adaptive greedy, 2–4 robot,
gürültü/kayıp/sapma, hareket/mesafe filtresi, kinematik USV, offline demo ve ham kayıtlar.
V2 adlarıyla mevcut yöntemler B0/B1/B2'dir; adaptive greedy, önerilen P değildir.

**9 Eylül: M1 holonomik QP tamamlandı.** Merkezi OSQP izleme denetleyicisi hız
çokgeni, alan sınırı, ikili CBF ve tüm doğrusal hareket aralığı için mesafe kısıtı
uygular. Komut bağımsız sayısal/geometrik kontrolden geçmeden yürütülmez; başarısız
koşular gerçek duruş anı ve kısmi sonuçlarıyla saklanır. Varsayılan filtre korunur.
[M1 tasarımı ve sınırları](M1_CONTROL.md), [ölçülen sonuçlar](../reports/m1_results_2026-09-09.md).
QP şu an yalnız holonomik model içindir; GP performans kısıtı veya ECC yeniden
üretimi değildir. Fiziksel güvenlik ya da görev ulaşılamazlığı kanıtı sunmaz.

**14 Eylül: M2 zamanlı Bellman-DP tamamlandı.** Gerçek alınan ölçümlerden posterior,
kaba hücre/kalan zaman üzerinde Bellman adayları, ortak GP covariance ile seçim,
zaman damgalı plan ve QP ile ilk aralığın yürütülmesi birbirine bağlandı. Yeni `dp`
yöntemi periyodik B3'ün ilk bağımsız sürümüdür; varsayılan B0/B1/B2 değişmedi.
Planlar görev bitişini sıfırlamaz; fiziksel örnekleme saati dışına ölçüm eklemez.
Plan/ölçüm/hareket bağlantıları ve kısmi başarısızlık kayıtları doğrulanır.
[M2 tasarımı](M2_PLANNING.md), [M2 sonuçları](../reports/m2_results_2026-09-14.md).

**15 Eylül: M3 SOGP tamamlandı.** Csató–Opper birincil algoritmasından sınırlı
sözlük, sıralı çevrimiçi güncelleme ve budama; B0/B1/B2/B3'e backend seçimi ve
demoya zamana bağlı sözlük paneli eklendi. Exact varsayılanı korunur. Gelecek SOGP
budaması etiket bağımlıdır; forecast yalnız mevcut yaklaşık posterioru koşullandırır.
Bu exact gelecek veya ulaşılabilirlik sertifikası değildir.
[M3 tasarımı](M3_SOGP.md), [M3 sonuçları](../reports/m3_results_2026-09-15.md).

**15 Eylül: M4 yürütme/bütçe yönetimi tamamlandı.** Önerilen `p` yöntemi B3'e üç şey
ekliyor: adayları görevin kendi kontrolcüsüyle nominal rollout'tan geçirip **varılan**
konumlarda puanlama; yürürlükteki planın kalanını mevcut durumdan yeniden denetleyip
açık bir marjın altında koruma; ve her adayı çalıştırılabilir bir hold devamıyla ortak
son teslime uzatarak **aynı kalan örnekleme bütçesi** üzerinden karşılaştırma. Karar
anları örnekleme epoch'larına ek olarak sapma/müdahale olaylarıyla da tetiklenir.
Kalan bütçe yalnız küresel saatten türetilir; yeniden planlama onu sıfırlayamaz ve bu
her kararda denetlenir. Görev sonu değeri çalıştırılabilir bir plandan gelen **üst
adaydır**; ulaşılabilirlik tabanı, toparlanma sertifikası veya RMSE sözü değildir.
§10'un üç zorunlu ablation'ı yapılandırma bayrağıdır. [M4 tasarımı](M4_EXECUTION.md),
[M4 sonuçları](../reports/m4_results_2026-09-15.md).

**V0 + M1 + M2 + M3 + M4, v2'nin tamamlanması değildir.**
Güçlü B3/P karşılaştırması görülmemiş görevlerde, tam ablation matrisi ve
geliştirilmiş USV değerlendirmesi hâlâ bekleyen işlerdir. P'yi uygulamış olmak
P'nin B3'ten iyi olduğunun kanıtı değildir. Ölçülen kanıtta P'nin planlama maliyeti
B3'ün yaklaşık 22 katı; rollout kapalıyken ablation sonucu **birebir aynı** çıktı,
olay tetiklemesi hiçbir yürütme farkı üretmedi ve plan koruma o görevde RMSE'yi
kötüleştirdi. Bu üç olumsuz bulgu korunacak ve M6'da rollout'un değeri kontrolcünün
gerçekten varamadığı koşullarda (dar geçit, daha çok robot, dönüş kısıtlı USV) aranacak.

**15 Eylül: ECC 2025 tam metni alındı ve M5 denetimi tamamlandı.** PDF, TUM aboneliğiyle
IEEE Xplore'dan indirildi; `references/private/` altında (gitignored, asla commit edilmez),
SHA-256 `BBA56A90...52A15E`, S01 kaydı güncellendi. Dokuz denetim konusunun **tamamı**
sayfa/denklem atfıyla kapatıldı ve `sources/ecc2025.py` ledger'ına işlendi;
`doctor --source-report` makine-okunur hâlini basıyor.
[Denklem defteri](equation_map.md), [denetim raporu](../reports/m5_results_2026-09-15.md).

Denetimin ortaya çıkardığı, bizim bağımsız profilimizden **gerçek farklar**:
`J` normalize edilmemiş **toplam** (bizde ağırlıklı ortalama); çekirdekte **signal variance
ön çarpanı yok** (`k(x,x)=1`); `σ²` latent, `σ_ε²` eklenmiyor; performans kısıtı
`J[l] ≤ J[0] − lγ`, `γ=60`; makale bu kısıtın **bütün l için olanaksız** olduğunu açıkça
söylüyor — M4'ün ulaşılabilirlik sorusu doğrudan buraya bağlanıyor. SOGP budaması
etiket bağımlı (M3'te bağımsız vardığımız sonuç doğrulandı).

**Kaynakta belirtilmeyen dokuz madde** (seed'ler, ground-truth karışım parametreleri,
başlangıç konumları, `α_ca`, `U`/hız sınırı, kontrol periyodu, Bellman ufku, eşzamanlı
örnek sırası, `α_J`'nin lineer ötesi biçimi) kayıtlı **proje tercihi** olur; asla komşu
değerden çıkarılmaz. Bunlar şekil yeniden üretimini **yalnız niteliksel** karşılaştırmaya
sınırlar (`CLAIM_LIMITS`).

**16 Eylül: M5 tamamlandı — `ecc2025` kaynak profili, şekiller ve fark raporu.**
Makalenin SOGP'si (β/ω kabul, η budama; p. 305'in harfiyen aktarımına karşı test edildi),
varyans azalma hızı satırı (eq. 8, 11–13, 15; sonlu farklarla doğrulandı), robot başına
QP (10)/(11)/(17) + çarpışma CBF'i (9), hücre MDP'si ve Bellman özyinelemesi (16) ve
kapalı döngü profil (E0: yalnız kısıt, E1: hiyerarşik + Algoritma 1) ayrı modüllerde.
Tek satırla çalışır: `python -m attain_sampling ecc-profile --seed 7`.
[M5 kaynak uyumu ve fark raporu](M5_SOURCE_ALIGNMENT.md),
[M5 sonuçları](../reports/m5_results_2026-09-15.md).

**Bu sayısal yeniden üretim değil, niteliksel karşılaştırmadır.** Makale seed,
ground-truth parametresi ve kesin başlangıç konumu yayımlamıyor. Hiçbir koşu "ECC
yeniden üretimi" diye adlandırılamaz; bir test bunu depo genelinde zorunlu kılıyor.

**Makalenin kendi içindeki tutarsızlıklar** (ledger R01–R06, D037, D041–D043):
basılı eq. (12) türeviyle çelişiyor; metin her örnekten sonra yeniden planlıyor,
Algoritma 1 yalnız rota boşalınca; Fig. 3/6 `J[0]≈3600` ile başlıyor ama 900 nokta ve
`k(x,x)=1` ile `J[0]=900`; şekillerdeki ~57/epoch düşüş basılı `L=4`, `t_s=10 s` ile iki
ölçekte de ulaşılamaz (~8 ve ~36); başlangıç karesinden (10) robotu 1e-6–1e-5 m/s ile
hareket ettirebilir, oysa Fig. 2'de 320 s'de bütün robotlar alanın içinde. Hiçbiri tahminle
kapatılmadı: ölçek ve başlangıç iki şekilde koşuldu (A–D yapılandırmaları).

**Sonuç (paket `11099e`, 40 koşu, 0 başarısız, ölçütler koşulardan önce yazıldı):**
makalenin "E1, E0'dan iyi" sıralaması yalnız E0'ın alana hiç giremediği A/C'de çıkıyor.
Bunun nedeni alan dışında gradyan olmaması; makalenin anlattığı takılma mekanizması değil.
Kenardan başlayınca (B/D) E0 daha düşük `J` ile bitiyor ve MSE'de E1 10 seed'in yalnız
2'sinde önde. Önceden tanımlanmış takılma ölçütü 0/20. `l = 1`'deki izleme 0/20 (R05 ile
tutarlı). Şekil ölçeğinde büyüklükler Fig. 6'ya yakın, ama bu bir eşleşme iddiası değil.
**Yapısal bulgu:** 300 örnek `n_d,max = 360`'ın altında kaldığı için robot yolları
ölçümlerden bağımsız; seed yalnız alanı değiştiriyor ve yol ölçütleri yapılandırma başına
tek bir örnek. Sonradan yapılmış gözlem (sayılmadı): D/E0 son 360 s'de alanın alt
kısmında kalıyor, üst kısım yüksek varyanslı açık kalıyor.
Olumsuz sonuçlar korunur; ölçüt veya ayar sonradan değiştirilmedi (D044, D046).

**17 Eylül: M6 tamamlandı — dondurulmuş protokolle görülmemiş görevlerde karşılaştırma.**
Protokol `m6-heldout-v1` koşulardan önce donduruldu (D048). Kapsamı: seed 9001–9040,
4 robot, 90 s; ana blok (nominal, kayıp, sapma, birleşik, 45 s kısa bütçe) × B0–B3/P;
birleşikte üç ablation; SOGP-32 ve 16 m çekirdek uyumsuzluğu blokları. Toplam 400 iş,
1.400 koşu, 0 başarısızlık; bütün metrikler ham kayıttan yeniden üretildi.
**Birincil sonuç olumsuz:** P − B3 RMSE farkının %95 aralığı beş senaryonun hepsinde
sıfırı içeriyor, P görev başına 11–46 s daha fazla planlıyor. Kayıp, sapma ve birleşik
senaryolarda **B2 hem B3'ten hem P'den anlamlı derecede iyi** (hedefe 38/37 görevde
ulaşıyor; B3 28, P 27/25). Rollout 40 görevin 37'sinde sonucu değiştirmedi. Plan koruma
varyansı düşürüyor ama RMSE'yi düşürmüyor. Erken uyarı yok: iki yöntemin tahmini de
son ~4–8 epoch'a kadar her görevde uyarı veriyor; kayıplı senaryolarda tek adımlık
tahmin sistematik olarak iyimser (+0.017), çünkü tahminler kaybı modellemiyor.
Nominalde yollar seed'den bağımsız. Model uyumsuzluğunda varyans düşerken RMSE
artıyor ve varyans hedefi yanıltıcı oluyor. P için üstünlük iddiası yok (D049).
[M6 protokolü](M6_PROTOCOL.md), [M6 sonuçları](../reports/m6_results_2026-09-17.md).

**17 Eylül: M7 tamamlandı — dönüş kısıtlı USV'de aynı soru.**
Araç sınıfı açıkça tanımlandı (`usv_curvature`, D050):
- yalnız ileri gidiyor, en küçük dönüş yarıçapı 4.44 m, yerinde dönemiyor;
- sertifikalı yay filtresi her robota alan içinde kendine ait bir bekleme dairesi
  bırakıyor ve hiçbir robotu durdurmuyor;
- B3 ve P, hareket primitive'lerinden oluşan bir Bellman ağacıyla planlıyor.

**v1** (`m7-usv-heldout-v1`, seed 9101–9140, paket `8b2fe1`): P, sapma ve birleşik
senaryolarda B3'ten anlamlı derecede iyi çıktı (−0.035). Ham kayıtlar bunun bir
**karşılaştırıcı kusurundan** geldiğini gösterdi:
- planlayıcının alan içi denetimi kontrolcünün değişmezinden daha katıydı;
- bu yüzden kenara yakın robotlara yalnız durma seçeneği kalıyordu;
- sapma altında 160 B3 robotunun 94'ü görev sonuna kadar hareketsiz kaldı (D056).

v1 olduğu gibi raporlandı. Denetim kesin yay sınırına çevrildi ve bir regresyon testi
eklendi.

**v2** (`m7-usv-heldout-v2`, seed 9201–9240, paket `7f95f2`, D057–D058): v1'in aynısı,
koşudan önce donduruldu.
- **P − B3 RMSE:** aralık beş senaryonun beşinde sıfırı içeriyor. Sapma ve birleşikte
  nokta tahmini P lehine (−0.008 / −0.007), ama anlamlı değil.
- **Varyans, varış hatası ve hedef:** P bozucu altında varyansı ve varış hatasını
  (~2 m) anlamlı biçimde düşürüyor. Birleşikte hedefe 37 görevde ulaşıyor, B3 29
  görevde.
- **Maliyet:** P, B3'ün 4.5–14 katı süre harcıyor.
- **B2:** yine en güçlü yöntem; B3'ten beş senaryonun beşinde anlamlı derecede iyi.
- **Rollout:** bu araçta kararları her görevde değiştiriyor ama RMSE'yi değiştirmiyor.
  Düz çizgi planlayıcıda varyansı düşürüp hedefe ulaşmayı 28'den 35'e çıkarıyor.
- **Düz çizgi planlayıcılı B3:** primitive'li B3'ten RMSE'de anlamlı derecede iyi.
- **Erken uyarı:** yok; geç iyimserlik yine ölçüm kaybından geliyor.

P için üstünlük iddiası yok. [M7 tasarımı](M7_USV.md),
[M7 sonuçları](../reports/m7_results_2026-09-17.md).

**18 Eylül: M8 tamamlandı — sunulabilir paket.** Yeni deney yok; her parça kayıtlı
koşulardan ve dondurulmuş analizlerden üretildi.
- **Demo:**
  - Dönüş kısıtlı USV modeli eklendi.
  - B3 ile P aynı dünyada yan yana izlenebiliyor.
  - P'nin kararları ("neden korudu / değiştirdi") düz cümleyle gösteriliyor.
  - Sabit görev hedefi, P'nin tahmininden ayrı çiziliyor.
  - Dört rehberli gösterim var: nominal döngü, kayıp ve sapma altında plan
    güncellemesi, USV dönüş sınırı, yöntemin yardımcı olmadığı durum. Hepsi geliştirme
    seed'lerinde; "yardımcı olmadığı durum" seed'i açık bir kuralla seçildi (D059–D060).
- **Belgeler (İngilizce):**
  - 8 sayfalık teknik not: `docs/technical_note/FIELDWORK_technical_note.pdf`. Tablo ve
    sayıları `analysis.json` dosyalarından dolduruluyor.
  - Ham kayıtlardan 6 şekil: `reports/figures/m8/`, hash manifestiyle.
  - Kısa README ve canlı demo yönergesi (`docs/DEMO.md`).
- **Video:** 107 s, `outputs/m8/FIELDWORK_m8_demo.mp4`; `scripts/make_video.py` ile
  yeniden üretilir (D061).
- **Kurulum sınaması:**
  - Commit'e girecek dosyalar ayrı bir klasöre kopyalandı; `uv.lock` ile çevrimdışı
    kurulum yapıldı ve 1.007 test orada geçti.
  - Sınama, sunucu değişikliğiyle eskimiş bir test beklentisini yakaladı; düzeltildi.
- **Düzeltme:** not yazılırken M6 raporundaki B2 aday kümesi tanımı düzeltildi (D062).

Masterplanın M0–M8 sırasının tamamı uygulanmıştır. Sıradaki adımlar kullanıcının
kararıdır: commit/depo paylaşımı, profesörle iletişim ve daha sonra araştırma önerisi.
Aktif öncelik dosyası araştırma önerisini ve e-posta hazırlığını hâlâ erteliyor.
M6 ve M7 (v1 ve v2) protokolleri yeniden koşulmaz ve ayarlanmaz; kayıp olasılığını hesaba
katan tahmin veya B2'nin üstünlüğünün nedeni gibi hipotezler ancak önceden bildirilmiş
yeni bir çalışmayla sınanır. M6'da dondurulmuş protokol, görülmemiş
görevler ve B0–B3/P + üç ablation birlikte raporlanır. Eşikler (`p_switch_margin`,
`p_deviation_trigger_m`, `p_intervention_trigger_mps`) geliştirmede seçilmiştir;
son deneyde ayarlanmaz. SOGP-64 geliştirme başlangıcıdır, evrensel optimum kapasite
değildir. 32'deki hata artışını ve stres testindeki forecast farkını koru.
M8 sunulabilir paket için asıl tamamlanma ölçütlerini masterplandan oku;
burada ikinci bir masterplan üretilmez.

ECC tam metni yoksa kaynak denklemlerini tahmin edip makale etiketi verme.
Bağımsız, kaynakları belirtilmiş SOGP ve kendi tanımlı DP/QP geliştirmesi engellenmez.
ROS 2/Unity kategorik yasak değildir; somut doğrulama ihtiyacı gerektirirse değerlendirilir.
MDP/DP, ertelenen ağır neural-network/MARL eğitimiyle karıştırılmaz.
Research proposal ve yeni formal ispatlar sonraya bırakılmıştır.

## Korunan kanıt ve çalıştırma

- M8: `scripts/make_showcases.py` → `figures_m8.py` → `build_note.py` → `make_video.py`
  (sıra ve kapsam için `REPRODUCIBILITY.md` "M8 presentable package").
- M7: v2 kanıtı `outputs/m7v2-20260917/heldout/batch-20260917T152510157339Z-7f95f2/analysis.json`
  (koşu `python scripts/run_m6.py --milestone m7v2`); v1 kanıtı
  `outputs/m7-20260917/heldout/batch-20260917T142113728110Z-8b2fe1/` (düzeltmeden önceki kod,
  paketteki `source_snapshot.zip`). Analiz: `python scripts/report_m6.py <batch>`.
  M7 son doğrulama: 968 ana test, %94.36 kapsam; Ruff/format/Mypy geçti.
- M6: ana kanıt `outputs/m6-20260916/heldout/batch-20260916T224142922453Z-609588/analysis.json`
  (koşu `python scripts/run_m6.py`, analiz `python scripts/report_m6.py <batch>`).
- M5: 880 ana test, %94.15 kapsam; Ruff/format/Mypy geçti. Ana kanıt:
  `outputs/m5-20260916/validation/batch-20260916T120304009049Z-11099e/validation.json`
  (SHA-256 LF normalize edilmiş içerik için; bkz. paketteki `MANIFEST_NOTE.md`).
  Şekiller: `scripts/figures_m5.py <batch>`; tek eşleşmiş koşu:
  `.\.venv\Scripts\python.exe -m attain_sampling ecc-profile --seed 7 --start edge`.
- M3: 607 ana test, 11 diagnostic, %93.65 kapsam; Ruff/format/Mypy geçti.
  132 kapalı döngü koşusu (128 küçük matris + 4 uzun pilot) tamamlandı;
  32/64/128 sözlük doluluk/budaması aynı 256 ölçümlük akışta ayrıca doğrulandı.
  Ana kanıt: `outputs/m3-20260915/validation/batch-20260915T122522343637Z-c34ba1/validation.json`.
  Sonuçlar geliştirme içindir, M6 görülmemiş görev kanıtı değildir.
- M3: `.\.venv\Scripts\python.exe -m attain_sampling simulate --gp-backend sogp --sogp-max-basis 64 --methods sweep,greedy,adaptive,dp --controller qp --robots 4`.
- Başlangıçta tekrarlanan Windows HTTP bağlantı sıfırlaması düzeltildi: erken
  403/404/409 yanıtlarından önce sınırlı POST gövdesi okunur; süre/boyut/origin/kilit
  kontrolleri korunur. Gecikmeli gövde ve 25 tekrarlı ret testi eklendi.

- M2 son kod doğrulaması: 485 ana test, 11 diagnostic testi, %93.29 kapsam;
  Ruff/format/Mypy geçti. 300 s dört robotlu pilot, sınırlı nominal/birleşik senaryolar
  ve kısmi görev sonu için ham kanıtlar `outputs/m2-20260914/` altında; ölçülen
  sonuçları yukarıdaki M2 raporundan oku. Bunlar M6 görülmemiş görev kanıtı değildir.
- M2 çalıştırma: `.\.venv\Scripts\python.exe -m attain_sampling simulate --methods sweep,greedy,adaptive,dp --controller qp --robots 4`.
  Demoda **Include periodic DP · M2**, ardından B3 kartı seçilir. DP ve QP bu aşamada
  yalnız holonomik robotlarda desteklenir; USV varsayılan filtreyle korunur.
- M1 son doğrulama: 318 ana test, 11 diagnostic testi, %92.97 kapsam; Ruff/Mypy ve
  çevrimdışı lock/paket kontrolleri geçti. 300 s pilot ardından 90 s geliştirme
  matrisi: toplam 54 yöntem koşusu tamamlandı; 12.240 gerçekleşen takım hareket
  aralığı sayısal toleranslar içinde doğrulandı. Bunlar geliştirme senaryolarıdır,
  nihai M6 istatistiksel kanıtı değildir. Ham paketler, ilk başarısız pilot ve
  test raporları `outputs/m1-20260909/` altında korunur.
- Önceki doğrulama: 187 ana test, 11 diagnostic testi, yaklaşık %91.9 kapsam.
- 54 yöntem koşusu, 12 ek takım-boyutu kontrolü ve paket doğrulaması:
  [geliştirme sonuçları](../reports/development_results_2026-09-08.md).
- Yalnız sapmada adaptive RMSE üç geliştirme seed'inde de kötüleşmiştir; bu bulgu ve
  ham sonuçlar korunur. Seed 7/19/31 görülmemiş nihai değerlendirme sayılamaz.
- [Diagnostic](../experiments/exact_gp_diagnostic/README_TR.md) küçük covariance,
  prefix ve uygulanabilirlik doğrulayıcısıdır; ana proje veya ECC yeniden üretimi değildir.
- [Demo yönergesi ve mevcut video](DEMO.md); başlatma: proje kökünde
  `scripts/demo.ps1`, adres `http://127.0.0.1:8765`.
- `simulate`, `benchmark`, `record`, `export` korunur; B3/P `--methods` ile seçilebilir.
  ECC kaynak profili bağımsız simülatörden ayrıdır ve `ecc-profile` ile çalışır. Gerçek ayarlar `MappingConfig` içindedir.
- M1 örneği: `.\.venv\Scripts\python.exe -m attain_sampling simulate --controller qp --scenario combined --robots 4`.
  Başarısız görev kaydı CLI çıkış kodu `4` üretir; `DONE` görev başarısını değil,
  çıktı paketinin tamamlandığını belirtir. Demoda QP seçimi ve kontrol kanıt paneli vardır.

## Tarihsel belgeler ve temizlik

[Eski devir paketi](handoffs/README.md) hash korunarak saklanır; paket içindeki eski
“aktif öncelik” ve aktarım promptu yalnız geçmiş girdidir. Kaynak konuşmanın outputs
dosyaları silinmemiştir. Eski ana masterplan, ertelenen ispat/yenilik notları ve
kullanılmayan v1 taslakları okunabilirliği/hash'i doğrulanan dış arşive taşınmıştır.

[Temizlik raporu](cleanup_report.md), tam arşiv konumunu, kaldırılanları,
koruma gerekçelerini ve bu görevdeki yeni kontrolleri kaydeder.
Çalışan kaynak/test kodu, ortam/lock ve olumsuz sonuçlar korunur.
Git kimliği/remote kullanıcıdan gelmediği için commit/push yapılmamıştır.

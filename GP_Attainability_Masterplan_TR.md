# GP Attainability — Yeni Master Plan

**Proje:** FIELDWORK — Execution-Aware Multi-Robot GP Sampling  
**Sahibi:** Tolga Tuna Akkaya  
**Sürüm:** 2.0 · 8 Eylül 2026  
**Yerel ek:** 9 Eylül 2026 · §1.1 odak keskinleştirmesi; kapsam ve aşama sırası değişmedi.  
**Aktif hedef:** Hatanaka'nın çalışma çizgisine bağlı, mühendisliği tamamlanmış, deneylerle değerlendirilen ve canlı gösterilebilen bir proje geliştirmek.

**Uygulama deposu:** `C:\Users\Lenovo\Desktop\GP Attainability`. Bu belgede kod ve rapor için verilen depo içi yollar bu köke göredir. Belgenin burada hazırlanması, uygulama deposundaki eski masterplanın otomatik değiştirilmesi anlamına gelmez; aktarım yönergesi ayrıca güncellenmiştir.

Bu belge, 1 Eylül tarihli masterplanın ve önceki aktarım promptunun kapsam ve uygulama sırasının yerine geçer. **Plan yeniden yazılmıştır; çalışan yazılım sıfırdan yazılmayacaktır.** Mevcut FIELDWORK uygulaması, kayıtlı sonuçlar ve diagnostic korunarak geliştirilecektir.

Öncelik sırası: **çalışan sistem → kaynakla doğrulanmış çekirdek → yürütme hatalarını hesaba katan yöntem → güçlü karşılaştırmalar → sunulabilir proje.** Research proposal, yeni teorik ispat ve başvuru yazışmaları sonraki çalışmadır. Makalenin doğruluğunu kontrol etmek, ertelenen geniş araştırma faaliyetiyle aynı şey değildir.

## 1. Yapacağımız proje

Birden fazla robot, başlangıçta bilinmeyen bir çevresel alanı ölçerek haritalayacak. GP modeli hem alan tahminini hem belirsizliği üretecek. Üst düzey planlayıcı robotlara örnekleme rotaları verecek; alt düzey kontrolcü hareket ve güvenlik kısıtlarını uygulayacak.

Projeyi sıradan bir GP demosundan ayıracak çalışma şudur: **Robotların gerçekten yaptığı hareket ve aldığı ölçüm, planlanan bilgi kazanımından saptığında, kalan görev süresine uygun yeni örnekleme planını hesaplamak ve bu kararın işe yarayıp yaramadığını ölçmek.** Kaçırılan ölçüm, geciken hedef, dönüş sınırı ve çarpışma önleme müdahalesi bu farkı oluşturabilir.

Ana sorumuz:

> Aynı görev bütçesinde, yürütmenin sonuçlarını ve kalan rotanın uygulanabilirliğini açıkça değerlendirmek; güçlü, düzenli yeniden planlama yapan bir yönteme göre harita kalitesi, hedefe ulaşma veya hesap maliyetinde ölçülebilir yarar sağlıyor mu?

Bu bir deney sorusudur; cevap baştan olumlu kabul edilmeyecek. Çıktı, mevcut yöntemlerin üstüne isim eklemekten ibaret olmayacak: zaman damgalı örnekleme planı, kontrolcüyle rota değerlendirmesi, gerçek ölçüm muhasebesi ve planın hangi koşulda geçersizleştiğini açıklayan bir mekanizma geliştirilecek.

Projenin senin geçmişinle bağlantısı; GP-MPC ve optimizasyon deneyimini çok robotlu bilgi toplama ve kısıtlı kontrole taşımasıdır. Hatanaka'nın ağ bağlantılı robotik ve dağıtık karar verme çizgisi bu yönle ilişkilidir. [Profesörün laboratuvar profili](https://hatanakalab.wixsite.com/website/faculty). Bu yakınlık, kodu ve deneyi ayrıntısıyla açıklayabildiğinde değer kazanır. Amaç teknik yeterliliğini görünür kılmaktır; kabul sonucuna ilişkin bir garanti veya yüzde değildir.

### 1.1 Odak keskinleştirmesi — 9 Eylül 2026

Ana deney sorusunun ve sunumun odağı şöyle netleştirilmiştir:

> Ölçüm kaybı ve hareket kısıtları altında hedeflenen belirsizlik azalmasının kaçırılmasını ne kadar erken öngörebiliyoruz; kalan görev bütçesiyle yeniden planlama hangi koşullarda görevi kurtarıyor?

Bu, yeni bir proje veya teori aşaması değildir. SOGP → MDP/Bellman-DP → QP omurgası, M0–M8 sırası, güçlü periyodik B3 karşılaştırıcısı ve üç temel ablation korunur. M4'teki bütçe/rollout/plan geçerliliği mekanizması ile M6'daki karşılaştırmalar bu soruyu görünür kılar:

- **Öngörü ve toparlanma:** Sabit görev hedefi ve değerlendirme ufku koşudan önce belirlenir; bir azalma-hızı eğrisi kullanılırsa ölçüm anlarındaki tanımı da önceden sabitlenir. Uyarının erkenliği, yanlış/kaçırılmış uyarılar ve aynı bütçede hedefe ulaşma B3 ile karşılaştırılır. RMSE ve hesap maliyeti ayrı raporlanır; plan tahminini yukarı çekmek görevi kurtarmak sayılmaz.
- **İddia sınırı:** Hedefi kaçırmak veya aday aramasında uygun rota bulamamak, hiçbir uygulanabilir rotanın hedefe ulaşamayacağını kanıtlamaz. Ana sistem koşullu öngörü ve deneysel toparlanma sonucu sunar. Küçük diagnostic'teki tam tarama sonucu yalnız kendi ayrık problemine aittir. ECC tam metin denetimi olmadan makalenin açık probleminin çözüldüğü veya genel bir olanaksızlık sertifikası üretildiği söylenmez.
- **İkinci doğrulama:** Çekirdek tamamlandıktan sonra §12'deki laboratuvar benchmark'ına uyarlama öncelikli adaydır; mevcut kinematik USV hızlı doğruluk kontrolü için korunur. Benchmark'ın gerektirdiği ROS 2 entegrasyonu ayrı değerlendirilir; bu aktarım tek başına saha/hidrodinamik doğrulaması değildir. Yeni bir USV fizik motoru veya operatör arayüzü bu ekin tamamlanma koşulu değildir.

Bu ek yalnız uygulama deposundaki plana işlendi; 8 Eylül tarihli dış kaynak dosya korunur. Yeni formal ispat ve research proposal sonraya bırakılmaya devam eder.

## 2. Başlangıç durumumuz: çalışan sürümü koru

8 Eylül'de mevcut deponun README'si, devam notu, kaynak dosya listesi ve geliştirme raporu incelendi. Aşağıdaki sayılar **depoda kayıtlı sonuçlardır; bu masterplan yazılırken yeniden çalıştırılmış test sonuçları değildir.** Uygulamaya devam eden görev önce güncel durumu doğrulayacak.

| Bileşen | Mevcut durum | Yeni plandaki karşılığı |
|---|---|---|
| FIELDWORK arayüzü, tekrar oynatma ve video | Mevcut | Korunacak; plan kararları ve kontrol müdahaleleri eklenecek |
| Exact GP, gerçek sentetik alan, gürültülü ölçüm | Mevcut | Küçük problem doğrulayıcısı ve karşılaştırma modeli |
| Sweep, nominal greedy, gerçek ölçümlerle adaptive greedy | Mevcut | Başlangıç yöntemleri; güçlü karşılaştırma için tek başına yeterli değil |
| Ölçüm kaybı, hareket sapması, 2–4 robot | Mevcut | Geliştirme senaryoları; yeni deneyler ayrı kaydedilecek |
| Merkezi hareket/mesafe filtresi | Mevcut | Kontrol referansı; QP/CBF diye yeniden adlandırılmayacak |
| Dönüş hızı sınırlı kinematik USV | Mevcut | Ön doğrulama; gerçek tekne veya hidrodinamik model değil |
| Test ve geliştirme koşuları | 187 test, 54 yöntem koşusu raporlanmış | Eski kanıt olarak korunacak; yeni sürüm ayrıca değerlendirilecek |
| Makaleye uygun SOGP, MDP/DP, performans QP'si | Henüz tamamlanmamış | Ana geliştirme işleri |
| Kalan bütçeyle çok adımlı aday rota ve referans yönetimi | Henüz tamamlanmamış | Projenin esas yeni uygulama hedefi |
| ECC2025 tam metin denetimi | Tam metin eksik | Yalnız makale yeniden üretimi bu girdiye bağlı |

Mevcut sonuçlarda adaptive yöntem, yalnız hareket sapması olan üç geliştirme seed'inin tamamında nominal greedy'den daha yüksek RMSE vermiş; ortalama değerler 0.1305 ve 0.1226. Buna rağmen GP varyansı düşmüş. Bu örnek korunacak: **daha düşük model belirsizliği, her zaman daha doğru harita demek değildir.** Yeni yöntemin geliştirilmesi bu gözlemi açıklamalı; yalnız grafiğin daha iyi görünmesine odaklanmamalı.

Mevcut üç seed `7, 19, 31` geliştirme verisidir. Yeni nihai değerlendirmede görülmemiş görevler ve seed'ler kullanılacak.

## 3. Kaynak makale ve uygulama kuralları

Ana çalışma: Suenaga, Hanif, Uto ve Hatanaka, **Hierarchical Multi-Robot Data Sampling for Environmental State Estimation through Online Gaussian Process**, ECC 2025. [Yayın kaydı](https://doi.org/10.23919/ECC65951.2025.11187026), [yazarın proje açıklaması](https://mhd-hanif.github.io/portfolio/gp-environmental-sampling/).

Önceki kaynak denetimi, merkezi sparse online GP, üst düzey MDP/Bellman tabanlı planlama ve alt düzey robot başına kısıt/QP yapısını işaret ediyor. **Kesin DP türü, ödül, durum tanımı, SOGP budaması ve QP denklemleri tam metinden doğrulanacak.** Kamuya açık açıklama bunların yerine geçmez.

İki çalışma profili kullanılacak:

| Profil | Ne yapılır? | Ne zaman kullanılabilir? |
|---|---|---|
| `independent` | Kaynakları belirtilmiş GP, kendi tanımladığımız MDP/DP, QP ve yeni yöntem | Hemen; bütün bağımsız tasarım tercihleri kaydedilir |
| `ecc2025` | Makaledeki denklemler, parametreler, controller/planner ve karşılaştırmalar | İlgili parçanın tam metin denetimi tamamlanınca |

Tam metin eksikliği `independent` SOGP, DP veya QP kodunun yazılmasını engellemez. Örneğin genel sparse GP algoritması birincil kaynağından uygulanabilir; bunun ECC makalesiyle aynı budama kuralını kullandığı ayrıca doğrulanmalıdır. Kaynak eksikliği nedeniyle makaleye ait sonuçlar tahmin edilmez.

Tam metin geldiğinde şu dokuz konu sayfa/denklem/parametre karşılığıyla kaydedilecek:

1. Tahmin edilen alan, robot modeli ve başlangıç koşulları.
2. Latent/predictive varyans ayrımı ve hedefin integral/toplam/maksimum tanımı.
3. SOGP güncellemeleri, sözlük kabulü, budama ve çoklu ölçüm sırası.
4. Üst düzey durum, aksiyon, geçiş, ödül, ufuk ve Bellman çözümü.
5. Robotlar arası hedef paylaşımı, merkezi bilgi ve yerel kontrol ayrımı.
6. Performans koşulu, QP amaç fonksiyonu ve slack'in anlamı/birimi.
7. Çarpışma, alan ve giriş kısıtları; kullanılan CBF ve varsayımları.
8. Kontrol/ölçüm/planlama saatleri ve sayısal çözüm ayarları.
9. Yeniden üretilecek şekiller, metrikler ve açıklanmayan ayrıntılar.

Kaynakta açıklanmayan bir ayar, proje tercihi olarak işaretlenir. Yeniden üretim toleransları ve fark raporu, sonuçlara bakarak sonradan esnetilmez. Makalede kullanılan bir bileşen eski kapsam dışı listesinde bulunsa bile kaynak profilinde korunur.

## 4. Yeni kapsam: hangi parçanın yeri ne?

| Parça | Karar ve gerekçe |
|---|---|
| Exact GP ve sparse online GP | İkisi de çekirdekte. Exact küçük problem doğrulaması; SOGP çevrimiçi ana hat ve kaynak uyumu için |
| MDP, Bellman, dinamik programlama | Çekirdekte. “RL kapsam dışı” diyerek kaldırılmayacak |
| QP ve uygun CBF kısıtları | Çekirdekte. İlk merkezi referans, ardından makalenin kısmi dağıtık yapısı doğrulanacak |
| Ölçüm kaybı, takip sapması, kontrol müdahalesi | Çekirdek deneylerin parçası |
| Kalan görev bütçesi ve zamanlı örnekleme planı | Çekirdek katkı uygulaması |
| USV doğrulaması | Ana teslimin ikinci dinamik modeli; mevcut basit sürüm geliştirilecek |
| ROS 2 | Yasak değil. Süreç ayrımı, mesaj zamanlaması veya USV benchmark bağlantısı doğrulanacaksa kullanılacak |
| Unity | Gerekli bir simülatör/benchmark bunu istiyorsa kullanılabilir; yalnız görsel etki için ana mimari taşınmayacak |
| NeuralRecon / Coverage-Recon | Ayrı 3B yeniden yapılandırma hattı. ECC projesinin zorunlu bağımlılığı sayılmıyor; gerekçe oluşursa sonraki entegrasyon |
| Deep RL / MARL eğitimi, Deep GP, deep ensemble | Ana problemi çözmek için şu anda gerekli değil. Ek ağır eğitim bu teslimde planlanmıyor; MDP/DP buna dahil değil |
| Zamanla değişen alan | İlk ortak benchmark statik. Kaynak makale gerektirirse kaynak profilinde korunur; ayrıca zaman uyumlu GP tasarımıyla genişletilebilir |
| Tam dağıtık GP fusion | İlk sistem merkezi GP + robot kontrol katmanları kullanır. Merkezi GP, kontrolün de bütünüyle merkezi olması demek değildir |
| Paket kaybı/gecikme teorisi | Yeni ispat ertelendi. Ölçümün alınmaması veya sisteme ulaşmaması simülasyonda incelenebilir; fiziksel paket kaybıyla eşitlenmez |
| Gerçek drone/tekne deneyi | İlk teslim için zorunlu değil. Donanım ve uygun deney ortamı oluşursa ayrı doğrulama aşaması |
| Semantic/VLM/LLM coverage | Bu scalar-field sorusuna katkısı tanımlanmadığı için aktif geliştirme işi değil |
| Birden fazla makaleden yararlanma | Serbest. ECC ana omurga, GP kaynağı algoritma temeli, USV çalışması doğrulama desteği; hepsini ayrı tez gibi birleştirme zorunluluğu yok |
| Research proposal, yeni teorem, başvuru e-postası | Çalışan proje ve sonuçlardan sonra |

Coverage-Recon, NeuralRecon çıktısıyla harita geri beslemesi kullanan ayrı bir araştırma yönüdür; bunun ROS 2/Unity bileşenlerini ECC scalar-field sistemine otomatik taşımayacağız. [Coverage-Recon makalesi](https://arxiv.org/abs/2510.18347).

Yeni teknoloji ekleme ölçütü: Belirli bir hata mekanizmasını, kaynak bileşenini veya deney sorusunu çözmeli. Yalnız teknoloji sayısını artırmak başarı ölçütü değildir.

## 5. Sistemin mimarisi

```text
Sentetik gerçek alan → sensör ölçümleri → alınan ölçüm defteri
                                           ↓
                                  Exact GP / SOGP
                                           ↓
Gerçek robot durumları → bütçe ve plan yöneticisi ← önceki planın kalanı
                                           ↓
                             MDP/DP ile aday rotalar
                                           ↓
                   kontrolcüyle rollout + ortak GP bilgi değerlendirmesi
                                           ↓
                      zamanlı çok robotlu örnekleme planı
                                           ↓
                           QP/kısıtlı düşük seviye kontrol
                                           ↓
                         robot hareketi → yeni gerçek durum

Bütün katmanlar → ham kayıtlar → metrikler → tekrar oynatma / demo
```

Gizli gerçek alan yalnız sensör üretimi ve değerlendirme katmanına açık olacak. Planlayıcı gerçek alanı, gelecekteki gürültüyü veya gelecekteki kayıp olaylarını görmeyecek. Arayüzde gerçek alanın gösterilmesi, algoritmanın ona erişmesi anlamına gelmeyecek.

Ana kayıtlar:

- `BeliefState`: alınan veri sürümü, posterior, GP türü, kernel/noise ayarı, sözlük durumu.
- `RobotState`: zaman, konum, gerekiyorsa yön/hız; kullanılan dinamik model.
- `SampleEvent`: robot, planlanan/gerçek zaman ve konum, denendi/alındı/kayboldu durumu.
- `SamplingPlan`: plan kimliği, üretim zamanı, ortak görev bitişi, rotalar ve her örnekleme olayı.
- `PlanEvaluation`: aynı planın her örnekleme adımındaki varyans tahmini, bütçe ve kısıt kontrolü, varsayımlar.
- `ExecutionEvent`: gecikme, kayıp ölçüm, QP müdahalesi, yeniden planlama nedeni, eski/yeni plan kimliği.

Sensörün hiç ölçmemesi ile ölçüp veriyi iletememesi genişletme aşamasında ayrı olay tipleri olacak. İlk kayıp senaryosu yalnız “bu ölçüm GP'ye ulaşmadı” anlamına gelecek.

## 6. GP ve ortam tasarımı

İlk geliştirme profili mevcut uygulamayı korur: 60 × 40 m alan, 2–4 robot, 90 s görev, 0.5 s hareket adımı, 5 s örnekleme aralığı. Bunlar **bağımsız geliştirme ayarlarıdır**, ECC parametreleri değildir. Mevcut kaynak açıklamasındaki 120 × 120 m, üç robot ve 10 s ölçüm ayarları doğrulanmış kaynak profilinde ayrıca ele alınacak.

### 6.1 Exact GP

Sabit kernel ve ölçüm gürültüsüyle exact GP, küçük veri miktarında doğru karşılaştırma noktası olacak. Posterior mean, latent varyans ve birden fazla gelecek konumdaki **ortak** covariance güncellemesi desteklenecek.

Bağımsız ana belirsizlik metriği sabit değerlendirme gridindeki ağırlıklı ortalama latent varyanstır:

`V(D) = Σ_j w_j Var[f(q_j) | D]`, burada `w_j ≥ 0` ve `Σ_j w_j = 1`.

Bu sonlu grid metriğidir. Grid dışındaki sürekli alan için garanti sayılmaz. Sensörün gelecekteki noisy ölçüm varyansı ayrı isimle kaydedilecek; latent varyansa ölçüm gürültüsünü karıştırmayacağız.

Exact GP'de sabit kernel/noise altında gelecekteki covariance yalnız örnekleme konumlarına bağlıdır. Buna karşılık gerçek harita hatası ölçülen değerlere ve modelin alanı ne kadar iyi temsil ettiğine bağlıdır. [GPML, Bölüm 2](https://gaussianprocess.org/gpml/chapters/RW2.pdf).

### 6.2 Sparse online GP

SOGP sonradan bırakılacak dekoratif bir özellik değildir. Çevrimiçi güncelleme, sınırlı sözlük ve kaynak algoritmasına yakınlık için uygulanacak. Geliştirme sırası:

1. Kaynak algoritmanın güncelleme ve sözlük kurallarını kaydet.
2. Budamanın etkisinin küçük olduğu örneklerde exact GP ile karşılaştır.
3. Sözlük dolarken admission/pruning olaylarını ve sayısal kararlılığı kaydet.
4. Aynı ölçüm dizisini farklı sözlük boyutlarında tekrar işle; mean/varyans farkı ve runtime'ı ölç.
5. Ana kapalı döngüye bağla; bütün karşılaştırma yöntemlerinde aynı GP backend'ini kullan.

Başlangıç için sözlük kapasitesi `32/64/128` denenebilir; bunlar proje aday ayarlarıdır. Nihai kapasite gelişim verisindeki hata/süre dengesiyle seçilecek. Budamanın ölçüm değerlerine bağlı olduğu durumda gelecekteki SOGP rotası için label-free exact tahmin iddia edilmeyecek. Sabit sözlükle koşullu forecast veya açıklanmış bir yaklaşık forecast kullanılabilir; hata ayrıca ölçülür. [Csató–Opper sparse online GP](https://eprints.soton.ac.uk/259182/1/gp2.pdf).

### 6.3 Alan aileleri ve model uyumsuzluğu

Geliştirmede geniş düzgün tepe, birbirinden uzak odaklar ve dar yapı içeren alanlar kullanılacak. Ana karşılaştırmada GP hiperparametreleri koşudan önce sabitlenir. Nihai deneylerde görülmemiş alan örnekleri ve ayrı bir kernel/uzunluk ölçeği uyumsuzluğu bloğu bulunur.

Gerçek alanı kullanarak online hiperparametre ayarı yapılmaz. Otomatik hiperparametre öğrenmesi eklenirse yalnız alınan ölçümlerle yapılır, çalışma süresi sayılır ve aynı deneyde bütün yöntemlere uygulanır. İlk teslim için böyle bir öğrenme zorunlu değildir.

## 7. Üst düzey MDP/DP planlayıcısı

Amaç, yalnız anlık yüksek varyans noktasını seçmekten çıkarak erişim süresini ve sonraki ölçümleri hesaba katmaktır.

Bağımsız ilk sürüm:

- Alan kaba hücrelere ayrılır; engel ve dinamik modeline göre kullanılabilir geçişler oluşturulur.
- Durum, en az hücre ve kalan ayrık zamanı içerir; USV için yön bilgisi veya uygun hareket primi eklenir.
- Eylemler komşu hücreye geçiş ve modelin izin verdiği bekleme/hareket seçenekleridir.
- Ödül, mevcut GP belirsizliği ve ulaşım maliyetinden tanımlanır; bütün terimlerin birimi ve normalizasyonu yazılır.
- Sonlu ufuklu Bellman geri hesaplamasıyla aday yollar üretilir. Bu, bağımsız tasarım kararıdır; ECC'nin kesin DP algoritması olduğu iddia edilmez.
- Robotlara aynı bilgiyi tekrar toplatmayı azaltmak için ortak covariance ile ardışık koşullama/atama yapılır; tek sabit robot sırasına bağımlılık denetlenir.

Mevcut posterior üzerinden dondurulmuş hücre ödülleri kullanmak, bütün GP geçmişini içeren bir belief-MDP'yi tam çözmek değildir. Hücre ödüllerini toplamak gerçek toplam bilgi kazanımıyla eşitlenmeyecek. **DP aday üretir; son seçim, rotanın zamanlı ortak ölçüm dizisinin GP üzerindeki etkisiyle yapılır.**

Başlangıç adayları: önceki planın hâlâ kullanılabilir kalanı, DP yolları ve kısa greedy yollar. Aday sayısı ile ufuk pilotta ölçülerek sınırlanacak; bütün çok robotlu yolların kombinatoryal tam taraması ana simülasyonda yapılmayacak.

Teslim ölçütü: üst düzey plan, her robot için yalnız waypoint listesi değil, hangi zamanda hangi ölçümün beklenildiğini veren ortak bir plan üretiyor olmalı.

## 8. Alt düzey kontrol ve uygulanabilirlik

### 8.1 İlk bağımsız QP

Holonomik modelde waypoint takibine yakın bir kontrol seçen QP kurulacak. Robotlar arası mesafe, alan ve giriş sınırları açık biçimde temsil edilecek. Basit bir geliştirme modeli için `p_dot = u` ve çiftler arası `h_ij = ||p_i-p_j||² - d_safe²` seçilebilir; merkezi QP'de nominal sürekli zaman koşulu `2(p_i-p_j)ᵀ(u_i-u_j) + α h_ij ≥ 0` olur. Bu formül bağımsız tasarımdır; ECC denklemi olduğu varsayılmaz.

Öklidyen hız topunu tam olarak uygulamak gerekiyorsa bunun saf lineer kısıtlı QP olmadığı dikkate alınır; konservatif çokgen/box yaklaşımı veya uygun konik çözüm seçimi açıkça belirtilir. Kısıt tanımı ile çözücü sınıfı birbirine uymalıdır.

Önce merkezi çözüm referans alınacak. Daha sonra kaynakta doğrulanan yerel QP/Voronoi paylaşımı uygulanacak; paylaşılan bilgi, eşzamanlılık ve iki robotun aynı güvenlik koşuluna katkısı kontrol edilecek. Yerel bir QP yazmak tek başına dağıtık güvenlik sağlamaz.

### 8.2 Performans kısıtı ve güvenlik ayrı tutulacak

Bağımsız ilk QP'nin görevi waypoint takibi ve hareket kısıtlarıdır. Makalenin variance-decay performans koşulu tam metinden çıkarılınca kaynak profilinde eklenir. Yeni yöntemde performans tercihlerinin kontrolcüye taşınması gerekiyorsa ölçüm anındaki öngörülen kazanç veya kaynakla doğrulanmış bir nicelik kullanılacak.

**Yeni veri gelmezken, sabit grid ve sabit GP için V(D) yalnız robot hareketiyle değişmez.** Bu nedenle doğrudan `dV/dt = kontrolün bir fonksiyonu` varsayarak yapay bir performans QP'si kurulmayacak. Ayrık ölçüm güncellemesi ile sürekli hareketin ilişkisi açık tanımlanmalıdır.

Performans slack'i ile güvenlik kısıtları ayrıdır. QP başarısızlığı, solver toleransı ve fallback davranışı kaydedilir. Güvenlik kısıtını sessizce gevşetmek veya her durumda “durmak güvenlidir” varsaymak kabul edilmez; bozucu altında duruş da sınırları ihlal edebilir. Geçerli bir kontrol bulunamazsa koşu başarısız olarak işaretlenir.

### 8.3 Sayısal doğrulama

Kısıtlar yalnız zaman adımı uçlarında denetlenmeyecek. Holonomik doğrusal segment için minimum çift mesafesi segment boyunca hesaplanır. USV hareketi eğri olarak uygulanıyorsa o modele uygun ara-zaman kontrolü kullanılır; mevcut doğrusal segment denetimi gerçek yay hareketine otomatik aktarılmaz.

Simülasyonda ihlal görülmemesi, bütün fiziksel sistemlerde güvenlik ispatı değildir. İlk teslimin hedefi gerçek uygulanan modelde açık kısıtlar, çözüm kaydı ve bağımsız ihlal kontrolüdür; yeni güvenlik teoremi değildir.

## 9. Yeni yöntem: yürütme ve bütçe farkındalığı

Mevcut adaptive greedy yalnız alınan verilerle hedefi güncelliyor. Yeni modül buna **çok adımlı zamanlı rota değerlendirmesi, kalan görev bütçesi ve plan geçerliliği** ekleyecek.

### 9.1 Her karar anında yapılacaklar

1. Gerçek robot durumlarını ve gerçekten ulaşmış ölçümleri al; GP'yi güncelle.
2. Ortak görev bitişine kalan süreyi, kalan örnekleme anlarını ve varsa mesafe bütçesini hesapla. Başlangıç planındaki bütçeyi yeniden sıfırlama.
3. Önceki planın kalanını mevcut durumdan tekrar yürütülebilirlik denetimine sok. Eski haliyle geçerli olduğunu varsayma.
4. DP/greedy kaynaklı yeni ortak rota adaylarını oluştur.
5. Adayları kullanılacak alt kontrolcü ve dinamiklerle nominal olarak ilerlet; gerçekçi erişim zamanlarını ve örnekleme konumlarını çıkar.
6. Her aday için ortak GP covariance güncellemeleriyle bütün ara örnekleme adımlarının ve görev sonunun varyansını hesapla.
7. Geçerli adaylar arasında aynı kalan bütçeye göre seçim yap. İlk ölçüt görev sonu V; benzer adaylarda yol ve plan değiştirme maliyeti kullanılabilir. Tolerans ve ağırlıklar geliştirmede sabitlenir.
8. Yeni planı ve varsa kullanılabilir eski planı sakla. Değiştirme gerekçesini, beklenen kazancı ve hesap süresini kaydet.
9. Kontrolü yalnız bir sonraki karar aralığı için uygula; gerçekleşen hareket/ölçümle tahmini karşılaştır.

Nominal rollout gelecekteki bilinmeyen rüzgârı veya kayıpları kullanmaz. İstenirse geliştirmede tanımlanmış küçük senaryo kümesiyle ilave risk değerlendirmesi yapılabilir; bu, bütün bozuculara karşı garanti olarak adlandırılmaz.

### 9.2 Belirsizlik referansı ne demektir?

Seçilen tek bir ortak planın ilk `j` ölçüm olayından hesaplanan eğri `B_k(j)` olarak kaydedilir. Bu, o planın varsayımları altında beklenen belirsizlik gidişidir. Farklı ufuklarda ayrı ayrı bulunan en iyi yolların noktaları birleştirilerek hayali bir eğri oluşturulmaz.

Exact GP, sabit model ve aynı uygulanabilir rota/problem tanımı altında, uygulanabilir bir planın doğru hesaplanan görev sonu V değeri minimizasyon probleminin en iyi değerine bir **üst adaydır**. “Daha aşağısı fiziksel olarak mümkün değil” anlamında alt sınır veya belirsizlik tabanı değildir. Yaklaşık SOGP forecast'i, özellikle değer bağımlı budama varsa, bu üst sınır özelliğini otomatik taşımaz; yalnız koşullu bir tahmin olarak kaydedilir. Arama hiçbir aday bulamadığında “aday araması başarısız” denir; bütün mümkün rotaların olanaksız olduğu iddia edilmez.

Arayüzde iki ayrı nesne olacak:

- **Sabit görev hedefi:** koşu başlamadan belirlenen, yöntemler için ortak eşik.
- **Güncellenen plan tahmini:** mevcut bütçe ve veriyle seçilen rotanın koşullu forecast'i.

Yeni plan tahminini yukarı çekmek, sabit görevi başarmak sayılmaz. Referansa kalan fark küçüldü diye harita iyileştiği sonucu çıkarılmaz.

### 9.3 Yeniden planlama tetikleyicileri

İlk doğrulama için her ölçüm anında değerlendirme yapılır. Sonra olay tetiklemeli sürüm eklenir: kaçırılan ölçüm, zaman/konum sapması, belirgin kontrol müdahalesi veya sabit kontrol aralığı sonunda yeniden değerlendirme. Eşikler geliştirmede seçilir; son deneyde ayarlanmaz.

Plan geçmişinin resetlenmesi fark metriğini yapay küçültebilir. Forecast hesaplarının karşılaştırılması için ayrı bir değerlendirme yapılacak: aynı kayıtlı `BeliefState` snapshot'ı, robot durumları, aday ölçüm planı, tahmin ufku ve doğrulama zamanı üzerinden farklı forecast yaklaşımları sınanacak. Ana kapalı döngü karşılaştırmasında ise her yöntem **kendi gerçekten topladığı veriden oluşan posterioru** kullanır; farklı yolların posteriorlarının aynı olması beklenmez. Mevcut rolling forecast ile görev başından nominal forecast doğrudan yarıştırılmayacak.

Önce deneysel, nominal yürütme değerlendirmesi tamamlanacak. Recursive feasibility, robust backup invariant ve formal attainability certificate sonraki araştırma hedefleridir; bu projenin bitiş koşulu değildir.

## 10. Karşılaştırmalar ve katkıyı ayırma

Ana yöntemin yalnız açık döngü bir planı yenmesi yeterli değil. Aşağıdaki yöntemler aynı GP, dinamik, alt kontrol, görev ve bilgi erişimiyle karşılaştırılacak:

| Kod | Yöntem | Rolü |
|---|---|---|
| B0 | Sweep/lawnmower | Basit kapsama referansı |
| B1 | Görev başında hesaplanan nominal greedy | Yürütme sapmasının etkisini gösteren tanısal referans |
| B2 | Her ölçümde gerçek posterior ve konumla yeniden hesaplanan greedy | Mevcut adaptive yöntemi temsil eden güçlü yerel referans |
| B3 | Her ölçümde gerçek posteriorla yeniden planlayan MDP/DP + aynı QP | **Ana karşılaştırıcı**; yeni yöntemin üstünlüğü otomatik varsayılmaz |
| P | Bütçe, kontrolcü rollout'u ve plan geçerliliği kullanan önerilen yöntem | Önce periyodik, sonra olay tetiklemeli sürüm |
| E0/E1 | Kaynaktaki constraint-only ve hierarchy | Tam metin denetiminden sonra ayrı makale karşılaştırması |

B3 de gerçek robot durumlarını, kalan süreyi ve gerçekten alınan veriyi görecek. Ona yapay olarak eski veri kullandırılmayacak. P ile fark, çok adımlı kontrol etkisini nasıl değerlendirdiği, plan değişimini nasıl kabul ettiği ve hangi olayda yeniden hesapladığıdır. Gerçek fark oluşturulamıyorsa yeni yöntem iddiası daraltılır.

Zorunlu ablation'lar:

1. **Kontrolcü rollout'u olmadan:** erişim konumu/süresi yalnız nominal waypoint/geometriden hesaplansın.
2. **Planı koruma/değiştirme mekanizması olmadan:** her kararda en iyi görünen yeni aday seçilsin; plan salınımı ve kalite ölçülsün.
3. **Olay tetiklemesi yerine periyodik:** bilgi ve rota değerlendirmesi aynı kalsın; hesap maliyeti ile kalite ayrışsın.

SOGP etkisi aynı politika altında ayrıca exact GP ile karşılaştırılır. GP değişimi, planlama katkısının başarısı gibi sunulmaz. Ablation'lar önce temsilî blokta çalıştırılır; sonuçla ilgisiz bütün parametrelerin tam çapraz çarpımı yapılmaz.

## 11. Deneyler ve değerlendirme

### 11.1 Senaryolar

| Senaryo | Ölçülen sorun |
|---|---|
| Nominal, geniş düzgün alan | Ek mekanizmanın gereksiz yere kaliteyi veya maliyeti bozup bozmadığı |
| Ölçüm kaybı | Planlanan bilginin GP'ye ulaşmaması |
| Takip sapması | Ölçümün hedeflenen yerde alınmaması |
| Dar geçit/robot etkileşimi | Güvenlik müdahalesinin zamanlı planı değiştirmesi |
| Birleşik bozucu | Ölçüm ve hareket hatalarının birlikte etkisi |
| Kısa kalan görev bütçesi | Uzak hedefin artık zamanında örneklenememesi |
| Model uyumsuzluğu | GP varyansı ile gerçek hata arasındaki ayrışma |
| USV kinematiği | Dönüş/ilerleme kısıtının plan seçimine etkisi |

Dar geçit veya engel senaryosu ancak ilgili geometri ve kontrol kısıtları uygulanınca açılır. İlk holonomik sonuçlar ile USV bozucularına aynı sayı verilmesi, aynı fiziksel bozucu şiddeti anlamına gelmez.

### 11.2 Adil bütçe

Ana karşılaştırma: aynı alan, başlangıç, görev süresi, robot sayısı, örnekleme takvimi ve sensör modeli. Gürültü/kayıp olayları seed–robot–örnekleme zamanı ile eşleştirilir; yöntemler farklı konumlarda ölçüm yapabilir. Gelecek olaylar planlayıcıya verilmez.

Eşit süre, eşit gerçekleşen yol veya enerji demek değildir. Yol ve alınan ölçüm sayısı ayrıca raporlanır. İkinci bir mesafe bütçesi deneyi yapılırsa bütün yöntemlere aynı sert bütçe uygulanır; sonradan farklı yolları eşitlemiş gibi sunulmaz. Enerji modeli yoksa metre “enerji” diye etiketlenmez.

### 11.3 Metrikler

| Metrik | Kullanımı |
|---|---|
| Görev sonu field RMSE | Ana harita kalitesi metriği; sabit test gridinde |
| Ortalama ve maksimum latent varyans | Model belirsizliği; RMSE'den ayrı |
| Sabit hedefe ulaşma oranı/zamanı | Eşik koşudan önce sabit; ulaşılamayan koşular başarısız/sansürlü olarak açık raporlanır |
| Gerçek yol ve alınan/kaçırılan ölçüm sayısı | Kaynak kullanımı ve görev muhasebesi |
| Planlama, GP, kontrol ve toplam süre | Medyan ve kuyruk gecikmeleri; offline ön planlama dahil |
| Minimum mesafe, alan/giriş ihlalleri, solver başarısızlığı | Gerçek uygulanan modelin kısıt davranışı |
| Geçersizleşen/değiştirilen plan, neden ve gecikme | Önerilen mekanizmanın nasıl çalıştığını açıklama |
| Ortak ufukta forecast hatası | Planın bilgi tahminini sınama; güvenlik sertifikası değil |

Performans slack'i varsa birimiyle raporlanır; farklı anlamdaki slack'ler kıyaslanmaz. Ham slack azalması tek başına yöntem başarısı değildir.

### 11.4 Geliştirme ve son değerlendirme

Önce mevcut seed'ler ve küçük yeni geliştirme setiyle hata ayıklanır. Daha sonra yöntemler, parametreler, birincil karşılaştırma ve seed listesi sürüm kaydına alınır. Başlangıç nihai hedefi ana senaryo başına **20 eşleştirilmiş, geliştirmede kullanılmamış görevdir**; süre/bellek pilotuna göre deney kapsamı koşular başlamadan kesinleştirilir. Bu sayı istatistiksel güç garantisi değildir.

Her yöntem çifti aynı görev üzerinde değerlendirilir; RMSE farkının dağılımı ve görev düzeyinde bootstrap güven aralığı gösterilir. Grid hücreleri veya aynı koşudaki zaman noktaları bağımsız deney gibi sayılmaz. Yöntem çökmesi veya kısıt ihlali ortalamadan sessizce atılmaz.

Son değerlendirmede yöntem ayarı değişirse eski sonuçlar geliştirme kanıtına dönüşür; yeni değerlendirme seti gerekir. İyileşen, eşit kalan ve kötüleşen senaryolar birlikte raporlanır. “Genel üstünlük” yalnız gösterildiği kapsamda kullanılabilir.

## 12. USV ve gerektiğinde ROS 2

Mevcut USV sürümü değişken ileri hız, sınırlı yaw rate ve sıfır hızda yön değiştirmeye izin veren örneklenmiş kinematik modeldir. Sonraki sürümde hangi araç sınıfını temsil ettiği açık seçilecek:

- Genel unicycle doğrulaması sürdürülürse bu isimle sunulur.
- Dubins/sabit hızlı araç deneyi yapılırsa yerinde dönüş kaldırılır, pozitif hız ve dönüş yarıçapı sınırı modele/planlayıcıya taşınır.
- Dönüş sırasında örnekleme konumları, kontrol müdahalesi ve ara-zaman geometri kontrolü aynı modele göre hesaplanır.
- İlk USV karşılaştırması aynı GP ve politika farkını kullanır; farklı field/bozucu ayarları ayrıca bildirilir.

Hatanaka grubunun **Constraint-Driven Multi-USV Coverage Path Generation for Aquatic Environmental Monitoring** çalışması ve açık benchmark'ı bu aktarım için birincil dayanak olabilir. Bu, makaledeki bütün dairesel yol kontrolünü veya fiziksel deneyi otomatik yeniden ürettiğimiz anlamına gelmez. [Makale](https://arxiv.org/abs/2411.00579), [laboratuvar benchmark'ı](https://github.com/htnk-lab/Multi-USV-Benchmark).

ROS 2 aşaması gerektiğinde GP, planlayıcı ve robot kontrol süreçlerini ayıracak; simülasyon saati, mesaj zaman damgası, ölçüm alındısı ve replay kaydı korunacak. Amaç sayısal sürümle aynı olay dizisinin sonuçlarını ve süreç zamanlamasını karşılaştırmak olacak. ROS 2 entegrasyonu, ana deneyleri ve demoyu gereksiz biçimde bekleten bir ön koşul olmayacak.

## 13. Kod yapısı ve geliştirme disiplini

Mevcut Python 3.11 ortamı, paket ismi, CLI ve offline arayüz korunacak. Kurulu optimizasyon ve sayısal kütüphanelerden yararlanılacak; sırf yeni plan için framework değiştirilmeyecek. Aşağıdaki yapı yeni dosyaların hedef yerleşimidir, mevcut dosyaların tamamının hazır olduğu iddiası değildir:

```text
src/attain_sampling/
  gp/               exact, sparse, forecast, GP sözleşmeleri
  planning/         coarse MDP, DP, ortak atama, zamanlı planlar
  control/          takip QP, güvenlik/alan kısıtları, solver kayıtları
  attainability/    bütçe, rollout, plan değerlendirme ve geçerlilik
  sim/              dünya, sensör, dinamikler, scheduler
  eval/             metrikler, eşleştirilmiş karşılaştırma, artefaktlar
  demo/             mevcut sunucu, replay ve arayüz
configs/
  independent/      bağımsız geliştirme ve değerlendirme ayarları
  ecc2025/          yalnız kaynakla doğrulanmış ayarlar
docs/
  CONTINUE_HERE.md, paper_audit.md, design_decisions.md, DEMO.md
reports/            tarihli geliştirme ve son değerlendirme raporları
```

`sim/mapping.py` içindeki çalışan parçalar ihtiyaç doğdukça bu arayüzlere ayrılacak. Büyük bir toplu refactor ile çalışan kanıtlar kaybedilmeyecek. Her adım bir önceki demo akışını çalışır tutmalı.

Bir koşu için config, seed'ler, kaynak sürümü/hash'i, ortam, ham ölçümler, plan sürümleri, kontrol ve metrik kayıtları saklanacak. Grafik ve video bu kayıtlardan üretilecek; demo animasyonunda sonuçlara uymayan yollar çizilmeyecek.

Mevcut aktarım klasörleri hash'i korunmuş tarihsel girdilerdir. Yeni plan ayrı sürüm olarak alınacak; eski manifest'e ait dosyalar sessizce değiştirilmeyecek. Uygulama görevinde aktif README/devam notu yeni planı gösterecek, eski plan tarihsel olarak işaretlenecek.

## 14. Test ve doğrulama

Test sayısı veya kapsam yüzdesi proje başarısı değildir. Aşağıdaki gerçek hata riskleri için test/deney yapılacak:

- Exact GP'nin batch/sequential güncellemeleri ve ortak covariance hesapları uyuşuyor mu?
- Aynı yerde gürültülü tekrar ölçümü latent varyansı beklenen yönde etkiliyor mu?
- SOGP mean/varyans farkı, budama ve eşzamanlı ölçüm sırası izlenebiliyor mu?
- Planlanan örnek konumu gerçekten o zamana kadar erişilebilir mi; kayıp ölçüm gerçek GP'ye ekleniyor mu?
- Farklı prefix tahminleri aynı tek planın parçaları mı?
- Planlayıcı gizli alanı ve gelecek olayları görmeden çalışıyor mu?
- QP kısıtları, infeasibility/fallback ve ara-zaman mesafe denetimi anlamlı zor durumlarda sınanıyor mu?
- Bütün yöntemler eşleştirilmiş olayları ve aynı bitiş bütçesini alıyor mu?
- Kaydedilmiş bir koşudan metrikler bağımsız olarak yeniden üretilebiliyor mu?
- Küçük tam taramalı diagnostic'te yaklaşık planın değeri gerçekten uygulanabilir adayla tutarlı mı?

Mevcut diagnostic ve onun eşit/kötü sonuçları korunacak. Diagnostic'in bir örneğinde yeniden planlamanın kazanç sağlamaması başarısız test değildir; doğru deney bulgusudur. Büyük yeni model için bu küçük örneğin süre veya garantileri genellenmez.

Yeni bir modülün ilgili doğruluk kontrolü ve uçtan uca smoke koşusu geçince sonraki işe geçilir. Yeni hata veya değişiklik olmadan aynı büyük test dizisini tekrar tekrar çalıştırmak gerekmez.

## 15. Compute yaklaşımı

Kullanıcı yoğun çalışmaya hazır; plan sabit bir “üç haftada bitsin” sınırına göre küçültülmeyecek. **Pratik kısıt uzun eğitim, gereksiz kombinatoryal arama ve kontrolsüz deney çoğalmasıdır.**

CPU ilk tercih olacak. GPU ancak ölçülmüş bir darboğaz için kullanılacak. Ana hat için neural network eğitimi gerekmiyor. Önce küçük GP doğrulaması, sonra sınırlı SOGP sözlüğü ve kaba DP ile gerçekçi kapalı döngü kurulacak.

Her büyük deneyden önce temsilî pilot yapılır: 4 robot, en pahalı aktif dinamik, uzun görev ve yeterli SOGP sözlük doluluğu. GP, aday üretme, rollout, QP, kayıt ve görselleştirme maliyetleri ayrı ölçülür. Mevcut saniye altı kısa koşular, yeni DP/SOGP/QP benchmark'ının süresi sayılmaz.

Başlangıç mühendislik ayarları: kısa `4–8` örnekleme aralığına yayılan aday ufukları, sınırlı sayıda ortak rota ve `32/64/128` sözlük pilotu. Görev sonuna kadar bir plan gerekiyorsa kısa adayın sonuna açıkça tanımlanmış uygulanabilir devam politikası eklenir; kısa ufuk değeri görev sonu değeriymiş gibi sunulmaz.

Maliyet yüksekse sırayla covariance önbelleği, aday eleme, seyrekleştirme ve sınırlı paralellik uygulanır. Arama bütçesi azaltılırsa bütün ilgili yöntemler aynı karşılaştırma mantığıyla yeniden değerlendirilir. Başarı göstermek için yalnız en kolay senaryolar tutulmaz.

Videolar bütün benchmark koşularında üretilmez; kayıtlı sonuçlardan seçilmiş sunum örnekleri için oluşturulur. Gerçek zaman iddiası yapılacaksa planlayıcının gecikmesi görev yürütmesine dahil edilmeli veya deadline aşımı açıkça modellenmelidir.

## 16. Uygulama sırası ve tamamlanma ölçütleri

Takvim yerine somut teslimlere göre ilerleyeceğiz. Önceki aşama kullanılabilir hâle gelirken bağımsız işler paralel yürütülebilir; kaynak beklemek bütün geliştirmeyi durdurmaz.

| Aşama | İş | Tamamlandı demek için |
|---|---|---|
| M0 — Mevcut sürümü sabitle | Kod/rapor durumunu doğrula, yeni planı aktif yap, eski kanıtları koru | Mevcut demo ve küçük karşılaştırma yeniden çalışıyor; mevcut/eksik listesi güncel |
| M1 — Gerçek kontrol katmanı | Merkezi QP, kısıtlar, solver/ara-zaman kayıtları; mevcut filtreyle kontrol deneyi | Robotlar uçtan uca QP ile hareket ediyor; zor durum ve başarısızlık kayıtları doğru |
| M2 — Hiyerarşik planlama | Zamanlı plan sözleşmesi, coarse MDP/DP, ortak bilgi değerlendirmesi | Gerçek posterior → DP hedefleri → QP → yeni ölçüm döngüsü çalışıyor |
| M3 — SOGP ana hattı | Online sparse GP ve exact karşılaştırmaları | Sözlük doluluğu/budama dahil kapalı döngü; GP farkı ve runtime raporu |
| M4 — Yürütme/bütçe modülü | Kontrolcü rollout'u, eski planın denetimi, aday/reference yönetimi | Kaçırılan ölçüm veya gecikmede doğru bütçeyle yeni plan; açıklanabilir olay kaydı |
| M5 — Kaynak uyumu | Tam metin geldikçe ECC denklemlerini ve baseline'larını ayrı profilde uygula | Denklem/parametre kaydı, yeniden üretilen şekiller ve fark raporu; kaynak yoksa açık eksik |
| M6 — Karşılaştırma | B0–B3/P, ablation, görülmemiş görevler | Dondurulmuş protokol, ham sonuçlar, olumsuz/eşit bulgular dahil rapor |
| M7 — USV aktarımı | Açık araç modeli, erişim/yol doğrulaması, gerekiyorsa ROS 2 | Aynı katkı sorusunun ikinci modelde sonuçları; model sınırları açık |
| M8 — Sunulabilir sürüm | Arayüz, demo, video, README, teknik sonuç notu | Başka bir kişi kurup koşabiliyor; iddialar doğrudan sonuç kayıtlarına bağlı |

M1 ve M3, temiz arayüzler üzerinden paralel ilerleyebilir. Tam metin erişimi M5'i etkiler; M0–M4, M6–M8'in bağımsız profilini bekletmez. Makale yeniden üretimi eksik kalırsa final paket açıkça bağımsız proje olarak sunulur; “ECC reproduction tamamlandı” denmez.

**Çalışan v0 demo, yeni masterplanın tamamlanması değildir.** Yeni ana teslim için hiyerarşi, SOGP, kısıtlı kontrol ve yürütme/bütçe mekanizması uygulanmış; güçlü karşılaştırma ve USV değerlendirmesi yapılmış olmalı. Yeni formal teorem veya research proposal bu tamamlanma ölçütüne eklenmeyecek.

## 17. Demo ve profesöre gösterilecek proje paketi

Arayüzün mevcut dört haritası korunacak: gerçek alan, posterior mean, belirsizlik ve hata. Bunlara planlanan/gerçek örnekler, eski/yeni rota, güvenlik müdahalesi ve yeniden planlama nedeni eklenecek.

Bir gösterimde kullanıcı aynı dünya ve seed üzerinde B3 ile P'yi yan yana izleyebilmeli. Belirlenmiş bir ölçüm kaybı veya rota gecikmesinden sonra planın neden değiştiği açık görünmeli. Sabit görev hedefi ile yeni plan tahmini farklı gösterilmeli; teknik log isimleri ana ekranı doldurmamalı.

Seçilecek gösterimler:

1. Nominal durumda sistemin temel çalışması.
2. Ölçüm kaybı veya kontrol müdahalesi altında planın güncellenmesi.
3. USV dönüş sınırının örnekleme kararını değiştirmesi.
4. Yöntemin kazanç sağlamadığı bir örnek ve olası açıklaması.

Son teslimler:

- Tek komutla başlatılabilen yerel demo ve tekrarlanabilir CLI koşuları.
- Kaynak/bağımsız tasarım ayrımını gösteren kısa teknik README.
- Ham verilerden üretilmiş ana karşılaştırma, ablation, runtime ve başarısızlık şekilleri.
- Tercihen 5–8 sayfalık teknik sonuç notu: problem, tasarım, deney, sonuç ve sınırlar. Bu bir research proposal değildir.
- Kayıtlı koşudan hazırlanmış 90–120 saniyelik video ve daha ayrıntılı canlı demo yönergesi.
- Kaynak sürümü/config/seed manifest'i ve yeniden çalıştırma açıklaması.

Sunumun ana mesajı sonuçlara göre yazılacak. Savunulabilir örnek: “Çok robotlu GP örnekleme sisteminde yürütme ile plan arasındaki farkı izleyen bir modül geliştirdim; güçlü yeniden planlama baseline'ına karşı şu koşullarda şu etkiyi ölçtüm.” Sayısal üstünlük çıkmazsa uydurulmayacak; hangi mekanizmanın çalışmadığı anlatılacak.

Senin açıklayabilmen gerekenler: GP varyansı ile gerçek hata neden ayrılır; MDP hangi yaklaşımı yapar; QP neyi kısıtlar; neden seçilen rota zamanında uygulanabilir görünür; forecast hangi olayda geçersizleşir; ana karşılaştırıcı ne kadar güçlüdür. Demo bu soruların yerini tutmayacak, onları görünür kılacak.

## 18. Sonuçlara göre kararlar ve sonraki araştırma

| Gözlem | Yapılacak şey |
|---|---|
| P yalnız nominal açık döngü planı yeniyor | Katkıyı güçlü yeniden planlama karşılaştırmasıyla yeniden değerlendir; genel üstünlük söyleme |
| P ile periyodik B3 aynı kaliteyi daha az hesapla veriyor | Sonucu hesap/kalite dengesi üzerinden değerlendir; harita kalitesi kazancı uydurma |
| P daha düşük varyans ama daha kötü RMSE veriyor | Model uyumsuzluğu ve örnekleme dağılımını incele; bütün sonuçları koru |
| Yöntem faydası yalnız bir senaryoda görülüyor | İddiayı o senaryo ve koşullarla sınırla; gelişimde seçilen demo ile nihai kanıtı ayır |
| SOGP forecast'i budamada sapıyor | Yaklaşım varsayımını düzelt, farkı ölç; nominal tahmini sertifika yapma |
| QP sık infeasible veya plan salınımı var | Önce kontrol/bütçe/tetikleme mekanizmasını düzelt; arayüz cilasıyla kapatma |
| ECC tam metni hâlâ yok | Bağımsız projeyi bitir; kaynak yeniden üretimini ayrı eksik olarak kaydet |

Çalışan sonuçlar oturduktan sonra araştırma proposal'ı hazırlanabilir. O aşamada incelenecek aday konular: uygulanabilir yedek planın korunması, koşullu performans sınırı, SOGP yaklaşım hatası ve zamanla değişen alan. Bunlar mevcut proje çıktısına göre seçilecek; bugün tamamlanmış teori gibi yazılmayacak.

**İlk icra emri:** Mevcut çalışan FIELDWORK sürümünü doğrula ve koru. Ardından gerçek QP kontrol katmanı ile zamanlı MDP/DP planlarını bağla; SOGP'yi paralel geliştir. Bütçe ve yürütme modülünü bu sistemin üzerine ekle. Güçlü baseline ve ablation sonuçları olmadan “yeni yöntem başarılı” deme. Çalışan projeyi tamamlamadan research proposal hazırlığına geri dönme.

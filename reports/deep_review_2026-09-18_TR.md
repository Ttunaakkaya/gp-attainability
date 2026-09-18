**GP Attainability / FIELDWORK — makale, master plan, kod ve deneylerin derin incelemesi**

18 Eylül 2026. Bu rapor çalışma dizininin bu tarihteki durumunu değerlendirir. İnceleme amacı analizdir; uygulama kodu, eski deney sonuçları ve protokoller değiştirilmedi.

**Ana değerlendirme**

FIELDWORK, çalışan ve ciddi biçimde doğrulanmış bir araştırma simülatörüne dönüşmüş. GP, zamanlı planlama, kısıtlı kontrol, gerçekleşen ölçümlerle güncelleme, kalan bütçe, plan değerlendirme, deney otomasyonu ve sunum katmanları birbirine bağlanmış. Deney kaydı ve başarısız sonuçları raporlama disiplini projenin en güçlü taraflarından biri.

Buna karşılık önerilen P politikasının güçlü periyodik B3 karşısında alan tahmin hatasını azalttığı gösterilmiş değil. İki geçerli ana çalışmanın toplam on senaryo karşılaştırmasında P−B3 RMSE güven aralıkları sıfırı içeriyor. P belirgin biçimde daha fazla hesap harcıyor. USV'de bazı varyans ve hedef başarısı kazanımları var; bunlar gerçek fakat daha doğru harita veya genel erişilebilirlik garantisi ile eşanlamlı değil.

Kaynak denetimi de bütünüyle kapanmış sayılamaz. Makalenin 12. denkleminde eksik olduğu ileri sürülen çarpan aslında basılı denklemde mevcut. Ayrıca ECC kontrol katmanının kullandığı sanal GP ile çevrimiçi SOGP'nin taşıdığı bilgi arasında, budama başlamadan bile ortaya çıkan bir uyumsuzluk var. Bu ikisi bağımsız profilin ExactGP sonuçlarını geçersiz kılmıyor; ECC'ye uyum ve makaleye yönelik eleştirilerin yeniden düzenlenmesini gerektiriyor.

Bugünkü en sağlam anlatım şu: **“Yürütme farkını hesaba katan bir GP örnekleme sistemi kurdum; güçlü karşılaştırıcılarla sınadım, ilk olumlu sonucu açıklayan bir karşılaştırıcı hatasını bulup düzelttim ve kalan kazanımların belirsizlik ile hesap maliyeti açısından sınırlarını gösterdim.”** “Yeni yöntem bütün koşullarda daha iyi” anlatımı mevcut kanıtla savunulamaz.

**1. İncelemenin kapsamı ve kanıt düzeyi**

Ana ECC makalesinin sekiz sayfası, özellikle denklem ve şekillerin bulunduğu sayfalar görsel olarak kontrol edildi. GPML, Csató–Opper ve ilgili IPP/kontrol kaynaklarının projeye dayanak oluşturan birincil metinleri ve ilgili algoritma/varsayım bölümleri incelendi. Master plan, karar kayıtları, kaynak ve varsayım belgeleri, çekirdek modüller, testler, M1–M7 raporları, M8 teknik notu ve şekil üretim zinciri karşılaştırıldı. Kaynak listesindeki her web kaydı veya üçüncü taraf deponun tamamı için yeni ve eksiksiz bir denetim yapıldığı iddia edilmiyor; erişilemeyen komşu kaynaklardan yeni teknik sonuç çıkarılmadı.

Bu incelemede yeniden yapılan kontroller:

| Kontrol | Sonuç | Ne gösterir? |
|---|---|---|
| Ana test paketi ve coverage | 1.007 test geçti; toplam kapsam %94,52 | Mevcut uygulama sözleşmelerinin geniş ölçüde korunduğunu |
| Küçük bağımsız diagnostic | 11 test geçti | Kendi küçük ayrık problemindeki hesapların tutarlılığını |
| Ruff, format, mypy | Geçti; 84 dosya biçim kontrolü, 44 kaynak dosya tip kontrolü | Statik kaliteyi; bilimsel iddiaların doğruluğunu tek başına göstermez |
| Üç büyük paketin manifestleri | 406 × 3 = 1.218 girdi; sıfır uyumsuzluk | Kayıtlı dosyaların mevcut manifestlerle tutarlılığını |
| Kaynak snapshot'ları | 58 + 62 + 64 = 184 dosya; sıfır hash uyumsuzluğu | Her paketin arşivlenen kaynaklarının kendi kaydıyla tutarlılığını |
| Analizlerin yeniden hesaplanması | Üç pakette kayıtlı analizle birebir eşleşti | Kayıt tablosundan üretilen istatistiklerin tekrarlanabilirliğini |
| Bağımsız yoğun matris hesabı | Seçilmiş 75 koşuda son RMSE ve varyans farkı en fazla yaklaşık 1,42×10⁻¹⁵ | Bu örneklerde GP son harita hesaplarının sayısal doğruluğunu |

Bağımsız GP kontrolü, her pakette beş ana senaryonun ilk seed'indeki beş yöntemi kapsıyor. Projenin GP sınıfı yerine doğrudan NumPy matris çözümü kullanıldı. Üç paketteki toplam 3.960 yöntem koşusu yeniden simüle edilmedi; bütün ham hareket yolları bu incelemede baştan geometri denetimine sokulmadı. Önceki raporların geniş ham-kayıt denetimleri ile burada yeni yapılan kontroller bu nedenle ayrı kanıt katmanlarıdır. Manifest tutarlılığı da dışarıda yayımlanmış, değiştirilemez bir ön kayıt anlamına gelmez.

Yeni kanıt dosyaları: [deney doğrulamaları](<C:/Users/Lenovo/Desktop/GP Attainability/reports/audit_evidence_2026-09-18.json>), [plan koruma örneği](<C:/Users/Lenovo/Desktop/GP Attainability/reports/audit_retention_probe_2026-09-18.json>), [SOGP–kontrol karşılaştırması](<C:/Users/Lenovo/Desktop/GP Attainability/reports/audit_sogp_controller_probe_2026-09-18.json>).

**2. Makaleler projenin hangi kısmını gerçekten destekliyor?**

**Suenaga ve diğerleri, ECC 2025.** Makalenin esas omurgası merkezi çevrimiçi sparse GP, hücreler üzerinde MDP/Bellman planlama ve robot başına kısıtlı kontrolün birleşimi. Yerel bilgi görevleri Voronoi paylaşımıyla kuruluyor; üst planlayıcı, yalnız anlık gradyanı izleyen kontrolün uzak belirsiz bölgelere gidememesine çözüm arıyor. FIELDWORK bu mimariyi anlamlı biçimde takip ediyor. Bununla birlikte bağımsız profilin merkezi holonomik QP'si, zamanlı adayları ve P politikası makaledeki sistemin aynısı değil; ayrı profiller kullanılması doğru tercih. [Makalenin yayın kaydı](https://doi.org/10.23919/ECC65951.2025.11187026).

Makaledeki J, sonlu bir değerlendirme kümesi üzerindeki **latent varyansların normalize edilmemiş toplamı**. Ortalama varyans kullanan bağımsız profil ile sayısal eşikler doğrudan kıyaslanamaz. Makale lineer azalma şartının sonsuza kadar sağlanamayacağını kendisi söylüyor; bunu yeni keşfedilmiş bir kusur gibi sunmak yanlış olur. Asıl soru geçici rejimde, verilen model ve kontrol altında bu azalma talebinin ne kadar sağlanabildiği.

Makale bazı sayısal ayrıntıları açıklamıyor. Birim köşegenli kernel ve 900 test noktasıyla J'nin başlangıçta yaklaşık 3.600 çizilmesi, bildirilen kurulumla uyuşmuyor. Alan, başlangıçlar, hız/giriş kümesi, kontrol periyodu ve bazı kazançlar konusunda bağımsız tercihler gerekiyor. Bu yüzden yerel ECC profili, açıklanmış farkları olan bir uygulama ve nitel karşılaştırma olarak değerlendirilmelidir; şekilleri birebir yeniden üreten bir referans uygulama olarak değil.

**GPML.** Exact GP'nin ortalama/kovaryans formülleri ve latent ile gürültülü gözlem varyansı ayrımı için doğru dayanak. Sabit kernel ve sabit örnek konumlarında posterior kovaryansı ölçüm değerlerinden bağımsız hesaplanabilir. Ancak GP'nin kendi modelindeki belirsizliğin azalması, model uyumsuzluğunda gerçekleşen harita RMSE'sinin mutlaka azalması demek değildir. FIELDWORK'ün iki metriği ayrı tutması doğru. [GPML, Bölüm 2](https://gaussianprocess.org/gpml/chapters/RW2.pdf).

**Csató–Opper.** SOGP yalnız sözlükte kalan noktalarla baştan GP kurmak değildir. Sözlüğe alınmayan gözlemlerin bilgisi de projeksiyon güncellemeleriyle katsayılara taşınır. Dolayısıyla sözlük koordinatları, mevcut posteriorun tamamını temsil etmeye yetmez. Projenin SOGP sınıfı bu katsayı yapısını koruyor; ECC kontrolünün kullandığı yeniden kurulmuş GP aynı bilgiyi korumuyor. Ayrıca değer bağımlı budama varsa gelecekteki sözlük ve kovaryans, gelecekteki ölçüm değerlerinden etkilenebilir. Dondurulmuş mevcut posterior üzerinden etiketsiz forecast geçerli bir yaklaşık hesap; tüm gelecekteki SOGP güncellemelerinin garantili simülasyonu değil. [Birincil teknik rapor](https://publications.aston.ac.uk/id/eprint/40231/1/NCRG_2001_014.pdf).

**Krause–Singh–Guestrin.** Mutual information ve belirli sensör yerleşimi koşullarındaki greedy garantileri, projedeki ortalama varyans hedefi ve hareket kısıtlı DP'ye otomatik aktarılmaz. Çalışma A-optimality/varyans türü ölçütlerin genel submodularity davranışını da tartışıyor. FIELDWORK için genel bir yaklaşık optimalite katsayısı çıkarılmamalı. [JMLR makalesi](https://www.jmlr.org/papers/volume9/krause08a/krause08a.pdf).

**Suryan–Tokekar.** Belirli GP varsayımları altında belirsizlik eşiğine ulaşmak için gerekli ölçüm yerleşimini ve tek/çok robotlu görev süresini ele alıyor. Bu, “hedef belirsizlik ve kalan zaman” fikrinin tek başına yeni olmadığını gösteriyor. Projenin olası farklılığı, yürütme sapması ve ölçüm kaybı sonrasında çevrimiçi kararın nasıl değiştiğinde aranmalı. Kaynağın model altında beklenen hata ile varyans ilişkisini, projedeki tek gerçekleşmiş sentetik alanın RMSE'sine eşitlememek gerekiyor. [Birincil metin](https://arxiv.org/html/1909.01895).

**Jakkala–Akella, 2024.** Sparse GP üzerinden çok robotlu informative path planning zaten çalışılmış. Bu metindeki yol bütçesi cezası, her koşulda sert hareket kısıtı garantisiyle aynı şey değil. FIELDWORK'ün gerçek kontrol yürütmesini ayrıca değerlendirmesi karşılaştırılabilir bir araştırma ekseni; ancak yalnız sparse GP ile çok robotlu planlamayı birleştirmek yenilik iddiasına yetmez. [Birincil metin](https://arxiv.org/html/2309.07050v3).

**Jakkala ve diğerleri, 2026.** Belirsizlik garantili IPP en yakın çalışmalar arasında. Sonlu değerlendirme kümesi, model varsayımları ve garantinin kapsadığı planlama problemi açıkça ayrılmalı. Çalışmanın kendisi yürütme belirsizliğini genişletilebilecek bir alan olarak tartışıyor. Bu, FIELDWORK'e araştırma alanı bırakıyor; mevcut P'nin bu alanı çözdüğünü göstermiyor. Saha deneyleri bulunan bu kaynakla kıyaslandığında FIELDWORK henüz simülasyon düzeyinde. [Birincil metin](https://arxiv.org/html/2602.05198v3).

**Kısıt tabanlı kontrol ve USV kaynakları.** Görevi eşitsizlikler/QP ile ifade etmek ve CBF güvenliği yerleşik araçlar. Bir kontrol satırını uygulamak, kaynak teoremin bütün varsayımlarının otomatik sağlandığı anlamına gelmez. Benzer biçimde Hatanaka çizgisindeki nonholonomik saha çalışmasıyla tematik yakınlık, aynı benchmark veya aynı tekne dinamiğinin kullanıldığı anlamına gelmiyor. [Notomista–Egerstedt](https://arxiv.org/abs/1811.02465), [ilgili USV çalışması](https://arxiv.org/html/2411.00579v2).

**3. Kaynak denetiminde düzeltilmesi gereken iki önemli nokta**

**3.1. “Denklem 12'de eksik çarpan” tespiti yanlış.** PDF'nin basılı 308. sayfasında `[z*]_{N+1}`, iki terimi de içeren büyük köşeli parantezin önünde duruyor. Sözlük terimini de çarpıyor. Proje belgeleri ve bir test, bu çarpanın ikinci terimde bulunmadığını ileri sürüyor. Görsel kaynak bunu desteklemiyor.

Mevcut sayısal gradyan uygulaması çarpanı doğru kullanıyor; bu yüzden düzeltilecek ilk şey çalışan türev değil, yanlış kaynak aktarımı. [Kod açıklaması](<C:/Users/Lenovo/Desktop/GP Attainability/src/attain_sampling/control/rate_constraint.py:38>), [denklem kaydı](<C:/Users/Lenovo/Desktop/GP Attainability/docs/equation_map.md:77>), [D037 kararı](<C:/Users/Lenovo/Desktop/GP Attainability/docs/decision_log.md:47>) ve [testin adı/gerekçesi](<C:/Users/Lenovo/Desktop/GP Attainability/tests/unit/test_rate_constraint.py:84>) aynı yanlış okumayı tekrar ediyor. Testin geçmesi, makalenin yanlışlığını kanıtlamıyor; testte elle kurulmuş, çarpanı çıkarılmış ifadenin yanlışlığını gösteriyor.

Makaledeki toplamın `F_d` üzerinden yazılmasıyla türetimdeki `F_d ∩ V_i` kısıtı arasındaki fark ayrı bir konu ve incelenmeye devam etmeli. Bir eleştirinin yanlış çıkması bütün kaynak belirsizliklerini ortadan kaldırmıyor. Ancak teknik nottaki “altı iç tutarsızlık” sayısı ve bu örnek tekrar değerlendirilmeden paylaşılmamalı.

**3.2. ECC kontrolünün bilgi modeli SOGP ile örtüşmüyor.** Kontrol kodu sanal posterioru, retained basis konumlarına yeni robot konumunu ekleyip `−(K + noise I)⁻¹` kurarak hesaplıyor. SOGP ise sözlüğe eklenmeyen ölçümlerin bilgisini C katsayısında saklıyor. Bu bilgi yalnız koordinatlardan geri kazanılamıyor. [Kontrol hesabı](<C:/Users/Lenovo/Desktop/GP Attainability/src/attain_sampling/control/rate_constraint.py:136>), [SOGP posterioru](<C:/Users/Lenovo/Desktop/GP Attainability/src/attain_sampling/gp/sogp.py:318>).

Küçük bir bağımsız örnek bunu görünür kılıyor: aynı noktada on gürültülü ölçüm, sözlük kapasitesi 360 ve yalnız bir sözlük elemanı. Kapasite budaması yok. Mevcut SOGP latent varyansı 0,015748; aynı noktada bir ölçüm daha varsayılınca 0,014337. ECC kontrolünün sözlükten yeniden kurduğu sanal varyans ise 0,074074. Aynı bilgi durumu için farklı hedef değerlendiriliyor.

Bu fark “gelecekte budama olabilir” uyarısından daha temel. Kaynak makaledeki Gaussian-likelihood gerekçesi de projeksiyonla sıkıştırılmış posterior için tek başına yeterli değil. Kaynağı izleyen profil ile mevcut SOGP posteriorundan türetilmiş tutarlı profil ayrı adlandırılıp karşılaştırılmalı; kaynak uygulaması sessizce başka algoritmaya çevrilmemeli. Bağımsız ExactGP ana sonuçlarının bu bulgu yüzünden yanlış olduğu sonucuna varılamaz.

**4. Master plan açısından neler tamamlandı?**

[Master plan](<C:/Users/Lenovo/Desktop/GP Attainability/GP_Attainability_Masterplan_TR.md>) formal bir teorem veya fiziksel USV deneyi zorunlu kılmıyor. Esas hedef çalışan hiyerarşi, bütçe/yürütme modülü, güçlü B3, ablation'lar ve dürüst sonuç paketi. 9 Eylül eki soruyu daha da daraltıyor: hedefin kaçırılmasını erken öngörmek ve kalan bütçeyle görevi kurtarmak.

| Aşama | Depoda görülen ilerleme | Bugünkü değerlendirme |
|---|---|---|
| M0 | İlk FIELDWORK, exact GP, greedy/adaptive, demo ve diagnostic korunmuş | Eski kanıt korunmuş; Git ile tarihsel sabitleme yapılmamış |
| M1 | Gerçek QP, hız/alan/ayrılma denetimleri, hata kayıtları | Uygulama bakımından güçlü |
| M2 | Zamanlı plan sözleşmesi, hücre DP, ortak örnek değerlendirmesi | Çalışıyor; tam GP-belief DP'si değil, açık bir yaklaşık model |
| M3 | Online SOGP, kabul/projeksiyon/budama, exact karşılaştırması | Bileşen tamam; küçük sözlükte kalite kaybı ölçülmüş |
| M4 | Kontrol rollout'u, kalan bütçe, eski planı koruma, olay kararları | Mekanizma tamam; hedef önceliği ve forecast kalibrasyonu açık |
| M5 | ECC metni, denklemler, ayrı profil, 40 koşuluk karşılaştırma | Uygulama var; kaynak yorumları ve posterior tutarlılığı yeniden açılmalı |
| M6 | 40 görülmemiş seed, güçlü yöntemler, ablation, SOGP/model blokları | Deney tamam; P'nin ana üstünlük hipotezi desteklenmedi |
| M7 | Dönüş yarıçapı kısıtlı araç; v1 hatasının tanısı ve yeni seed'lerle v2 | İkinci model doğrulaması tamam; fiziksel tekne doğrulaması değil |
| M8 | Arayüz, dört demo, yaklaşık 107 saniyelik video, sekiz sayfalık not | Yerel paket var; dışarıdan kurulabilir kanıt paketi hâlâ eksik |

Planın geniş deney menüsü daha dar bir uygulamaya dönüşmüş. Ana dünya ailesi sentetik Gaussian bileşenler ve dalgalardan oluşuyor; alan aileleri, dar geçitler ve görev geometrisi çeşitliliği sınırlı. ROS 2'nin olmaması tek başına plan ihlali değil: plan onu koşullu tutuyor. Buna karşılık “M0–M8 tamam” ifadesi, kaynak uyumu ve dış yeniden üretim eksiklerini görünmez kılmamalı.

SOGP kodda mevcut olsa da ana M6/M7 kıyasları ExactGP ile yapılmış. Bu tercih planlama katkısını GP yaklaşım hatasından ayırmak için iyi. Ancak “SOGP + P + USV birlikte güçlü ve ölçeklenebilir” iddiası için aynı düzeyde ana deney kanıtı yok. Uzun görev, dolu sözlük ve sık budama altında uçtan uca çalışma ayrı değerlendirme gerektiriyor.

**5. Şu ana kadarki gelişim ve dönüm noktaları**

İlk sürümde 187 test ve 54 yöntem koşusu raporlanıyordu. Temel demo ve küçük diagnostic vardı; asıl hiyerarşik omurga henüz tamam değildi. M1'de 318 test ve QP koşuları; M2'de 485 test ve zamanlı planlama; M3'te 607 test, 132 kapalı döngü koşusu ve uzun SOGP akışı; M4'te 55 koşu ve 376 plan üzerinden yürütme değerlendirmesi kaydedilmiş. Bunlar geçmiş raporların sayıları, bu incelemede ayrı ayrı yeniden koşulmuş sonuçlar değil.

15–16 Eylül'de tam ECC metni ve kaynak profili eklendi. M5'in 40 yöntem koşusu, makaledeki nitel avantajı temiz biçimde yeniden üretmedi: dış başlangıçlarda hiyerarşi alana girişe yardım ederken, diğer başlangıçlarda sonuçlar karışık. Tanımlanan durma ölçütünde beklenen deadlock yakalanmadı. Eksik kaynak parametreleri ve yukarıdaki bilgi modeli farkı varken buradan “makale çalışmıyor” sonucu çıkarılamaz.

17 Eylül'de M6, 1.400 yöntem koşusuyla P'nin güçlü B3'ü RMSE bakımından geçemediğini gösterdi. Sonra USV M7 v1, 1.280 koşuda olumlu görünen bir sonuç üretti. Bu sonucun altında B3 primitive planlayıcısının gereğinden sıkı alan sınırı denetimi bulundu: kenara yakın robotlara yalnız durma kalıyor, duran robot yeni duruma geçemediği için takılı kalıyordu.

Bu bulgu projenin en önemli bilimsel dönüm noktası. Avantaj korunup pazarlanmak yerine sorun kayda geçirildi, yay sınırı kontrolü düzeltildi ve tamamen yeni 40 seed ile 1.280 koşuluk v2 yapıldı. Büyük RMSE avantajı kayboldu. v1'in olumlu sonucu, sağlam B3 karşısında P üstünlüğü olarak kullanılmıyor. Bu yaklaşım doğru.

v2'de yalnız kod ve seed değil, aynı geliştirme kuralından hesaplanan belirsizlik hedefi de 0,156'dan 0,0774'e değişti. Bu kayıtlı bir değişiklik; gizli tuning kanıtı değil. Ancak v1 ve v2 hedef başarı yüzdeleri, aynı eşik altında yapılmış karşılaştırmalar gibi okunmamalı. 18 Eylül'de dayanıklılık düzeltmeleri, 1.007 testlik sürüm ve M8 sunumu tamamlanmış.

**6. Kodun başarılı tarafları**

**GP katmanı:** ExactGP'de Cholesky ve üçgensel çözümler, latent/predictive ayrımı ve ortak koşullandırma doğru tercihler. Birden çok aday örneğin bilgi katkısını bağımsızmış gibi toplayıp korelasyonu iki kez saymamak önemli. SOGP'de sınırlı sözlük, açık kabul/projeksiyon/budama kayıtları, deterministik ölçüm sırası ve başarısız toplu güncellemede kısmi durum bırakmayan yapı mevcut.

**Saat ve bütçe:** Gerçek alınan ölçüm ile planlanan ölçüm, görev zamanı ile kalan örnek epoch'ları, aday rota ile uygulanmış rota ayrılmış. Yöntemler arası aynı epoch/robot anahtarlı gürültü ve kayıp çizelgeleri, P daha sık karar verdiği için rastgele bozucuların değişmesini önlüyor. Bu, adil kıyas için basit bir seed eşitlemesinden daha değerli.

**Kontrol:** Merkezi QP yalnız çözücünün “başarılı” durumuna güvenmiyor. Artıklar, dual/KKT tutarlılığı ve geometrik sonuçlar kontrol ediliyor. Hız çokgeni, alan kısıtı ve bütün hareket segmentinde ayrılma denetimi mevcut. Çözücü hatasının sessizce başarıya çevrilmemesi ve hata öncesi kayıtların korunması güçlü taraflar.

**USV:** Tam yay entegrasyonu, dönüş yarıçapı ve robotların özel bekleme çemberi değişmezi açık tanımlanmış. v2'nin planlayıcı-kontrolcü geometrisini aynılaştırması gerçek bir iyileştirme. Bunun bedeli daha dar uygulanabilir hareket kümesi; dar alanlarda nasıl davranacağı mevcut açık alan sonuçlarından çıkarılamaz.

**Deney altyapısı:** Protokol hash'i, iş listesi, ham kayıt, kaynak snapshot'ı, analiz ve rapor arasında iz sürülebiliyor. Başarısızlıklar ve atlanan adayların nedenleri görünür. Geliştirme/held-out ayrımı, üç temel ablation, model uyumsuzluğu ve SOGP blokları, yalnız güzel rota videolarından oluşan bir projeye göre çok daha güçlü kanıt sağlıyor.

**Ürün/sunum:** Demo ve replay, sabit görev hedefini seçilen plan tahmininden ayırabiliyor. Sunucu tarafında loopback, Host/Origin, boyut/süre ve eşzamanlı çalıştırma kontrolleri var. Bu incelemede tarayıcı üzerinden yeni uçtan uca oturum yapılmadı; ürün değerlendirmesi kod, entegrasyon testleri ve mevcut sunum çıktılarından geliyor.

**7. Kod ve tasarımda dikkat edilmesi gereken noktalar**

**Hedefe ulaşan aday varken hedefi kaçıran plan korunabiliyor.** [Plan seçimi](<C:/Users/Lenovo/Desktop/GP Attainability/src/attain_sampling/attainability/policy.py:399>) mevcut plan yeterince iyi ise switch margin ile onu koruyor. Sabit hedef [seçimden sonra](<C:/Users/Lenovo/Desktop/GP Attainability/src/attain_sampling/attainability/policy.py:427>) okunup risk raporuna dönüştürülüyor. Bu nedenle hedef geçişi kararın önceliği değil.

Yeniden ürettiğim sentetik örnekte en iyi adayın görev sonu varyansı 0,764091381; hedef 0,764093180; seçilen eski planınki 0,764094979. Durum etiketi aday kümesinde hedefin mümkün olduğunu doğru söylüyor, fakat seçilen rota hedefi kaçırıyor. Fark küçük ve örnek yapısal açığı görünür kılmak için kurulmuş; ana deneylerde maddi etki gösterildiği iddia edilmiyor. Hedef sert görev koşuluysa, hedefe geçen adayın önceliği veya açık bir hedef toleransı gerekli. Hedef yalnız izleme metriğiyse, “görevi kurtaran politika” anlatımı daraltılmalı.

**DP'nin ödülü tam gelecekteki GP inancı değil.** Hücre DP'si kendi rotasının önceki adımlarının sonraki bilgi kazancını nasıl azalttığını tam state olarak taşımıyor. Önceden planlanmış robotların örnekleriyle koşullandırma ve sonradan ortak exact skor hesaplama var; bunlar faydalı. Ancak aday üreticisinin hiç önermediği daha iyi bir rota sonradan puanlanamaz. Tekrarlı yüksek ödüllü hücrelerin fazla çekici görünmesi ve kaba 9×7 hareket ağı olası sınırlamalar. Bunların B2'nin başarısını ne ölçüde açıkladığı henüz deneysel olarak ayrıştırılmamış.

**B2 zayıf bir baseline değil.** Gerçek posterior ve konumla her ölçümde karar veriyor, tek adımlık ortak bilgi hesabı yapıyor; USV adayları da araç yürütmesi üzerinden değerlendiriliyor. Dolayısıyla çok adımlı DP'nin “daha akıllı olduğu için” otomatik üstün gelmesi beklenmemeli. Aday konum kümeleri ile arama ufkunu ayrı eşitleyen bir kontrol deneyi, politika farkını ayrıklaştırma farkından ayırabilir.

**Forecast, gelecekteki kapalı döngü politikanın tam simülasyonu değil.** Kısa plan ufkundan sonra son konumda kalma devamı kullanılıyor. 90 saniyelik bir görevde dört ölçüm epoch'u/20 saniyelik rota ardından hareketsiz devam varsayımı, başlangıçtaki tahmini kötümser yapabiliyor. Diğer taraftan gelecekteki bütün ölçümlerin alınacağı varsayımı kayıplı görevlerde iyimserlik getiriyor. Aynı tahmin mekanizmasında zamanla değişen iki hata yönü var; risk etiketi tek başına kalibre bir başarısızlık olasılığı değil.

**Olay tetikleri hesap tasarrufu sağlamıyor.** P olay kararlarını periyodik ölçüm kararlarına ekliyor. Birleşik holonomik senaryoda yaklaşık 38, USV'de yaklaşık 109 kararın B3'ün 18 kararıyla karşılaştırılması bunu gösteriyor. “Event-triggered” kelimesi burada otomatik olarak daha az hesap anlamına gelmiyor. Tasarruf amaçlanacaksa ucuz bir geçerlilik testiyle bazı periyodik pahalı aramaların gerçekten atlanması gerekir.

**Hesap zamanı görev saatine yüklenmiyor.** Planlama sırasında robotun eski komutla ilerlemesi, deadline kaçırması veya gecikmiş planı uygulaması ana fiziksel bütçeye işlenmiyor. Bu yüzden eşit simülasyon süresi, eşit gerçek zaman uygulanabilirliği değildir. Kaydedilen işlem süreleri paralel iş yükünden etkilenebilir; yine de aşağıdaki büyüklükler gerçek zaman iddiasından önce ayrı zamanlama deneyini gerekli kılıyor.

**Bozucu modelinin sınırı var.** Holonomik drift güvenlik QP'sinden önce istenen hıza ekleniyor; filtre bu bozulmuş komutu görüyor. Bu, güvenlik filtresinden sonra gelen bilinmeyen fiziksel akıntı altında robust güvenlik gösterimi değil. USV de hidrodinamik tekne modeli değil: ileri giden, durabilen, yerinde dönemeyen kinematik bir model. [Uygulama sırası](<C:/Users/Lenovo/Desktop/GP Attainability/src/attain_sampling/sim/mapping.py:327>).

**Bakım maliyeti yükseliyor.** Yaklaşık 44 kaynak dosyası ve 11 bin satırlık yapıda modüler sınırlar var; fakat yaklaşık 1.700 satırlık mapping modülü, 570 satır civarındaki ana döngü ve 360 satır civarındaki plan yöneticisi çok sayıda sorumluluk taşıyor. Yaygın `dict[str, Any]` kullanımı nedeniyle strict mypy, kayıt alanlarının anlamını veya schema tutarlılığını bütünüyle denetleyemez. Öncelik büyük yeniden yazım değil; olay kaydı, karar sonucu ve araç adımı gibi sınırları tipli veri yapılarıyla kademeli ayırmak olmalı.

**8. Deney sonuçlarının doğru okuması**

Yöntemler: B0 sweep; B1 görev başında nominal greedy; B2 gerçekleşen veriyle adaptive greedy; B3 periyodik DP; P rollout, plan koruma ve olay tetiklerini ekleyen politika. Aşağıdaki farklar görev sonu alan RMSE'sinde **P − B3**; negatif değer P lehine. Her satır 40 eşleştirilmiş göreve dayanıyor.

| Senaryo | Holonomik M6: ortalama [%95 aralık] | Düzeltilmiş USV M7 v2: ortalama [%95 aralık] |
|---|---:|---:|
| Nominal | +0,00248 [−0,00101; +0,00613] | +0,00077 [−0,00417; +0,00540] |
| Ölçüm kaybı | −0,00171 [−0,00670; +0,00329] | −0,00229 [−0,00852; +0,00402] |
| Takip sapması | +0,00099 [−0,00318; +0,00521] | −0,00777 [−0,01572; +0,00044] |
| Birleşik | +0,00389 [−0,00283; +0,01062] | −0,00671 [−0,01420; +0,00082] |
| Kısa bütçe | +0,00255 [−0,00468; +0,01022] | −0,00343 [−0,01417; +0,00743] |

Aralıkların sıfırı içermesi yöntemlerin eşdeğer olduğunun kanıtı değil. Özellikle USV sapma/birleşik koşullarında faydalı büyüklükte bir iyileşme de mevcut aralıklarla uyumlu. Ancak bu veriyle “P daha iyi” sonucu da gösterilmiş değil. Eşdeğerlik veya pratik olarak önemsiz fark iddiası için önceden tanımlanmış bir etki eşiği ve ona uygun analiz gerekir.

B2 on ana senaryo bloğunun dokuzunda en düşük veya en düşükle eşit ortalama RMSE'yi veriyor; kalan M6 nominal blokta B3 önde. Birleşik senaryoda M6 RMSE'leri B2=0,1395, B3=0,1466, P=0,1505. USV v2'de B2=0,1544, B3=0,1651, P=0,1584. P'nin B3'e yaklaşması/onu bazı ölçütlerde geçmesi, B2'yi geçtiği anlamına gelmiyor. İkincil çiftli karşılaştırmaların çokluğu nedeniyle bu desen genel bir üstünlük teoremi gibi sunulmamalı.

**P'nin yararlı ikincil bulguları var.** USV birleşik koşulda P'nin ortalama varyans farkı yaklaşık −0,011, %95 aralık [−0,016; −0,006]. Varış hatası da yaklaşık 2,47 m azalıyor. Sabit 0,0774 hedefini P 37/40, B3 29/40 görevde tutturuyor. Eşleştirilmiş tabloda yalnız P'nin başardığı dokuz, yalnız B3'ün başardığı bir görev var. Bunlar hedeflenen model belirsizliği bakımından olumlu; RMSE ana sonucunun yerine geçirilemez.

**Rollout katkısı araç bağımlı.** Holonomik M6 birleşik blokta rollout çıkarıldığında 40 görevin 37'sinde davranış değişmiyor; kalan üçünde çıkarılması RMSE'yi iyileştiriyor. Bu ortamda kontrolcü, planlayıcının geometrik varsayımını büyük ölçüde zaten gerçekleştiriyor. USV'de rollout bütün görevlerde karar değiştiriyor ve varış doğruluğunu artırıyor; yine de RMSE ablation aralığı sıfırı içeriyor. Plan koruma ve olay tetiklerinin USV varyansında faydası var, ana harita hatasında ayrıştırılmış üstünlüğü yok.

**Erken uyarı sorusu açık kalıyor.** M6'da başarısız görevlerin ayrılması çoğunlukla son yaklaşık 20 saniyeye kalıyor; P, B3'ten daha erken uyarı vermiyor. Aday kümesinde hedef kaçırılması bütün mümkün rotaların başarısız olacağı anlamına gelmez. Mevcut forecast'in devam varsayımı, kayıp modeli ve aday üretimi değiştirilmeden uyarının yalnız görsel sunumunu iyileştirmek araştırma sorusunu çözmez.

**SOGP ucuzluğunun kalite bedeli var.** M6 birleşik ek blokta 32 elemanlı SOGP, exact GP'ye göre B3'te yaklaşık +0,0137, P'de +0,0166 RMSE artışı gösteriyor; iki aralık da sıfırın üzerinde. Bu bir sayısal çökme değil, yaklaşımın bilgi/kalite maliyeti. Sözlük kapasitesi, novelty ve çalışma ölçeği gerçek kalite/maliyet eğrisi üzerinde seçilmeli.

**Model uyumsuzluğu kritik.** Length-scale değişimi bazı bloklarda model varyansını azaltırken RMSE'yi yaklaşık 0,031–0,060 artırıyor. Böyle bir modelde hedef başarı oranının %100 olması daha doğru harita elde edildiği anlamına gelmez. Mevcut kaynakların model altında söyledikleri ile gerçek alan hatasının ayrı tutulması bu yüzden zorunlu.

**Hesap maliyeti ana zayıflık.** Kaydedilen medyan toplam planlama süreleri:

| Senaryo | M6 B3 / P | USV v2 B3 / P |
|---|---:|---:|
| Nominal, 90 s görev | 0,92 / 22,2 s | 20,8 / 105,9 s |
| Birleşik, 90 s görev | 0,86 / 42,8 s | 12,8 / 174,3 s |
| Takip sapması, 90 s görev | 0,96 / 46,8 s | 14,9 / 196,8 s |

Mutlak süreler donanım ve eşzamanlı iş yüküne bağlı. Bunlardan tek başına fiziksel platformda kesin deadline ihlali hükmü çıkarılmaz. Fakat P'nin bugünkü sürümünün “benzer kaliteyi daha az hesapla” sunduğu da söylenemez. İzole benchmark, karar başına p95/p99, deadline kaçırma oranı ve gecikme altındaki kapalı döngü performans gerekli.

Ana sayılar ve önceki ayrıntılı denetimler: [M6 raporu](<C:/Users/Lenovo/Desktop/GP Attainability/reports/m6_results_2026-09-17.md>), [M7 v1/v2 raporu](<C:/Users/Lenovo/Desktop/GP Attainability/reports/m7_results_2026-09-17.md>), [bu incelemenin hesapları](<C:/Users/Lenovo/Desktop/GP Attainability/reports/audit_evidence_2026-09-18.json>).

**9. Deney sayısı ve genellenebilirlik**

Üç büyük pakette 1.200 karşılaştırma işi ve 3.960 yöntem koşusu var. Bunlar 3.960 bağımsız dünya değil. Seed'ler bloklar ve yöntemler arasında yeniden kullanılıyor; bu, eşleştirilmiş kıyas için doğru ama bağımsız örnek sayısı anlatılırken dikkat gerektiriyor. Her ana hücrenin istatistik birimi 40 görev.

Sabit kernel ve nominal yürütmede variance-based ExactGP politikası ölçüm değerlerine göre rota değiştirmiyor. Aynı geometri ve eksiksiz ölçüm çizelgesinde farklı alan seed'leri aynı rotayı üretebiliyor. Bu seed'ler harita hatası bakımından anlamlı tekrarlar, fakat 40 farklı planlama geometrisi anlamına gelmiyor. Yeni başlangıçlar, alan oranları, bütçeler, korelasyon yapıları ve bozucu zamanlamaları ayrı genelleme eksenleri.

Kayıtlarda başarısız koşu bulunmaması, uygulanan simülasyon modeli ve bu görev kümesinde olumlu bulgu. Fiziksel güvenlik, bütün başlangıçlar veya bütün çevreler için kanıt değil. Benzer şekilde 40 seed'lik sonuçlara bakıp yeni ayar seçmek o sonuçları geliştirme verisine dönüştürür; yeni yöntem sürümü yeni ve önceden ayrılmış görevlerle sınanmalı.

**10. Yeniden üretilebilirlik ve belge sorunları**

**Git geçmişi yok.** Çalışma dizininde main henüz commitsiz; uzak depo da tanımlı değil. Dosyalar untracked. Kaynak snapshot'ları deneyleri kısmen koruyor; fakat sürüm geçmişi, değişiklik incelemesi ve dışarıdan belirli sürümü edinme bakımından eksik var. “Yerelde kurulabilir” ile “başka araştırmacı aynı sürümü ve kanıtı alabilir” farklı tamamlanma koşulları.

**M8 üretimi eski batch adlarına bağlı.** [Şekil betiği](<C:/Users/Lenovo/Desktop/GP Attainability/scripts/figures_m8.py:33>) üç belirli timestamp klasörünü sabit yazıyor. Üretilmiş outputs Git dışında. [Yeniden üretim belgesi](<C:/Users/Lenovo/Desktop/GP Attainability/REPRODUCIBILITY.md:168>) yeni checkout'ta deneyleri yeniden oluşturmayı söylüyor; yeni koşu farklı klasör adı üretecek. Üstelik güncel kodla M7 v1'in eski hatasını aynı biçimde yeniden üretmek mümkün değil; tarihsel snapshot gerekiyor. Dosyalar yerelde mevcutken M8 çalışabilir, temiz dış kurulumun tüm tarihsel şekilleri kendiliğinden üretmesi henüz sağlanmış değil.

Somut çözüm: batch yollarını CLI/manifest girdisi yapmak; güncel tekrar ile tarihsel tekrar komutlarını ayırmak; küçük bir kanıt paketinde protokolleri, kaynak snapshot'larını, özet kayıtları ve hash'leri yayımlanabilir sürüme bağlamak. Lisanslı özel ECC PDF'si bu pakete dahil edilmemeli.

**Belgelerde güncel ve tarihsel durum karışıyor.** [paper_audit](<C:/Users/Lenovo/Desktop/GP Attainability/docs/paper_audit.md:59>) hâlâ varyansı `ambiguous` ve tam metni 1 Eylül itibarıyla yok gösteren zorunlu kayıt içeriyor. [Varsayım defteri](<C:/Users/Lenovo/Desktop/GP Attainability/docs/assumption_ledger.md:13>) Gaussian likelihood için eski açık durumu tutuyor. Tarihsel kayıt silinmemeli, fakat güncel geçerlilik ve yerine geçen karar açık olmalı. A10 gibi gerçekten yaklaşık kalan maddeler sırf metin geldi diye kanıtlanmış sayılmamalı.

**Teknik notta kaynak ve kapsam temizliği gerekiyor.** Kaynakçadaki “K. Suenaga” doğru ilk yazar “Masaya Suenaga” ile uyuşmuyor; BibTeX zaten düzeltilmiş. “Denklem 12 kendi türeviyle uyuşmuyor” örneği geri çekilmeli. “Geliştirmede yalnız 7,19,31 kullanıldı” ifadesi bütün proje için fazla geniş: protokolün dışladığı ek geliştirme/diagnostic seed'leri de var. İfade hangi deney ailesine ait olduğunu söylemeli. Küçük tablo numarası sırası da sunumda düzeltilebilir. [Teknik not kaynağı](<C:/Users/Lenovo/Desktop/GP Attainability/docs/technical_note/technical_note.html:162>).

**11. Öncelik sırası ve bitiş ölçütleri**

| Öncelik | İş | Tamamlandığını ne gösterir? |
|---|---|---|
| 1 — bilimsel doğruluk | Denklem 12 aktarımı, test adı, D037, teknik not ve kaynakça düzeltmesi | PDF ile görsel eşleşme; doğru finite-difference testi korunur; yanlış makale eleştirisi kalmaz |
| 1 — model tutarlılığı | ECC sanal posteriorunun SOGP ile ilişkisini açıklaştırma | Projeksiyon ve budama örneklerinde iki modelin farkı ölçülür; faithful ve tutarlı varyant ayrılır |
| 1 — hedef sözleşmesi | Hedefe ulaşan aday ile plan koruma arasında açık öncelik | Hedef geçişi, tolerans ve seçilen plan riski test edilir; davranış değişimi ölçülür |
| 2 — dış yeniden üretim | Git sürümü, parametrik batch girdileri, tarihsel snapshot rehberi | Temiz dizinde küçük smoke ve arşivlenmiş sonuçlardan M8 üretimi çalışır |
| 2 — araştırma tasarımı | Eşit aday kümesi/hesap bütçesiyle B2, B3 ve P karşılaştırması | Planlama farkı ile ayrıklaştırma ve fazladan hesap etkisi ayrılır |
| 2 — forecast | Kayıpları ve hareketli devamı hesaba katan kalibrasyon deneyi | Görev sonu hata, erken uyarı süresi, yanlış alarm ve kaçırma birlikte iyileşir |
| 3 — ölçek ve zamanlama | Uzun görev, dolu SOGP, izole CPU ve deadline deneyi | Kalite/maliyet eğrisi ve gecikmeli yürütme sonucu raporlanır |
| 3 — genelleme | Yeni geometri, farklı alan aileleri, uygun dış benchmark | Yeni geliştirme ve held-out ayrımıyla kazanımın kapsamı belirlenir |
| 3 — bakım | Ana olay döngüsü ve kayıt sözleşmelerini tipli parçalara ayırma | Mevcut davranış korunur; sorumluluklar daha küçük modüllerde izlenir |

İlk üç iş mevcut kanıtı değiştirmeden güvenilir anlatımı netleştirir; politika davranışı değiştirilirse yeni deney sürümü gerekir. Araştırma yönünde en yüksek değer, P'ye daha çok seçenek eklemekten önce neden ucuz B2'nin güçlü olduğunu ve P'nin bütçesinin nereye gittiğini açıklamakta.

Erken uyarı yeni ana hedef seçilecekse başarı ölçütü önceden yazılmalı: örneğin belirli yanlış alarm oranında kaç saniye erken uyarı, kaç görev kurtarma ve ne kadar ek CPU. RMSE yeni sürümün birincil hedefi kalacaksa pratik olarak önemli fark eşiği, örneklem büyüklüğü ve yeniden değerlendirme kuralları önceden belirlenmeli. Mevcut held-out kümeler tasarım seçmek için kullanıldıktan sonra yeni sürümün nihai kanıtı olarak tekrar kullanılamaz.

**12. Projenin bugünkü değeri**

Mühendislik portföyü olarak değerli: yalnız algoritma isimlerini bir araya getiren bir demo değil, ölçüm-konum-zaman-kontrol ilişkisini uygulayan ve sonuçlarının izini taşıyan bir sistem var. Teknik görüşmede güçlü noktalar QP kabul denetimleri, ortak GP koşullandırması, SOGP yaklaşım sınırları, adil bozucu çizelgesi ve M7 karşılaştırıcı hatasının nasıl bulunduğu.

Araştırma katkısı olarak sonuç daha dar: yürütme farkına duyarlı politika kurulmuş ve ciddi biçimde sınanmış; belirli USV koşullarında model belirsizliği/varış doğruluğu faydaları gözlenmiş, RMSE üstünlüğü ve daha erken uyarı gösterilememiş. Yeni formal attainability sonucu yok; mevcut master plan zaten bunu bitiş koşulu yapmıyor. Böyle sunulduğunda çalışma savunulabilir. Daha geniş iddia için önce kaynak tutarlılığı, hedef sözleşmesi ve gerçek hesap bütçesi çözülmeli.

Bu inceleme sonunda üretim kodu ve deney protokolleri aynı kaldı. Eklenenler bu rapor ile üç denetim JSON'u. Yukarıdaki öneriler uygulanmış değişiklikler olarak okunmamalıdır.

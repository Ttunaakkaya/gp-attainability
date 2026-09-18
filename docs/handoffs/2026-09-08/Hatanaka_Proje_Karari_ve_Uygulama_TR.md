# Hatanaka başvurusu için proje kararı

8 Eylül 2026 · Tolga Tuna Akkaya için araştırma ve uygulama notu

> Son kullanıcı kararı: Önce çalışan proje ve gösterilebilir demo tamamlanacak. Research proposal, yeni geniş literatür taraması ve yeni teori geliştirme sonraya bırakıldı. Uygulama sırası için [AKTIF_ONCELIK_PROJE.md](AKTIF_ONCELIK_PROJE.md) geçerlidir; aşağıdaki araştırma planı arka plan olarak korunur.

## Karar

**Execution-Aware GP Attainability for Multi-Robot Environmental Sampling**

Türkçesi: **Uygulama sapmaları altında, çok robotlu çevre haritalamada ulaşılabilir belirsizlik hedeflerinin tasarımı.**

Mevcut GP Attainability projesini bu soruya odaklayarak tamamlamak, erişebildiğim portföy kanıtları ve güncel laboratuvar çalışmaları üzerinden en güçlü önerim. Bu, ölçülmüş bir kabul olasılığı veya profesörün açıklanmış kişisel tercihi değildir. Danışman kontenjanı, akademik kayıt, referans ve görüşme sonucu bilinmeden yüzde verilemez.

Son tercih güncellemen: Yoğun çalışmaya hazırsın; temel kısıt uzun eğitim ve deney koşuları. Bu nedenle kapsamı sırf birkaç haftaya sığsın diye küçültmüyoruz. Ek emeği daha çok özellik yerine **makaleye sadakat, uygulanabilir kontrol kuralı, güçlü karşılaştırmalar ve ikinci bir dinamik modelde doğrulama** için kullanıyoruz.

## Geçmişinle neden eşleşiyor?

28 Temmuz tarihli mevcut CV; Bahçeşehir mekatronik lisansı (2024), TUM'da Nisan 2025'ten beri yüksek lisans, görüntü işleme ve endüstriyel AI çalışmaları, PyLCSS için aktif öğrenme prototipi, GP-MPC ve model predictive safety filter deneyimi listeliyor. Güncel öğrenci durumunun değişmediği ayrıca doğrulanmış değildir.

Yerel proje denetimi şu ayrımı ortaya koydu:

| Mevcut çalışma | Doğrudan işe yarayan taraf | Başvuruda iddia sınırı |
|---|---|---|
| Interactive Control Systems | GP-MPC, optimizasyon, kontrol simülasyonu ve açıklanmış matematik | Çalışan kod güçlü kanıt; mevcut sınırlı benchmark bütün denetleyicilerin üstünlüğünü kanıtlamıyor. Safety filter için genel formal güvenlik iddiası kullanılmamalı. |
| PyLCSS | Bilgiye göre örnek seçimi, surrogate model ve deney düzeni | CV'deki prototip ve katkı durumu, doğrulanmış upstream birleşme veya yayın diye sunulmamalı. |
| GroundedSwarm | Çok ajanlı simülasyon, kaynak sadakati ve deney altyapısı | İncelenen son kayıtlarda başarılı ve kabul edilebilir tam bütçeli makale yeniden üretimi yok. |
| Motor Vision | Veriden çalıştırmaya giden algı sistemi ve test ayrımı | Kontrol teorisi katkısının yerine geçmez; geliştirme metriği nihai saha başarısı gibi sunulmamalı. |
| GP Attainability | Yapılandırma, deney kaydı, kaynak ve varsayım denetimi hazır | Depo hâlâ Gate 0: hedef makale denklemleri ve araştırma sonuçları henüz uygulanmamış. |

Seni anlatacak araştırma çizgisi: **Tek sistemde belirsizliği hesaba katan kontrolden, birden çok robotun bilgi toplama hedefinin gerçekten uygulanabilirliğine geçiş.** Görüşmede bu bağlantıyı kendi projelerindeki somut kod ve sonuçlarla açıklayabilmelisin.

## Laboratuvar hakkında karar için önemli bulgular

Hatanaka'nın resmi profili; dağıtık karar verme, optimalite ve dayanıklılık, ağ bağlantılı robotik, insan-sistem etkileşimi ve akıllı tarım/deniz/enerji uygulamalarını vurguluyor. Matematiksel yöntemi uygulama ile birleştiren çalışma bu araştırma çizgisine uyuyor. Bunun bir öğrenci seçim kriteri olduğu açıklanmıyor. [Laboratuvar ve profesör](https://hatanakalab.wixsite.com/website/faculty)

2024–2027 KAKEN projesi, tarla ataması ile izleme kontrolünü bütünleştiren çok robotlu hiyerarşik kontrol üzerine. Resmi ilerleme raporunda çevrimiçi GP ile çevresel durum tahmini ve gerçek tarla deneyleri yer alıyor. Bu fonun bitişi Mart 2027; devam fonu veya öğrenci yeri anlamına gelmiyor. [KAKEN 24K00906](https://kaken.nii.ac.jp/ja/grant/KAKENHI-PROJECT-24K00906/)

2025–2026 yayın listeleri GP ile örnekleme, scalar-field saha tahmini, açı duyarlı kapsama, 3B harita geri beslemesi ve deniz robotlarını içeriyor. Dolayısıyla GP, CBF, kamera yönelimi veya harita geri beslemesini eklemek tek başına yeni katkı olamaz. Bazı kayıtlar yayımlanmış, bazıları gönderilmiş veya gelecek etkinlik olarak listelenmiş; hepsini tamamlanmış yayın saymıyoruz. [2025 kayıtları](https://hatanakalab.wixsite.com/website/%E8%A4%87%E8%A3%BD-2024), [güncel yayınlar](https://hatanakalab.wixsite.com/website/publication)

## Ana makale ve gerçek erişim durumu

Suenaga, Hanif, Uto ve Hatanaka, **Hierarchical Multi-Robot Data Sampling for Environmental State Estimation through Online Gaussian Process**, ECC 2025. [DOI](https://doi.org/10.23919/ECC65951.2025.11187026), [yazarın yayın kaydı](https://mhd-hanif.github.io/publication/2025-paper-suenaga-et-al)

Yazar açıklaması; sparse online GP, üst düzey planlama ve alt düzey kısıt tabanlı çok robotlu kontrol mimarisini anlatıyor. Önceki kaynak denetimi ayrıca istenen belirsizlik azalma hızının ilerleyen aşamalarda sağlanamadığı gözlemini kaydediyor. **Bu açıklama kesin denklemler, varyans tanımı veya bütün parametreler için yeterli değil.** Bu oturumdaki yeni aramada tam metin elde edilemedi; bu, makalenin hiçbir yerde erişilebilir olmadığı anlamına gelmez.

Tam metin gelince ilk iş: makaledeki hedef fonksiyonun latent/predictive/prospective variance tanımını, normalizasyonunu, örnekleme ve kontrol saatlerini, SOGP admission/pruning kuralını, planner ve QP denklemlerini sayfa/denklem bazında çıkarmak. Güncellenmeyen bir GP'nin sabit değerlendirme noktalarındaki posterior varyansı yalnız robot hareket etti diye değişmez. Bu yüzden sürekli zamanlı kontrol hedefinin tam olarak hangi nicelik olduğu kritik.

Bu metin olmadan bağımsız exact-GP deneyleri yapılabilir; ECC yeniden üretimi tamamlandı denemez. Yazar nüshası veya üniversite kütüphanesinden edinilen kopya yeterli sonraki girdidir.

## Araştırma sorusu

Bir robot, planlanan ölçümü kaçırır; güvenlik filtresi rotasını değiştirir; hız sınırı yüzünden hedefe geç ulaşır. Eski planın beklediği bilgi kazanımı artık gerçekleşmeyebilir.

**Soru:** Kalan süre ve gerçek yürütme durumuna göre ulaşılabilir belirsizlik hedefini nasıl güncelleriz; hangi koşullarda hedefin hâlâ uygulanabilir olduğunu gösteririz; koşullar bozulduğunda bunu nasıl açıkça bildiririz?

Hedef, performans koşulunu kolaylaştırıp ihlal sayısını yapay olarak azaltmak değildir. Aynı kaynaklarla yararlı bir harita üretirken verilen performans sözünün tutarlılığını artırmaktır.

## Yenilik nerede olabilir, nerede olamaz?

Jakkala vd. 2026, GP belirsizlik eşiği ve yol bütçesi altında bilgi toplayan rota üretimini zaten ele alıyor. İlgili sınırlar arasında çevrimiçi model değişimi ve gerçek yürütme belirsizliği var. Bu nedenle “finite-budget GP planning” veya “uncertainty guarantee” yeni diye sunulamaz. Aday katkı, bütün görev boyunca **yürütülebilir bir planı tanık olarak koruyan referans yönetimi** ve gerçek yürütme/sparse güncelleme farklarının açık hesabıdır. [En yakın çalışma](https://arxiv.org/html/2602.05198v3)

Bu ayrım yeni bir araştırma için gerekçe oluşturuyor; kapsamlı literatür denetimi ve laboratuvarın yayımlanmamış işleri bilinmeden öncelik iddiası oluşturmaz.

“Gürültü tabanını çıkardım” yeterli katkı değil. Sabit modelde tekrarlanan gürültülü ölçümler latent varyansı sıfıra yaklaştırabilir. Yeni bir ölçümün predictive varyansı ise sensör gürültüsünü de içerir. İkisi ayrılmalı. [GPML, Bölüm 2](https://gaussianprocess.org/gpml/chapters/RW2.pdf)

## Yapılacak sistem

1. **Makale yeniden üretimi.** Yalnız tam metinden doğrulanan SOGP/planner/QP; temel eğriler, robot yolları ve belirtilen başarısızlık davranışı. Uyuşmayan sonuçlar gizlenmeden kaydedilir.
2. **Kesin küçük referans çözümü.** Sabit kernel ve gürültü altında, küçük dünyada bütün geçerli rotaları sayarak en iyi erişilebilir sonuç hesaplanır. Bu yalnız o sonlu problem için optimumdur.
3. **Uygulanabilir plan ve hedef yöneticisi.** Daha büyük dünyada kısa ufuk ve sınırlı adaylarla iyi bir rota bulunur; aynı dinamikler ve güvenlik katmanı üzerinden yürütülmesi simüle edilir. Her örnekleme anındaki belirsizlik referansı saklanır.
4. **Planı koruma veya geçersizleştirme kuralı.** Yeni kontrol hareketi sonrası eski planın kalan kısmı hâlâ uygulanabiliyorsa tutulur. Yeni plan ancak karşılaştırılabilir şekilde denetlenirse kabul edilir. Aynı güvenlik filtresi üzerinden nominal simülasyon yapmak yalnız nominal planı doğrular. Sınırlandırılmış sapmalara karşı güvence isteniyorsa kabul edilen sapma kümesinin tamamı için kalan planın uygulanabilirliği ve belirsizlik sınırı denetlenmelidir; örneğin erişilebilir durum kümeleri veya küçük problemde bütün izin verilen kayıp durumları kullanılır. Bu yapılmadığında sonuç nominal tanık ve geçersizleştirme mekanizması olarak adlandırılır. Ölçüm kaybı, model değişimi veya öngörülmeyen sapma sınırları aşarsa eski güvence geçersiz olarak işaretlenir.
5. **Sparse-GP aktarımı.** Önce exact/frozen-model koşullarında çalışan kural, gerçek SOGP güncellemeleri ile değerlendirilir. Dictionary pruning farkı ayrıca ölçülür. Ölçüm değerlerine bağlı pruning varken gelecekteki sparse covariance otomatik olarak label-free sayılamaz. [Csató–Opper](https://eprints.soton.ac.uk/259182/1/gp2.pdf)
6. **İkinci dinamik modelde doğrulama.** Ana sonuç çıktıktan sonra sabit hızlı veya dönüş sınırı olan USV modeliyle aynı yürütme sorununu test et. İkinci tam araştırma projesi değil, yöntemin aktarılabilirlik deneyi olacak. [Açık USV makalesi](https://arxiv.org/html/2411.00579v2), [laboratuvar benchmark deposu](https://github.com/htnk-lab/Multi-USV-Benchmark)

## Matematikte çözülmesi gereken esas iş

İlk bağımsız modelde sabit değerlendirme noktalarında ağırlıklı latent varyans kullan:

\[
V(D)=\sum_{q\in Q}w_q\operatorname{Var}[f(q)\mid D],\qquad w_q\ge0,\ \sum_qw_q=1.
\]

Uygulanabilir bir planın h adımlık ön ekinin beklenen sonucu:

\[
B_{k,h}=V(D_k\cup S_{k,h}(\pi_k)).
\]

Burada gelecekteki ölçüm konumları, sabit modelde covariance hesabı için yeterlidir. Gelecekteki ölçüm değerleri kernel yeniden öğrenimi veya değer bağımlı pruning açıldığında artık göz ardı edilemez.

Bir uygulanabilir planın değeri, minimize edilen optimum için **üst adaydır**. En iyi mümkün değer veya kaçınılmaz fiziksel taban değildir. Her ön ek için iyi bir aday bulmak da bunların hepsini sağlayan tek bir ortak rota bulunduğu anlamına gelmez; ortak plan saklanmalıdır.

Hata için \(E_k=[V_k-B_k]_+\) tanımlanabilir. Bir adımlık koşul gerçekten sağlanırsa şu tür bir koşullu hesap kurulabilir:

\[
E_{k+1}\le\rho E_k+s_k+\epsilon_k+d_k,\qquad 0<\rho<1.
\]

Burada s, bir örnekleme aralığındaki görev gevşetmesinin varyans birimindeki negatif olmayan katkısı; epsilon yürütme/model farkı için geçerli üst sınır; d ise daha sıkı bir referansa geçmenin getirdiği pozitif farktır. Ham QP slack'i türev/barrier birimindeyse doğrudan bu eşitsizliğe konamaz; ilgili aralık boyunca türetilmiş integrali veya geçerli ayrık zaman dönüşümü gerekir. Bu eşitsizliği açarak geometrik toplam elde etmek kolaydır. **Araştırma katkısı, eşitsizliği varsaymak değil; gerçek hareket ve bilgi güncellemesi altında nasıl sağlanacağını tasarlamaktır.** Gözlenmiş maksimum hatayı geleceğin kesin sınırı olarak kullanma.

İlk teori hedefi: sonlu ufuk, sabit GP, açıkça sınırlandırılmış sapmalar ve uygulanabilir yedek plan altında koşullu bir referans güvencesi. Sonsuz zamanlı recursive feasibility, gerçek alan hatası veya keyfi arızalara rağmen güvenlik ayrı iddialardır. Kanıt çıkmazsa sonuç deneysel yöntem olarak raporlanır; başlığa “certified” eklenmez.

## Sonucu inandırıcı kılacak karşılaştırmalar

| Karşılaştırma | Neyi sınar? |
|---|---|
| Makalenin hiyerarşik yöntemi ve yalnız alt düzey yöntemi | Kaynak sadakati ve temel davranış |
| Greedy variance/information-gain ve tarama rotası | Karmaşık yöntemin basit yöntemlere göre faydası |
| Basit adaptif hız veya ampirik plato kuralı | Kazanç yalnız hedefi gevşetmekten mi geliyor? |
| Uygulanabilir referans; yedek-plan denetimi kapalı | Planı gerçekten korumanın katkısı |
| Tam önerilen yöntem | Bütün kuralın etkisi |
| Küçük dünyada bütün rotaların optimumu | Aday referansın ne kadar sıkı olduğu |

Tüm yöntemler aynı alan, başlangıç, planlanan ölçüm takvimi, hız/güvenlik kısıtları ve deney bütçesiyle çalışır. Ölçüm kaybı karşılaştırmasında aynı dış kayıp olayları kullanılır. Planlanan ve gerçekten alınan ölçümler ayrı sayılır. Her yöntemin kendi gevşetilmiş eşiği üzerinden başarı karşılaştırılmaz.

Birincil metrikler: ortak sabit değerlendirme grid'inde field RMSE ve latent IVAR, referans aşımı, gerçek bilgi kazanımı, aynı doğruluk hedefine ulaşma süresi. İkincil: görev slack'i, referans gevşetme miktarı/sıklığı, yedek-plan kaybı, QP fizibilitesi, minimum mesafe ve çözüm süresi. Bir CBF örnekler arasında da kontrol edilmeden yalnız kayıt anlarında mesafeye bakarak güvenlik sonucu çıkarılmaz.

Önceden kilitlenecek karar: eşit bütçede harita hatası için gerekçeli bir noninferiority marjı ve referans ihlalinde beklenen iyileşme. Örneğin %5 marj tartışılabilir bir başlangıç tasarım kararıdır; literatür standardı veya elde edilmiş sonuç değildir. Marj görülmüş test sonuçlarına göre seçilmez. 20–30 bağımsız harita/başlangıç/kayıp senaryosu çiftiyle başla; seed tek başına aynı deterministik deneyin kopyası olmamalı. Etki büyüklüğü ve belirsizlik aralığı örnek sayısını belirlesin.

## Compute planı

Ana proje neural-network eğitimi veya MARL eğitimi gerektirmiyor. Hesap yükü GP covariance, rota adayları ve QP çözümlerinde. Tam GP'yi büyüyen bütün veriyle tekrar tekrar yeniden çarpanlara ayırmak kübik maliyet yaratabilir; sparse bütçe ve artımlı hesap gerekli. Büyük tarla scheduler'ındaki ayrık atama problemleri de kombinatoryal büyüyebilir. “CPU kullanıyor” ifadesi otomatik olarak hafif demek değildir.

| Parça | Hesabı sınırlama kararı |
|---|---|
| Matematik doğrulaması | Exact GP ve yalnız küçük dünyada exhaustive oracle |
| Ana deney | Başlangıçta 2–4 robot; 128/256 dictionary bütçesi adayları; 30×30 değerlendirme grid'i |
| Planlama | Kısa ufuk ve sınırlı beam/adayı; maliyeti açık raporla |
| Kayıt | Her kontrol tick'inde büyük harita yerine ölçüm/replan anında snapshot |
| Görselleştirme | Seçilmiş birkaç koşu; tüm benchmark için video üretme |
| Daha gerçekçi doğrulama | Kinematik USV/ROS2; yalnız bilimsel iddia için gerekirse fotogerçekçi 3B |

Bunlar **önerilen geliştirme ayarlarıdır; hedef makalenin parametreleri değildir.** Yeniden üretim konfigürasyonu ayrı tutulur.

Gerçek runtime ölçülene kadar 300 koşu için saat sözü verilmez. İlk 10 temsilî koşuda median/p95 süre, peak RAM ve planlama/QP/GP zaman payını ölç. Toplam duvar süresi kabaca koşu sayısı × ölçülmüş süre / etkin paralellik; bellek, ısınma ve iş parçacığı çakışması ayrıca kontrol edilir. Büyük koşu başlamadan bu hesabı yapıp gerekirse yöntemi optimize et.

## Tamamlama sırası ve geçiş koşulları

Takvimden çok kanıtla ilerle:

1. **Kaynak kapısı:** ECC tam metni, denklem tablosu, eksik parametreler ve fark listesi. Tam metin olmadan yeniden üretim iddiası kapalı kalır.
2. **Bağımsız temel:** GP oracle, gürültü ayrımı, ortak ölçümler, erişim kısıtı ve plan/yürütme farkı. Bu oturumdaki diagnostic yalnız buraya katkı sağlar.
3. **Yeniden üretim:** En az bir ana figür ve temel davranış. Uyum sağlanmazsa nedenini araştır; yeni yöntemle üzerini örtme.
4. **Yeni kontrol kuralı:** Yedek planın korunması/değiştirilmesi, referans güncellemesi, geçersizleştirme kaydı. Yalnız skaler hedef kaydırma yeterli değil.
5. **Teori ve çürütme testleri:** Varsayımlar altında kanıt; dışına çıkıldığında açık başarısızlık örnekleri. Küçük dünyada optimuma karşı kontrol.
6. **Kilitli deney:** Baseline, ablation, eşit bütçe, bağımsız senaryolar ve adil belirsizlik aralıkları.
7. **SOGP ve USV doğrulaması:** Önce sparse farkı, sonra farklı dinamik. Fayda yoksa dürüstçe sınırlandır.
8. **Başvuru paketi:** Çalıştırılabilir repo; yeniden üretim manifestosu; 6–8 sayfa teknik rapor; 2 sayfa İngilizce araştırma özeti; 2–3 dakika video; 8–10 slayt görüşme anlatısı. Bu dosyaların tamamı şu anda bitmiş değildir.

## Neden daha büyük bir 3B proje seçmedim?

Coverage-Recon ciddi bir ikinci aday: açık çalışma, çevrimiçi NeuralRecon ve çok drone kontrolü birlikte var. Hazır modellerle başlamak büyük ağları baştan eğitmeyi gerektirmeyebilir. Fakat gerçek rekonstrüksiyon kalitesini ölçmek, kapalı döngü görüntü üretmek ve farklı sahnelerde doğru kalite etiketlerini kurmak kapsamlı iş. Geometrik coverage'a güven aralığı eklemek, mesh kalitesine otomatik bir garanti sağlamaz. [Coverage-Recon](https://arxiv.org/abs/2510.18347)

Uzun çalışma isteğin bu adayı daha uygulanabilir yapıyor. Yine de GP projesini öne çıkaran şey yalnız hız değil: portföyünle doğrudan bağlantılı ve kontrol teorisi açısından daha temiz sınanabilir bir soru olması. Ek emeği önce bu sorunun güçlü çözümüne yatırmak daha iyi.

2026 tarla scheduler'ına rüzgâr/batarya belirsizliği eklemek de güçlü olabilir; ancak hiyerarşik model, ayrık atama ve robust fizibiliteyi birlikte yeniden kurmak gerekir. Bu seçeneğin GP projesinden daha etkili olduğunu gösteren bir kanıt yok. [Tarla scheduler yayını](https://doi.org/10.1002/asjc.70139)

## Başvuru iletişimi

Önceki konuşmalarında Bahar 2027 IGP(C) incelenmiş. Bu rota hâlâ hedefse resmi danışman onayı son tarihi **4 Ekim 2026, Türkiye saatiyle 17:59**; başvuru **11 Ekim, 17:59**. Bunlar akademik proje kapsamını küçültme gerekçesi değil, ilk teması araştırmayla paralel yürütme gerekçesi. Danışman onayı, üniversite kabulünün yerine geçmiyor. [Güncel resmi takvim](https://admissions.isct.ac.jp/en/013/graduate/programs/science-and-engineering/igp-c)

İlk mailde mevcut güçlü kontrol uygulamanı ve araştırma sorunu paylaş; hedef makaleyi yeniden ürettiğini veya tam metnini okuduğunu henüz söyleme. Yazar nüshasını ve bu dar sorunun laboratuvarın mevcut işleriyle örtüşüp örtüşmediğini sor. Hiçbir mesaj bu oturumda gönderilmedi.

TUM'daki yüksek lisans durumun, Science Tokyo'da neden yeni yüksek lisans veya doktora istediğin ve akademik referansın da anlatının parçası olmalı. Bunları proje sonucu adına uyduramayız. Genel IGP başvurusunda İngilizce skoru artık merkezi bir zorunlu belge değil; danışman veya burs ayrıca isteyebilir. [Resmi FAQ](https://admissions.isct.ac.jp/en/013/graduate/programs/science-and-engineering/igp-faq)

## Dürüst teslim durumu

Bu dosya kişiselleştirilmiş proje kararı ve uygulama protokolüdür. Laboratuvar/kaynak araştırması ve portföy denetimi tamamlandı; ana makale yeniden üretimi, özgün kontrolcü, nihai benchmark, makale raporu ve kabul sonucu tamamlanmış değildir. Bağımsız diagnostic'in gerçek çalıştırma sonuçları kendi klasöründe ayrıca tutulur. Mevcut masaüstü projeleri değiştirilmedi.

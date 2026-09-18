# Aktif öncelik: çalışan proje

8 Eylül 2026 · Kullanıcının son yönlendirmesi

**Aktif ve ayrıntılı plan: [GP_Attainability_Masterplan_TR.md](GP_Attainability_Masterplan_TR.md), sürüm 2.0.** Kullanıcının son isteğiyle baştan yazıldı; eski masterplanın ve önceki aktarım promptunun kapsam ve sırasının yerine geçer.

**Önce çalışan, gösterilebilir ve teknik olarak güçlü projeyi tamamla. Research proposal daha sonra hazırlanacak.** Mevcut FIELDWORK uygulaması korunacak; yeni plan yazılması kodun yeniden yazılması anlamına gelmez.

Şimdilik ertelenenler: yeni geniş literatür taraması, özgünlük/teorem geliştirme, research proposal, akademik başvuru metinleri ve profesöre e-posta hazırlığı. Uygulamanın doğruluğu için gerekli kaynak ve denklem kontrolleri devam eder.

## Yapılacak ürün

Çok robotlu GP çevre haritalama simülatörü. Kullanıcı, robotların hangi bölgeyi neden örneklediğini; planlanan ve gerçekleşen ölçümlerin farkını; ölçüm kaybı veya hareket sapmasının harita ve görev hedeflerine etkisini görebilmeli.

- Başlangıçta 2–4 robot, bilinen simülasyon alanı ve gürültülü sensör ölçümleri.
- Posterior mean, uncertainty map, gerçek alan ve hata haritası.
- SOGP, üst düzey MDP/Bellman-DP ve alt düzey QP/kısıt katmanları. Kaynak makalenin temel bileşenleri korunacak.
- Basit tarama ve greedy yanında gerçek ölçümlerle periyodik MDP/DP yeniden planlama karşılaştırması.
- Kalan süre, zamanlı örnekleme planı, kontrolcüyle rota değerlendirmesi ve plan geçerliliği kullanan yeni yöntem.
- Hız/alan/robot mesafesi kısıtları; planlanan ve gerçek hareket ile örnekleme kayıtları.
- Tekrarlanabilir ölçüm kaybı ve rota sapması senaryoları.
- Aynı koşullarda RMSE, belirsizlik, yol, örnek sayısı ve runtime grafikleri.
- Anlaşılır demo arayüzü; seçilmiş senaryoları kaydetme ve kısa video üretme.
- Ana karşılaştırmanın ardından aynı yaklaşımın dönüş sınırı olan bir USV modelinde gösterimi; mevcut kinematik modelin geliştirilmesi.

## Çalışma sırası

1. Mevcut çalışan sürümü ve kayıtlı sonuçları doğrula; koru.
2. Gerçek QP kontrol katmanını ve zamanlı MDP/DP planlarını bağla; SOGP'yi paralel geliştir.
3. Kontrolcü rollout'u, kalan görev bütçesi ve plan geçerliliği mekanizmasını ekle.
4. Güçlü periyodik yeniden planlama baseline'ı ve ablation'larla, geliştirmede kullanılmamış görevlerde karşılaştır.
5. Kaynak denetimi tamamlanan bileşenleri ECC profilinde ayrıca doğrula; USV değerlendirmesini tamamla.
6. Arayüz, çalıştırma talimatları, teknik sonuç notu ve video ile projeyi sunulabilir hâle getir.

Makale tam metni yoksa bağımsız modda ilerle; bağımsız SOGP, MDP/DP ve QP geliştirmesi devam eder. Kaynak kilidi yalnız ECC yeniden üretimi iddiasına uygulanır. Tahmin edilmiş denklemlere makale etiketi verme. Exact-GP diagnostic ve mevcut v0 demo, yeni masterplanın tamamlanması değildir.

Kullanıcı yoğun çalışmaya hazır; asıl kısıt uzun compute ve eğitim koşuları. Temsilî runtime ölçümü yap, gereksiz büyük ağ/MARL eğitimlerini ekleme. MDP/dinamik programlama bu ertelemeye dahil değildir. ROS 2 ve USV entegrasyonu yasak değildir; somut deney ihtiyacına göre kullanılabilir. Bundan sonraki uygulama görevi yeni masterplanın M0–M8 sırasını izlemeli.

## Projenin bu aşamada bitmiş sayılması

SOGP + MDP/DP + QP hiyerarşisi, yürütme/bütçe mekanizması, güçlü karşılaştırmalar ve USV değerlendirmesi tamamlanmalı; tek komutla çalışan uygulama, tekrarlanabilir senaryolar, gerçek sonuç grafikleri, anlamlı doğruluk testleri, kısa teknik README ve demo videosu hazır olmalı. Kaynak erişimi yoksa ECC yeniden üretimi ayrı eksik olarak belirtilir. Yeni yöntemin üstünlüğü çıkmazsa sonuç olduğu gibi sunulur. Research proposal ve yeni teorik ispatlar daha sonra ele alınır.

# Aktif öncelik: çalışan proje

8 Eylül 2026 · Kullanıcının son yönlendirmesi

**Önce çalışan, gösterilebilir ve teknik olarak güçlü projeyi tamamla. Research proposal daha sonra hazırlanacak.** Bu karar, önceki araştırma planındaki teslim sırasının yerine geçer.

Şimdilik ertelenenler: yeni geniş literatür taraması, özgünlük/teorem geliştirme, research proposal, akademik başvuru metinleri ve profesöre e-posta hazırlığı. Uygulamanın doğruluğu için gerekli kaynak ve denklem kontrolleri devam eder.

## Yapılacak ürün

Çok robotlu GP çevre haritalama simülatörü. Kullanıcı, robotların hangi bölgeyi neden örneklediğini; planlanan ve gerçekleşen ölçümlerin farkını; ölçüm kaybı veya hareket sapmasının harita ve görev hedeflerine etkisini görebilmeli.

- Başlangıçta 2–4 robot, bilinen simülasyon alanı ve gürültülü sensör ölçümleri.
- Posterior mean, uncertainty map, gerçek alan ve hata haritası.
- Basit tarama, greedy bilgi toplama ve yürütme durumuna göre yeniden planlama karşılaştırması.
- Hız/alan/robot mesafesi kısıtları; planlanan ve gerçek hareket ile örnekleme kayıtları.
- Tekrarlanabilir ölçüm kaybı ve rota sapması senaryoları.
- Aynı koşullarda RMSE, belirsizlik, yol, örnek sayısı ve runtime grafikleri.
- Anlaşılır demo arayüzü; seçilmiş senaryoları kaydetme ve kısa video üretme.
- Son aşamada, ana proje tamamlanınca aynı yaklaşımın dönüş sınırı olan bir USV modelinde gösterimi.

## Çalışma sırası

1. Mevcut repo ve yeni diagnostic'i incele; kullanılabilir bileşenleri koru.
2. En küçük uçtan uca çalışan sistemi kur: gerçek alan → ölçüm → GP → robot hareketi → yeni ölçüm → grafikler.
3. Baseline ve hata senaryolarını ekle; yeni planlamanın işe yaradığı ve yaramadığı durumları ölç.
4. Dinamik/kısıt modelini ve takip sapmalarını geliştir.
5. Arayüz, çalıştırma talimatları, seçilmiş demo ve video ile projeyi sunulabilir hâle getir.

Makale tam metni yoksa bağımsız modda ilerle; kaynak kilidini kaldırarak tahmin edilmiş denklemlere makale etiketi verme. Exact-GP diagnostic ana projenin kendisi değildir. Birkaç düğümlü örnekten gerçek alan haritalaması yapan kapalı döngü sisteme geçilmelidir.

Kullanıcı yoğun çalışmaya hazır; asıl kısıt uzun compute ve eğitim koşuları. Temsilî runtime ölçümü yap, gereksiz büyük ağ/MARL eğitimlerini ekleme. Yeni bir masterplan yazmak yerine küçük doğrulanmış adımlarla uygulamayı ilerlet.

## Projenin bu aşamada bitmiş sayılması

Tek komutla çalışan uygulama, birkaç tekrarlanabilir gösterim senaryosu, gerçek karşılaştırma grafikleri, anlamlı doğruluk testleri, kısa teknik README ve demo videosu hazır olmalı. Yeni yöntemin üstünlüğü çıkmazsa sonuç olduğu gibi sunulur; yalnız daha iyi görünsün diye senaryo veya metrik değiştirilmez. Research proposal ve akademik katkı tartışması bu çalışan proje üzerinden daha sonra yapılır.

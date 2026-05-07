# 📋 Proje Değişiklik Günlüğü (Changelog)

---

## Neler yapıldı 21.04.2026

* Projenin "Statik Risk Kuralları" altyapısından, gerçek veriye dayalı "Makine Öğrenmesi (Machine Learning)" tabanlı Dinamik Risk Analizi altyapısına geçişinin temelleri atıldı.

* 108.000 satırlık Amazon satış veri seti (CSV) üzerinde Keşifsel Veri Analizi (EDA) yapılarak, orijinal veri bozulmadan (Read-Only) eksik veriler ve satış trendleri bir Jupyter Notebook (EDA_Amazon_Sales.ipynb) üzerinde raporlandı.

* Yapay zekanın mantıksız kararlar almasını (Garbage In, Garbage Out) engellemek adına, ürünlerin geçmiş satış hızlarıyla orantılı (Lead Time ve Safety Stock metriklerine dayalı) sentetik envanter verisi üreten ve satırları SQLite tabanına (amazon_sales.db) enjekte eden csv_to_db.py migrasyon betiği yazıldı.

* Geçmiş 7, 14 ve 30 günlük satış ivmelerini (Lag Features) kullanarak gelecek 30 günlük kümülatif talebi tahmin eden ve bu modeli bir Artifact olarak diske kaydeden ilk XGBoost modeli (Nokta Tahmin / Point Prediction) eğitildi ve entegre edildi.

---

## Neler yapıldı 30.04.2026

* Makine Öğrenmesi (ML) altyapısı, tekil nokta tahmininden (Point Prediction) çıkarak endüstri standartlarında Olasılıksal (Probabilistic) Tahmin yapan bir mimariye (Quantile XGBoost) yükseltildi.

* XGBoost modelinin `reg:quantileerror` özelliği kullanılarak, sistemin eğitim süresini uzatmadan tek bir geçişte P10 (İyimser/Düşük), P50 (Medyan/Olası) ve P90 (Kötümser/Kuyruk Riski) tahminlerini aynı anda üretebilmesi sağlandı.

* E-ticarette sıkça görülen "seyrek" (intermittent) satış verilerini modelin daha iyi anlayabilmesi için Özellik Çıkarımı (Feature Engineering) süreci geliştirildi. Ani talep patlamalarını saptamak için Satış İvmesi (`velocity_ratio`) ve geçmiş satışı olmayan ürünleri işaretlemek için `is_no_history` metrikleri algoritmaya eklendi.

* "Asılsız Alarm" (Alert Fatigue) krizlerini önlemek amacıyla, ajanın ve otonom tarayıcının kriz/risk tetikleyicileri tamamen P50 (Medyan) talebine bağlandı. Ancak "Tedarik Zinciri Kriz Yönetimi" standartları gereği, JSON çıktısına P90 (Tail Risk) değeri de eklenerek n8n üzerinden yetkililere "En kötü senaryo" tahmini sunulabilir hale getirildi.

* Modelin kalitesini sadece "hata payı" ile değil, gerçek "İş Metrikleri (Business Metrics)" ile ölçmek amacıyla `evaluate_model.ipynb` Notebook'u oluşturuldu. Modelin Sipariş Karşılama Oranı (Fill Rate) ve naif tahmine kıyasla başarısını ölçen MASE (Mean Absolute Scaled Error) skorları bu dosyada raporlandı (Modelimizin naif tahminden %25 daha başarılı olduğu kanıtlandı).

* Yeni eklenen yetenekler doğrultusunda `README.md`, `TUTORIAL.md` ve Gelecek LLM'ler için yazılan `llm_context` dosyaları güncellendi. Model ağırlıklarının (`.pkl`) sızmasını engelleyen `.gitignore` kontrolleri yapılıp tüm mimari Github'a başarıyla ve güvenle gönderildi.

---

## Neler yapıldı 05.05.2026

### 🐛 Hata Giderme

* **Ajan Döngü (GraphRecursionError) Hatası Giderildi:** Kullanıcı birden fazla kategori için aynı anda arama yaptığında (örn: "kurta and set products"), LangGraph'ın `recursion_limit=5` sınırı aşılarak `GraphRecursionError` fırlatılıyordu. FastAPI'deki `except` bloğu bu hatayı yutarak kullanıcıya genel "teknik güçlük" mesajı iletiyordu. Limit `5 → 15` olarak güncellendi; böylece ajan 5–6 araç çağrısına kadar rahatça çalışırken sonsuz döngü sigortası da korundu.

* **n8n JSON Gövde Hatası Giderildi:** Slack'ten gelen mesaj metni (`$json.text`) mention tag'i (`<@U12345>`) veya tırnak işareti içerdiğinde, n8n'deki HTTP Request node'unun "Using JSON" modunda hazırladığı raw JSON şablonu bozuluyordu. n8n node'u "Using Fields Below" (Key-Value) moduna alındı; bu değişiklik n8n'in tüm özel karakterleri otomatik olarak escape etmesini sağladı.

### ✨ Yeni Özellikler & İyileştirmeler

* **Akıllı Ajan Arama Stratejisi:** LangGraph System Prompt'una, SKU kısaltma sözlüğünü (Kurta=KR, Set=SET, Saree=SA vb.) öğreten ve döngü önleme kuralları (NEVER retry the exact same search term, max 2 attempts) içeren "Search Strategy" bloğu eklendi. Artık ajan "kurta" ile arama yaparken sonuç bulamazsa kendi zekasıyla "KR" kısaltmasını dener; 2 başarısız denemeden sonra dürüstçe "Bulamadım, lütfen tam SKU kodunu verin" der.

* **Olasılıksal Sunum Zorunluluğu:** System Prompt'a "Forecast Presentation" bloğu eklendi. Ajan artık P10/P50/P90 değerlerini asla tek bir "Predicted Demand" sayısına indirgemez; her üç quantile'ı interval olarak sunar ve P50 ile P90 arasındaki kuyruk riski farkını açıkça yorumlar.

* **Dinamik Risk Eşikleri (`lead_time_days`):** Sabit 7 ve 14 günlük risk eşikleri kaldırıldı. `inventory` tablosuna `lead_time_days` (INTEGER) kolonu eklendi. `csv_to_db.py`, her SKU'ya satış hızına göre gerçekçi bir tedarik süresi atar (yüksek hacim → 3 gün, orta hacim → 7 gün, düşük hacim → 14 gün). Risk hesaplaması `days_of_stock < lead_time_days` (High) ve `days_of_stock < lead_time_days * 2` (Medium) formülüne dönüştürüldü. Bu değişiklik, yerel tedarikçiden 3 günde gelen hızlı dönen bir ürünü, uzak tedarikçiden 14 günde gelen seyrek satılan bir ürünle aynı kriterle yanlış değerlendirme sorununu ortadan kaldırdı.

* **Araç Çıktısı Zenginleştirildi:** `calculate_inventory_risk` aracı artık JSON çıktısına `lead_time_days` ve `days_of_stock` alanlarını da ekliyor. Bu sayede LLM, "P50 medyan talebine göre stok 1170 gün dayanır ama P90 spike senaryosunda yalnızca 23 gün dayanır" gibi somut ve zamansal analizler yapabilmekte.

* **Eğitim Veri Bütünlüğü Düzeltmesi (`min_periods=30`):** `train_model.py`'de `FixedForwardWindowIndexer`'ın `min_periods=1` kullanması, her SKU'nun son 29 günü için eksik pencereli (kısmi) hedefler üretiyordu. Bu kısmi hedefler `NaN` yerine küçük sayılar olarak kalıp modelin yanlış öğrenmesine neden olabiliyordu. `min_periods=30` olarak düzeltildi; artık yalnızca tam 30 günlük gelecek penceresi olan satırlar eğitime giriyor.

* **Kapsamlı Mimari Savunma & Kod Kalitesi İncelemesi:** Projenin tüm katmanları (graph yapısı, global model singleton, SQL güvenliği, data leakage) bağımsız bir kod incelemesiyle sorgulandı. Gerçek sorunlar (min_periods, statik eşikler) düzeltildi; haksız eleştiriler (GIL-korumalı singleton, parametrik SQL injection'ı engelliyor, ReAct döngüsü zaten mevcut) kodsal kanıtlarla savunuldu ve belgelendi.

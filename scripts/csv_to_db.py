import pandas as pd
import sqlite3
import os
import random

# ─────────────────────────────────────────────
# İş Parametreleri (Business Assumptions)
# ─────────────────────────────────────────────
ASSUMED_LEAD_TIME_DAYS = 7    # Tedarikçiden mal gelme süresi
REORDER_CYCLE_DAYS = 30       # İki sipariş arasındaki süre
SAFETY_FACTOR = 1.5           # Güvenlik çarpanı (threshold için)
MIN_THRESHOLD = 5             # Minimum critical threshold
MIN_STOCK = 0                 # Stok alt sınırı

# Risk bölgesi dağılımı (agent test çeşitliliği için)
# Her SKU bu oranlarla bir bölgeye atanır:
RISK_DISTRIBUTION = {
    "healthy":  0.40,   # Stok >> threshold  → Low Risk
    "marginal": 0.35,   # Stok ≈ threshold   → Medium/High Risk
    "critical": 0.25,   # Stok < threshold   → Critical Risk
}


def build_database():
    csv_path = os.path.join(os.path.dirname(__file__), "../database/cleaned_sales.csv")
    db_path = os.path.join(os.path.dirname(__file__), "../database/amazon_sales.db")

    print(f"[*] Veri Okunuyor: {csv_path}")
    try:
        df = pd.read_csv(csv_path, low_memory=False)
    except FileNotFoundError:
        print("[!] Hata: cleaned_sales.csv dosyası bulunamadı.")
        return

    print(f"[*] Veritabanı Bağlantısı Kuruluyor: {db_path}")
    # Eğer eski db varsa temizle (Temiz bir başlangıç)
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # ──────────────────────────────────────
    # 1. TABLO: Satış Geçmişi (sales_history)
    # ──────────────────────────────────────
    print(f"[*] Tablo 1 (sales_history) Oluşturuluyor... ({len(df)} satır)")
    # Pandas'ın kendi to_sql özelliğini kullanarak hızlıca SQL'e dönüştürüyoruz.
    df.to_sql("sales_history", conn, if_exists="replace", index=False)

    # Zaman serisi analizini (XGBoost vs.) hızlandırmak için Index ekliyoruz.
    cursor.execute("CREATE INDEX idx_sku_date ON sales_history(sku, date);")

    # ──────────────────────────────────────
    # 2. TABLO: Stok Durumu (inventory)
    #    Veri-odaklı (data-driven) üretim
    # ──────────────────────────────────────
    print("[*] SKU bazlı satış hızları hesaplanıyor...")
    unique_skus = df['sku'].dropna().unique()
    total_active_days = df['date'].nunique()  # Toplam gün sayısı (91)

    # Her SKU'nun toplam satış miktarı ve aktif gün sayısı
    sku_stats = df.groupby('sku').agg(
        total_qty=('qty', 'sum'),
        active_days=('date', 'nunique')
    )

    print(f"[*] Tablo 2 (inventory) Oluşturuluyor... ({len(unique_skus)} benzersiz ürün)")
    inventory_data = []

    random.seed(42)  # Tekrarlanabilirlik (reproducibility) için

    # Risk bölgesi sınırlarını hazırla
    zones = list(RISK_DISTRIBUTION.keys())
    weights = list(RISK_DISTRIBUTION.values())

    stats = {"healthy": 0, "marginal": 0, "critical": 0}

    for sku in unique_skus:
        # ── Satış hızını hesapla ──
        if sku in sku_stats.index:
            total_qty = sku_stats.loc[sku, 'total_qty']
            active_days = sku_stats.loc[sku, 'active_days']
            avg_daily_sales = total_qty / max(active_days, 1)
        else:
            avg_daily_sales = 0.1  # Fallback: çok düşük satışlı ürün

        # ── Lead Time: satış hızına göre dinamik tedarik süresi ──
        # Yüksek hacimli ürünler yerel tedarikçiden, düşük hacimli olanlar uzak tedarikçiden
        if avg_daily_sales > 5:
            lead_time_days = 3    # Yüksek hacim → yerel/hızlı tedarikçi
        elif avg_daily_sales >= 1:
            lead_time_days = 7    # Orta hacim → standart tedarik
        else:
            lead_time_days = 14   # Düşük hacim → uzak/seyrek tedarikçi

        # ── Critical Threshold: ürüne özgü lead time dayalı ──
        critical_threshold = int(avg_daily_sales * lead_time_days * SAFETY_FACTOR)
        critical_threshold = max(critical_threshold, MIN_THRESHOLD)

        # ── Current Stock: kontrollü çeşitlilik ──
        # Max stok = tam dolu bir reorder döngüsü + güvenlik stoku
        max_stock = int(avg_daily_sales * (REORDER_CYCLE_DAYS + ASSUMED_LEAD_TIME_DAYS))
        max_stock = max(max_stock, critical_threshold * 4, 10)  # minimum anlamlı üst sınır

        # SKU'yu rastgele bir risk bölgesine ata
        zone = random.choices(zones, weights=weights, k=1)[0]
        stats[zone] += 1

        if zone == "healthy":
            # Stok, threshold'un 3-5 katı → rahat bölge
            current_stock = random.randint(critical_threshold * 3, max_stock)
        elif zone == "marginal":
            # Stok, threshold civarında (1x - 3x arası) → uyarı bölgesi
            current_stock = random.randint(critical_threshold, critical_threshold * 3)
        else:  # critical
            # Stok, threshold'un altında → alarm bölgesi
            current_stock = random.randint(MIN_STOCK, max(critical_threshold - 1, MIN_STOCK))

        inventory_data.append((sku, current_stock, critical_threshold, lead_time_days))

    cursor.execute('''
        CREATE TABLE inventory (
            sku TEXT PRIMARY KEY,
            current_stock INTEGER,
            critical_threshold INTEGER,
            lead_time_days INTEGER DEFAULT 7
        )
    ''')

    cursor.executemany(
        "INSERT INTO inventory (sku, current_stock, critical_threshold, lead_time_days) VALUES (?, ?, ?, ?)",
        inventory_data
    )

    conn.commit()
    conn.close()

    # ── Özet Rapor ──
    print("=" * 55)
    print("[+] BAŞARILI!")
    print(f"    Satış geçmişi : {len(df):,} satır (gerçek)")
    print(f"    Envanter       : {len(unique_skus):,} SKU (veri-odaklı sentetik)")
    print(f"    Risk dağılımı  : 🟢 Sağlıklı {stats['healthy']}"
          f" | 🟡 Marjinal {stats['marginal']}"
          f" | 🔴 Kritik {stats['critical']}")
    print(f"    Parametreler   : lead_time={ASSUMED_LEAD_TIME_DAYS}d,"
          f" safety={SAFETY_FACTOR}x,"
          f" reorder_cycle={REORDER_CYCLE_DAYS}d")
    print(f"    Çıktı          : {db_path}")
    print("=" * 55)


if __name__ == "__main__":
    build_database()

import pandas as pd
import numpy as np
import sqlite3
import os
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, r2_score
import pickle

def train_demand_forecaster():
    db_path = os.path.join(os.path.dirname(__file__), "../database/amazon_sales.db")
    model_dir = os.path.join(os.path.dirname(__file__), "../models")
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, "xgboost_demand_forecaster.pkl")
    
    print("[*] Veritabanından geçmiş satışlar yükleniyor...")
    conn = sqlite3.connect(db_path)
    
    # İptal edilenleri sayma (Sadece gerçekleşen veya yolda olan talepleri tahmin edelim)
    # Status içerisinde 'Cancelled' kelimesi geçmeyenleri al
    query = """
    SELECT sku, date, qty 
    FROM sales_history 
    WHERE status NOT LIKE '%Cancelled%' AND qty > 0
    """
    df = pd.read_sql(query, conn)
    conn.close()
    
    # Veri Tipi düzeltmeleri
    df['date'] = pd.to_datetime(df['date'])
    df['qty'] = pd.to_numeric(df['qty'])
    
    print(f"[*] Ham satış verisi: {len(df)} satır. Günlük bazda kümeleniyor...")
    
    # SKU ve Date'e göre toplam satış
    daily_sales = df.groupby(['sku', 'date'])['qty'].sum().reset_index()
    
    # Tüm SKUs ve tüm Tarihler için cross-join (Kayıp günleri 0 yapmak için)
    skus = daily_sales['sku'].unique()
    dates = pd.date_range(daily_sales['date'].min(), daily_sales['date'].max())
    
    # Büyük bir MultiIndex oluşturup DataFrame'i dolduruyoruz
    print("[*] Eksik günler (Sıfır satış olan günler) dolduruluyor...")
    idx = pd.MultiIndex.from_product([skus, dates], names=['sku', 'date'])
    full_df = pd.DataFrame(index=idx).reset_index()
    
    # Gerçek satışları sol birleştirme ile üzerine yaz
    merged_df = pd.merge(full_df, daily_sales, on=['sku', 'date'], how='left')
    merged_df['qty'] = merged_df['qty'].fillna(0)
    
    # Zamana göre sırala (Lag hesaplamaları için kritik!)
    merged_df = merged_df.sort_values(by=['sku', 'date']).reset_index(drop=True)
    
    print("[*] Geriye Dönük (Lag) Özellikler (Feature Engineering) hesaplanıyor...")
    # Geçmiş 7, 14 ve 30 günlük toplam satışlar
    merged_df['lag_7'] = merged_df.groupby('sku')['qty'].transform(lambda x: x.rolling(7, min_periods=1).sum())
    merged_df['lag_14'] = merged_df.groupby('sku')['qty'].transform(lambda x: x.rolling(14, min_periods=1).sum())
    merged_df['lag_30'] = merged_df.groupby('sku')['qty'].transform(lambda x: x.rolling(30, min_periods=1).sum())
    
    # Yeni Özellikler (Velocity ve Seyreklik)
    merged_df['velocity_ratio'] = merged_df['lag_7'] / (merged_df['lag_30'] + 1)
    merged_df['is_no_history'] = (merged_df['lag_30'] == 0).astype(int)
    
    print("[*] Gelecek 30 Gün (Hedef/Target) hesaplanıyor...")
    # Shift ile bir sonraki günden itibaren 30 günlük toplam
    indexer = pd.api.indexers.FixedForwardWindowIndexer(window_size=30)
    merged_df['target_30d'] = merged_df.groupby('sku')['qty'].transform(lambda x: x.rolling(window=indexer, min_periods=1).sum().shift(-1))
    
    # Target'ı null olan satırları atıyoruz (Çünkü o günlerden sonraki 30 günü bilmiyoruz)
    # NOT: Verisetinin son 30 günü train testine giremez, çünkü "gelecek 30 günü" yaşanmadı!
    train_df = merged_df.dropna(subset=['target_30d'])
    
    print(f"[*] Eğitim veriseti hazır: {len(train_df)} örneklem. XGBoost Eğitimi Başlıyor...")
    
    features = ['lag_7', 'lag_14', 'lag_30', 'velocity_ratio', 'is_no_history']
    X = train_df[features]
    y = train_df['target_30d']
    
    # XGBoost Regressor (Quantile Forecasting)
    model = xgb.XGBRegressor(
        objective='reg:quantileerror',
        quantile_alpha=[0.1, 0.5, 0.9],
        n_estimators=150, 
        learning_rate=0.1, 
        max_depth=6, 
        random_state=42, 
        n_jobs=-1
    )
    
    print("[*] Tüm veri ile Olasılıksal Model (Quantile P10, P50, P90) eğitiliyor...")
    model.fit(X, y)
    
    # Modeli kaydetme
    with open(model_path, "wb") as f:
        pickle.dump(model, f)
        
    print(f"[+] Model başarıyla '{model_path}' konumuna Artifact olarak (Pickle) kaydedildi.")

if __name__ == "__main__":
    train_demand_forecaster()

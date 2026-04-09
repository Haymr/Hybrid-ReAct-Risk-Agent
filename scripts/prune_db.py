import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "../database/agent_state.db")

def prune_old_threads(days_old=7):
    """
    (Production Ready Taslak)
    LangGraph checkpoint_id'leri UUIDv6 formatındadır ve zaman damgası içerir.
    Veritabanını tamamen sıfırlamak yerine, bu UUID'lerin zaman damgaları 
    çözümlenerek (SQL veya Python tarafında) sadece belirtilen süreden (ör: 7 gün) 
    daha eski olan thread_id'ler silinecektir (Pruning).
    """
    if not os.path.exists(DB_PATH):
        print("Veritabanı henüz oluşmamış.")
        return

    print(f"[PROTOTİP BİLGİSİ] Üretim (Production) aşamasında bu script, {days_old} günden daha eski konuşma geçmişlerini (UUIDv6 tabanlı) budamak için çalışacaktır.")
    print("Mevcut durumda over-engineering'i engellemek adına script pasife alınmıştır.")

if __name__ == "__main__":
    prune_old_threads()

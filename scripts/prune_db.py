import sqlite3
import os
import datetime
import sys

DB_PATH = os.path.join(os.path.dirname(__file__), "../database/agent_state.db")

def get_datetime_from_uuidv6(uuid_str: str) -> datetime.datetime:
    """
    Extracts the UTC datetime from a UUIDv6 string used by LangGraph.
    UUIDv6 starts with a 60-bit timestamp indicating 100-ns intervals since 1582.
    """
    uuid_hex = uuid_str.replace('-', '')
    # The first 15 characters contain the 60-bit timestamp
    timestamp_hex = uuid_hex[:15]
    timestamp_100ns = int(timestamp_hex, 16)
    
    # 122192928000000000 equals 100-ns intervals between 1582-10-15 and 1970-01-01
    unix_time = (timestamp_100ns - 122192928000000000) / 10000000.0
    return datetime.datetime.fromtimestamp(unix_time, tz=datetime.timezone.utc)

def prune_old_threads(days_old=7):
    """
    Production-ready script to prune old LangGraph conversation threads.
    It resolves UUIDv6 time signatures to calculate thread age and safely 
    removes threads (and their events) that haven't been active for 'days_old'.
    """
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    print(f"Connecting to database to prune threads inactive for more than {days_old} days...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # Get all unique thread_ids and their latest checkpoint
        cursor.execute("SELECT thread_id, MAX(checkpoint_id) FROM checkpoints GROUP BY thread_id")
        threads = cursor.fetchall()
        
        now = datetime.datetime.now(datetime.timezone.utc)
        threads_to_delete = []

        for thread_id, latest_checkpoint in threads:
            try:
                last_active = get_datetime_from_uuidv6(latest_checkpoint)
                age = now - last_active
                if age.days > days_old:
                    threads_to_delete.append(thread_id)
            except Exception as e:
                print(f"Warning: Could not parse timestamp for thread {thread_id} (Checkpoint: {latest_checkpoint}) -> {e}")
                
        if not threads_to_delete:
            print("No old threads found to prune. Database is clean.")
            return

        print(f"Found {len(threads_to_delete)} thread(s) older than {days_old} days. Commencing deletion...")
        
        # Execute deletion
        placeholders = ','.join(['?'] * len(threads_to_delete))
        cursor.execute(f"DELETE FROM writes WHERE thread_id IN ({placeholders})", threads_to_delete)
        deleted_writes = cursor.rowcount
        
        cursor.execute(f"DELETE FROM checkpoints WHERE thread_id IN ({placeholders})", threads_to_delete)
        deleted_checkpoints = cursor.rowcount
        
        # Vacuum to compress SQLite memory and recover disk space safely
        cursor.execute("VACUUM")
        
        conn.commit()
        print("Pruning complete.")
        print(f"Total Threads Deleted: {len(threads_to_delete)}")
        print(f"Freed DB Rows -> Checkpoints: {deleted_checkpoints}, Writes/Events: {deleted_writes}")
        
    except Exception as e:
        print(f"An error occurred during pruning: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    # Support overriding days dynamically: python prune_db.py 30
    days = 7
    if len(sys.argv) > 1:
        try:
            days = int(sys.argv[1])
        except ValueError:
            print("Usage: python prune_db.py [days]")
            sys.exit(1)
            
    prune_old_threads(days_old=days)

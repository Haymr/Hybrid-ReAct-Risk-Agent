import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Create Products table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            current_stock INTEGER NOT NULL,
            critical_threshold INTEGER NOT NULL,
            sales_velocity_30d INTEGER NOT NULL
        )
    """)

    # Create Orders table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            quantity INTEGER NOT NULL,
            order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (product_id) REFERENCES products (id)
        )
    """)

    # Mock Data Injection
    try:
        cursor.executemany(
            """INSERT OR IGNORE INTO products (name, current_stock, critical_threshold, sales_velocity_30d) 
               VALUES (?, ?, ?, ?)""",
            [
                ("Laptop Pro X", 12, 50, 120),
                ("Wireless Mouse", 150, 30, 45),
                ("Mechanical Keyboard", 5, 20, 80)
            ]
        )
        conn.commit()
    except sqlite3.Error as e:
        print(f"Database error during initialization: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
    print(f"Database initialized and mock data injected at {DB_PATH}")

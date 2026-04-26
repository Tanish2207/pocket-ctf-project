import sqlite3
import os

# Make sure we're looking at the DB in the backend folder
DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bluelab.db")
print(f"Looking for DB at: {DB_PATH}")
print(f"DB exists: {os.path.exists(DB_PATH)}")

if not os.path.exists(DB_PATH):
    print("\n[!] bluelab.db does not exist yet!")
    print("This means the FastAPI server was never started, or init_db() never ran.")
    print("\nCreating the database and tables now...")
    
    os.chdir(os.path.dirname(os.path.abspath(__file__)))
    from database import init_db
    init_db()
    print("[OK] Database initialized!\n")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# View all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()
print("Tables:", [t[0] for t in tables])

# View each table's contents
for table in tables:
    table_name = table[0]
    cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
    count = cursor.fetchone()[0]
    print(f"\n--- {table_name} ({count} rows) ---")
    if count > 0:
        cursor.execute(f"SELECT * FROM {table_name}")
        rows = cursor.fetchall()
        cols = [desc[0] for desc in cursor.description]
        print("  Columns:", cols)
        for row in rows:
            print(" ", dict(row))

conn.close()

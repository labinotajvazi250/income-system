import sqlite3

con = sqlite3.connect("data_DB")
cur = con.cursor()

# shfaq tabelat
tables = cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
print("Tabelat:", tables)

# provo me shtu buy_date ne secilen tabele
for t in tables:
    table = t[0]
    try:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN buy_date TEXT")
        print("U shtua buy_date te:", table)
    except:
        print("Ekziston ose s’lejohet te:", table)

con.commit()
con.close()

print("Perfundoj ✔")
input("Enter per exit...")

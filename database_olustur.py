import sqlite3

# Veritabanı dosyasına bağlan (Yoksa otomatik oluşturur)
conn = sqlite3.connect('dogal_yemegim.db')
cursor = conn.cursor()

# Ürünler tablosunu oluştur
cursor.execute('''
CREATE TABLE IF NOT EXISTS urunler (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad TEXT NOT NULL,
    fiyat TEXT NOT NULL,
    resim TEXT,
    mesaj TEXT
)
''')

# Örnek ürünleri ekleyelim
ornek_urunler = [
    ('Soğuk Sıkım Zeytinyağı', '650 TL', 'zeytinyagi.jpg', 'Zeytinyagi'),
    ('Karakovan Balı', '850 TL', 'bal.jpg', 'Bal'),
    ('Ev Tarhanası', '300 TL', 'tarhana.jpg', 'Tarhana')
]

cursor.executemany('INSERT INTO urunler (ad, fiyat, resim, mesaj) VALUES (?, ?, ?, ?)', ornek_urunler)

conn.commit()
conn.close()
print("Veritabanı ve tablolar başarıyla oluşturuldu!")
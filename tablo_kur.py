import sqlite3
import os

# Mevcut klasör yolunu al
base_path = os.path.dirname(__file__)
db_path = os.path.join(base_path, 'dogal_yemegim.db')

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

# 1. Eğer eski/hatalı tablo varsa temizle (isteğe bağlı ama garanti yol)
cursor.execute('DROP TABLE IF EXISTS urunler')

# 2. Ürünler tablosunu sıfırdan oluştur
cursor.execute('''
CREATE TABLE urunler (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ad TEXT NOT NULL,
    fiyat TEXT NOT NULL,
    resim TEXT,
    mesaj TEXT
)
''')

# 3. İçine ilk ürünleri yerleştir (Site boş görünmesin)
ornekler = [
    ('Soğuk Sıkım Zeytinyağı', '650 TL', 'https://images.unsplash.com/photo-1474979266404-7eaacbcd87c5?w=500', 'Zeytinyagi'),
    ('Karakovan Balı', '850 TL', 'https://images.unsplash.com/photo-1471943311424-646960669fba?w=500', 'Bal'),
    ('Ev Tarhanası', '300 TL', 'https://images.unsplash.com/photo-1547592166-23ac45744acd?w=500', 'Tarhana'),
   
('Karakovan Balı', '850 TL', 'https://bit.ly/3IrjXmU', 'Bal_Siparis'),
('Soğuk Sıkım Zeytinyağı', '600 TL', 'https://bit.ly/3Inp3kE', 'Zeytinyagi_Siparis'),
('Ev Yapımı Tarhana', '250 TL', 'https://bit.ly/3ImQ8S8', 'Tarhana_Siparis'),
('Doğal Çiçek Poleni', '400 TL', 'https://bit.ly/3InpX9E', 'Polen_Siparis'),
('Organik Köy Yumurtası', '120 TL', 'https://bit.ly/3IpH9S8', 'Yumurta_Siparis'),
('Taş Baskı Zeytin', '350 TL', 'https://bit.ly/3InpYmG', 'Zeytin_Siparis')

]

cursor.executemany('INSERT INTO urunler (ad, fiyat, resim, mesaj) VALUES (?, ?, ?, ?)', ornekler)

conn.commit()
conn.close()
print("Süper! Tablo oluşturuldu ve örnek ürünler eklendi.")
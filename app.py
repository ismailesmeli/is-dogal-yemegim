import sqlite3
import os
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename

# --- UYGULAMA AYARLARI ---
app = Flask(__name__)
app.secret_key = 'is_dogal_yemegim_ozel_sifre'

UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- VERİTABANI BAĞLANTISI ---
def get_db_connection():
    db_path = os.path.join(os.path.dirname(__file__), 'dogal_yemegim.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row 
    return conn

# --- VERİTABANI TABLO HAZIRLIĞI ---
def tablo_olustur():
    conn = get_db_connection()
    # Yorumlar tablosunu her ihtimale karşı temizleyip en doğru haliyle kuralım
    conn.execute('DROP TABLE IF EXISTS yorumlar') 
    conn.execute('''CREATE TABLE yorumlar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        urun_id INTEGER,
        isim TEXT,
        yorum_metni TEXT,
        puan INTEGER,
        onayli_alisveris INTEGER DEFAULT 0,
        tarih DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    # Ürünler tablosu yoksa oluşturalım (Sütunlar: ad, fiyat, resim, mesaj, aciklama)
    conn.execute('''CREATE TABLE IF NOT EXISTS urunler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT, fiyat TEXT, resim TEXT, mesaj TEXT, aciklama TEXT
    )''')
    conn.commit()
    conn.close()

# DİKKAT: Tabloyu kod çalışır çalışmaz oluşturması için burada çağırıyoruz
tablo_olustur()

# --- ANA SAYFA VE ÜRÜNLER ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/urunler')
def urunler():
    query = request.args.get('q')
    conn = get_db_connection()
    if query:
        urunler = conn.execute('SELECT * FROM urunler WHERE ad LIKE ?', ('%' + query + '%',)).fetchall()
    else:
        urunler = conn.execute('SELECT * FROM urunler').fetchall()
    conn.close()
    return render_template('urunler.html', urunler=urunler)

@app.route('/urun/<int:id>')
def urun_detay(id):
    conn = get_db_connection()
    urun = conn.execute('SELECT * FROM urunler WHERE id = ?', (id,)).fetchone()
    
    # Sadece onaylı yorumları çekiyoruz
    yorumlar = conn.execute('SELECT * FROM yorumlar WHERE urun_id = ? AND onayli_alisveris = 1 ORDER BY id DESC', (id,)).fetchall()
    
    # ⭐ ORTALAMA HESAPLAMA
    ortalama_puan = 0
    if yorumlar:
        toplam_puan = sum([y['puan'] for y in yorumlar])
        ortalama_puan = round(toplam_puan / len(yorumlar), 1) # Örn: 4.3 gibi

    conn.close()
    return render_template('urun_detay.html', urun=urun, yorumlar=yorumlar, ortalama=ortalama_puan)

# --- YORUM YAPMA ---
@app.route('/yorum_yap', methods=['POST'])
def yorum_yap():
    urun_id = request.form.get('urun_id')
    isim = request.form.get('isim')
    yorum = request.form.get('yorum')
    puan = request.form.get('puan')

    conn = get_db_connection()
    # Onay durumunu 0 yapıyoruz (Admin onaylayana kadar görünmez)
    conn.execute('INSERT INTO yorumlar (urun_id, isim, yorum_metni, puan, onayli_alisveris) VALUES (?, ?, ?, ?, 0)',
                 (urun_id, isim, yorum, puan))
    conn.commit()
    conn.close()
    flash('Yorumunuz alındı, admin onayından sonra yayınlanacaktır.', 'info')
    return redirect(url_for('urun_detay', id=urun_id))

# --- ADMİN İÇİN YORUM ONAYLAMA ROTASI ---
@app.route('/admin/yorum-onayla/<int:id>')
def yorum_onayla(id):
    if not session.get('admin_girdi'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('UPDATE yorumlar SET onayli_alisveris = 1 WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    flash('Yorum onaylandı ve yayınlandı!', 'success')
    return redirect(url_for('admin_dashboard'))
# --- GİRİŞ / ÇIKIŞ ---
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == 'admin' and request.form['password'] == '1234':
            session['admin_girdi'] = True
            flash('Başarıyla giriş yapıldı!', 'success')
            return redirect(url_for('urunler'))
        else:
            flash('Hatalı kullanıcı adı veya şifre!', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('admin_girdi', None)
    return redirect(url_for('home'))

# --- SEPET İŞLEMLERİ ---
@app.route('/sepet/ekle/<int:id>')
def sepete_ekle(id):
    if 'sepet' not in session:
        session['sepet'] = []
    
    conn = get_db_connection()
    urun = conn.execute('SELECT * FROM urunler WHERE id = ?', (id,)).fetchone()
    conn.close()

    if urun:
        sepet = session['sepet']
        sepet.append({'id': urun['id'], 'ad': urun['ad'], 'fiyat': urun['fiyat']})
        session['sepet'] = sepet
        flash(f"{urun['ad']} sepete eklendi!", "success")
    
    return redirect(url_for('urunler'))

@app.route('/sepet')
def sepet_goruntule():
    sepet = session.get('sepet', [])
    toplam = 0
    for urun in sepet:
        try:
            fiyat_temiz = urun['fiyat'].replace(' TL', '').replace('.', '').replace(',', '').strip()
            toplam += int(fiyat_temiz)
        except: pass
    return render_template('sepet.html', sepet=sepet, toplam=toplam)

@app.route('/sepet/temizle')
def sepet_temizle():
    session.pop('sepet', None)
    return redirect(url_for('sepet_goruntule'))

# --- SİPARİŞ ONAY (YENİ) ---
@app.route('/siparis-onay')
def siparis_onay():
    sepet = session.get('sepet', [])
    if not sepet:
        flash("Sepetiniz boş!", "warning")
        return redirect(url_for('urunler'))
    
    # Sepet özetini WhatsApp için hazırlayalım
    ozet = ", ".join([u['ad'] for u in sepet])
    return render_template('siparis_onay.html', sepet_ozeti=ozet)

# --- ADMİN PANELİ VE İŞLEMLER ---
@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_girdi'):
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    
    # 1. Toplam Ürün Sayısı
    toplam_urun = conn.execute('SELECT COUNT(*) FROM urunler').fetchone()[0]
    
    # 2. En Son Eklenen Ürün (Pahalı yerine en günceli görmek daha mantıklı)
    son_urun = conn.execute('SELECT ad, fiyat FROM urunler ORDER BY id DESC LIMIT 1').fetchone()
    
    # 3. 🔥 KRİTİK KISIM: Onay Bekleyen Yorumları Çek (onayli_alisveris = 0 olanlar)
    bekleyen_yorumlar = conn.execute('SELECT * FROM yorumlar WHERE onayli_alisveris = 0 ORDER BY tarih DESC').fetchall()
    
    conn.close()
    
    # HTML'e hepsini gönderiyoruz
    return render_template('admin_dashboard.html', 
                           toplam=toplam_urun, 
                           pahali=son_urun, 
                           bekleyen_yorumlar=bekleyen_yorumlar)
@app.route('/admin/ekle', methods=['GET', 'POST'])
def urun_ekle():
    if not session.get('admin_girdi'):
        return redirect(url_for('login'))
    if request.method == 'POST':
        ad = request.form['ad']
        fiyat = request.form['fiyat']
        mesaj = request.form['mesaj']
        
        # Resim yükleme kontrolü
        file = request.files.get('resim_dosya')
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            resim_yolu = url_for('static', filename='uploads/' + filename)
        else:
            resim_yolu = request.form['resim'] # Link verildiyse onu al

        conn = get_db_connection()
        conn.execute('INSERT INTO urunler (ad, fiyat, resim, mesaj) VALUES (?, ?, ?, ?)', (ad, fiyat, resim_yolu, mesaj))
        conn.commit()
        conn.close()
        flash('Ürün başarıyla eklendi!', 'success')
        return redirect(url_for('urunler'))
    return render_template('admin_ekle.html')

@app.route('/admin/sil/<int:id>') # <-- Buradaki adrese dikkat!
def urun_sil(id):
    if not session.get('admin_girdi'):
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    # Önce ürüne ait yetim kalacak yorumları silelim
    conn.execute('DELETE FROM yorumlar WHERE urun_id = ?', (id,))
    # Sonra ürünü silelim
    conn.execute('DELETE FROM urunler WHERE id = ?', (id,))
    conn.commit()
    conn.close()
    
    flash('Ürün ve yorumları başarıyla silindi!', 'danger')
    return redirect(url_for('urunler'))

import time # En üste ekle

@app.route('/urun_guncelle/<int:id>', methods=['GET', 'POST'])
def urun_guncelle(id):
    if not session.get('admin_girdi'): 
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    urun = conn.execute('SELECT * FROM urunler WHERE id = ?', (id,)).fetchone()

    if request.method == 'POST':
        ad = request.form['ad']
        fiyat = request.form['fiyat']
        
        # Resim yükleme kontrolü
        file = request.files.get('resim_dosya')
        if file and file.filename != '':
            # Dosya ismini benzersiz yap (Örn: 16469234_resim.jpg)
            filename = secure_filename(f"{int(time.time())}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            resim_yolu = url_for('static', filename='uploads/' + filename)
        else:
            # Eğer yeni resim seçilmediyse eski resmi koru
            resim_yolu = urun['resim']

        conn.execute('UPDATE urunler SET ad = ?, fiyat = ?, resim = ? WHERE id = ?',
                     (ad, fiyat, resim_yolu, id))
        conn.commit()
        conn.close()
        flash('Ürün ve fotoğraf başarıyla güncellendi!', 'success')
        return redirect(url_for('urunler'))

    conn.close()
    return render_template('urun_guncelle.html', urun=urun)
# --- DİĞER SAYFALAR ---
@app.route('/hakkimizda')
def hakkimizda(): return render_template('hakkimizda.html')

@app.route('/iletisim')
def iletisim(): return render_template('iletisim.html')

if __name__ == "__main__":
    # Kendi bilgisayarın için en güvenli ve standart ayar budur
    app.run(debug=True, port=5001)
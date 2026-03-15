import os
import psycopg2
import psycopg2.extras
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
import time

# --- UYGULAMA AYARLARI ---
app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'is_dogal_yemegim_ozel_sifre')

UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- VERİTABANI BAĞLANTISI (PostgreSQL) ---
def get_db_connection():
    # Render'daki DATABASE_URL'i kullanır
    database_url = os.environ.get('DATABASE_URL')
    conn = psycopg2.connect(database_url, sslmode='require')
    return conn

# --- VERİTABANI TABLO HAZIRLIĞI ---
def tablo_olustur():
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Ürünler tablosu
    cur.execute('''CREATE TABLE IF NOT EXISTS urunler (
        id SERIAL PRIMARY KEY,
        ad TEXT, 
        fiyat TEXT, 
        resim TEXT, 
        mesaj TEXT, 
        aciklama TEXT
    )''')
    
    # Yorumlar tablosu
    cur.execute('''CREATE TABLE IF NOT EXISTS yorumlar (
        id SERIAL PRIMARY KEY,
        urun_id INTEGER,
        isim TEXT,
        yorum_metni TEXT,
        puan INTEGER,
        onayli_alisveris INTEGER DEFAULT 0,
        tarih TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.commit()
    cur.close()
    conn.close()

# Tabloları oluştur
tablo_olustur()

# --- ANA SAYFA VE ÜRÜNLER ---
@app.route('/')
def home():
    return render_template('index.html')

@app.route('/urunler')
def urunler():
    query = request.args.get('q')
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    if query:
        cur.execute('SELECT * FROM urunler WHERE ad ILIKE %s', ('%' + query + '%',))
    else:
        cur.execute('SELECT * FROM urunler')
    urunler = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('urunler.html', urunler=urunler)

@app.route('/urun/<int:id>')
def urun_detay(id):
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM urunler WHERE id = %s', (id,))
    urun = cur.fetchone()
    
    # Sadece onaylı yorumları çekiyoruz
    cur.execute('SELECT * FROM yorumlar WHERE urun_id = %s AND onayli_alisveris = 1 ORDER BY id DESC', (id,))
    yorumlar = cur.fetchall()
    
    # ⭐ ORTALAMA HESAPLAMA
    ortalama_puan = 0
    if yorumlar:
        toplam_puan = sum([y['puan'] for y in yorumlar])
        ortalama_puan = round(toplam_puan / len(yorumlar), 1)

    cur.close()
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
    cur = conn.cursor()
    cur.execute('INSERT INTO yorumlar (urun_id, isim, yorum_metni, puan, onayli_alisveris) VALUES (%s, %s, %s, %s, 0)',
                 (urun_id, isim, yorum, puan))
    conn.commit()
    cur.close()
    conn.close()
    flash('Yorumunuz alındı, admin onayından sonra yayınlanacaktır.', 'info')
    return redirect(url_for('urun_detay', id=urun_id))

# --- ADMİN İÇİN YORUM ONAYLAMA ROTASI ---
@app.route('/admin/yorum-onayla/<int:id>')
def yorum_onayla(id):
    if not session.get('admin_girdi'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('UPDATE yorumlar SET onayli_alisveris = 1 WHERE id = %s', (id,))
    conn.commit()
    cur.close()
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
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM urunler WHERE id = %s', (id,))
    urun = cur.fetchone()
    cur.close()
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

# --- SİPARİŞ ONAY ---
@app.route('/siparis-onay')
def siparis_onay():
    sepet = session.get('sepet', [])
    if not sepet:
        flash("Sepetiniz boş!", "warning")
        return redirect(url_for('urunler'))
    
    ozet = ", ".join([u['ad'] for u in sepet])
    return render_template('siparis_onay.html', sepet_ozeti=ozet)

# --- ADMİN PANELİ VE İŞLEMLER ---
@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_girdi'):
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    
    cur.execute('SELECT COUNT(*) FROM urunler')
    toplam_urun = cur.fetchone()[0]
    
    cur.execute('SELECT ad, fiyat FROM urunler ORDER BY id DESC LIMIT 1')
    son_urun = cur.fetchone()
    
    cur.execute('SELECT * FROM yorumlar WHERE onayli_alisveris = 0 ORDER BY tarih DESC')
    bekleyen_yorumlar = cur.fetchall()
    
    cur.close()
    conn.close()
    
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
        
        file = request.files.get('resim_dosya')
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            resim_yolu = url_for('static', filename='uploads/' + filename)
        else:
            resim_yolu = request.form['resim']

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute('INSERT INTO urunler (ad, fiyat, resim, mesaj) VALUES (%s, %s, %s, %s)', 
                    (ad, fiyat, resim_yolu, mesaj))
        conn.commit()
        cur.close()
        conn.close()
        flash('Ürün başarıyla eklendi!', 'success')
        return redirect(url_for('urunler'))
    return render_template('admin_ekle.html')

@app.route('/admin/sil/<int:id>')
def urun_sil(id):
    if not session.get('admin_girdi'):
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute('DELETE FROM yorumlar WHERE urun_id = %s', (id,))
    cur.execute('DELETE FROM urunler WHERE id = %s', (id,))
    conn.commit()
    cur.close()
    conn.close()
    
    flash('Ürün ve yorumları başarıyla silindi!', 'danger')
    return redirect(url_for('urunler'))

@app.route('/urun_guncelle/<int:id>', methods=['GET', 'POST'])
def urun_guncelle(id):
    if not session.get('admin_girdi'): 
        return redirect(url_for('login'))
        
    conn = get_db_connection()
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    cur.execute('SELECT * FROM urunler WHERE id = %s', (id,))
    urun = cur.fetchone()

    if request.method == 'POST':
        ad = request.form['ad']
        fiyat = request.form['fiyat']
        
        file = request.files.get('resim_dosya')
        if file and file.filename != '':
            filename = secure_filename(f"{int(time.time())}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
            resim_yolu = url_for('static', filename='uploads/' + filename)
        else:
            resim_yolu = urun['resim']

        cur.execute('UPDATE urunler SET ad = %s, fiyat = %s, resim = %s WHERE id = %s',
                    (ad, fiyat, resim_yolu, id))
        conn.commit()
        cur.close()
        conn.close()
        flash('Ürün başarıyla güncellendi!', 'success')
        return redirect(url_for('urunler'))

    cur.close()
    conn.close()
    return render_template('urun_guncelle.html', urun=urun)

# --- DİĞER SAYFALAR ---
@app.route('/hakkimizda')
def hakkimizda(): return render_template('hakkimizda.html')

@app.route('/iletisim')
def iletisim(): return render_template('iletisim.html')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

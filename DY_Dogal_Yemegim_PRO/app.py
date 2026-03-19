import sqlite3
import os
import time
import json
import urllib.parse
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dy_dogal_yemegim_2026_gizli')

ADMIN_USER = os.environ.get('ADMIN_USER', 'admin')
ADMIN_PASS = os.environ.get('ADMIN_PASS', '1234')
PER_PAGE = 12

UPLOAD_FOLDER = 'static/uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

ALLOWED = {'png', 'jpg', 'jpeg', 'gif', 'webp', 'avif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED

def get_db_connection():
    db_path = os.path.join(os.path.dirname(__file__), 'dogal_yemegim.db')
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn

def add_col(conn, table, col, col_type, default=None):
    try:
        if default is not None:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {col} {col_type} DEFAULT {default}')
        else:
            conn.execute(f'ALTER TABLE {table} ADD COLUMN {col} {col_type}')
    except Exception:
        pass

def tablo_olustur():
    conn = get_db_connection()
    conn.execute('''CREATE TABLE IF NOT EXISTS kategoriler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT NOT NULL,
        ikon TEXT DEFAULT '🌿',
        sira INTEGER DEFAULT 0
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS urunler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ad TEXT, fiyat INTEGER DEFAULT 0, indirim_fiyat INTEGER DEFAULT 0,
        resim TEXT, mesaj TEXT, aciklama TEXT,
        kategori_id INTEGER, stok INTEGER DEFAULT 100,
        featured INTEGER DEFAULT 0, aktif INTEGER DEFAULT 1
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS yorumlar (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        urun_id INTEGER, isim TEXT, yorum_metni TEXT, puan INTEGER,
        onayli_alisveris INTEGER DEFAULT 0,
        tarih DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.execute('''CREATE TABLE IF NOT EXISTS siparisler (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        musteri_ad TEXT, tel TEXT, adres TEXT,
        urunler_json TEXT, toplam INTEGER DEFAULT 0,
        durum TEXT DEFAULT 'Yeni',
        tarih DATETIME DEFAULT CURRENT_TIMESTAMP
    )''')
    add_col(conn, 'urunler', 'indirim_fiyat', 'INTEGER', 0)
    add_col(conn, 'urunler', 'kategori_id', 'INTEGER')
    add_col(conn, 'urunler', 'stok', 'INTEGER', 100)
    add_col(conn, 'urunler', 'featured', 'INTEGER', 0)
    add_col(conn, 'urunler', 'aktif', 'INTEGER', 1)
    conn.commit()
    conn.close()

tablo_olustur()


def get_sepet_toplam():
    return sum(int(i['fiyat']) * int(i.get('adet', 1)) for i in session.get('sepet', []))

def get_sepet_adet():
    return sum(i.get('adet', 1) for i in session.get('sepet', []))

app.jinja_env.globals['get_sepet_adet'] = get_sepet_adet
app.jinja_env.filters['from_json'] = json.loads


@app.route('/')
def home():
    conn = get_db_connection()
    featured = conn.execute('SELECT * FROM urunler WHERE featured=1 AND aktif=1 LIMIT 8').fetchall()
    kategoriler = conn.execute('SELECT * FROM kategoriler ORDER BY sira').fetchall()
    conn.close()
    return render_template('index.html', featured=featured, kategoriler=kategoriler)


@app.route('/urunler')
def urunler():
    query = request.args.get('q', '')
    kategori_id = request.args.get('kategori', '')
    siralama = request.args.get('siralama', 'yeni')
    sayfa = max(1, int(request.args.get('sayfa', 1)))

    conn = get_db_connection()
    kategoriler = conn.execute('SELECT * FROM kategoriler ORDER BY sira').fetchall()

    sql = 'SELECT u.*, k.ad as kat_ad FROM urunler u LEFT JOIN kategoriler k ON u.kategori_id=k.id WHERE u.aktif=1'
    params = []
    if query:
        sql += ' AND u.ad LIKE ?'
        params.append(f'%{query}%')
    if kategori_id:
        sql += ' AND u.kategori_id=?'
        params.append(kategori_id)

    order_map = {
        'fiyat_asc': 'u.fiyat ASC',
        'fiyat_desc': 'u.fiyat DESC',
        'indirimli': 'u.indirim_fiyat DESC',
        'yeni': 'u.id DESC',
    }
    sql += f' ORDER BY {order_map.get(siralama, "u.id DESC")}'

    tum = conn.execute(sql, params).fetchall()
    toplam_urun = len(tum)
    toplam_sayfa = max(1, (toplam_urun + PER_PAGE - 1) // PER_PAGE)
    urun_listesi = tum[(sayfa - 1) * PER_PAGE: sayfa * PER_PAGE]
    conn.close()

    return render_template('urunler.html',
        urunler=urun_listesi, kategoriler=kategoriler,
        kategori_id=kategori_id, siralama=siralama,
        query=query, sayfa=sayfa,
        toplam_sayfa=toplam_sayfa, toplam_urun=toplam_urun)


@app.route('/urun/<int:id>')
def urun_detay(id):
    conn = get_db_connection()
    urun = conn.execute(
        'SELECT u.*, k.ad as kat_ad FROM urunler u LEFT JOIN kategoriler k ON u.kategori_id=k.id WHERE u.id=?', (id,)
    ).fetchone()
    yorumlar = conn.execute(
        'SELECT * FROM yorumlar WHERE urun_id=? AND onayli_alisveris=1 ORDER BY id DESC', (id,)
    ).fetchall()
    ortalama = round(sum(y['puan'] for y in yorumlar) / len(yorumlar), 1) if yorumlar else 0
    benzer = []
    if urun and urun['kategori_id']:
        benzer = conn.execute(
            'SELECT * FROM urunler WHERE kategori_id=? AND id!=? AND aktif=1 LIMIT 4',
            (urun['kategori_id'], id)
        ).fetchall()
    conn.close()
    return render_template('urun_detay.html', urun=urun, yorumlar=yorumlar, ortalama=ortalama, benzer=benzer)


@app.route('/yorum_yap', methods=['POST'])
def yorum_yap():
    urun_id = request.form.get('urun_id')
    isim = request.form.get('isim')
    yorum = request.form.get('yorum')
    puan = request.form.get('puan', 5)
    conn = get_db_connection()
    conn.execute('INSERT INTO yorumlar (urun_id, isim, yorum_metni, puan) VALUES (?,?,?,?)',
                 (urun_id, isim, yorum, puan))
    conn.commit()
    conn.close()
    flash('Yorumunuz alındı, onaydan sonra yayınlanacak.', 'info')
    return redirect(url_for('urun_detay', id=urun_id))


@app.route('/sepet/ekle/<int:id>')
def sepete_ekle(id):
    conn = get_db_connection()
    urun = conn.execute('SELECT * FROM urunler WHERE id=? AND aktif=1', (id,)).fetchone()
    conn.close()
    if not urun:
        flash('Ürün bulunamadı.', 'danger')
        return redirect(url_for('urunler'))

    fiyat = urun['indirim_fiyat'] if urun['indirim_fiyat'] else urun['fiyat']
    sepet = session.get('sepet', [])

    for item in sepet:
        if item['id'] == id:
            if item['adet'] < (urun['stok'] or 999):
                item['adet'] += 1
            flash(f"{urun['ad']} sepete eklendi!", 'success')
            session['sepet'] = sepet
            return redirect(request.referrer or url_for('urunler'))

    sepet.append({'id': urun['id'], 'ad': urun['ad'], 'fiyat': fiyat,
                  'adet': 1, 'resim': urun['resim'] or ''})
    session['sepet'] = sepet
    flash(f"{urun['ad']} sepete eklendi!", 'success')
    return redirect(request.referrer or url_for('urunler'))


@app.route('/sepet/artir/<int:id>')
def sepet_artir(id):
    sepet = session.get('sepet', [])
    for item in sepet:
        if item['id'] == id:
            item['adet'] = item.get('adet', 1) + 1
            break
    session['sepet'] = sepet
    return redirect(url_for('sepet_goruntule'))


@app.route('/sepet/azalt/<int:id>')
def sepet_azalt(id):
    sepet = session.get('sepet', [])
    for i, item in enumerate(sepet):
        if item['id'] == id:
            item['adet'] = item.get('adet', 1) - 1
            if item['adet'] <= 0:
                sepet.pop(i)
            break
    session['sepet'] = sepet
    return redirect(url_for('sepet_goruntule'))


@app.route('/sepet/kaldir/<int:id>')
def sepet_kaldir(id):
    session['sepet'] = [i for i in session.get('sepet', []) if i['id'] != id]
    return redirect(url_for('sepet_goruntule'))


@app.route('/sepet')
def sepet_goruntule():
    sepet = session.get('sepet', [])
    toplam = get_sepet_toplam()
    return render_template('sepet.html', sepet=sepet, toplam=toplam)


@app.route('/sepet/temizle')
def sepet_temizle():
    session.pop('sepet', None)
    return redirect(url_for('sepet_goruntule'))


@app.route('/siparis-onay')
def siparis_onay():
    sepet = session.get('sepet', [])
    if not sepet:
        flash('Sepetiniz boş!', 'warning')
        return redirect(url_for('urunler'))
    toplam = get_sepet_toplam()
    return render_template('siparis_onay.html', sepet=sepet, toplam=toplam)


@app.route('/siparis/tamamla', methods=['POST'])
def siparis_tamamla():
    sepet = session.get('sepet', [])
    if not sepet:
        return redirect(url_for('urunler'))

    ad = request.form.get('ad', '').strip()
    tel = request.form.get('tel', '').strip()
    adres = request.form.get('adres', '').strip()
    toplam = get_sepet_toplam()

    if not ad or not tel or not adres:
        flash('Lütfen tüm alanları doldurun!', 'danger')
        return redirect(url_for('siparis_onay'))

    conn = get_db_connection()
    cur = conn.execute(
        'INSERT INTO siparisler (musteri_ad, tel, adres, urunler_json, toplam) VALUES (?,?,?,?,?)',
        (ad, tel, adres, json.dumps(sepet, ensure_ascii=False), toplam)
    )
    siparis_id = cur.lastrowid
    conn.commit()
    conn.close()

    satirlar = '\n'.join([
        f"- {u['ad']} x{u.get('adet',1)} = {int(u['fiyat'])*int(u.get('adet',1))} TL"
        for u in sepet
    ])
    mesaj = (f"Merhaba *DY Doğal Yemeğim* 🌿\n\n"
             f"*SİPARİŞ #{siparis_id}*\n{'─'*20}\n{satirlar}\n\n"
             f"*Toplam: {toplam} TL*\n\n"
             f"*Müşteri Bilgileri:*\n👤 {ad}\n📞 {tel}\n📍 {adres}")
    wa_url = f"https://wa.me/905510465380?text={urllib.parse.quote(mesaj)}"

    session.pop('sepet', None)
    session['son_siparis'] = {
        'id': siparis_id, 'ad': ad,
        'urunler': sepet, 'toplam': toplam, 'wa_url': wa_url
    }
    return redirect(url_for('siparis_tamamlandi'))


@app.route('/siparis/tamamlandi')
def siparis_tamamlandi():
    siparis = session.pop('son_siparis', None)
    if not siparis:
        return redirect(url_for('home'))
    return render_template('siparis_tamamlandi.html', siparis=siparis)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if request.form['username'] == ADMIN_USER and request.form['password'] == ADMIN_PASS:
            session['admin_girdi'] = True
            flash('Başarıyla giriş yapıldı!', 'success')
            return redirect(url_for('admin_dashboard'))
        flash('Hatalı kullanıcı adı veya şifre!', 'danger')
    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('admin_girdi', None)
    return redirect(url_for('home'))


@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_girdi'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    toplam_urun = conn.execute('SELECT COUNT(*) FROM urunler WHERE aktif=1').fetchone()[0]
    toplam_siparis = conn.execute('SELECT COUNT(*) FROM siparisler').fetchone()[0]
    bugun_siparis = conn.execute("SELECT COUNT(*) FROM siparisler WHERE DATE(tarih)=DATE('now')").fetchone()[0]
    toplam_gelir = conn.execute('SELECT COALESCE(SUM(toplam),0) FROM siparisler').fetchone()[0]
    bekleyen_yorum_sayi = conn.execute('SELECT COUNT(*) FROM yorumlar WHERE onayli_alisveris=0').fetchone()[0]
    bekleyen_yorumlar = conn.execute(
        'SELECT y.*, u.ad as urun_ad FROM yorumlar y LEFT JOIN urunler u ON y.urun_id=u.id WHERE y.onayli_alisveris=0 ORDER BY y.tarih DESC'
    ).fetchall()
    son_siparisler = conn.execute('SELECT * FROM siparisler ORDER BY tarih DESC LIMIT 5').fetchall()
    stok_az = conn.execute('SELECT * FROM urunler WHERE stok<=5 AND aktif=1').fetchall()
    conn.close()
    return render_template('admin_dashboard.html',
        toplam_urun=toplam_urun, toplam_siparis=toplam_siparis,
        bugun_siparis=bugun_siparis, toplam_gelir=toplam_gelir,
        bekleyen_yorum_sayi=bekleyen_yorum_sayi, bekleyen_yorumlar=bekleyen_yorumlar,
        son_siparisler=son_siparisler, stok_az=stok_az)


@app.route('/admin/ekle', methods=['GET', 'POST'])
def urun_ekle():
    if not session.get('admin_girdi'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    kategoriler = conn.execute('SELECT * FROM kategoriler ORDER BY sira').fetchall()
    if request.method == 'POST':
        ad = request.form['ad']
        fiyat = int(request.form.get('fiyat', 0) or 0)
        indirim_fiyat = int(request.form.get('indirim_fiyat', 0) or 0)
        mesaj = request.form.get('mesaj', '')
        aciklama = request.form.get('aciklama', '')
        kategori_id = request.form.get('kategori_id') or None
        stok = int(request.form.get('stok', 100) or 100)
        featured = 1 if request.form.get('featured') else 0
        file = request.files.get('resim_dosya')
        if file and file.filename and allowed_file(file.filename):
            fname = secure_filename(f"{int(time.time())}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
            resim = url_for('static', filename='uploads/' + fname)
        else:
            resim = request.form.get('resim', '')
        conn.execute(
            'INSERT INTO urunler (ad, fiyat, indirim_fiyat, resim, mesaj, aciklama, kategori_id, stok, featured) VALUES (?,?,?,?,?,?,?,?,?)',
            (ad, fiyat, indirim_fiyat, resim, mesaj, aciklama, kategori_id, stok, featured))
        conn.commit()
        conn.close()
        flash('Ürün başarıyla eklendi!', 'success')
        return redirect(url_for('urunler'))
    conn.close()
    return render_template('admin_ekle.html', kategoriler=kategoriler)


@app.route('/admin/sil/<int:id>')
def urun_sil(id):
    if not session.get('admin_girdi'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM yorumlar WHERE urun_id=?', (id,))
    conn.execute('DELETE FROM urunler WHERE id=?', (id,))
    conn.commit()
    conn.close()
    flash('Ürün silindi.', 'danger')
    return redirect(url_for('urunler'))


@app.route('/urun_guncelle/<int:id>', methods=['GET', 'POST'])
def urun_guncelle(id):
    if not session.get('admin_girdi'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    urun = conn.execute('SELECT * FROM urunler WHERE id=?', (id,)).fetchone()
    kategoriler = conn.execute('SELECT * FROM kategoriler ORDER BY sira').fetchall()
    if request.method == 'POST':
        ad = request.form['ad']
        fiyat = int(request.form.get('fiyat', 0) or 0)
        indirim_fiyat = int(request.form.get('indirim_fiyat', 0) or 0)
        aciklama = request.form.get('aciklama', '')
        mesaj = request.form.get('mesaj', '')
        kategori_id = request.form.get('kategori_id') or None
        stok = int(request.form.get('stok', 100) or 100)
        featured = 1 if request.form.get('featured') else 0
        aktif = 1 if request.form.get('aktif') else 0
        file = request.files.get('resim_dosya')
        if file and file.filename and allowed_file(file.filename):
            fname = secure_filename(f"{int(time.time())}_{file.filename}")
            file.save(os.path.join(app.config['UPLOAD_FOLDER'], fname))
            resim = url_for('static', filename='uploads/' + fname)
        else:
            resim = urun['resim']
        conn.execute(
            'UPDATE urunler SET ad=?, fiyat=?, indirim_fiyat=?, resim=?, aciklama=?, mesaj=?, kategori_id=?, stok=?, featured=?, aktif=? WHERE id=?',
            (ad, fiyat, indirim_fiyat, resim, aciklama, mesaj, kategori_id, stok, featured, aktif, id))
        conn.commit()
        conn.close()
        flash('Ürün güncellendi!', 'success')
        return redirect(url_for('urunler'))
    conn.close()
    return render_template('urun_guncelle.html', urun=urun, kategoriler=kategoriler)


@app.route('/admin/featured/<int:id>')
def toggle_featured(id):
    if not session.get('admin_girdi'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('UPDATE urunler SET featured=CASE WHEN featured=1 THEN 0 ELSE 1 END WHERE id=?', (id,))
    conn.commit()
    conn.close()
    flash('Öne çıkarma durumu güncellendi.', 'success')
    return redirect(request.referrer or url_for('urunler'))


@app.route('/admin/siparisler')
def admin_siparisler():
    if not session.get('admin_girdi'):
        return redirect(url_for('login'))
    durum_filtre = request.args.get('durum', '')
    conn = get_db_connection()
    if durum_filtre:
        siparisler = conn.execute('SELECT * FROM siparisler WHERE durum=? ORDER BY tarih DESC', (durum_filtre,)).fetchall()
    else:
        siparisler = conn.execute('SELECT * FROM siparisler ORDER BY tarih DESC').fetchall()
    conn.close()
    return render_template('admin_siparisler.html', siparisler=siparisler, durum_filtre=durum_filtre)


@app.route('/admin/siparis-durum/<int:id>', methods=['POST'])
def siparis_durum(id):
    if not session.get('admin_girdi'):
        return redirect(url_for('login'))
    durum = request.form.get('durum')
    conn = get_db_connection()
    conn.execute('UPDATE siparisler SET durum=? WHERE id=?', (durum, id))
    conn.commit()
    conn.close()
    flash(f'Sipariş #{id} → {durum}', 'success')
    return redirect(url_for('admin_siparisler'))


@app.route('/admin/kategoriler', methods=['GET', 'POST'])
def admin_kategoriler():
    if not session.get('admin_girdi'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    if request.method == 'POST':
        ad = request.form.get('ad', '').strip()
        ikon = request.form.get('ikon', '🌿').strip() or '🌿'
        if ad:
            sira = (conn.execute('SELECT COALESCE(MAX(sira),0) FROM kategoriler').fetchone()[0] or 0) + 1
            conn.execute('INSERT INTO kategoriler (ad, ikon, sira) VALUES (?,?,?)', (ad, ikon, sira))
            conn.commit()
            flash(f'"{ad}" kategorisi eklendi.', 'success')
    kategoriler = conn.execute(
        'SELECT k.*, COUNT(u.id) as urun_sayisi FROM kategoriler k LEFT JOIN urunler u ON k.id=u.kategori_id GROUP BY k.id ORDER BY k.sira'
    ).fetchall()
    conn.close()
    return render_template('admin_kategoriler.html', kategoriler=kategoriler)


@app.route('/admin/kategoriler/sil/<int:id>')
def kategori_sil(id):
    if not session.get('admin_girdi'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('UPDATE urunler SET kategori_id=NULL WHERE kategori_id=?', (id,))
    conn.execute('DELETE FROM kategoriler WHERE id=?', (id,))
    conn.commit()
    conn.close()
    flash('Kategori silindi.', 'danger')
    return redirect(url_for('admin_kategoriler'))


@app.route('/admin/yorum-onayla/<int:id>')
def yorum_onayla(id):
    if not session.get('admin_girdi'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('UPDATE yorumlar SET onayli_alisveris=1 WHERE id=?', (id,))
    conn.commit()
    conn.close()
    flash('Yorum onaylandı!', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/yorum-sil/<int:id>')
def yorum_sil(id):
    if not session.get('admin_girdi'):
        return redirect(url_for('login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM yorumlar WHERE id=?', (id,))
    conn.commit()
    conn.close()
    flash('Yorum silindi.', 'danger')
    return redirect(url_for('admin_dashboard'))


@app.route('/hakkimizda')
def hakkimizda():
    return render_template('hakkimizda.html')


@app.route('/iletisim')
def iletisim():
    return render_template('iletisim.html')


if __name__ == '__main__':
    app.run(debug=True, port=5001)

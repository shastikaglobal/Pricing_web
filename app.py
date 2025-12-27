import os
import psycopg2
from psycopg2.extras import DictCursor
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'shastika_manual_approval_key'

# -------------------- CONFIGURATION --------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

# Check if we are running on Render to use PostgreSQL (Persistent)
# Otherwise, use SQLite locally (Temporary)
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    if DATABASE_URL:
        # Connect to Render PostgreSQL
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    else:
        # Connect to local SQLite
        conn = sqlite3.connect('products.db')
        conn.row_factory = sqlite3.Row
        return conn

UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# -------------------- DATABASE INIT --------------------
def init_db():
    conn = get_db_connection()
    cur = conn.cursor()
    
    if DATABASE_URL:
        # POSTGRESQL VERSION
        cur.execute('''CREATE TABLE IF NOT EXISTS products 
                        (id SERIAL PRIMARY KEY, 
                         name TEXT, price TEXT, available TEXT, 
                         description TEXT, image TEXT, category TEXT, unit TEXT)''')
        
        cur.execute('''CREATE TABLE IF NOT EXISTS users 
                        (id SERIAL PRIMARY KEY, 
                         email TEXT UNIQUE, password TEXT, role TEXT, status TEXT)''')
        
        cur.execute('''CREATE TABLE IF NOT EXISTS login_logs 
                        (id SERIAL PRIMARY KEY, 
                         email TEXT, login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
        
        cur.execute("SELECT * FROM users WHERE email=%s", ('admin@test.com',))
        if not cur.fetchone():
            cur.execute("INSERT INTO users (email, password, role, status) VALUES (%s, %s, %s, %s)",
                         ('admin@test.com', generate_password_hash('admin123'), 'admin', 'active'))
    else:
        # SQLITE VERSION (Local)
        cur.execute('''CREATE TABLE IF NOT EXISTS products 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                         name TEXT, price TEXT, available TEXT, 
                         description TEXT, image TEXT, category TEXT, unit TEXT)''')
        
        cur.execute('''CREATE TABLE IF NOT EXISTS users 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                         email TEXT UNIQUE, password TEXT, role TEXT, status TEXT)''')
        
        cur.execute('''CREATE TABLE IF NOT EXISTS login_logs 
                        (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                         email TEXT, login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

        admin_check = cur.execute("SELECT * FROM users WHERE email='admin@test.com'").fetchone()
        if not admin_check:
            cur.execute("INSERT INTO users (email, password, role, status) VALUES (?, ?, ?, ?)",
                         ('admin@test.com', generate_password_hash('admin123'), 'admin', 'active'))
        
    conn.commit()
    cur.close()
    conn.close()

# -------------------- ROUTES --------------------

@app.route('/')
@app.route('/pricing')
def pricing():
    if 'user' not in session:
        return render_template('logingate.html')
    
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products")
    products = cur.fetchall()
    cur.close()
    conn.close()
    return render_template('pricing.html', products=products)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        pw = request.form.get('password')
        conn = get_db_connection()
        cur = conn.cursor()
        try:
            query = "INSERT INTO users (email, password, role, status) VALUES (%s, %s, %s, %s)" if DATABASE_URL else "INSERT INTO users (email, password, role, status) VALUES (?, ?, ?, ?)"
            cur.execute(query, (email, generate_password_hash(pw), 'customer', 'pending'))
            conn.commit()
            flash("Account pending admin approval.")
            return redirect(url_for('pricing'))
        except:
            flash("Email already registered.")
        finally:
            cur.close()
            conn.close()
    return render_template('register.html')

@app.route('/auth', methods=['POST'])
def auth():
    email = request.form.get('email')
    password = request.form.get('password')
    conn = get_db_connection()
    cur = conn.cursor()
    
    query = "SELECT password, role, status FROM users WHERE email=%s" if DATABASE_URL else "SELECT password, role, status FROM users WHERE email=?"
    cur.execute(query, (email,))
    user = cur.fetchone()
    
    if user and check_password_hash(user[0], password):
        if user[2] != 'active':
            flash("Your account is pending admin approval.")
            cur.close()
            conn.close()
            return redirect(url_for('pricing'))
            
        log_query = "INSERT INTO login_logs (email) VALUES (%s)" if DATABASE_URL else "INSERT INTO login_logs (email) VALUES (?)"
        cur.execute(log_query, (email,))
        conn.commit()
        session['user'] = email
        session['role'] = user[1]
        cur.close()
        conn.close()
        return redirect(url_for('admin' if user[1] == 'admin' else 'pricing'))
    
    cur.close()
    conn.close()
    flash("Invalid Credentials")
    return redirect(url_for('pricing'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if session.get('role') != 'admin':
        return redirect(url_for('pricing'))

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        name, price, unit = request.form.get('name'), request.form.get('price'), request.form.get('unit')
        avail, cat, desc = request.form.get('available'), request.form.get('category'), request.form.get('description')
        file = request.files.get('image')
        filename = secure_filename(file.filename) if file else ''
        if file: file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        
        insert_query = "INSERT INTO products (name,price,available,description,image,category,unit) VALUES (%s,%s,%s,%s,%s,%s,%s)" if DATABASE_URL else "INSERT INTO products (name,price,available,description,image,category,unit) VALUES (?,?,?,?,?,?,?)"
        cur.execute(insert_query, (name, price, avail, desc, filename, cat, unit))
        conn.commit()

    cur.execute("SELECT * FROM products")
    products = cur.fetchall()
    cur.execute("SELECT * FROM login_logs ORDER BY login_time DESC LIMIT 10")
    logs = cur.fetchall()
    cur.execute("SELECT id, email, role, status FROM users")
    users = cur.fetchall()
    
    cur.close()
    conn.close()
    return render_template('admin.html', products=products, logs=logs, users=users)

@app.route('/approve_user/<int:user_id>')
def approve_user(user_id):
    if session.get('role') == 'admin':
        conn = get_db_connection()
        cur = conn.cursor()
        query = "UPDATE users SET status='active' WHERE id=%s" if DATABASE_URL else "UPDATE users SET status='active' WHERE id=?"
        cur.execute(query, (user_id,))
        conn.commit()
        cur.close()
        conn.close()
    return redirect(url_for('admin'))

@app.route('/delete_user/<int:user_id>')
def delete_user(user_id):
    if session.get('role') == 'admin':
        conn = get_db_connection()
        cur = conn.cursor()
        query = "DELETE FROM users WHERE id=%s AND role != 'admin'" if DATABASE_URL else "DELETE FROM users WHERE id=? AND role != 'admin'"
        cur.execute(query, (user_id,))
        conn.commit()
        cur.close()
        conn.close()
    return redirect(url_for('admin'))

@app.route('/delete_product/<int:product_id>')
def delete_product(product_id):
    if session.get('role') == 'admin':
        conn = get_db_connection()
        cur = conn.cursor()
        query = "DELETE FROM products WHERE id=%s" if DATABASE_URL else "DELETE FROM products WHERE id=?"
        cur.execute(query, (product_id,))
        conn.commit()
        cur.close()
        conn.close()
    return redirect(url_for('admin'))

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_product(id):
    if session.get('role') != 'admin': 
        return redirect(url_for('pricing'))
    
    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        query = "UPDATE products SET name=%s, price=%s, unit=%s, available=%s, category=%s, description=%s WHERE id=%s" if DATABASE_URL else "UPDATE products SET name=?, price=?, unit=?, available=?, category=?, description=? WHERE id=?"
        cur.execute(query, (
            request.form.get('name'), request.form.get('price'), request.form.get('unit'), 
            request.form.get('available'), request.form.get('category'), request.form.get('description'), id
        ))
        conn.commit()
        cur.close()
        conn.close()
        return redirect(url_for('admin'))

    query = "SELECT * FROM products WHERE id=%s" if DATABASE_URL else "SELECT * FROM products WHERE id=?"
    cur.execute(query, (id,))
    product = cur.fetchone()
    cur.close()
    conn.close()
    return render_template('edit.html', p=product)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('pricing'))

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)




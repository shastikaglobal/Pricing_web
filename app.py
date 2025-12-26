import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'shastika_manual_approval_key'

# -------------------- CONFIGURATION --------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'static', 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# -------------------- DATABASE INIT --------------------
def init_db():
    conn = sqlite3.connect('products.db')
    # Create tables if they don't exist
    conn.execute('''CREATE TABLE IF NOT EXISTS products 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     name TEXT, price TEXT, available TEXT, 
                     description TEXT, image TEXT, category TEXT, unit TEXT)''')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS users 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     email TEXT UNIQUE, password TEXT, role TEXT, status TEXT)''')
    
    conn.execute('''CREATE TABLE IF NOT EXISTS login_logs 
                    (id INTEGER PRIMARY KEY AUTOINCREMENT, 
                     email TEXT, login_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')

    # Ensure Admin exists and is active
    admin_check = conn.execute("SELECT * FROM users WHERE email='admin@test.com'").fetchone()
    if not admin_check:
        conn.execute("INSERT INTO users (email, password, role, status) VALUES (?, ?, ?, ?)",
                     ('admin@test.com', generate_password_hash('admin123'), 'admin', 'active'))
    conn.commit()
    conn.close()

# -------------------- ROUTES --------------------
@app.route('/')
@app.route('/pricing')
def pricing():
    if 'user' not in session:
        return render_template('logingate.html')
    
    conn = sqlite3.connect('products.db')
    products = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    return render_template('pricing.html', products=products)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email = request.form.get('email')
        pw = request.form.get('password')
        conn = sqlite3.connect('products.db')
        try:
            conn.execute("INSERT INTO users (email, password, role, status) VALUES (?, ?, ?, ?)",
                         (email, generate_password_hash(pw), 'customer', 'pending'))
            conn.commit()
            flash("Account pending admin approval.")
            return redirect(url_for('pricing'))
        except:
            flash("Email already registered.")
        finally:
            conn.close()
    return render_template('register.html')

@app.route('/auth', methods=['POST'])
def auth():
    email = request.form.get('email')
    password = request.form.get('password')
    conn = sqlite3.connect('products.db')
    user = conn.execute("SELECT password, role, status FROM users WHERE email=?", (email,)).fetchone()
    
    if user and check_password_hash(user[0], password):
        if user[2] != 'active':
            flash("Your account is pending admin approval.")
            conn.close()
            return redirect(url_for('pricing'))
            
        conn.execute("INSERT INTO login_logs (email) VALUES (?)", (email,))
        conn.commit()
        session['user'] = email
        session['role'] = user[1]
        conn.close()
        return redirect(url_for('admin' if user[1] == 'admin' else 'pricing'))
    
    conn.close()
    flash("Invalid Credentials")
    return redirect(url_for('pricing'))

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if session.get('role') != 'admin':
        return redirect(url_for('pricing'))

    conn = sqlite3.connect('products.db')
    if request.method == 'POST':
        name, price, unit = request.form.get('name'), request.form.get('price'), request.form.get('unit')
        avail, cat, desc = request.form.get('available'), request.form.get('category'), request.form.get('description')
        file = request.files.get('image')
        filename = secure_filename(file.filename) if file else ''
        if file: file.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))
        conn.execute("INSERT INTO products (name,price,available,description,image,category,unit) VALUES (?,?,?,?,?,?,?)",
                     (name, price, avail, desc, filename, cat, unit))
        conn.commit()

    products = conn.execute("SELECT * FROM products").fetchall()
    logs = conn.execute("SELECT * FROM login_logs ORDER BY login_time DESC LIMIT 10").fetchall()
    users = conn.execute("SELECT id, email, role, status FROM users").fetchall()
    conn.close()
    return render_template('admin.html', products=products, logs=logs, users=users)

@app.route('/approve_user/<int:user_id>')
def approve_user(user_id):
    if session.get('role') == 'admin':
        conn = sqlite3.connect('products.db')
        conn.execute("UPDATE users SET status='active' WHERE id=?", (user_id,))
        conn.commit()
        conn.close()
    return redirect(url_for('admin'))

@app.route('/delete_user/<int:user_id>')
def delete_user(user_id):
    if session.get('role') == 'admin':
        conn = sqlite3.connect('products.db')
        conn.execute("DELETE FROM users WHERE id=? AND role != 'admin'", (user_id,))
        conn.commit()
        conn.close()
    return redirect(url_for('admin'))

# NEW: Product Deletion Route
@app.route('/delete_product/<int:product_id>')
def delete_product(product_id):
    if session.get('role') == 'admin':
        conn = sqlite3.connect('products.db')
        conn.execute("DELETE FROM products WHERE id=?", (product_id,))
        conn.commit()
        conn.close()
    return redirect(url_for('admin'))

@app.route('/edit/<int:id>', methods=['GET', 'POST'])
def edit_product(id):
    if session.get('role') != 'admin': return redirect(url_for('pricing'))
    conn = sqlite3.connect('products.db')
    if request.method == 'POST':
        conn.execute("UPDATE products SET name=?, price=?, unit=?, available=?, category=?, description=? WHERE id=?",
                     (request.form.get('name'), request.form.get('price'), request.form.get('unit'), 
                      request.form.get('available'), request.form.get('category'), request.form.get('description'), id))
        conn.commit()
        conn.close()
        return redirect(url_for('admin'))
    product = conn.execute("SELECT * FROM products WHERE id=?", (id,)).fetchone()
    conn.close()
    return render_template('edit.html', p=product)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('pricing'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'valley_talley_secret_key'

# Database initialization
def init_db():
    conn = sqlite3.connect('valley_talley.db')
    c = conn.cursor()
    
    # Create users table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password TEXT NOT NULL,
                    valley_talley INTEGER DEFAULT 100,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )''')
    
    # Create items table
    c.execute('''CREATE TABLE IF NOT EXISTS items (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    name TEXT NOT NULL,
                    description TEXT,
                    category TEXT,
                    image_url TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )''')
    
    # Create trades table
    c.execute('''CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    item1_id INTEGER,
                    item2_id INTEGER,
                    valley_talley_amount INTEGER,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    completed_at TIMESTAMP,
                    FOREIGN KEY (item1_id) REFERENCES items (id),
                    FOREIGN KEY (item2_id) REFERENCES items (id)
                )''')
    
    conn.commit()
    conn.close()

# Helper functions
def get_db_connection():
    conn = sqlite3.connect('valley_talley.db')
    conn.row_factory = sqlite3.Row
    return conn

def get_user_talley(user_id):
    conn = get_db_connection()
    user = conn.execute('SELECT valley_talley FROM users WHERE id = ?', (user_id,)).fetchone()
    conn.close()
    return user['valley_talley'] if user else 0

def update_user_talley(user_id, amount):
    conn = get_db_connection()
    conn.execute('UPDATE users SET valley_talley = valley_talley + ? WHERE id = ?', (amount, user_id))
    conn.commit()
    conn.close()

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        try:
            conn.execute('INSERT INTO users (username, password, valley_talley) VALUES (?, ?, 100)',
                         (username, password))
            conn.commit()
            flash('Registration successful! You received 100 Valley Talley coins.', 'success')
            return redirect(url_for('login'))
        except sqlite3.IntegrityError:
            flash('Username already exists!', 'error')
        finally:
            conn.close()
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE username = ? AND password = ?',
                           (username, password)).fetchone()
        conn.close()
        
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            flash('Login successful!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid credentials!', 'error')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('index'))

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    user_id = session['user_id']
    conn = get_db_connection()
    
    # Get user info
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    
    # Get user items
    items = conn.execute('SELECT * FROM items WHERE user_id = ?', (user_id,)).fetchall()
    
    # Get pending trades
    pending_trades = conn.execute('''
        SELECT t.*, i1.name as item1_name, i2.name as item2_name, 
               u1.username as user1_name, u2.username as user2_name
        FROM trades t
        JOIN items i1 ON t.item1_id = i1.id
        JOIN items i2 ON t.item2_id = i2.id
        JOIN users u1 ON i1.user_id = u1.id
        JOIN users u2 ON i2.user_id = u2.id
        WHERE (i1.user_id = ? OR i2.user_id = ?) AND t.status = 'pending'
    ''', (user_id, user_id)).fetchall()
    
    # Get all items for trading
    all_items = conn.execute('''
        SELECT i.*, u.username as owner_name
        FROM items i
        JOIN users u ON i.user_id = u.id
        WHERE i.user_id != ?
    ''', (user_id,)).fetchall()
    
    conn.close()
    
    return render_template('dashboard.html', user=user, items=items, 
                          pending_trades=pending_trades, all_items=all_items)

@app.route('/add_item', methods=['POST'])
def add_item():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    name = request.form['name']
    description = request.form['description']
    category = request.form['category']
    image_url = request.form.get('image_url', '')
    
    conn = get_db_connection()
    conn.execute('INSERT INTO items (user_id, name, description, category, image_url) VALUES (?, ?, ?, ?, ?)',
                 (session['user_id'], name, description, category, image_url))
    conn.commit()
    conn.close()
    
    flash('Item added successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/propose_trade', methods=['POST'])
def propose_trade():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    item1_id = request.form['item1_id']
    item2_id = request.form['item2_id']
    valley_talley_amount = int(request.form.get('valley_talley', 0))
    
    conn = get_db_connection()
    
    # Verify items exist and belong to correct users
    item1 = conn.execute('SELECT * FROM items WHERE id = ?', (item1_id,)).fetchone()
    item2 = conn.execute('SELECT * FROM items WHERE id = ?', (item2_id,)).fetchone()
    
    if not item1 or not item2:
        flash('Invalid items selected!', 'error')
        return redirect(url_for('dashboard'))
    
    # Check if user has enough Valley Talley if needed
    if valley_talley_amount > 0:
        user_talley = get_user_talley(session['user_id'])
        if user_talley < valley_talley_amount:
            flash('Not enough Valley Talley coins!', 'error')
            return redirect(url_for('dashboard'))
    
    # Create trade
    conn.execute('INSERT INTO trades (item1_id, item2_id, valley_talley_amount) VALUES (?, ?, ?)',
                 (item1_id, item2_id, valley_talley_amount))
    conn.commit()
    conn.close()
    
    flash('Trade proposed successfully!', 'success')
    return redirect(url_for('dashboard'))

@app.route('/respond_trade/<int:trade_id>/<action>')
def respond_trade(trade_id, action):
    if 'user_id' not in session:
        return redirect(url_for('login'))
    
    conn = get_db_connection()
    trade = conn.execute('SELECT * FROM trades WHERE id = ?', (trade_id,)).fetchone()
    
    if not trade:
        flash('Trade not found!', 'error')
        return redirect(url_for('dashboard'))
    
    # Verify user is involved in the trade
    item1 = conn.execute('SELECT * FROM items WHERE id = ?', (trade['item1_id'],)).fetchone()
    item2 = conn.execute('SELECT * FROM items WHERE id = ?', (trade['item2_id'],)).fetchone()
    
    if item1['user_id'] != session['user_id'] and item2['user_id'] != session['user_id']:
        flash('You are not authorized to respond to this trade!', 'error')
        return redirect(url_for('dashboard'))
    
    if action == 'accept':
        # Complete the trade
        conn.execute('UPDATE trades SET status = "completed", completed_at = ? WHERE id = ?',
                     (datetime.now(), trade_id))
        
        # Transfer items
        conn.execute('UPDATE items SET user_id = ? WHERE id = ?', 
                     (item2['user_id'], item1['id']))
        conn.execute('UPDATE items SET user_id = ? WHERE id = ?', 
                     (item1['user_id'], item2['id']))
        
        # Transfer Valley Talley if applicable
        if trade['valley_talley_amount'] > 0:
            # Deduct from proposer
            update_user_talley(item1['user_id'], -trade['valley_talley_amount'])
            # Add to acceptor
            update_user_talley(item2['user_id'], trade['valley_talley_amount'])
        
        # Award bonus Valley Talley to both parties
        update_user_talley(item1['user_id'], 10)
        update_user_talley(item2['user_id'], 10)
        
        flash('Trade completed successfully! Both parties received 10 Valley Talley coins.', 'success')
    elif action == 'reject':
        conn.execute('UPDATE trades SET status = "rejected" WHERE id = ?', (trade_id,))
        flash('Trade rejected.', 'info')
    
    conn.commit()
    conn.close()
    
    return redirect(url_for('dashboard'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)

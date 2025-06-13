import os
import json
import time
import requests
from flask import Flask, render_template, redirect, url_for

# Read options from add-on config
PORT = int(os.getenv('PORT', 80))
GROCY_URL = os.getenv('ADDON_OPTIONS', '') and json.loads(os.getenv('ADDON_OPTIONS')).get('grocy_url') or 'http://grocy:9283'
GROCY_API_KEY = os.getenv('ADDON_OPTIONS', '') and json.loads(os.getenv('ADDON_OPTIONS')).get('grocy_api_key') or ''

app = Flask(__name__, template_folder="/var/www/templates", static_folder="/var/www/static")
HEADERS = { 'Content-Type': 'application/json', 'GROCY-API-KEY': GROCY_API_KEY }

@app.route('/')
def index():
    return render_template('home.html', products=[])

@app.route('/import')
def import_data():
    # Fetch Grocy shopping list entries
    url = f"{GROCY_URL}/api/stock/shopping_list"
    r = requests.get(url, headers=HEADERS)
    items = r.json()

    products = []
    for item in items:
        qty = item.get('amount', 0)
        # Grocy returns product_id; fetch product name
        prod = requests.get(f"{GROCY_URL}/api/objects/products/{item['product_id']}", headers=HEADERS).json()
        products.append([qty, prod.get('qu_id_purchase_unit', ''), prod.get('name', '')])

    return render_template('home.html', products=products)

@app.route('/delete_data')
def delete_data():
    # Delete all shopping list entries
    url = f"{GROCY_URL}/api/stock/shopping_list"
    items = requests.get(url, headers=HEADERS).json()
    for item in items:
        requests.delete(f"{GROCY_URL}/api/stock/shopping_list/{item['id']}", headers=HEADERS)
    time.sleep(1)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=9007, debug=False)

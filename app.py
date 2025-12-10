from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_cors import CORS
import pandas as pd
import os
from datetime import datetime

app = Flask(__name__, static_folder='static', template_folder='templates')
CORS(app)

DATA_FILE = "customers.xlsx"

# Initialize with sample data if file doesn't exist
if not os.path.exists(DATA_FILE):
    sample_data = pd.DataFrame([
        {
            'CustomerName': 'John Doe', 'CustomerType': 'Regular', 'Product': 'Laptop',
            'Quantity': 2, 'Region': 'North', 'Date': '2024-01-15', 'UnitPrice': 1200,
            'StoreLocation': 'Store A', 'Discount': 10, 'Salesperson': 'Alice',
            'TotalPrice': 2160, 'PaymentMethod': 'Credit Card', 'Promotion': 'Yes',
            'Returned': 0, 'OrderID': 'ORD001', 'ShippingCost': 50,
            'OrderDate': '2024-01-15', 'DeliveryDate': '2024-01-20', 'RegionManager': 'Bob'
        },
        {
            'CustomerName': 'Jane Smith', 'CustomerType': 'Premium', 'Product': 'Phone',
            'Quantity': 1, 'Region': 'South', 'Date': '2024-01-16', 'UnitPrice': 800,
            'StoreLocation': 'Store B', 'Discount': 5, 'Salesperson': 'Charlie',
            'TotalPrice': 760, 'PaymentMethod': 'Cash', 'Promotion': 'No',
            'Returned': 0, 'OrderID': 'ORD002', 'ShippingCost': 30,
            'OrderDate': '2024-01-16', 'DeliveryDate': '2024-01-21', 'RegionManager': 'Diana'
        }
    ])
    sample_data.to_excel(DATA_FILE, index=False)

def read_excel():
    return pd.read_excel(DATA_FILE)

def write_excel(df):
    df.to_excel(DATA_FILE, index=False)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/customers', methods=['GET'])
def get_customers():
    df = read_excel()
    return jsonify(df.to_dict('records'))

@app.route('/api/customers', methods=['POST'])
def add_customer():
    data = request.json
    df = read_excel()
    new_row = pd.DataFrame([data])
    df = pd.concat([df, new_row], ignore_index=True)
    write_excel(df)
    return jsonify({'message': 'Customer added successfully'}), 201

@app.route('/api/customers/<customer_name>', methods=['PUT'])
def update_customer(customer_name):
    data = request.json
    df = read_excel()
    df.loc[df['CustomerName'] == customer_name, list(data.keys())] = list(data.values())
    write_excel(df)
    return jsonify({'message': 'Customer updated successfully'})

@app.route('/api/customers/<customer_name>', methods=['DELETE'])
def delete_customer(customer_name):
    df = read_excel()
    df = df[df['CustomerName'] != customer_name]
    write_excel(df)
    return jsonify({'message': 'Customer deleted successfully'})

@app.route('/api/analytics/region/<region>', methods=['GET'])
def region_sales(region):
    df = read_excel()
    filtered = df[df['Region'] == region]
    summary = filtered.groupby('Product')['TotalPrice'].sum().to_dict()
    return jsonify(summary)

@app.route('/api/analytics/store/<store>', methods=['GET'])
def store_sales(store):
    df = read_excel()
    filtered = df[df['StoreLocation'] == store]
    summary = filtered.groupby('Product')['TotalPrice'].sum().to_dict()
    return jsonify(summary)

@app.route('/api/analytics/salesperson/<person>', methods=['GET'])
def salesperson_sales(person):
    df = read_excel()
    filtered = df[df['Salesperson'] == person]
    summary = filtered.groupby('Product')['TotalPrice'].sum().to_dict()
    return jsonify(summary)

@app.route('/api/analytics/dashboard', methods=['GET'])
def dashboard():
    df = read_excel()
    return jsonify({
        'totalSales': float(df['TotalPrice'].sum()),
        'totalCustomers': int(df['CustomerName'].nunique()),
        'totalOrders': len(df),
        'avgOrderValue': float(df['TotalPrice'].mean())
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)

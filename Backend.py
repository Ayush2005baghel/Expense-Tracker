from http.server import HTTPServer, BaseHTTPRequestHandler
import sqlite3
import json
import csv
import io
import os
from urllib.parse import urlparse, parse_qs

def init_db():
    conn = sqlite3.connect("expenses.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            category TEXT NOT NULL,
            description TEXT,
            amount REAL NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            monthly_salary REAL NOT NULL DEFAULT 0
        )
    """)
    # Insert default salary if not exists
    cursor.execute("SELECT COUNT(*) as count FROM settings")
    if cursor.fetchone()['count'] == 0:
        cursor.execute("INSERT INTO settings (monthly_salary) VALUES (0)")
    conn.commit()
    conn.close()

def get_db():
    conn = sqlite3.connect("expenses.db")
    conn.row_factory = sqlite3.Row
    return conn

class ExpenseHandler(BaseHTTPRequestHandler):

    def _send_response(self, status=200, content_type='application/json', body=''):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        if isinstance(body, str):
            self.wfile.write(body.encode('utf-8'))
        else:
            self.wfile.write(body)

    def _get_body(self):
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length > 0:
            body = self.rfile.read(content_length)
            return json.loads(body.decode('utf-8'))
        return {}

    def do_OPTIONS(self):
        self._send_response(204)

    def do_GET(self):
        parsed_path = urlparse(self.path)
        path = parsed_path.path

        # Serve front-end
        if path == '/':
            if not os.path.exists('index.html'):
                self._send_response(404, 'text/html', 'ERROR: index.html not found!')
                return
            with open('index.html', 'r', encoding='utf-8') as f:
                self._send_response(200, 'text/html', f.read())
            return

        # Get all expenses
        if path == '/api/expenses':
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM expenses ORDER BY date DESC")
            rows = cursor.fetchall()
            conn.close()
            expenses = [dict(row) for row in rows]
            self._send_response(200, 'application/json', json.dumps(expenses))
            return

        # Get salary and calculate remaining/savings
        if path == '/api/salary':
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT monthly_salary FROM settings WHERE id = 1")
            row = cursor.fetchone()
            salary = row['monthly_salary'] if row else 0
            
            # Calculate total expenses
            cursor.execute("SELECT SUM(amount) as total FROM expenses")
            total_row = cursor.fetchone()
            total_expenses = total_row['total'] if total_row['total'] else 0
            
            # Calculate monthly savings
            cursor.execute("""
                SELECT substr(date, 1, 7) AS month, SUM(amount) as total
                FROM expenses
                GROUP BY month
                ORDER BY month DESC
            """)
            monthly_data = cursor.fetchall()
            monthly_savings = [{'month': r['month'], 'savings': salary - r['total']} for r in monthly_data]
            
            conn.close()
            self._send_response(200, 'application/json', json.dumps({
                'salary': salary,
                'total_expenses': total_expenses,
                'remaining': salary - total_expenses,
                'monthly_savings': monthly_savings
            }))
            return

        # Category summary
        if path == '/api/summary/category':
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT category, SUM(amount) as total FROM expenses GROUP BY category ORDER BY total DESC")
            rows = cursor.fetchall()
            conn.close()
            summary = [{'category': r['category'], 'total': r['total']} for r in rows]
            self._send_response(200, 'application/json', json.dumps(summary))
            return

        # Monthly summary
        if path == '/api/summary/monthly':
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT substr(date, 1, 7) AS month, SUM(amount) as total
                FROM expenses
                GROUP BY month
                ORDER BY month
            """)
            rows = cursor.fetchall()
            conn.close()
            summary = [{'month': r['month'], 'total': r['total']} for r in rows]
            self._send_response(200, 'application/json', json.dumps(summary))
            return

        if path == '/api/summary/category/animated':
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT category, SUM(amount) as total 
                FROM expenses 
                GROUP BY category 
                ORDER BY total DESC 
                LIMIT 5
            """)
            rows = cursor.fetchall()
            conn.close()
            summary = [{'category': r['category'], 'total': r['total']} for r in rows]
            self._send_response(200, 'application/json', json.dumps(summary))
            return

        if path == '/api/summary/monthly/animated':
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT substr(date, 1, 7) AS month, SUM(amount) as total
                FROM expenses
                GROUP BY month
                ORDER BY month
            """)
            rows = cursor.fetchall()
            conn.close()
            summary = [{'month': r['month'], 'total': r['total']} for r in rows]
            self._send_response(200, 'application/json', json.dumps(summary))
            return

        # Export CSV
        if path == '/api/export/csv':
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM expenses ORDER BY date DESC")
            rows = cursor.fetchall()
            conn.close()

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(['ID', 'Date', 'Category', 'Description', 'Amount'])
            for row in rows:
                writer.writerow([row['id'], row['date'], row['category'], row['description'], row['amount']])

            csv_content = output.getvalue()
            self.send_response(200)
            self.send_header('Content-Type', 'text/csv')
            self.send_header('Content-Disposition', 'attachment; filename=expenses_export.csv')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(csv_content.encode('utf-8'))
            return

        # Not found
        self._send_response(404, 'application/json', json.dumps({'error': 'Not found'}))

    def do_POST(self):
        if self.path == '/api/expenses':
            try:
                data = self._get_body()
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO expenses (date, category, description, amount)
                    VALUES (?, ?, ?, ?)
                """, (data['date'], data['category'], data.get('description', ''), data['amount']))
                conn.commit()
                new_id = cursor.lastrowid
                conn.close()
                self._send_response(201, 'application/json', json.dumps({'id': new_id, 'message': 'Expense added'}))
            except Exception as e:
                self._send_response(400, 'application/json', json.dumps({'error': str(e)}))
            return
        
        if self.path == '/api/salary':
            try:
                data = self._get_body()
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("UPDATE settings SET monthly_salary = ? WHERE id = 1", (data['salary'],))
                conn.commit()
                conn.close()
                self._send_response(200, 'application/json', json.dumps({'message': 'Salary updated'}))
            except Exception as e:
                self._send_response(400, 'application/json', json.dumps({'error': str(e)}))
            return
            
        self._send_response(404, 'application/json', json.dumps({'error': 'Not found'}))

    def do_PUT(self):
        if self.path.startswith('/api/expenses/'):
            try:
                expense_id = int(self.path.split('/')[-1])
                data = self._get_body()
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE expenses
                    SET date=?, category=?, description=?, amount=?
                    WHERE id=?
                """, (data['date'], data['category'], data.get('description', ''), data['amount'], expense_id))
                conn.commit()
                conn.close()
                self._send_response(200, 'application/json', json.dumps({'message': 'Expense updated'}))
            except Exception as e:
                self._send_response(400, 'application/json', json.dumps({'error': str(e)}))
            return
        self._send_response(404, 'application/json', json.dumps({'error': 'Not found'}))

    def do_DELETE(self):
        if self.path.startswith('/api/expenses/'):
            try:
                expense_id = int(self.path.split('/')[-1])
                conn = get_db()
                cursor = conn.cursor()
                cursor.execute("DELETE FROM expenses WHERE id=?", (expense_id,))
                conn.commit()
                conn.close()
                self._send_response(200, 'application/json', json.dumps({'message': 'Expense deleted'}))
            except Exception as e:
                self._send_response(400, 'application/json', json.dumps({'error': str(e)}))
            return
        self._send_response(404, 'application/json', json.dumps({'error': 'Not found'}))

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {format % args}")

if __name__ == '__main__':
    init_db()
    print("🚀 Server running on http://localhost:5000")
    server = HTTPServer(('localhost', 5000), ExpenseHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n🛑 Server stopped.")
        server.shutdown()
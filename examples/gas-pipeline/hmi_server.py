#!/usr/bin/env python3

"""
Gas Pipeline HMI — Web Server

Run this OUTSIDE Mininet (in a separate terminal) to serve the dashboard:

    cd examples/gas-pipeline
    python3 hmi_server.py

Then open http://localhost:8080 in your browser.

The server provides:
    - GET /           → serves hmi.html (the dashboard)
    - GET /api/status → returns JSON with both physical (SQLite) and network (ENIP) data
"""

import http.server
import json
import sqlite3
import os
import time

PORT = 8080
DB_PATH = 'gas_pipeline_db.sqlite'
ENIP_DATA_PATH = 'logs/hmi_data.json'


class HMIHandler(http.server.SimpleHTTPRequestHandler):

    def do_GET(self):
        if self.path == '/api/status':
            self._serve_api()
        elif self.path == '/' or self.path == '/index.html':
            self.path = '/hmi.html'
            return super().do_GET()
        else:
            return super().do_GET()

    def _serve_api(self):
        """Return combined physical + network state as JSON."""
        self.send_response(200)
        self.send_header('Content-type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-cache')
        self.end_headers()

        data = {
            'physical': self._read_sqlite(),
            'network': self._read_enip_json(),
            'server_time': time.time()
        }

        self.wfile.write(json.dumps(data).encode())

    def _read_sqlite(self):
        """Read physical state from the SQLite database."""
        try:
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            cursor.execute('SELECT name, pid, value FROM gas_pipeline')
            rows = cursor.fetchall()
            conn.close()

            result = {}
            for name, pid, value in rows:
                try:
                    result[name] = float(value) if value else 0.0
                except (ValueError, TypeError):
                    result[name] = 0.0
            return result
        except Exception as e:
            return {'error': str(e)}

    def _read_enip_json(self):
        """Read ENIP network state from the JSON file written by hmi_poller.py."""
        try:
            if os.path.exists(ENIP_DATA_PATH):
                mtime = os.path.getmtime(ENIP_DATA_PATH)
                age = time.time() - mtime
                with open(ENIP_DATA_PATH, 'r') as f:
                    data = json.load(f)
                data['_age_seconds'] = round(age, 1)
                return data
            return {'error': 'No ENIP data file found. Is hmi_poller running in Mininet?'}
        except Exception as e:
            return {'error': str(e)}

    def log_message(self, format, *args):
        """Suppress default HTTP request logging to keep terminal clean."""
        pass


if __name__ == '__main__':
    os.chdir(os.path.dirname(os.path.abspath(__file__)) or '.')
    server = http.server.HTTPServer(('0.0.0.0', PORT), HMIHandler)
    print('=' * 60)
    print('  Gas Pipeline HMI Server')
    print('  Dashboard: http://localhost:%d' % PORT)
    print('  API:       http://localhost:%d/api/status' % PORT)
    print('=' * 60)
    print('Press Ctrl+C to stop.')
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nShutting down HMI server.')
        server.shutdown()

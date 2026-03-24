import urllib.request
import json

req = urllib.request.Request(
    'http://127.0.0.1:8000/api/v1/schema-mapping/scan',
    headers={'Content-Type': 'application/json'},
    data=json.dumps({"event_id": 1, "limit": 500}).encode('utf-8'),
    method='POST'
)
try:
    with urllib.request.urlopen(req) as response:
        print("Success:", response.read().decode())
except urllib.error.HTTPError as e:
    print(f"HTTPError: {e.code} - {e.read().decode()}")
except Exception as e:
    print("Error:", e)

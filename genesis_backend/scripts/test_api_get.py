import urllib.request
import json
import urllib.parse

# 1. Login
data = urllib.parse.urlencode({'username': 'admin@demo.local', 'password': 'admin123', 'grant_type': 'password'}).encode()
req = urllib.request.Request('http://localhost:8000/api/v1/auth/login', data=data)
try:
    with urllib.request.urlopen(req) as response:
        resp = json.loads(response.read().decode())
        token = resp['access_token']
        print('Token achieved')
        
        # 2. Get proposals
        req2 = urllib.request.Request('http://localhost:8000/api/v1/schema-mapping/proposals?event_id=1&limit=50', headers={'Authorization': f'Bearer {token}'})
        with urllib.request.urlopen(req2) as res2:
            print('Proposals:', res2.read().decode())
except Exception as e:
    print('Error:', getattr(e, 'read', lambda: str(e))())

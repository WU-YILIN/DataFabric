import httpx
import asyncio

async def main():
    async with httpx.AsyncClient(base_url='http://localhost:8000') as client:
        # Use form data, not json payload, for OAuth2 parameters
        resp = await client.post('/api/v1/auth/login', data={'username': 'admin@demo.local', 'password': 'admin123'})
        if resp.status_code != 200:
            print("Login failed:", resp.status_code, resp.text)
            return
        
        token = resp.json()['access_token']
        headers = {'Authorization': f'Bearer {token}'}
        
        # Test GET /proposals
        res1 = await client.get('/api/v1/schema-mapping/proposals?limit=50&event_id=1', headers=headers)
        print("Proposals Output:", res1.status_code, res1.text)

if __name__ == '__main__':
    asyncio.run(main())

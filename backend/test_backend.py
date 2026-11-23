from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

print('=== COMPREHENSIVE BACKEND TEST ===')

# Health
r = client.get('/api/health')
h = r.json()
print(f'1. GET /api/health: {r.status_code} - {h.get("status")}')

# Dashboard
r = client.get('/api/dashboard')
data = r.json()
print(f'2. GET /api/dashboard: {r.status_code} - keys: {list(data.keys())[:5]}')

# Plants
r = client.get('/api/plants')
plants = r.json()
print(f'3. GET /api/plants: {r.status_code} - {len(plants)} plant(s)')

pid = plants[0]['id'] if plants else 1

# Plant detail
r = client.get(f'/api/plants/{pid}')
p = r.json()
print(f'4. GET /api/plants/{pid}: {r.status_code}')
ana_count = len(p.get("analyses", []))
rep_count = len(p.get("reports", []))
print(f'   analyses={ana_count}, reports={rep_count}')

# Reports
r = client.get(f'/api/reports?plant_id={pid}')
reps = r.json()
print(f'5. GET /api/reports?plant_id={pid}: {r.status_code} - {len(reps)} report(s)')
if reps:
    rep0 = reps[0]
    rid = rep0['id']
    aid = rep0.get('analysis_id')
    durl = rep0.get('download_url')
    print(f'   Report #{rid}: analysis_id={aid}, download_url={durl}')

    # Download PDF
    r2 = client.get(durl)
    print(f'6. GET {durl}: {r2.status_code} - {len(r2.content)} bytes')

# Knowledge
r = client.get('/api/knowledge')
entries = r.json()
print(f'7. GET /api/knowledge: {r.status_code} - {len(entries)} entries')

r = client.get('/api/knowledge?query=root+rot')
print(f'8. GET ?query=root+rot: {r.status_code} - {len(r.json())} entries')

# Devices
r = client.get('/api/devices')
devs = r.json()
st = devs[0]['status'] if devs else 'N/A'
print(f'9. GET /api/devices: {r.status_code} - {len(devs)} devices, status={st}')

# Chat
payload = {'message': 'Is my plant healthy?', 'plant_id': pid}
r = client.post('/api/chat', json=payload)
print(f'10. POST /api/chat: {r.status_code}')
if r.status_code == 200:
    reply = r.json().get('reply', '')
    print(f'    Reply: {reply[:100]}...')

# Analyses
r = client.get('/api/analyses')
print(f'11. GET /api/analyses: {r.status_code} - {len(r.json())} analyses')

# Settings
r = client.get('/api/settings')
s = r.json()
diag = s.get("diagnosis_configured")
chat = s.get("chat_configured")
print(f'12. GET /api/settings: {r.status_code} - diagnosis={diag}, chat={chat}')

# Conversations
r = client.get('/api/conversations')
print(f'13. GET /api/conversations: {r.status_code} - {len(r.json())} conversations')

print()
print('=== ALL ENDPOINT TESTS COMPLETE ===')

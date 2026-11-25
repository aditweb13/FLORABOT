"""Test ESP32-CAM upload pipeline with a real JPEG image."""
from fastapi.testclient import TestClient
from app.main import app
import io, pathlib

client = TestClient(app)

print('=== ESP32-CAM PIPELINE TEST (Real JPEG) ===')

# 1. Register a new test plant
r = client.post('/api/plants', data={
    'name': 'Test Peace Lily',
    'species': 'Spathiphyllum',
    'category': 'Houseplant',
    'location': 'Office',
    'pot_size_cm': '15',
    'soil_type': 'Peat Mix',
    'watering_frequency_days': '7'
})
print(f'1. POST /api/plants: {r.status_code}')
if r.status_code != 200:
    print(f'   Error: {r.text}')
    exit(1)
plant = r.json()
pid = plant['id']
print(f'   Created: {plant["name"]} (id={pid})')

# 2. Load a real JPEG already stored by FloraBOT (the previous hard-coded
# fixture was no longer present in the development upload directory).
img_path = pathlib.Path('data/uploads/d15967fc05814732ab48e3c70932bddf.jpg')
if not img_path.exists():
    img_path = next(pathlib.Path('data/uploads').glob('*.jpg'), None)
if img_path is None:
    raise SystemExit('No existing JPEG capture is available for the pipeline test.')
else:
    jpeg_bytes = img_path.read_bytes()
    print(f'2. Testing automatic discovery without plant_id using {len(jpeg_bytes):,} byte JPEG...')
    r = client.post('/api/camera/upload',
        files={'image': ('plant.jpg', io.BytesIO(jpeg_bytes), 'image/jpeg')},
        data={'device_id': 'esp32-cam-01'}
    )
    print(f'   Status: {r.status_code}')
    if r.status_code != 200:
        raise AssertionError(f'Plantless camera upload failed: {r.text[:500]}')
    if r.status_code == 200:
        cam = r.json()
        print(f'   Result: status={cam.get("status")}, analysis_id={cam.get("analysis_id")}')
        print(f'   Health: {cam.get("health_status")}, Provider: {cam.get("provider")}')
        aid = cam.get('analysis_id')
        assert cam.get('plant_id'), 'Automatic discovery did not return a plant record.'
        analysis = client.get(f'/api/analyses/{aid}').json()
        assert isinstance(analysis.get('detections'), list)
        assert not analysis['detections'], 'Local detector results should no longer be produced.'
        print('   Verified analysis uses hosted providers without local model detections.')
    else:
        print(f'   Error: {r.text[:300]}')
        aid = None

    # 3. Test device endpoint (raw JPEG, like actual ESP32-CAM firmware POSTs)
    print(f'3. Testing /api/devices/esp32-cam-01/images (raw JPEG POST)...')
    r2 = client.post('/api/devices/esp32-cam-01/images',
        content=jpeg_bytes,
        headers={'Content-Type': 'image/jpeg', 'X-Plant-Id': str(pid)}
    )
    print(f'   Status: {r2.status_code}')
    assert r2.status_code == 200, f'Raw camera image failed: {r2.text[:500]}'
    if r2.status_code == 200:
        r2d = r2.json()
        print(f'   Result: {r2d.get("status")}, analysis_id={r2d.get("analysis_id")}')

# 4. Verify reports
r = client.get(f'/api/reports?plant_id={pid}')
reps = r.json()
print(f'4. Reports for plant {pid}: {len(reps)} report(s)')
for rep in reps:
    rid = rep['id']
    r3 = client.get(rep['download_url'])
    print(f'   Report #{rid}: {r3.status_code}, {len(r3.content):,} bytes PDF')

# 5. Test /api/plants/{id}/analyze
print(f'5. Testing /api/plants/{pid}/analyze (manual trigger)...')
r = client.post(f'/api/plants/{pid}/analyze',
    files={'image': ('plant.jpg', io.BytesIO(img_path.read_bytes()), 'image/jpeg')}
)
print(f'   Status: {r.status_code}')
if r.status_code == 200:
    an = r.json()
    print(f'   analysis_id={an.get("id")}, health={an.get("health_status")}')
    print(f'   stress={an.get("stress_status")}, watering={an.get("watering_status")}')

# 6. Clean up - delete test plant
r = client.delete(f'/api/plants/{pid}')
print(f'6. DELETE /api/plants/{pid}: {r.status_code}')

print()
print('=== PIPELINE TEST COMPLETE ===')

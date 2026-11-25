"""
Phase 1 automated verification test.
Validates database connectivity, OpenAPI schema generation, and core API endpoints.
"""
import sys
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from app.main import app, api_health, dashboard, list_plants, search_knowledge_endpoint, get_settings
from app.database import get_db

def run_phase1_tests():
    print("=== FloraBOT Phase 1 Verification Test ===")
    db = next(get_db())

    # 1. OpenAPI Documentation Schema
    print("1. Verifying OpenAPI schema generation...")
    schema = app.openapi()
    assert schema["info"]["title"] == "FloraBOT AI API", "Unexpected OpenAPI title"
    paths_count = len(schema.get("paths", {}))
    assert paths_count > 0, "No paths found in OpenAPI schema"
    print(f"   [PASS] OpenAPI schema generated successfully with {paths_count} endpoints.")

    # 2. Health Endpoint
    print("2. Verifying /api/health endpoint...")
    h = api_health(db)
    assert h["status"] == "online", "Health status is not online"
    assert "timestamp" in h, "Missing timestamp in health response"
    print(f"   [PASS] Health endpoint returned status: {h['status']} (active devices: {h.get('online_devices', 0)}).")

    # 3. Dashboard Endpoint
    print("3. Verifying /api/dashboard endpoint...")
    d = dashboard(db)
    assert "total_plants" in d, "Missing total_plants in dashboard response"
    assert "plants" in d, "Missing plants in dashboard response"
    assert "devices" in d, "Missing devices in dashboard response"
    print(f"   [PASS] Dashboard endpoint returned {d['total_plants']} plants and {len(d['devices'])} devices.")

    # 4. Plants List Endpoint
    print("4. Verifying /api/plants endpoint...")
    plants = list_plants(db)
    assert isinstance(plants, list), "Plants response is not a list"
    print(f"   [PASS] Plants endpoint returned {len(plants)} plant records.")

    # 5. Knowledge Search Endpoint
    print("5. Verifying /api/knowledge endpoint...")
    k = search_knowledge_endpoint(category="all", query="", db=db)
    assert isinstance(k, list) and len(k) > 0, "Knowledge base returned empty list"
    print(f"   [PASS] Knowledge endpoint returned {len(k)} botanical reference entries.")

    # 6. Settings Endpoint
    print("6. Verifying /api/settings endpoint...")
    s = get_settings()
    assert "camera_stream_url" in s, "Missing camera_stream_url in settings"
    print(f"   [PASS] Settings endpoint verified with camera URL: {s['camera_stream_url']}")

    print("\n[SUCCESS] All Phase 1 backend verification checks PASSED!")

if __name__ == "__main__":
    run_phase1_tests()

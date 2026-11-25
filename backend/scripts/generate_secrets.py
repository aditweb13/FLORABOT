"""
FloraBOT Cryptographic Secret Key Generator:
Generates high-entropy cryptographic keys for JWT tokens, IoT devices,
and production database passwords.
"""

import secrets

def generate_production_secrets():
    jwt_secret = secrets.token_hex(32)
    device_api_key = f"fb_iot_{secrets.token_hex(16)}"
    db_password = secrets.token_urlsafe(18)
    
    print("\n========================================================")
    print("  FLORABOT PRODUCTION SECRET KEY GENERATOR")
    print("========================================================\n")
    print("# Copy and paste these into your production backend/.env file:\n")
    print(f"JWT_SECRET_KEY={jwt_secret}")
    print(f"DEVICE_API_KEY={device_api_key}")
    print(f"POSTGRES_PASSWORD={db_password}")
    print(f"DATABASE_URL=postgresql://florabot:{db_password}@localhost:5432/florabot_db\n")
    print("========================================================\n")

if __name__ == "__main__":
    generate_production_secrets()

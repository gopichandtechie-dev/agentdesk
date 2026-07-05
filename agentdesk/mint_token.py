import requests
import firebase_admin
from firebase_admin import auth, credentials

cred = credentials.Certificate(
    "/Users/gopichand/gcp-keys/agentdesk-dev-500305-b5bde7767b97.json"
)

firebase_admin.initialize_app(cred)

custom_token = auth.create_custom_token(
    "demo-user",
    {
        "tenant_id": "tenant_demo",
        "role": "ops"
    }
).decode()

API_KEY = ""

url = (
    f"https://identitytoolkit.googleapis.com/v1/accounts:signInWithCustomToken"
    f"?key={API_KEY}"
)

resp = requests.post(
    url,
    json={
        "token": custom_token,
        "returnSecureToken": True
    },
)

print(resp.status_code)
print(resp.json())
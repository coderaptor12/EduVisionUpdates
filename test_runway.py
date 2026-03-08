import requests
from config import RUNWAY_API_KEY, RUNWAY_API_URL

headers = {
    "Authorization": f"Bearer {RUNWAY_API_KEY}",
    "Content-Type": "application/json",
    "X-Runway-Version": "2024-11-01"
}


payload = {
    "prompt": "Create an educational animated video explaining Smart Parking System for students",
    "model": "gen3",
    "duration": 8,
    "resolution": "720p"
}

response = requests.post(
    f"{RUNWAY_API_URL}/videos",
    json=payload,
    headers=headers
)

print(response.status_code)
print(response.json())

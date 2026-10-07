import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

base_url = "https://127.0.0.1:4433"

endpoints_to_test = [
    "/WPMS/login",
    "/api/system/login",
    "/api/v1/login",
    "/api/global/login",
    "/admin/login",
    "/dss/api/login",
    "/WPMS/getPublicKey"
]

print(f"Testando endpoints da API no Defense IA ({base_url})...")

for ep in endpoints_to_test:
    url = f"{base_url}{ep}"
    try:
        response = requests.get(url, verify=False, timeout=3)
        print(f"[GET] {ep} -> Status: {response.status_code}")
        if response.status_code in [200, 401, 403, 405]:
            print(f"      Resposta: {response.text[:200]}")
    except Exception as e:
        print(f"[GET] {ep} -> Falhou: {e}")

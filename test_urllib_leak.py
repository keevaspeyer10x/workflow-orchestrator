
import urllib.request
import urllib.error

secret_url = "https://httpbin.org/status/403?key=SECRET_KEY_VALUE"

try:
    urllib.request.urlopen(secret_url)
except Exception as e:
    print(f"Exception type: {type(e)}")
    print(f"str(e): {str(e)}")
    if "SECRET_KEY_VALUE" in str(e):
        print("LEAK DETECTED in str(e)")
    else:
        print("No leak in str(e)")

    if hasattr(e, 'reason'):
        print(f"e.reason: {e.reason}")
    if hasattr(e, 'url'):
        print(f"e.url: {e.url}")
        if "SECRET_KEY_VALUE" in e.url:
             print("Key is present in e.url")

print("-" * 20)

invalid_url = "https://invalid-domain-name-xyz-123.com/?key=SECRET_KEY_VALUE"
try:
    urllib.request.urlopen(invalid_url)
except Exception as e:
    print(f"Exception type: {type(e)}")
    print(f"str(e): {str(e)}")
    if "SECRET_KEY_VALUE" in str(e):
        print("LEAK DETECTED in str(e)")
    else:
        print("No leak in str(e)")

import urllib.request

try:
    req = urllib.request.Request("ht tp://bad?key=SECRET_KEY_VALUE")
    urllib.request.urlopen(req)
except Exception as e:
    print(f"Exception type: {type(e)}")
    print(f"str(e): {str(e)}")
    if "SECRET_KEY_VALUE" in str(e):
        print("LEAK DETECTED in str(e)")
    else:
        print("No leak in str(e)")
# ================= IP DETECTION =================

# الحصول على IP الحقيقي من Render
ip = request.headers.get('X-Forwarded-For')

if ip:
    ip = ip.split(',')[0]  # أول IP
else:
    ip = request.remote_addr

try:
    geo = requests.get(f"http://ip-api.com/json/{ip}?fields=country,city").json()

    country = geo.get("country", "Unknown")
    city = geo.get("city", "Unknown")

    print(f"🌍 {username} joined room [{room}] from {country} - {city} (IP: {ip})")

except Exception as e:
    print(f"⚠️ IP lookup failed: {e}")

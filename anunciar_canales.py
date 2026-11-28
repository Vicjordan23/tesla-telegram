"""Publica en el canal principal el anuncio de los canales por tienda (con el logo de la comunidad y un boton por canal)."""
import json
import os
import sys
import urllib.request

CANALES = [("Amazon", "CholleslaAmzn"), ("AliExpress", "CholleslaAliExpress"), ("Hansshow", "CholleslaHansshow"),
           ("Jowua", "CholleslaJowua"), ("Tesery", "CholleslaTesery"), ("Temu", "CholleslaTemu"), ("Yeslak", "CholleslaYeslak")]

TEXTO = ("\U0001F4E2 <b>NUEVO: un canal de Telegram para cada tienda</b>\n\n"
         "¿Solo te interesan los chollos de una tienda? Elige tu canal y recibe únicamente sus accesorios para Tesla, "
         "con el precio final, cada 30 minutos y sin sonido.\n\n"
         + "\n".join(f"• {n}: @{u}" for n, u in CANALES)
         + "\n\n\U0001F446 Únete a los que quieras y compártelos con otros propietarios de Tesla.\n"
         "\U0001F310 https://chollesla.es")

botones = [{"text": f"Chollesla {n}", "url": f"https://t.me/{u}"} for n, u in CANALES]
cuerpo = {
    "chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
    "photo": "https://chollesla.es/canales/comunidad.webp",
    "caption": TEXTO,
    "parse_mode": "HTML",
    "reply_markup": {"inline_keyboard": [botones[i:i + 2] for i in range(0, len(botones), 2)]},
}

if "--prueba" in sys.argv:
    print(TEXTO, len(TEXTO))
    sys.exit(0)

base = f"https://api.telegram.org/bot{os.environ['TELEGRAM_BOT_TOKEN']}/"
foto = urllib.request.urlopen(urllib.request.Request(cuerpo["photo"], headers={"User-Agent": "Mozilla/5.0"}), timeout=60).read()
cuerpo["photo"] = "attach://foto"
limite = "----chollesla"
partes = []
for k, v in cuerpo.items():
    v = json.dumps(v) if isinstance(v, dict) else str(v)
    partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
from io import BytesIO
from PIL import Image
jpg = BytesIO()
Image.open(BytesIO(foto)).convert("RGB").resize((640, 640)).save(jpg, "JPEG", quality=92)
partes.append(f'--{limite}\r\nContent-Disposition: form-data; name="foto"; filename="canales.jpg"\r\nContent-Type: image/jpeg\r\n\r\n'.encode() + jpg.getvalue() + b"\r\n")
partes.append(f"--{limite}--\r\n".encode())
req = urllib.request.Request(base + "sendPhoto", data=b"".join(partes), headers={"Content-Type": f"multipart/form-data; boundary={limite}"})
with urllib.request.urlopen(req, timeout=60) as r:
    print("OK", json.loads(r.read())["result"]["message_id"])

#!/usr/bin/env python3
"""Publica en Instagram (@tesla.accesorios) el carrusel del accesorio de la franja actual.

Mismo producto y misma franja de 30 min que Telegram/Facebook. Las 4 tarjetas JPEG las genera
tarjetas.py y viven en un repo PUBLICO (Instagram necesita URLs publicas): IMAGENES_URL.

Secretos (GitHub Actions): IG_USER_ID (id de la cuenta de Instagram profesional) y
IG_TOKEN (token de pagina/usuario con instagram_content_publish; si falta se usa FB_PAGE_TOKEN).
Opcional: VENTANA.

Uso:  python publicar_instagram.py [--prueba] [--forzar]
"""
import json
import os
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
API = "https://graph.facebook.com/v21.0"
IMAGENES_URL = os.environ.get("IMAGENES_URL", "https://raw.githubusercontent.com/Vicjordan23/tesla-tarjetas/main")
CANAL = "t.me/teslaaccesorios"


def dentro_de_ventana(texto):
    if not texto:
        return True
    ini, fin = texto.split("-")
    try:
        from zoneinfo import ZoneInfo
        ahora = datetime.now(ZoneInfo("Europe/Madrid")).strftime("%H:%M")
    except Exception:
        ahora = datetime.now().strftime("%H:%M")
    return ini.strip() <= ahora <= fin.strip()


def elegir(productos):
    asins = sorted(p["asin"] for p in productos)
    random.Random(2026).shuffle(asins)  # misma semilla y franja que Telegram/Facebook
    return asins[int(time.time() // 1800) % len(asins)]


def leyenda(p):
    try:
        opinion = json.loads((AQUI / "opiniones.json").read_text(encoding="utf-8")).get(p["asin"], "")
    except Exception:
        opinion = ""
    partes = [f"{p.get('emoji', '🔥')} {p['titulo']}", p["descripcion"], f"✅ {p['modelos']}"]
    if opinion:
        partes.append(f"💬 {opinion}")
    partes.append(f"🛒 Enlace de compra en Amazon en nuestro canal de Telegram: {CANAL} (enlace en la bio). "
                  "Un accesorio nuevo cada 30 minutos.")
    partes.append("Enlaces de afiliado de Amazon: a ti no te cuesta nada más.")
    partes.append("#tesla #teslamodel3 #teslamodely #accesoriostesla #teslaespaña")
    return "\n\n".join(partes)[:2200]


def llamar(ruta, datos, token, metodo="POST"):
    datos = {**datos, "access_token": token}
    if metodo == "GET":
        req = urllib.request.Request(f"{API}/{ruta}?{urllib.parse.urlencode(datos)}")
    else:
        req = urllib.request.Request(f"{API}/{ruta}", data=urllib.parse.urlencode(datos).encode())
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit(f"Instagram devolvio {e.code} en {ruta}: {e.read().decode()[:400]}")


def esperar(id_, token):
    for _ in range(20):
        estado = llamar(id_, {"fields": "status_code"}, token, "GET").get("status_code")
        if estado == "FINISHED":
            return
        if estado in ("ERROR", "EXPIRED"):
            sys.exit(f"Contenedor {id_} en estado {estado}")
        time.sleep(3)
    sys.exit(f"Contenedor {id_} no termino a tiempo")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = set(sys.argv[1:])
    productos = [p for p in json.loads((AQUI / "productos.json").read_text(encoding="utf-8")) if not p.get("pausado")]
    if "--forzar" not in args and not dentro_de_ventana(os.environ.get("VENTANA", "")):
        print("Fuera de la ventana horaria; no se publica.")
        return
    asin = elegir(productos)
    p = next(x for x in productos if x["asin"] == asin)
    imagenes = [f"{IMAGENES_URL}/{asin}_{i}.jpg" for i in range(1, 5)]
    texto = leyenda(p)
    if "--prueba" in args:
        print(texto, "\n\nIMAGENES:", *imagenes, sep="\n")
        return
    token = os.environ.get("IG_TOKEN") or os.environ.get("FB_PAGE_TOKEN", "")
    if not token:
        sys.exit("Falta IG_TOKEN o FB_PAGE_TOKEN")
    usuario = os.environ.get("IG_USER_ID", "")
    if not usuario:  # con un token de pagina, la cuenta de Instagram vinculada se averigua sola
        r = llamar("me", {"fields": "instagram_business_account"}, token, "GET")
        usuario = (r.get("instagram_business_account") or {}).get("id", "")
        if not usuario:
            sys.exit(f"La pagina no tiene Instagram profesional vinculado (o falta permiso): {r}")
    hijos = []
    for url in imagenes:
        r = llamar(f"{usuario}/media", {"image_url": url, "is_carousel_item": "true"}, token)
        hijos.append(r["id"])
    for h in hijos:
        esperar(h, token)
    c = llamar(f"{usuario}/media", {"media_type": "CAROUSEL", "children": ",".join(hijos), "caption": texto}, token)
    esperar(c["id"], token)
    pub = llamar(f"{usuario}/media_publish", {"creation_id": c["id"]}, token)
    print("Publicado", asin, pub)


if __name__ == "__main__":
    main()

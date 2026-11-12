#!/usr/bin/env python3
"""Publica un accesorio de productos.json en la pagina de Facebook «Accesorios Tesla España».

Pensado para GitHub Actions (sin archivos de estado): el producto depende de la hora,
asi que cada franja horaria toca uno distinto y no se repite hasta acabar la vuelta.
El enlace de Amazon va en el parametro "link" (tarjeta con foto), no en el texto,
por lo que el tag de afiliado no se ve escrito en la publicacion.

Variables: FB_PAGE_ID, FB_PAGE_TOKEN (secretos), VENTANA (opcional, "09:00-23:30").

Uso:
  python publicar_facebook.py             publica el que toca ahora
  python publicar_facebook.py --prueba    muestra lo que publicaria, sin enviar
  python publicar_facebook.py --forzar    ignora la ventana horaria
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
TAG = "teslaaccesorios-21"
CANAL = "https://t.me/teslaaccesorios"
API = "https://graph.facebook.com/v21.0"


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
    # Misma semilla y misma franja de 30 min que publicar_siguiente.py (Telegram):
    # asi Facebook y Telegram publican el mismo producto a la vez.
    random.Random(2026).shuffle(asins)
    return asins[int(time.time() // 1800) % len(asins)]


def construir(p):
    jowua = p.get("tienda") == "jowua"
    url = p["url"] if jowua else f"https://www.amazon.es/dp/{p['asin']}?tag={TAG}"
    try:  # resumen de lo que dicen los compradores en Amazon (opiniones.json, solo hechos leidos en la ficha)
        opinion = json.loads((AQUI / "opiniones.json").read_text(encoding="utf-8")).get(p["asin"], "")
    except Exception:
        opinion = ""
    bloque = f"💬 Opiniones de compradores en Amazon: {opinion}\n\n" if opinion and not jowua else ""
    if jowua:  # tienda Jowua: descuento (sin precios) y aviso de afiliado
        aviso = "🏷️ 5 % de descuento con el código VICTOR5 (con este enlace se aplica solo).\nEnlace de afiliado de Jowua.\n"
    else:
        aviso = "Enlace de afiliado de Amazon: a ti no te cuesta nada más.\n"
    texto = (
        f"{p.get('emoji', '🔥')} {p['titulo']}\n\n"
        f"{p['descripcion']}\n\n"
        f"✅ {p['modelos']}\n\n"
        f"{bloque}"
        f"{aviso}"
        f"Más accesorios cada 30 minutos en Telegram: {CANAL}"
    )
    return texto, url


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = set(sys.argv[1:])
    productos = json.loads((AQUI / "productos.json").read_text(encoding="utf-8"))
    extra = AQUI / "productos_jowua.json"  # articulos de Jowua (otra tienda de afiliado)
    if extra.exists():
        productos += json.loads(extra.read_text(encoding="utf-8"))
    productos = [p for p in productos if not p.get("pausado")]
    if "--forzar" not in args and not dentro_de_ventana(os.environ.get("VENTANA", "")):
        print("Fuera de la ventana horaria; no se publica.")
        return
    asin = elegir(productos)
    p = next(x for x in productos if x["asin"] == asin)
    texto, url = construir(p)
    if "--prueba" in args:
        print(texto, "\n\nTARJETA ->", url)
        return
    pagina, token = os.environ.get("FB_PAGE_ID", ""), os.environ.get("FB_PAGE_TOKEN", "")
    if not pagina or not token:
        sys.exit("Faltan FB_PAGE_ID o FB_PAGE_TOKEN")
    datos = urllib.parse.urlencode({"message": texto, "link": url, "access_token": token}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{API}/{pagina}/feed", data=datos), timeout=30) as r:
            print("Publicado", asin, r.read().decode()[:120])
    except urllib.error.HTTPError as e:
        sys.exit(f"Facebook devolvio {e.code}: {e.read().decode()[:400]}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Publica en X (@TeslaAccesorios) el accesorio de la franja actual (el mismo que Facebook y Telegram).

Solo biblioteca estandar. Firma OAuth 1.0a (usuario) y POST https://api.twitter.com/2/tweets.
Secretos (GitHub Actions): X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN, X_ACCESS_SECRET. VENTANA opcional.

Uso:
  python publicar_x.py            publica el que toca
  python publicar_x.py --prueba   muestra el texto sin enviar
  python publicar_x.py --forzar   ignora la ventana horaria
"""
import base64
import hashlib
import hmac
import json
import os
import random
import secrets
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
ENDPOINT = "https://api.twitter.com/2/tweets"


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


def largo_x(texto):
    """X cuenta cada enlace como 23 caracteres."""
    n = 0
    for palabra in texto.replace("\n", " \n ").split(" "):
        n += 23 if palabra.startswith("https://") else len(palabra)
        n += 1
    return n - 1


def construir(p):
    url = f"https://www.amazon.es/dp/{p['asin']}?tag={TAG}"
    try:
        opinion = json.loads((AQUI / "opiniones.json").read_text(encoding="utf-8")).get(p["asin"], "")
    except Exception:
        opinion = ""
    opinion = opinion.replace("Los compradores destacan", "Compradores:").replace("Los compradores dicen", "Compradores:")
    final = f"\n\n🛒 {url} (enlace de afiliado)\nMás en Telegram: {CANAL}"
    partes = [f"{p.get('emoji', '🔥')} {p['titulo']}", f"✅ {p['modelos']}", opinion]
    while True:
        texto = "\n\n".join(x for x in partes if x) + final
        if largo_x(texto) <= 268 or not any(partes[1:]):
            break
        partes[2 if partes[2] else 1] = ""  # recorta primero la opinion, despues los modelos
    return texto


def firmar(metodo, url, params, claves):
    oauth = {
        "oauth_consumer_key": claves["ck"],
        "oauth_nonce": secrets.token_hex(16),
        "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())),
        "oauth_token": claves["at"],
        "oauth_version": "1.0",
    }
    q = lambda s: urllib.parse.quote(str(s), safe="~")
    base_params = "&".join(f"{q(k)}={q(v)}" for k, v in sorted({**params, **oauth}.items()))
    base = "&".join([metodo, q(url), q(base_params)])
    clave = f"{q(claves['cs'])}&{q(claves['as'])}".encode()
    oauth["oauth_signature"] = base64.b64encode(hmac.new(clave, base.encode(), hashlib.sha1).digest()).decode()
    return "OAuth " + ", ".join(f'{q(k)}="{q(v)}"' for k, v in sorted(oauth.items()))


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
    texto = construir(p)
    if "--prueba" in args:
        print(texto, f"\n\n[{largo_x(texto)} caracteres en X]")
        return
    claves = {k: os.environ.get(v, "") for k, v in
              {"ck": "X_API_KEY", "cs": "X_API_SECRET", "at": "X_ACCESS_TOKEN", "as": "X_ACCESS_SECRET"}.items()}
    if not all(claves.values()):
        sys.exit("Faltan secretos X_API_KEY, X_API_SECRET, X_ACCESS_TOKEN o X_ACCESS_SECRET")
    req = urllib.request.Request(
        ENDPOINT, data=json.dumps({"text": texto}).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": firmar("POST", ENDPOINT, {}, claves)})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            print("Publicado", asin, r.read().decode()[:150])
    except urllib.error.HTTPError as e:
        sys.exit(f"X devolvio {e.code}: {e.read().decode()[:400]}")


if __name__ == "__main__":
    main()

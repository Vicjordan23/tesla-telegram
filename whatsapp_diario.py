#!/usr/bin/env python3
"""Envia a TU chat privado de Telegram 5 mensajes listos para copiar y pegar en WhatsApp.

- Elige 5 productos distintos al azar (sin repetir hasta recorrer todo el catalogo).
- Cada producto va en un mensaje aparte, en texto plano con formato WhatsApp (*negrita*),
  para mantener pulsado -> Copiar -> pegar en el canal de WhatsApp.
- Va a TELEGRAM_CHAT_ID_PRIVADO (tu chat con el bot), NUNCA al canal publico.

Uso:
  python whatsapp_diario.py            envia los 5 mensajes
  python whatsapp_diario.py --prueba   los muestra por pantalla sin enviarlos
"""
import json
import os
import random
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

from publicar_siguiente import TAG, leer_env, url_producto

AQUI = Path(__file__).resolve().parent
CUANTOS = 5


def elegir(productos, cuantos=CUANTOS):
    """Por dia: toma el siguiente tramo de una lista barajada (semilla = vuelta).
    Sin estado -> sirve en GitHub Actions. No repite hasta completar la vuelta."""
    asins = sorted(p["asin"] for p in productos)
    n = len(asins)
    dia = date.today().toordinal()
    inicio = dia * cuantos
    vuelta, pos = divmod(inicio, n)
    orden = []
    while len(orden) < cuantos:
        baraja = asins[:]
        random.Random(f"wa-{vuelta}").shuffle(baraja)
        orden += baraja[pos:]
        vuelta, pos = vuelta + 1, 0
    elegidos = orden[:cuantos]
    return [next(p for p in productos if p["asin"] == a) for a in elegidos]


def mensaje(p):
    return (
        f"{p.get('emoji', '🔥')} *{p['titulo']}*\n\n"
        f"{p['descripcion']}\n\n"
        f"✅ {p['modelos']}\n\n"
        f"🛒 {url_producto(p['asin'])}"
    )


def enviar(token, chat, texto):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps({"chat_id": chat, "text": texto,
                         "link_preview_options": {"is_disabled": True}}).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    env = leer_env()
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID_PRIVADO"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    productos = [p for p in json.loads((AQUI / "productos.json").read_text(encoding="utf-8"))
                 if not p.get("pausado")]
    textos = [mensaje(p) for p in elegir(productos)]

    if "--prueba" in sys.argv[1:]:
        print(("\n\n" + "-" * 40 + "\n\n").join(textos))
        return

    token, chat = env.get("TELEGRAM_BOT_TOKEN", ""), env.get("TELEGRAM_CHAT_ID_PRIVADO", "")
    if not token or not chat:
        sys.exit("Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID_PRIVADO")
    enviar(token, chat, f"📲 Tus {CUANTOS} mensajes de hoy para WhatsApp ({date.today():%d/%m}). "
                        "Mantén pulsado cada uno → Copiar → pégalo en el canal.")
    for t in textos:
        res = enviar(token, chat, t)
        if not res.get("ok"):
            sys.exit(f"Telegram devolvio error: {res}")
        time.sleep(1)
    print("Enviados", len(textos))


if __name__ == "__main__":
    main()

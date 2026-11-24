"""Resumen semanal para Telegram: «Top 5 de la semana» (domingo).
Elige hasta 5 productos con datos reales: primero las BAJADAS de precio reales de la semana (historial_precios.json,
mayor % primero), despues los ESTRELLA (los de mas clics en Afiliados). Cada linea lleva el precio final y el enlace de
afiliado de SU tienda. Nada inventado. Uso: python resumen_semanal.py [--prueba]"""
import html
import json
import os
import sys

import marca
import publicar_siguiente as ps
from traducir import a_espanol

MAX = 5


def _corto(t, n=58):
    t = html.unescape(a_espanol(t)).strip()
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def elegir():
    productos = json.loads((ps.AQUI / "productos.json").read_text(encoding="utf-8"))
    for nombre in ("productos_jowua.json", "productos_hansshow.json", "productos_tesery.json", "productos_aliexpress.json", "productos_temu.json"):
        f = ps.AQUI / nombre
        if f.exists():
            productos += json.loads(f.read_text(encoding="utf-8"))
    productos = ps.con_precio([p for p in productos if not p.get("pausado")])
    por_id = {p["asin"]: p for p in productos}
    elegidos, vistos = [], set()
    bajas = []
    for p in productos:
        pr = ps.datos_precio(p)
        b = ps.bajada_real(p, pr) if pr else None
        if b and ps.imagen_de(p["asin"]):
            bajas.append((b["pct"], p["asin"], b))
    marcas = set()  # evita dos variantes casi iguales (mismo comienzo de titulo)
    for _, asin, b in sorted(bajas, reverse=True):
        clave = por_id[asin]["titulo"][:22].lower()
        if len(elegidos) >= 3 or clave in marcas:
            continue
        marcas.add(clave)
        elegidos.append((por_id[asin], b))
        vistos.add(asin)
    for asin in ps.ESTRELLA:
        if len(elegidos) >= MAX:
            break
        if asin in por_id and asin not in vistos:
            elegidos.append((por_id[asin], None))
            vistos.add(asin)
    return elegidos[:MAX]


def construir():
    filas, hay_amazon = [], False
    for i, (p, b) in enumerate(elegir(), 1):
        t = ps.tienda_de(p)
        pr = ps.datos_precio(p)
        url = ps.url_producto(p["asin"]) if t == "amazon" else p["url"]
        hay_amazon = hay_amazon or t == "amazon"
        precio = ps.eur(pr["final"]) if pr else ""
        extra = f" (antes {ps.eur(b['antes'])}, -{b['pct']} %)" if b else ""
        filas.append(f'{i}. <a href="{html.escape(url, quote=True)}">{html.escape(_corto(p["titulo"]), quote=False)}</a> — <b>{precio}</b>{extra}')
    if not filas:
        return None
    texto = "🏆 <b>Top accesorios Tesla de la semana</b>\nBajadas de precio reales y los más pulsados, con precio final:\n\n" + "\n".join(filas)
    texto += f'\n\n🔔 Comparte el canal con otro dueño de Tesla: https://t.me/teslaaccesorios\n🌐 Todas las ofertas: <a href="{html.escape(marca.web_utm("telegram", "resumen"), quote=True)}">{html.escape(marca.WEB_CORTA, quote=False)}</a>'
    if hay_amazon:
        texto += "\n\n" + ps.AVISO_AMAZON
    return texto


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    texto = construir()
    if not texto:
        print("Sin productos para el resumen; no se publica.")
        return
    if "--prueba" in sys.argv:
        print(texto)
        return
    token, chat = os.environ.get("TELEGRAM_BOT_TOKEN", ""), os.environ.get("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        sys.exit("Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID")
    res = ps._telegram(token, "sendMessage", {"chat_id": chat, "text": texto, "parse_mode": "HTML", "disable_web_page_preview": True})
    if not res.get("ok"):
        sys.exit(f"Telegram devolvio error: {res}")
    print("Resumen semanal publicado")


if __name__ == "__main__":
    main()

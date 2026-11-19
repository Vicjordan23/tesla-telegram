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
TIENDAS = ("amazon", "jowua", "hansshow", "tesery", "evdance")
# Turno de 134 franjas de 30 min: ciclo de 7 (Amazon, Jowua y Hansshow 2 veces cada una y Tesery 1: comision del 2 %) x19 y EVDANCE 1 sola (envio a Espana caro)
TURNO = ("amazon", "jowua", "hansshow", "amazon", "jowua", "hansshow", "tesery") * 19 + ("evdance",)  # 134 franjas: EVDANCE 1 vez (~cada 2,8 dias; 11 productos = vuelta de ~1 mes)


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
    # Misma logica que publicar_siguiente.py (Telegram): una tienda por franja (Amazon, Jowua, Hansshow por
    # turnos = 1/3 cada una), cada una con su lista barajada (semilla 2026). Telegram y Facebook publican lo mismo a la vez.
    franja = int(time.time() // 1800)
    turno = [t for t in TURNO if any(tienda_de(p) == t for p in productos)]
    pos = franja % len(turno)
    tienda = turno[pos]
    lista = lista_tienda(productos, tienda)  # los caros (>= mediana de la tienda) salen el doble
    k = (franja // len(turno)) * turno.count(tienda) + turno[:pos].count(tienda)  # EVDANCE pesa 1/7 (envio caro a Espana)
    return lista[k % len(lista)]


def tienda_de(p):
    return p.get("tienda", "amazon")


DESCUENTOS = {"amazon": 0.0, "jowua": 0.05, "hansshow": 0.20, "tesery": 0.05, "evdance": 0.20}  # descuento de cada tienda con su codigo
CODIGOS = {"jowua": "ACCESORIOSTESLA", "hansshow": "VICTOR", "tesery": "ACCESORIOSTESLA", "evdance": "EVEU20"}


def con_precio(productos):
    """Regla de Vic: producto sin precio = no se publica. Si no se puede leer ningun precio, no se filtra (para no parar todo)."""
    ids = set()
    for nombre in ("precios.json", "precios_tesery.json"):
        try:
            ids |= set(json.loads((AQUI / nombre).read_text(encoding="utf-8")))
        except Exception:
            pass
    return [p for p in productos if p["asin"] in ids] if ids else productos


def lista_tienda(productos, tienda):
    """Lista rotativa de una tienda: todos los productos una vez (barajados, semilla 2026) y despues, otra vez,
    los de precio igual o superior a la mediana de la tienda (barajados, semilla 2027): los caros dan mas comision
    y salen el doble. IDENTICA en publicar_siguiente.py, publicar_facebook.py y publicar_instagram.py."""
    precios = {}
    for nombre in ("precios.json", "precios_tesery.json"):
        try:
            precios.update(json.loads((AQUI / nombre).read_text(encoding="utf-8")))
        except Exception:
            pass
    base = sorted(p["asin"] for p in productos if tienda_de(p) == tienda)
    random.Random(2026).shuffle(base)
    valores = sorted(precios[a]["p"] for a in base if a in precios)
    if len(valores) < 4:
        return base
    mediana = valores[len(valores) // 2]
    caros = sorted(a for a in base if a in precios and precios[a]["p"] >= mediana)
    random.Random(2027).shuffle(caros)
    return base + caros


def linea_precio(p):
    """Precio FINAL (con el descuento de la tienda) a partir de precios.json (se actualiza cada semana). '' si no hay precio."""
    d = None
    for nombre in ("precios.json", "precios_tesery.json"):  # Tesery tiene su propio archivo de precios
        try:
            d = d or json.loads((AQUI / nombre).read_text(encoding="utf-8")).get(p["asin"])
        except Exception:
            pass
    if not d:
        return ""
    t = tienda_de(p)
    dto = DESCUENTOS.get(t, 0)
    final = int(d["p"] * (1 - dto) + 0.5)

    def eur(c):
        return f"{c // 100:,}".replace(",", ".") + f",{c % 100:02d} €"

    desde = "Desde " if d.get("d") else ""
    dia = d["f"][8:10] + "/" + d["f"][5:7]
    if dto:
        return f"💶 {desde}{eur(final)} con el código {CODIGOS[t]} (precio en tienda: {eur(d['p'])}; precio del {dia})"
    return f"💶 {desde}{eur(final)} (precio del {dia}; puede variar)"


def construir(p):
    tienda = tienda_de(p)
    jowua = tienda == "jowua"
    url = f"https://www.amazon.es/dp/{p['asin']}?tag={TAG}" if tienda == "amazon" else p["url"]
    try:  # resumen de lo que dicen los compradores en Amazon (opiniones.json, solo hechos leidos en la ficha)
        opinion = json.loads((AQUI / "opiniones.json").read_text(encoding="utf-8")).get(p["asin"], "")
    except Exception:
        opinion = ""
    bloque = f"💬 Opiniones de compradores en Amazon: {opinion}\n\n" if opinion and tienda == "amazon" else ""
    lp = linea_precio(p)
    if lp:
        bloque += lp + "\n\n"
    if jowua:  # tienda Jowua: descuento (sin precios) y aviso de afiliado
        aviso = "🏷️ 5 % de descuento con el código ACCESORIOSTESLA (con este enlace se aplica solo).\n"
    elif tienda == "hansshow":  # Hansshow: cupon de afiliado de Victor (el enlace lleva su codigo bg_ref)
        aviso = "🏷️ 20 % de descuento con el código VICTOR al pagar.\n"
    elif tienda == "tesery":  # Tesery (GoAffPro): codigo de Vic, 5 %
        aviso = "🏷️ 5 % de descuento con el código ACCESORIOSTESLA al pagar.\n"
    elif tienda == "evdance":  # EVDANCE (Awin)
        aviso = "🏷️ Con el código EVEU20 hasta 20 % de descuento en la tienda. Consulta el envío a España en la ficha.\n"
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
    for nombre in ("productos_jowua.json", "productos_hansshow.json", "productos_tesery.json", "productos_evdance.json"):  # otras tiendas de afiliado
        extra = AQUI / nombre
        if extra.exists():
            productos += json.loads(extra.read_text(encoding="utf-8"))
    productos = con_precio([p for p in productos if not p.get("pausado")])
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

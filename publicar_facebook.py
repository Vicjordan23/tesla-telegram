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
from traducir import a_espanol
import marca
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
TAG = "teslafacebook-21"  # ID de seguimiento de Amazon propio de este canal (24/11/2026): sus clics y ventas salen por separado en el informe de Afiliados
CANAL = "https://t.me/teslaaccesorios"
API = "https://graph.facebook.com/v21.0"
TIENDAS = ("amazon", "jowua", "hansshow", "tesery", "aliexpress", "temu")
TURNO = ("amazon", "amazon", "aliexpress", "aliexpress", "amazon", "amazon", "amazon", "hansshow", "amazon", "amazon", "jowua", "amazon", "aliexpress", "tesery", "amazon", "amazon", "hansshow", "temu", "amazon", "amazon") * 7  # 140 franjas, ciclo de 20: Amazon 12 (60 %), AliExpress 3, Hansshow 2, Jowua, Tesery y Temu 1. 26/11 (Vic): mayoria Amazon, es la unica tienda con ventas. Pares e impares equilibrados.


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
    k = (franja // len(turno)) * turno.count(tienda) + turno[:pos].count(tienda)
    return lista[k % len(lista)]


def tienda_de(p):
    return p.get("tienda", "amazon")


DESCUENTOS = {"amazon": 0.0, "jowua": 0.05, "hansshow": 0.20, "tesery": 0.05, "aliexpress": 0.0, "temu": 0.0}  # descuento de cada tienda con su codigo
CODIGOS = {"jowua": "ACCESORIOSTESLA", "hansshow": "VICTOR", "tesery": "ACCESORIOSTESLA"}


def con_precio(productos):
    """Regla de Vic: producto sin precio = no se publica. Si no se puede leer ningun precio, no se filtra (para no parar todo)."""
    ids = set()
    for nombre in ("precios.json", "precios_tesery.json", "precios_aliexpress.json", "precios_temu.json"):
        try:
            ids |= set(json.loads((AQUI / nombre).read_text(encoding="utf-8")))
        except Exception:
            pass
    return [p for p in productos if p["asin"] in ids] if ids else productos


ESTRELLA = ["B0H11V8456", "B0FC21DNGX", "B0FCC6MMTV", "B0GC5TXB1L", "B0F7JXXSZS", "B0HHK2P5SX"]  # mas clics en Afiliados (20/11/2026)


def lista_tienda(productos, tienda):
    """Lista rotativa de una tienda: todos los productos una vez (barajados, semilla 2026) y despues, otra vez,
    los de precio igual o superior a la mediana de la tienda (barajados, semilla 2027): los caros dan mas comision
    y salen el doble. IDENTICA en publicar_siguiente.py, publicar_facebook.py y publicar_instagram.py."""
    precios = {}
    for nombre in ("precios.json", "precios_tesery.json", "precios_aliexpress.json", "precios_temu.json"):
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
    lista = base + caros
    # Productos con clics reales (informe de Afiliados 20/11/2026): salen 2 veces mas por vuelta, al principio y a mitad.
    estrella = [a for a in ESTRELLA if a in base and a in precios]
    if estrella:
        mitad = len(lista) // 2
        lista = estrella + lista[:mitad] + estrella + lista[mitad:]
    return lista


def linea_precio(p):
    """Precio FINAL (con el descuento de la tienda) a partir de precios.json (se actualiza cada semana). '' si no hay precio."""
    d = None
    for nombre in ("precios.json", "precios_tesery.json", "precios_aliexpress.json", "precios_temu.json"):  # Tesery tiene su propio archivo de precios
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
        return f"💶 {desde}{eur(final)} con el código {CODIGOS[t]} (precio en tienda: {eur(d['p'])})"
    return f"💶 {desde}{eur(final)}"


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
    elif tienda == "aliexpress":  # AliExpress (afiliados)
        aviso = "Enlace de afiliado de AliExpress: a ti no te cuesta nada más. Revisa la variante y el envío en la ficha.\n"
    elif tienda == "temu":  # Temu (afiliados)
        aviso = "Enlace de afiliado de Temu: a ti no te cuesta nada más. Revisa la variante y el envío en la ficha.\n"
    else:
        aviso = "Enlace de afiliado de Amazon: a ti no te cuesta nada más.\n"
    texto = (
        f"{p.get('emoji', '🔥')} {a_espanol(p['titulo'])}\n\n"
        f"{a_espanol(p['descripcion'])}\n\n"
        f"✅ {p['modelos']}\n\n"
        f"{bloque}"
        f"{aviso}"
        f"{marca.PIE_FACEBOOK}"
    )
    return texto, url


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = set(sys.argv[1:])
    productos = json.loads((AQUI / "productos.json").read_text(encoding="utf-8"))
    for nombre in ("productos_jowua.json", "productos_hansshow.json", "productos_tesery.json", "productos_aliexpress.json", "productos_temu.json"):  # otras tiendas de afiliado
        extra = AQUI / nombre
        if extra.exists():
            productos += json.loads(extra.read_text(encoding="utf-8"))
    productos = con_precio([p for p in productos if not p.get("pausado")])
    if "--forzar" not in args and not dentro_de_ventana(os.environ.get("VENTANA", "")):
        print("Fuera de la ventana horaria; no se publica.")
        return
    asin = elegir(productos)
    asin = os.environ.get("PRODUCTO_FORZADO") or asin  # prueba manual de un producto concreto
    p = next(x for x in productos if x["asin"] == asin)
    texto, url = construir(p)
    if "--prueba" in args:
        print(texto, "\n\nTARJETA ->", url)
        return
    pagina, token = os.environ.get("FB_PAGE_ID", ""), os.environ.get("FB_PAGE_TOKEN", "")
    if not pagina or not token:
        sys.exit("Faltan FB_PAGE_ID o FB_PAGE_TOKEN")
    imagenes = {}
    for nombre in ("imagenes_ig.json", "imagenes_tesery.json", "imagenes_aliexpress.json", "imagenes_temu.json"):
        try:
            imagenes.update(json.loads((AQUI / nombre).read_text(encoding="utf-8")))
        except Exception:
            pass
    if imagenes.get(asin):  # foto del producto con el logo de Chollesla; el enlace de compra va en el texto
        try:
            foto = marca.con_logo(marca.descargar(imagenes[asin]))
            res = marca.subir_foto_facebook(foto, {"message": f"{texto}\n\n🛒 {url}"}, token, pagina)
            print("Publicado con foto", asin, str(res)[:120])
            return
        except Exception as e:
            print("Foto con logo no publicada, se usa la tarjeta de enlace:", e)
    datos = urllib.parse.urlencode({"message": texto, "link": url, "access_token": token}).encode()
    try:
        with urllib.request.urlopen(urllib.request.Request(f"{API}/{pagina}/feed", data=datos), timeout=30) as r:
            print("Publicado", asin, r.read().decode()[:120])
    except urllib.error.HTTPError as e:
        sys.exit(f"Facebook devolvio {e.code}: {e.read().decode()[:400]}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Publica en Instagram (@tesla.accesorios) la FOTO REAL del accesorio de la franja actual.

Misma rotacion que Telegram/Facebook (una tienda por franja de 30 min: Amazon, Jowua, Hansshow, y dentro
de cada una su lista barajada con semilla 2026), asi que el mismo producto sale en los tres canales.
La imagen es la foto del producto (imagenes_ig.json: id -> URL publica JPEG). Sin tarjetas dibujadas.
Si el producto de la franja no tiene imagen conocida, no se publica nada en esa franja.

Secretos (GitHub Actions): IG_USER_ID (id de la cuenta de Instagram profesional) y
IG_TOKEN (token con instagram_content_publish; si falta se usa FB_PAGE_TOKEN).
Opcionales: VENTANA ("08:00-23:30"), TIENDAS_IG (p. ej. "jowua,hansshow" para excluir Amazon).

Uso:  python publicar_instagram.py [--prueba] [--forzar]
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
API = "https://graph.facebook.com/v21.0"
CANAL = "t.me/teslaaccesorios"
TIENDAS = ("amazon", "jowua", "hansshow", "tesery", "evdance", "aliexpress")
# Turno de 134 franjas de 30 min: ciclo de 7 (Amazon, Jowua y Hansshow 2 veces cada una y Tesery 1: comision del 2 %) x19 y EVDANCE 1 sola (envio a Espana caro)
TURNO = ("amazon", "jowua", "hansshow", "amazon", "jowua", "hansshow", "tesery", "aliexpress", "aliexpress") * 15 + ("evdance",)  # 136 franjas: ciclo de 9 (AliExpress 2 de 9, comision ~9 %) x15 y EVDANCE 1 vez


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


def tienda_de(p):
    return p.get("tienda", "amazon")


def elegir(productos):
    # Identico a publicar_siguiente.py / publicar_facebook.py (no tocar uno sin tocar los otros).
    franja = int(time.time() // 1800)
    turno = [t for t in TURNO if any(tienda_de(p) == t for p in productos)]
    pos = franja % len(turno)
    tienda = turno[pos]
    lista = lista_tienda(productos, tienda)  # los caros (>= mediana de la tienda) salen el doble
    k = (franja // len(turno)) * turno.count(tienda) + turno[:pos].count(tienda)  # EVDANCE pesa 1/7 (envio caro a Espana)
    return lista[k % len(lista)]


DESCUENTOS = {"amazon": 0.0, "jowua": 0.05, "hansshow": 0.20, "tesery": 0.05, "evdance": 0.20, "aliexpress": 0.0}  # descuento de cada tienda con su codigo
CODIGOS = {"jowua": "ACCESORIOSTESLA", "hansshow": "VICTOR", "tesery": "ACCESORIOSTESLA", "evdance": "EVEU20"}


def con_precio(productos):
    """Regla de Vic: producto sin precio = no se publica. Si no se puede leer ningun precio, no se filtra (para no parar todo)."""
    ids = set()
    for nombre in ("precios.json", "precios_tesery.json", "precios_aliexpress.json"):
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
    for nombre in ("precios.json", "precios_tesery.json", "precios_aliexpress.json"):
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
    for nombre in ("precios.json", "precios_tesery.json", "precios_aliexpress.json"):  # Tesery tiene su propio archivo de precios
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


def leyenda(p):
    tienda = tienda_de(p)
    partes = [f"{p.get('emoji', '🔥')} {a_espanol(p['titulo'])}", a_espanol(p["descripcion"]), f"✅ {p['modelos']}"]
    lp = linea_precio(p)
    if lp:
        partes.append(lp)
    if tienda == "amazon":
        try:
            opinion = json.loads((AQUI / "opiniones.json").read_text(encoding="utf-8")).get(p["asin"], "")
        except Exception:
            opinion = ""
        if opinion:
            partes.append(f"💬 Opiniones de compradores en Amazon: {opinion}")
        partes.append("Enlace de afiliado de Amazon: a ti no te cuesta nada más.")
    elif tienda == "jowua":
        partes.append("🏷️ 5 % de descuento con el código ACCESORIOSTESLA (con el enlace del canal se aplica solo).")
    elif tienda == "hansshow":
        partes.append("🏷️ 20 % de descuento con el código VICTOR al pagar.")
    elif tienda == "tesery":
        partes.append("🏷️ 5 % de descuento con el código ACCESORIOSTESLA al pagar.")
    elif tienda == "aliexpress":
        partes.append("🏷️ Enlace de afiliado de AliExpress: a ti no te cuesta nada más. Revisa la variante y el envío en la ficha.")
    elif tienda == "evdance":
        partes.append("🏷️ Con el código EVEU20 hasta 20 % de descuento en la tienda. Consulta el envío a España en la ficha.")
    partes.append("🛒 Enlace de compra en la bio y en el canal de Telegram. Un accesorio nuevo cada 30 minutos." + chr(10) * 2 + marca.PIE_TEXTO)
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
    productos = json.loads((AQUI / "productos.json").read_text(encoding="utf-8"))
    for nombre in ("productos_jowua.json", "productos_hansshow.json", "productos_tesery.json", "productos_evdance.json", "productos_aliexpress.json"):  # otras tiendas de afiliado
        extra = AQUI / nombre
        if extra.exists():
            productos += json.loads(extra.read_text(encoding="utf-8"))
    productos = con_precio([p for p in productos if not p.get("pausado")])
    if "--forzar" not in args and not os.environ.get("PRODUCTO_FORZADO") and not dentro_de_ventana(os.environ.get("VENTANA", "")):
        print("Fuera de la ventana horaria; no se publica.")
        return
    cada = int(os.environ.get("IG_CADA", "1") or "1")  # 17/11/2026: tras el bloqueo de Meta (2207051), publicar solo 1 de cada N franjas
    if "--forzar" not in args and not os.environ.get("PRODUCTO_FORZADO") and cada > 1 and int(time.time() // 1800) % cada != 0:
        print(f"IG_CADA={cada}: esta franja no toca publicar en Instagram.")
        return
    asin = elegir(productos)  # la rotacion se calcula con TODAS las tiendas para coincidir con Telegram/Facebook
    asin = os.environ.get("PRODUCTO_FORZADO") or asin  # prueba manual de un producto concreto
    p = next(x for x in productos if x["asin"] == asin)
    permitidas = [t.strip() for t in os.environ.get("TIENDAS_IG", "").split(",") if t.strip()]
    if permitidas and tienda_de(p) not in permitidas:
        print(f"Tienda {tienda_de(p)} excluida de Instagram (TIENDAS_IG); no se publica {asin}.")
        return
    imagenes = {}
    for nombre in ("imagenes_ig.json", "imagenes_tesery.json", "imagenes_aliexpress.json"):  # fotos reales por producto (Tesery en su propio archivo)
        try:
            imagenes.update(json.loads((AQUI / nombre).read_text(encoding="utf-8")))
        except Exception:
            pass
    imagen = imagenes.get(asin)
    if not imagen:
        print(f"Sin imagen del producto para {asin}; no se publica en esta franja.")
        return
    texto = leyenda(p)
    if "--prueba" in args:
        print(texto, "\n\nIMAGEN ->", imagen)
        return
    token = os.environ.get("IG_TOKEN") or os.environ.get("FB_PAGE_TOKEN", "")
    if not token:
        sys.exit("Falta IG_TOKEN o FB_PAGE_TOKEN")
    usuario = os.environ.get("IG_USER_ID", "")
    if not usuario:  # con un token de pagina, la cuenta de Instagram vinculada se averigua sola
        r = llamar("me", {"fields": "instagram_business_account"}, token, "GET")
        usuario = (r.get("instagram_business_account") or {}).get("id", "")
        if not usuario:  # token de usuario: buscar entre sus paginas la que tenga Instagram vinculado
            paginas = llamar("me/accounts", {"fields": "name,instagram_business_account,access_token"}, token, "GET")
            for pg in paginas.get("data", []):
                if pg.get("instagram_business_account"):
                    usuario = pg["instagram_business_account"]["id"]
                    token = pg.get("access_token") or token
                    break
        if not usuario:
            sys.exit("Sin Instagram profesional vinculado, o al token le faltan los permisos "
                     f"instagram_basic / instagram_content_publish / pages_show_list. Respuesta: {r}")
    c = llamar(f"{usuario}/media", {"image_url": imagen, "caption": texto}, token)
    esperar(c["id"], token)
    pub = llamar(f"{usuario}/media_publish", {"creation_id": c["id"]}, token)
    print("Publicado", asin, pub)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Actualiza los precios SIN navegador: lee los precios de cada tienda por internet y reescribe
precios.json (Amazon, Jowua, Hansshow, EVDANCE) y precios_tesery.json (Tesery).

Pensado para GitHub Actions (workflow actualizar_precios.yml), una vez por semana (regla de Vic, 16/11/2026:
todos los posts llevan precio final con el descuento de la tienda y se actualiza cada semana).

Fuentes:
  Jowua, Hansshow, Tesery  -> <tienda>/es-es/products.json (EUR). Se cruza por id con <tienda>/products.json
                              porque en es-es los handles pueden venir traducidos.
  EVDANCE                  -> eu.evdances.com/es/products.json
  Amazon.es                -> Creators API getItems (offersV2.listings.price). Necesita los secretos
                              CREATORS_API_CREDENTIAL_ID / CREATORS_API_CREDENTIAL_SECRET.
Formato: {"<id>": {"p": centimos (precio de lista, sin codigo), "d": 1 si varias variantes con distinto precio, "f": "AAAA-MM-DD"}}
Si una tienda no se puede leer, se dejan sus precios como estaban (y se avisa). Nunca se borran precios.

Uso (desde proyecto/):
  python actualizar_precios_web.py            prueba: muestra lo que cambiaria, no escribe
  python actualizar_precios_web.py --aplicar  escribe precios.json y precios_tesery.json (o APLICAR=1)
  python actualizar_precios_web.py --solo tesery,jowua   limita las tiendas
"""
import datetime
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
HOY = datetime.date.today().isoformat()
UA = "Mozilla/5.0 (compatible; TeslaAccesorios/1.0; +precios)"

TIENDAS_WEB = {  # tienda -> (base con idioma es-es para precios en EUR, base por defecto para ids/handles ingleses)
    "jowua": ("https://www.jowua-life.com/es-es", "https://www.jowua-life.com"),
    "hansshow": ("https://www.hansshow.com/es-es", "https://www.hansshow.com"),
    "tesery": ("https://www.tesery.com/es-es", "https://www.tesery.com"),
    "evdance": ("https://eu.evdances.com/es", None),
}
CATALOGOS = ("productos.json", "productos_jowua.json", "productos_hansshow.json", "productos_tesery.json", "productos_evdance.json")


def get_json(url, intentos=5):
    for i in range(intentos):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 430, 503) and i < intentos - 1:
                time.sleep(6 * (i + 1))
                continue
            raise
        except Exception:
            if i < intentos - 1:
                time.sleep(4)
                continue
            raise


def catalogo_shopify(base):
    """Devuelve {id: producto} recorriendo products.json."""
    out = {}
    for pagina in range(1, 40):
        datos = get_json(f"{base}/products.json?limit=250&page={pagina}")
        prods = datos.get("products", [])
        if not prods:
            break
        for p in prods:
            out[p["id"]] = p
        time.sleep(1)
    return out


def rango_precio(p):
    """(min, max) en centimos: variantes disponibles si las hay (si no, todas)."""
    vs = p.get("variants", [])
    elegidas = [v for v in vs if v.get("available")] or vs
    precios = []
    for v in elegidas:
        try:
            c = round(float(v.get("price")) * 100)
        except (TypeError, ValueError):
            continue
        if c > 0:
            precios.append(c)
    return (min(precios), max(precios)) if precios else None


def precios_shopify(tienda):
    """{handle (es-es o ingles): (min, max)} en EUR para una tienda Shopify."""
    base_es, base_en = TIENDAS_WEB[tienda]
    es = catalogo_shopify(base_es)
    en = catalogo_shopify(base_en) if base_en else {}
    out = {}
    for pid, p in es.items():
        r = rango_precio(p)
        if not r:
            continue
        out[p["handle"]] = r
        if pid in en:  # el mismo producto con el handle en ingles (el de las URL de afiliado)
            out[en[pid]["handle"]] = r
    return out


def handle_de(p):
    t = p.get("tienda", "amazon")
    if t == "evdance":
        return p["asin"][len("EVDANCE-"):]
    if t == "hansshow":
        return p["asin"][len("HANSSHOW-"):]
    if t == "tesery":
        return p["asin"][len("TESERY-"):]
    if t == "jowua":
        m = re.search(r"/products/([^?/]+)", p.get("url_larga") or p.get("url") or "")
        return m.group(1) if m else None
    return None


def precios_amazon(asins):
    """{ASIN: (precio, precio)} con la Creators API (getItems). {} si no hay credenciales o la API no da precio."""
    if not (os.environ.get("CREATORS_API_CREDENTIAL_ID") and os.environ.get("CREATORS_API_CREDENTIAL_SECRET")):
        print("  Amazon: faltan los secretos de la Creators API; se omite.")
        return {}
    import buscar_productos as bp  # reutiliza token y llamadas
    token = bp.obtener_token()
    out, muestra = {}, True
    for i in range(0, len(asins), 10):
        lote = asins[i:i + 10]
        cuerpo = {"itemIds": lote, "partnerTag": bp.TAG, "marketplace": bp.MARKET,
                  "resources": ["offersV2.listings.price", "offersV2.listings.availability"]}
        try:
            r = bp.post_json(bp.GET_ITEMS, cuerpo, {"Authorization": f"Bearer {token}", "x-marketplace": bp.MARKET})
        except urllib.error.HTTPError as e:
            print(f"  Amazon getItems HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
            time.sleep(2)
            continue
        time.sleep(1.2)
        for it in (r.get("itemsResult") or {}).get("items") or []:
            ofertas = it.get("offersV2") or {}
            listings = ofertas.get("listings", []) if isinstance(ofertas, dict) else ofertas
            if muestra and listings:
                print("  Amazon muestra de listing:", json.dumps(listings[0])[:400])
                muestra = False
            for o in listings:
                if not isinstance(o, dict):
                    continue
                if (o.get("availability") or {}).get("type") not in (None, "IN_STOCK"):
                    continue
                money = (o.get("price") or {}).get("money") or {}
                amount = money.get("amount")
                if isinstance(amount, (int, float)) and amount > 0 and money.get("currency", "EUR") == "EUR":
                    c = round(float(amount) * 100)
                    out[it.get("asin")] = (c, c)
                    break
    return out


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    aplicar = "--aplicar" in args or os.environ.get("APLICAR", "").lower() in ("1", "true", "yes")
    solo = None
    if "--solo" in args:
        solo = set(args[args.index("--solo") + 1].split(","))
    productos = []
    for n in CATALOGOS:
        f = AQUI / n
        if f.exists():
            productos += json.loads(f.read_text(encoding="utf-8"))
    activos = [p for p in productos if not p.get("pausado")]
    por_tienda = {}
    for p in activos:
        por_tienda.setdefault(p.get("tienda", "amazon"), []).append(p)

    precios = json.loads((AQUI / "precios.json").read_text(encoding="utf-8"))
    precios_t = json.loads((AQUI / "precios_tesery.json").read_text(encoding="utf-8")) if (AQUI / "precios_tesery.json").exists() else {}
    cambios, fallos = [], []
    resumen = []

    for tienda, lista in sorted(por_tienda.items()):
        if solo and tienda not in solo:
            continue
        print(f"== {tienda}: {len(lista)} productos activos")
        try:
            if tienda == "amazon":
                tabla = precios_amazon([p["asin"] for p in lista])
                clave = lambda p: p["asin"]
            else:
                tabla = precios_shopify(tienda)
                clave = handle_de
        except Exception as e:
            print(f"  ERROR leyendo {tienda}: {type(e).__name__} {e}; se dejan sus precios como estaban")
            resumen.append((tienda, 0, len(lista), len(lista)))
            continue
        destino = precios_t if tienda == "tesery" else precios
        ok = 0
        for p in lista:
            r = tabla.get(clave(p)) if clave(p) else None
            if not r:
                fallos.append(p["asin"])
                continue
            ok += 1
            nuevo = {"p": r[0], "d": 1 if r[1] != r[0] else 0, "f": HOY}
            ant = destino.get(p["asin"])
            if ant and ant["p"] != nuevo["p"]:
                cambios.append((p["asin"], ant["p"], nuevo["p"]))
            destino[p["asin"]] = nuevo
        resumen.append((tienda, ok, len(lista), len(lista) - ok))
        if lista and ok < 0.5 * len(lista):
            print(f"  AVISO: solo {ok} de {len(lista)} con precio; revisar la fuente de {tienda}")

    print("\nRESUMEN (tienda, con precio nuevo, activos, sin actualizar):")
    for r in resumen:
        print("  ", r)
    grandes = [c for c in cambios if abs(c[2] - c[1]) / max(c[1], 1) > 0.4]
    print(f"Precios cambiados: {len(cambios)} (saltos de mas del 40 %: {len(grandes)})")
    for a, x, y in grandes[:20]:
        print(f"   salto: {a} {x / 100:.2f} -> {y / 100:.2f}")
    print(f"Sin precio nuevo: {len(fallos)}")
    for a in fallos[:15]:
        print("   sin actualizar:", a)
    activos_ids = {p["asin"] for p in activos}
    sin_nada = [a for a in activos_ids if a not in precios and a not in precios_t and (not solo)]
    print(f"Activos sin ningun precio (los publicadores los saltan): {len(sin_nada)}")

    # Regla de Vic: producto sin precio = no se publica. Si una tienda se leyo bien pero un producto lleva mas de
    # MAX_DIAS sin precio nuevo (agotado, retirado...), se le quita el precio y los publicadores lo saltan.
    MAX_DIAS = 10
    limite = (datetime.date.today() - datetime.timedelta(days=MAX_DIAS)).isoformat()
    leidas = {t for t, ok, tot, falta in resumen if tot and ok >= 0.5 * tot}
    caducados = []
    for p in activos:
        t = p.get("tienda", "amazon")
        if t not in leidas:
            continue
        destino = precios_t if t == "tesery" else precios
        d = destino.get(p["asin"])
        if d and d["f"] < limite:
            caducados.append(p["asin"])
            if aplicar:
                del destino[p["asin"]]
    print(f"Precios caducados (mas de {MAX_DIAS} dias sin actualizar) {'quitados' if aplicar else 'que se quitarian'}: {len(caducados)}")
    for a in caducados[:15]:
        print("   caducado:", a)

    if not aplicar:
        print("\nModo prueba (sin --aplicar / APLICAR): no se escribe nada.")
        return
    (AQUI / "precios.json").write_text(json.dumps(precios, ensure_ascii=False), encoding="utf-8", newline="\n")
    (AQUI / "precios_tesery.json").write_text(json.dumps(precios_t, ensure_ascii=False), encoding="utf-8", newline="\n")
    print("precios.json y precios_tesery.json escritos.")


if __name__ == "__main__":
    main()

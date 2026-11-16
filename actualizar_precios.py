#!/usr/bin/env python3
"""Genera precios.json (id -> precio de lista en centimos) a partir de las tablas de precios recogidas de las tiendas.

Se actualiza cada semana (decision de Vic 16/11/2026: todos los posts llevan precio final con el descuento).
precios.json: {"<id>": {"p": 6399, "d": 0, "f": "2026-11-16"}}  p = centimos de euro (precio de lista, sin codigo),
d = 1 si hay varias variantes con distinto precio (el texto dice "desde"), f = fecha de la medicion.
Los scripts de publicacion aplican el descuento de cada tienda (Jowua 5 %, Hansshow 20 %, EVDANCE 20 %; Amazon 0 %).

Entradas (carpeta DATOS, por defecto la del script o la que se pase como 1er argumento):
  jowua_precios.json   [{"h": handle, "v": [[precio, comparado, disponible], ...]}, ...]   (/es-es/products.json de Jowua, EUR)
  hs_precios.txt       "clave5:min[:max][:X]" separados por espacios/lineas; clave5 = ultimos 5 car. del hash djb2-xor
                       (base 36, 7 posiciones) del handle; importes en centimos (/es-es/products.json de Hansshow, EUR)
  evdance_precios.txt  "handle_completo:min[:max]" (centimos) por linea (eu.evdances.com/es/products.json)
  amazon_precios.txt   "ASIN:41,99" (precio mostrado en amazon.es) separados por espacios/lineas
Uso:  python actualizar_precios.py [carpeta_datos]
"""
import datetime
import json
import re
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
DATOS = Path(sys.argv[1]) if len(sys.argv) > 1 else AQUI
HOY = datetime.date.today().isoformat()


def hash5(handle):
    h = 5381
    for c in handle:
        h = ((h * 33) ^ ord(c)) & 0xFFFFFFFF
    n, s = h, ""
    while n:
        s = "0123456789abcdefghijklmnopqrstuvwxyz"[n % 36] + s
        n //= 36
    return s.rjust(7, "0")[2:]


def cargar(nombre):
    return json.loads((AQUI / nombre).read_text(encoding="utf-8"))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    cat = {}
    for n in ("productos.json", "productos_jowua.json", "productos_hansshow.json", "productos_evdance.json"):
        if (AQUI / n).exists():
            for p in cargar(n):
                if not p.get("pausado"):
                    cat[p["asin"]] = p
    out, faltan = {}, []

    # Jowua
    jw = {}
    f = DATOS / "jowua_precios.json"
    if f.exists():
        for x in json.loads(f.read_text(encoding="utf-8")):
            u = [round(float(v[0]) * 100) for v in x["v"] if v[2]] or [round(float(v[0]) * 100) for v in x["v"]]
            jw[x["h"]] = (min(u), max(u))
    # Jowua 2: fichas HTML (JSON-LD EUR) "hash5:min[:max]" en centimos; el 0 se ignora
    jw2 = {}
    f = DATOS / "jw2_precios.txt"
    if f.exists():
        for t in f.read_text(encoding="utf-8").split():
            k = t.split(":")
            nums = [int(a) for a in k[1:] if a.isdigit() and int(a) > 0]
            if nums:
                jw2[k[0]] = (min(nums), max(nums))
    # Hansshow
    hs = {}
    f = DATOS / "hs_precios.txt"
    if f.exists():
        for t in f.read_text(encoding="utf-8").split():
            k = t.split(":")
            nums = [int(a) for a in k[1:] if a.isdigit()]
            if nums:
                hs[k[0]] = (min(nums), max(nums))
    # EVDANCE
    ev = {}
    f = DATOS / "evdance_precios.txt"
    if f.exists():
        for l in f.read_text(encoding="utf-8").split():
            k = l.split(":")
            ev[k[0]] = (int(k[1]), int(k[2]) if len(k) > 2 else int(k[1]))
    # Amazon
    am = {}
    f = DATOS / "amazon_precios.txt"
    if f.exists():
        for t in f.read_text(encoding="utf-8").split():
            a, _, v = t.partition(":")
            m = re.search(r"(\d[\d.]*),(\d{2})", v)
            if m:
                am[a] = int(m.group(1).replace(".", "")) * 100 + int(m.group(2))

    for aid, p in cat.items():
        tienda = p.get("tienda", "amazon")
        r = None
        if tienda == "amazon" and aid in am:
            r = (am[aid], am[aid])
        elif tienda == "jowua":
            m = re.search(r"/products/([^?/]+)", p.get("url_larga", ""))
            r = (jw.get(m.group(1)) or jw2.get(hash5(m.group(1)))) if m else None
        elif tienda == "hansshow":
            r = hs.get(hash5(aid[len("HANSSHOW-"):]))
        elif tienda == "evdance":
            r = ev.get(aid[len("EVDANCE-"):])
        if r:
            out[aid] = {"p": r[0], "d": 1 if r[1] != r[0] else 0, "f": HOY}
        else:
            faltan.append(aid)
    with open(AQUI / "precios.json", "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(out, ensure_ascii=False, indent=0))
    print(f"{len(out)} precios de {len(cat)} productos activos; sin precio: {len(faltan)}")
    for a in faltan[:30]:
        print("  sin precio:", a)


if __name__ == "__main__":
    main()

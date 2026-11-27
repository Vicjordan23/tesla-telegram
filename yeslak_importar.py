#!/usr/bin/env python3
"""Importa el catalogo de Yeslak (tienda Shopify) filtrado para Model 3 Highland / Model Y Juniper.

Genera, junto a este archivo:
  productos_yeslak.json  (catalogo que leen los publicadores)
  precios_yeslak.json    ({id: {p: centimos EUR minimos, d: 1 si las variantes tienen distinto precio, f: fecha}})
  imagenes_yeslak.json   ({id: foto principal en JPEG cuadrado via wsrv.nl})

Afiliado (panel yeslak.goaffpro.com, 27/11/2026): <url>?ref=Chollesla · codigo VICTORMARTINJUA (15 %) · comision 3 %.
Se excluyen: la etiqueta 'no-discount' y los duplicados «30% OFF» (no admiten el codigo), agotados, tarjetas regalo,
volante a la derecha, y lo que no sea de Highland / Juniper (Cybertruck, Model S/X, 3/Y antiguos, solo Model Y L).

Uso (desde proyecto/):  python yeslak_importar.py
"""
import html
import json
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import quote

from tesery_importar import categoria
from traducir import a_espanol

AQUI = Path(__file__).resolve().parent
TIENDA = "https://www.yeslak.com/es"
REF = "?ref=Chollesla"
FUERA = r"right.?hand|\bRHD\b|gift ?card|gift pack|halloween|christmas|pumpkin|price difference|shipping protection|deposit|pre.?order"


def descargar():
    todos = []
    for pagina in range(1, 40):
        req = urllib.request.Request(f"{TIENDA}/products.json?limit=250&page={pagina}",
                                     headers={"User-Agent": "Mozilla/5.0", "Cookie": "localization=ES"})  # precios en EUR
        with urllib.request.urlopen(req, timeout=60) as r:
            prods = json.loads(r.read().decode("utf-8"))["products"]
        if not prods:
            break
        todos += prods
        time.sleep(1)
    return todos


def modelos(p):
    """'Model ...' segun titulo y etiquetas, o None si no vale para Highland ni Juniper."""
    titulo = p["title"]
    etiquetas = {t.strip().lower() for t in p.get("tags", [])}
    nombra_nuevo = bool(re.search(r"juniper|highland", titulo, re.I))
    juniper = bool(re.search(r"juniper", titulo, re.I)) or bool(etiquetas & {"model y juniper", "model y juniper standard"})
    highland = bool(re.search(r"highland", titulo, re.I)) or bool(etiquetas & {"model 3 highland", "model 3 highland standard"})
    if not nombra_nuevo:
        if re.search(r"20(1[7-9]|2[0-2])\s*[-–~]\s*(20)?2[0-5]\b", titulo):  # 3/Y antiguos
            return None
        otros = re.search(r"cybertruck|model\s?[sx]\b|model\s?y\s?l\b", titulo, re.I)
        if otros and not re.search(r"model\s?(3|y\b(?!\s?l\b))", titulo, re.I):
            return None
    if juniper and highland:
        return "Model Y Juniper y Model 3 Highland"
    if juniper:
        return "Model Y Juniper"
    if highland:
        return "Model 3 Highland"
    return None


def en_espanol(titulo):
    t = a_espanol(html.unescape(titulo))
    t = re.sub(r"^\s*yeslak\s*\|\s*|\s*\|\s*yeslak\s*$", "", t, flags=re.I)
    return re.sub(r"\b[Mm]odelo (3|Y|S|X)\b", r"Model \1", t).strip()


def main():
    hoy = date.today().isoformat()
    crudos = descargar()
    elegidos, vistos = [], set()
    for p in crudos:
        vs = [v for v in p.get("variants", []) if v.get("available")]
        if not vs or "no-discount" in p.get("tags", []) or re.search(r"\d+ ?% ?OFF", p["title"], re.I) or re.search(FUERA, p["title"], re.I):
            continue
        m = modelos(p)
        cent = [round(float(v["price"]) * 100) for v in vs if float(v["price"]) > 0]
        if not m or not cent or p["handle"] in vistos:
            continue
        vistos.add(p["handle"])
        elegidos.append((p, m, cent))
    with ThreadPoolExecutor(6) as ex:
        titulos = list(ex.map(en_espanol, [p["title"] for p, _, _ in elegidos]))
    prods, precios, imgs = [], {}, {}
    for (p, m, cent), titulo in zip(elegidos, titulos):
        pid = f"YESLAK-{p['handle']}"
        emoji, cat = categoria(titulo)
        prods.append({"asin": pid, "tienda": "yeslak", "url": f"{TIENDA}/products/{p['handle']}{REF}", "emoji": emoji,
                      "titulo": titulo, "descripcion": f"{cat} de Yeslak para tu Tesla.", "modelos": m, "pausado": False})
        precios[pid] = {"p": min(cent), "d": 1 if max(cent) != min(cent) else 0, "f": hoy}
        if p.get("images"):
            imgs[pid] = "https://wsrv.nl/?url=" + quote(p["images"][0]["src"], safe="") + "&output=jpg&w=1080&h=1080&fit=contain&cbg=white&q=90"
    for nombre, datos, sangria in (("productos_yeslak.json", prods, 1), ("precios_yeslak.json", precios, None), ("imagenes_yeslak.json", imgs, None)):
        (AQUI / nombre).write_text(json.dumps(datos, ensure_ascii=False, indent=sangria), encoding="utf-8", newline="\n")
    ingles = sum(a == b for a, b in zip(titulos, [p["title"] for p, _, _ in elegidos]))
    print(f"{len(prods)} productos de {len(crudos)}; sin foto: {len(prods) - len(imgs)}; sin traducir: {ingles}")


if __name__ == "__main__":
    main()

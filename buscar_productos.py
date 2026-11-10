#!/usr/bin/env python3
"""Busca accesorios Tesla en Amazon.es con la Creators API y los anade a productos.json.

Variables de entorno (secretos de GitHub, NUNCA en el codigo ni en archivos):
  CREATORS_API_CREDENTIAL_ID, CREATORS_API_CREDENTIAL_SECRET
Opcionales:
  APLICAR=1      escribe productos.json (sin esto solo muestra lo que anadiria)
  MAX_NUEVOS=12  maximo de productos nuevos por ejecucion

Reglas del proyecto: solo ASIN que existen y estan en stock, el titulo debe decir
Tesla + modelo actual (Highland/Juniper/2025/2026), sin precios, enlace solo con
el tag teslaaccesorios-21 (lo pone publicar_siguiente.py). Amazon filtra
minReviewsRating=4 (4 estrellas o mas); la API no devuelve nota ni n.o de opiniones.
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
TAG = "teslaaccesorios-21"
MARKET = "www.amazon.es"
TOKEN_URLS = ["https://api.amazon.co.uk/auth/o2/token", "https://api.amazon.com/auth/o2/token"]
API = "https://creatorsapi.amazon/catalog/v1/searchItems"
MAX_NUEVOS = int(os.environ.get("MAX_NUEVOS", "12"))
APLICAR = os.environ.get("APLICAR", "").lower() in ("1", "true", "yes")

CONSULTAS = [
    "tesla model y juniper accesorios", "tesla model 3 highland accesorios",
    "tesla model y juniper alfombrillas", "tesla model 3 highland alfombrillas",
    "tesla model y juniper maletero", "tesla model y juniper consola central",
    "tesla model y juniper protector pantalla", "tesla model 3 highland protector",
    "tesla model y juniper asiento", "tesla model y juniper luces led",
    "tesla model y juniper funda", "tesla model y juniper organizador",
    "tesla model y juniper soporte", "tesla model 3 highland interior",
    "tesla model y juniper exterior", "tesla model y juniper cable carga",
    "tesla model y juniper parasol", "tesla model y juniper limpieza",
]
ACTUAL = re.compile(r"juniper|highland|2025|2026|nuevo|new model", re.I)
ANTIGUO = re.compile(r"(2017|2018|2019|2020|2021)\s*[-–]\s*(2022|2023)\b")
EXCLUIR = re.compile(r"juguete|miniatura|escala|1[:/]\d{2}|libro|camiseta|taza|peluche|lego|rc\b|mando a distancia|"
                     r"model s\b|model x\b|cybertruck|roadster", re.I)


def post_json(url, cuerpo, cabeceras):
    req = urllib.request.Request(url, data=json.dumps(cuerpo).encode("utf-8"),
                                 headers={"Content-Type": "application/json", **cabeceras}, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def obtener_token():
    cid = os.environ.get("CREATORS_API_CREDENTIAL_ID", "")
    sec = os.environ.get("CREATORS_API_CREDENTIAL_SECRET", "")
    if not cid or not sec:
        sys.exit("Faltan los secretos CREATORS_API_CREDENTIAL_ID / CREATORS_API_CREDENTIAL_SECRET")
    ultimo = ""
    for url in TOKEN_URLS:
        try:
            r = post_json(url, {"grant_type": "client_credentials", "client_id": cid,
                                "client_secret": sec, "scope": "creatorsapi::default"}, {})
            if r.get("access_token"):
                print(f"Token OK ({url.split('/')[2]})")
                return r["access_token"]
            ultimo = f"{url}: sin access_token"
        except urllib.error.HTTPError as e:
            ultimo = f"{url}: HTTP {e.code} {e.read().decode('utf-8', 'replace')[:300]}"
        except Exception as e:  # red, DNS...
            ultimo = f"{url}: {type(e).__name__} {e}"
        print("Token fallo ->", ultimo)
    sys.exit("No se pudo obtener el token. " + ultimo)


def buscar(token, consulta, pagina, rating):
    cuerpo = {
        "partnerTag": TAG, "marketplace": MARKET, "keywords": consulta, "searchIndex": "All",
        "itemCount": 10, "itemPage": pagina, "minReviewsRating": rating, "sortBy": "Relevance",
        "languagesOfPreference": ["es_ES"],
        "resources": ["itemInfo.title", "offersV2.listings.availability"],
    }
    return post_json(API, cuerpo, {"Authorization": f"Bearer {token}", "x-marketplace": MARKET})


def buscar_seguro(token, consulta, pagina):
    for rating in (4, "4"):  # la doc es ambigua: entero o cadena
        try:
            return buscar(token, consulta, pagina, rating)
        except urllib.error.HTTPError as e:
            cuerpo = e.read().decode("utf-8", "replace")[:400]
            if e.code == 429:
                time.sleep(5)
                continue
            if e.code in (401, 403):
                sys.exit(f"Sin acceso a la API (HTTP {e.code}): {cuerpo}")
            print(f"  consulta '{consulta}' rating={rating!r}: HTTP {e.code} {cuerpo}")
    return {}


def en_stock(item):
    ofertas = item.get("offersV2") or {}
    listings = ofertas.get("listings", []) if isinstance(ofertas, dict) else ofertas
    for o in listings:
        if isinstance(o, dict) and (o.get("availability") or {}).get("type") == "IN_STOCK":
            return True
    return False


def titulo_corto(t):
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) <= 95:
        return t
    corte = t[:95].rsplit(" ", 1)[0].rstrip(" ,;:-|(")
    return corte + "…"


def modelos_de(t):
    j, h = re.search(r"juniper", t, re.I), re.search(r"highland", t, re.I)
    if j and h:
        return "Model Y Juniper y Model 3 Highland"
    if j:
        return "Model Y Juniper"
    if h:
        return "Model 3 Highland"
    if re.search(r"model\s*y", t, re.I) and re.search(r"model\s*3", t, re.I):
        return "Model 3 y Model Y (2025-2026)"
    if re.search(r"model\s*y", t, re.I):
        return "Model Y 2025-2026"
    return "Model 3 2024-2026"


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    ruta = AQUI / "productos.json"
    productos = json.loads(ruta.read_text(encoding="utf-8"))
    conocidos = {p["asin"] for p in productos}
    token = obtener_token()
    nuevos, vistos = [], set()
    for q in CONSULTAS:
        if len(nuevos) >= MAX_NUEVOS:
            break
        for pagina in (1, 2):
            r = buscar_seguro(token, q, pagina)
            time.sleep(1.2)  # limite inicial: 1 peticion por segundo
            items = (r.get("searchResult") or {}).get("items") or []
            print(f"'{q}' p{pagina}: {len(items)} resultados")
            for it in items:
                asin = it.get("asin", "")
                t = ((it.get("itemInfo") or {}).get("title") or {}).get("displayValue", "")
                if (not re.fullmatch(r"[A-Z0-9]{10}", asin) or asin in conocidos or asin in vistos
                        or not re.search(r"tesla", t, re.I) or not ACTUAL.search(t)
                        or ANTIGUO.search(t) or EXCLUIR.search(t) or not en_stock(it)):
                    continue
                vistos.add(asin)
                nuevos.append({
                    "asin": asin, "emoji": "🚗", "titulo": titulo_corto(t),
                    "descripcion": "Accesorio para tu Tesla, bien valorado en Amazon.es (4 estrellas o más).",
                    "modelos": modelos_de(t), "pausado": False, "auto": True,
                })
                if len(nuevos) >= MAX_NUEVOS:
                    break
            if len(items) < 10 or len(nuevos) >= MAX_NUEVOS:
                break
    print(f"\nProductos nuevos encontrados: {len(nuevos)}")
    for n in nuevos:
        print(f"  {n['asin']}  {n['modelos']:35}  {n['titulo']}")
    if not nuevos:
        return
    if not APLICAR:
        print("\nModo prueba (APLICAR no activo): no se escribe nada.")
        return
    productos.extend(nuevos)
    ruta.write_text(json.dumps(productos, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"productos.json actualizado: {len(productos)} entradas")


if __name__ == "__main__":
    main()

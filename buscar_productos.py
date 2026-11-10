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
CAND_MAX = MAX_NUEVOS * 4  # se recogen mas candidatos porque luego se filtran por opiniones
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
                     r"model s\b|model x\b|cybertruck|roadster|model\s*y\s*l\b", re.I)


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


GET_ITEMS = "https://creatorsapi.amazon/catalog/v1/getItems"
MIN_OPINIONES = int(os.environ.get("MIN_OPINIONES", "50"))
MIN_ESTRELLAS = float(os.environ.get("MIN_ESTRELLAS", "4.3"))


def detalles(token, asins):
    """Pide nota y n.o de opiniones con getItems. Devuelve {asin: (estrellas, opiniones)}.
    Si la API no da esos datos devuelve {} (y entonces no se anade nada)."""
    salida = {}
    for i in range(0, len(asins), 10):
        lote = asins[i:i + 10]
        cuerpo = {"itemIds": lote, "partnerTag": TAG, "marketplace": MARKET,
                  "resources": ["customerReviews.count", "customerReviews.starRating"]}
        try:
            r = post_json(GET_ITEMS, cuerpo, {"Authorization": f"Bearer {token}", "x-marketplace": MARKET})
        except urllib.error.HTTPError as e:
            print(f"  getItems HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:500]}")
            time.sleep(1.2)
            continue
        time.sleep(1.2)
        items = (r.get("itemsResult") or {}).get("items") or []
        if items and not salida:
            print("  getItems muestra de customerReviews:", json.dumps(items[0].get("customerReviews"))[:300])
        for it in items:
            cr = it.get("customerReviews") or {}
            n = cr.get("count")
            s = cr.get("starRating")
            s = s.get("value") if isinstance(s, dict) else s
            if isinstance(n, (int, float)) and isinstance(s, (int, float)):
                salida[it.get("asin")] = (float(s), int(n))
    return salida


def en_stock(item):
    ofertas = item.get("offersV2") or {}
    listings = ofertas.get("listings", []) if isinstance(ofertas, dict) else ofertas
    for o in listings:
        if isinstance(o, dict) and (o.get("availability") or {}).get("type") == "IN_STOCK":
            return True
    return False


def titulo_corto(t):
    t = re.sub(r"[【】\[\]]", " ", t.split("|")[0])  # quita lo que va tras « | » y los corchetes decorativos
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) <= 95:
        return t
    corte = t[:95].rsplit(" ", 1)[0].rstrip(" ,;:-|(")
    return corte + "…"


def modelos_de(t):
    base = _modelos_base(t)
    if re.search(r"(no|not)\s+(es\s+)?(para|for)\s+(el\s+)?(modelo\s+)?(est[aá]ndar|standard)", t, re.I):
        base += " (no para la versión Standard)"
    return base


def _modelos_base(t):
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
        if len(nuevos) >= CAND_MAX:
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
                if len(nuevos) >= CAND_MAX:
                    break
            if len(items) < 10 or len(nuevos) >= CAND_MAX:
                break
    print(f"\nCandidatos antes de filtrar por opiniones: {len(nuevos)}")
    if not nuevos:
        return
    # La API de Creators no devuelve nota ni n.o de opiniones (comprobado 10/11/2026). Por defecto no se
    # consulta getItems; la calidad la garantiza el filtro minReviewsRating=4 de la busqueda.
    datos = detalles(token, [n["asin"] for n in nuevos]) if os.environ.get("USAR_GETITEMS") else {}
    if not datos:
        nuevos = nuevos[:MAX_NUEVOS]
        print("Sin datos de opiniones: se confia en el filtro de 4 estrellas de Amazon.")
        for n in nuevos:
            print(f"  {n['asin']}  {n['modelos']:35}  {n['titulo']}")
        if not nuevos or not APLICAR:
            print("\nModo prueba (APLICAR no activo): no se escribe nada.")
            return
        productos.extend(nuevos)
        ruta.write_text(json.dumps(productos, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"productos.json actualizado: {len(productos)} entradas")
        return
    buenos = []
    for n in nuevos:
        est, num = datos.get(n["asin"], (0.0, 0))
        marca = "OK " if est >= MIN_ESTRELLAS and num >= MIN_OPINIONES else "no "
        print(f"  {marca}{n['asin']}  {est:.1f} estrellas, {num} opiniones  {n['titulo']}")
        if marca == "OK ":
            n["descripcion"] = "Accesorio para tu Tesla muy bien valorado por los compradores de Amazon.es."
            buenos.append(n)
    nuevos = buenos[:MAX_NUEVOS]
    print(f"\nProductos nuevos que cumplen (>= {MIN_ESTRELLAS} estrellas y >= {MIN_OPINIONES} opiniones): {len(nuevos)}")
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

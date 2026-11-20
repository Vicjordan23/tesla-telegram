#!/usr/bin/env python3
"""Productos Tesla de AliExpress con la API de afiliados (AliExpress Open Platform, app «botize aliexpress», Affiliates API).

Lee las claves de las variables de entorno (secretos de GitHub; nunca en archivos):
  ALIEXPRESS_APP_KEY, ALIEXPRESS_APP_SECRET
  ALIEXPRESS_TRACKING_ID (opcional, por defecto «enlace_id», el ID de rastreo por defecto del portal)
  APLICAR=1  -> escribe aliexpress_raw.json y ejecuta aliexpress_importar.py (productos/precios/imagenes_aliexpress.json)
  MAX_PAGINAS (opcional, por defecto 20 por busqueda, 50 productos por pagina)

Sin APLICAR solo prueba: una pagina de una busqueda + un enlace, y un resumen. No imprime nunca las claves.

API: POST https://api-sg.aliexpress.com/sync, firma HMAC-SHA256 (clave = App Secret) de los parametros ordenados
por nombre y concatenados nombre+valor, en hexadecimal mayusculas.
  aliexpress.affiliate.product.query  (keywords, ship_to_country=ES, target_currency=EUR, target_language=ES,
                                       sort=LAST_VOLUME_DESC, tracking_id) -> devuelve promotion_link (enlace de afiliado)
  aliexpress.affiliate.link.generate  (source_values, promotion_link_type=0, tracking_id) -> para los que no traen enlace
"""
import hashlib
import hmac
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
URL = "https://api-sg.aliexpress.com/sync"
BUSQUEDAS = ["tesla", "tesla model 3", "tesla model y", "model 3 highland", "model y juniper",
             "tesla accesorios", "tesla model y 2025", "tesla model 3 2024"]


def firmar(params, secreto, modo="sha256"):
    texto = "".join(k + str(params[k]) for k in sorted(params))
    if modo == "md5":  # firma TOP antigua: md5(secreto + texto + secreto)
        return hashlib.md5((secreto + texto + secreto).encode("utf-8")).hexdigest().upper()
    return hmac.new(secreto.encode("utf-8"), texto.encode("utf-8"), hashlib.sha256).hexdigest().upper()


MODO = {"firma": None}  # se fija con la primera llamada que funciona


def _params(metodo, negocio, clave, modo):
    if modo == "md5":  # protocolo TOP: hora de Pekin en texto, v=2.0, format=json
        hora = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(time.time() + 8 * 3600))
        p = {"app_key": clave, "method": metodo, "timestamp": hora, "sign_method": "md5", "v": "2.0", "format": "json"}
    else:
        p = {"app_key": clave, "method": metodo, "timestamp": str(int(time.time() * 1000)), "sign_method": "sha256"}
    p.update({k: str(v) for k, v in negocio.items()})
    return p


def llamar(metodo, negocio, clave, secreto):
    modos = [MODO["firma"]] if MODO["firma"] else ["sha256", "md5"]
    for modo in modos:
        params = _params(metodo, negocio, clave, modo)
        params["sign"] = firmar(params, secreto, modo)
        req = urllib.request.Request(URL, data=urllib.parse.urlencode(params).encode("utf-8"),
                                     headers={"Content-Type": "application/x-www-form-urlencoded;charset=utf-8"})
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read().decode("utf-8"))
        codigo = str((resp.get("error_response") or {}).get("code", ""))
        if "Signature" in codigo and modo != modos[-1]:
            print(f"Firma {modo} rechazada ({codigo}); pruebo la siguiente")
            continue
        if not MODO["firma"] and "Signature" not in codigo:
            MODO["firma"] = modo
            print(f"Firma aceptada: {modo}")
        return resp
    return resp


def resultado(respuesta, nombre):
    """Devuelve result de resp_result o lanza un error legible (sin claves)."""
    if "error_response" in respuesta:
        e = respuesta["error_response"]
        raise RuntimeError(f"API error {e.get('code')}: {e.get('msg')} {e.get('sub_code', '')} {e.get('sub_msg', '')}".strip())
    rr = respuesta.get(nombre, {}).get("resp_result", {})
    if str(rr.get("resp_code")) != "200":
        raise RuntimeError(f"resp_code {rr.get('resp_code')}: {rr.get('resp_msg')} | claves: {list(respuesta)[:3]}")
    return rr.get("result") or {}


def centimos(v):
    try:
        return int(round(float(str(v).replace(",", ".")) * 100))
    except (TypeError, ValueError):
        return 0


def a_raw(p):
    return {
        "id": str(p.get("product_id")),
        "t": p.get("product_title", ""),
        "p": centimos(p.get("target_sale_price") or p.get("sale_price")),
        "po": centimos(p.get("target_original_price") or p.get("original_price")),
        "c": str(p.get("commission_rate", "")).rstrip("%"),
        "v": int(p.get("lastest_volume") or 0),
        "s": str(p.get("evaluate_rate", "")),
        "img": p.get("product_main_image_url", ""),
        "l": p.get("promotion_link", ""),
    }


def buscar(q, pagina, clave, secreto, tracking):
    res = resultado(llamar("aliexpress.affiliate.product.query", {
        "keywords": q, "page_no": pagina, "page_size": 50, "ship_to_country": "ES", "target_currency": "EUR",
        "target_language": "ES", "sort": "LAST_VOLUME_DESC", "tracking_id": tracking,
    }, clave, secreto), "aliexpress_affiliate_product_query_response")
    return [a_raw(p) for p in (res.get("products") or {}).get("product", [])], res.get("total_record_count")


def enlaces(ids, clave, secreto, tracking):
    """{id: enlace} para productos sin promotion_link, de 20 en 20."""
    salida = {}
    for i in range(0, len(ids), 20):
        trozo = ids[i:i + 20]
        res = resultado(llamar("aliexpress.affiliate.link.generate", {
            "promotion_link_type": 0, "tracking_id": tracking,
            "source_values": ",".join(f"https://es.aliexpress.com/item/{x}.html" for x in trozo),
        }, clave, secreto), "aliexpress_affiliate_link_generate_response")
        for e in (res.get("promotion_links") or {}).get("promotion_link", []):
            for x in trozo:
                if x in e.get("source_value", ""):
                    salida[x] = e.get("promotion_link", "")
        time.sleep(0.5)
    return salida


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    crudo_c, crudo_s = os.environ.get("ALIEXPRESS_APP_KEY", ""), os.environ.get("ALIEXPRESS_APP_SECRET", "")
    clave, secreto = crudo_c.strip(), crudo_s.strip()
    if (clave, secreto) != (crudo_c, crudo_s):
        print("Aviso: el App Key o el App Secret guardados tenian espacios o saltos de linea al principio/final (se han quitado)")
    print(f"App Key: {len(clave)} caracteres, solo digitos: {clave.isdigit()}; App Secret: {len(secreto)} caracteres")
    tracking = os.environ.get("ALIEXPRESS_TRACKING_ID") or "enlace_id"
    if not clave or not secreto:
        sys.exit("Faltan ALIEXPRESS_APP_KEY / ALIEXPRESS_APP_SECRET (secretos de GitHub)")
    aplicar = bool(os.environ.get("APLICAR"))
    max_pag = int(os.environ.get("MAX_PAGINAS") or 20)

    if not aplicar:  # prueba: 1 pagina + 1 enlace
        prods, total = buscar("tesla model y juniper", 1, clave, secreto, tracking)
        print(f"PRUEBA OK: {len(prods)} productos en la pagina 1 (total segun la API: {total}); tracking_id={tracking}")
        for p in prods[:5]:
            print(f"  {p['id']} | {p['p'] / 100:.2f} EUR | comision {p['c']} % | ventas30 {p['v']} | enlace {'SI' if p['l'] else 'NO'} | {p['t'][:70]}")
        if prods:
            e = enlaces([prods[0]["id"]], clave, secreto, tracking)
            print("link.generate:", "OK " + e[prods[0]["id"]] if e.get(prods[0]["id"]) else "sin enlace")
        return

    todos = {}
    for q in BUSQUEDAS:
        for pag in range(1, max_pag + 1):
            try:
                prods, _ = buscar(q, pag, clave, secreto, tracking)
            except Exception as e:
                print(f"{q} p{pag}: {e}")
                break
            nuevos = 0
            for p in prods:
                if p["id"] not in todos:
                    todos[p["id"]] = p
                    nuevos += 1
            print(f"{q} p{pag}: {len(prods)} (+{nuevos})")
            if not prods or max(p["v"] for p in prods) == 0:  # ordenado por ventas: lo que sigue ya no vende
                break
            time.sleep(0.5)
    # Enlace CORTO (s.click.aliexpress.com/e/_xxx) para todos: el promotion_link de product.query mide ~1.000 caracteres
    # (demasiado para Pinterest y los botones de Telegram). Si link.generate falla, se queda el largo.
    cortos = {}
    try:
        cortos = enlaces(list(todos), clave, secreto, tracking)
    except Exception as e:
        print(f"link.generate: {e}")
    for i, l in cortos.items():
        if l:
            todos[i]["l"] = l
    print(f"Total {len(todos)} productos; con enlace de afiliado {sum(1 for p in todos.values() if p['l'])}; "
          f"cortos {sum(1 for p in todos.values() if '/e/' in p['l'])}")
    (AQUI / "aliexpress_raw.json").write_text(json.dumps(list(todos.values()), ensure_ascii=False), encoding="utf-8")
    import aliexpress_importar
    sys.argv = [sys.argv[0]]
    aliexpress_importar.main()


if __name__ == "__main__":
    main()

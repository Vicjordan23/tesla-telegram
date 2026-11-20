#!/usr/bin/env python3
"""Convierte aliexpress_raw.json (sacado del portal de afiliados portals.aliexpress.com con Chrome:
buscador del «Centro de anuncios» + «Generador de enlaces» con el ID de rastreo enlace_id) en:
  productos_aliexpress.json  (catalogo con el mismo formato que productos_tesery.json; tienda = "aliexpress")
  precios_aliexpress.json    ({id: {p: centimos, d: 1, f: fecha}}; d=1 porque AliExpress da el precio minimo de las variantes)
  imagenes_aliexpress.json   ({id: url de la foto principal})

Formato de aliexpress_raw.json: lista de {id, t (titulo), p (centimos con descuento, envio a ES), po (centimos sin descuento),
c (comision %), v (ventas: lastest_volume de la API; no se afirma un periodo concreto), s (puntuacion de AliExpress, NO se publica),
img, l (enlace corto de afiliado s.click o "")}.

Reglas: solo Model 3 / Model Y; fuera lo que solo nombra Cybertruck, Model S o Model X. Activo (pausado=false) solo si
el titulo dice Highland, Juniper o un ano 2024-2026 (compatibilidad de la regla de Vic) Y tiene enlace de afiliado.
No se publican puntuaciones (la regla de Vic prohibe estrellas/notas); las ventas de 30 dias son un dato real de AliExpress.

Uso (desde proyecto/):  python aliexpress_importar.py [AAAA-MM-DD]
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

AQUI = Path(__file__).resolve().parent

CATEGORIAS = [
    (r"parasol|sombrilla|techo solar|techo de cristal|sunshade", "☀️", "Parasol"),
    (r"ambiental|ambient|luz|luces|led|iluminaci|l[aá]mpara", "💡", "Iluminación"),
    (r"alfombrilla|alfombra|esterilla", "🧽", "Alfombrillas"),
    (r"protector de pantalla|vidrio templado|cristal templado|pel[ií]cula.*pantalla", "📱", "Protector de pantalla"),
    (r"volante|yoke", "🎛️", "Volante"),
    (r"carga|cargador|nacs|cable|adaptador|usb|magsafe|hub", "🔌", "Carga y conexión"),
    (r"reposabrazos|consola|organizador|almacenamiento|caja|bandeja|caj[oó]n|gancho", "🗄️", "Almacenamiento y organización"),
    (r"pedal", "🦶", "Pedales"),
    (r"guardabarros|salpicadero|aleta|faldilla", "🛞", "Protección exterior"),
    (r"puerta|manija|manilla|umbral", "🚪", "Puertas"),
    (r"maletero|frunk|port[oó]n|trasero", "🧳", "Maletero"),
    (r"asiento|reposacabezas|funda", "💺", "Asientos"),
    (r"rueda|llanta|neum[aá]tico|tapacubos|v[aá]lvula", "🛞", "Ruedas"),
    (r"c[aá]mara|espejo|retrovisor", "📷", "Cámaras y espejos"),
    (r"altavoz|audio|sonido", "🔊", "Audio"),
    (r"fibra de carbono|aler[oó]n|spoiler|difusor|emblema|adhesivo|vinilo|pel[ií]cula|pegatina|embellecedor", "🏁", "Estética y protección"),
    (r"soporte|m[oó]vil|tel[eé]fono|tablet", "📱", "Soportes"),
]

SOLO_SXC = re.compile(r"cybertruck|model\s?[sx]\b", re.I)
TRES_Y = re.compile(r"model\s?[3y]\b|modelo\s?[3y]\b|highland|juniper|\b3\s*/\s*y\b|\by\s*/\s*3\b|\bm[3y]\b", re.I)
NUEVOS = re.compile(r"highland|juniper|2024|2025|2026", re.I)


def modelos(t):
    h = re.search(r"highland|model\s?3[^a-z]{0,25}(2024|2025|2026)", t, re.I)
    j = re.search(r"juniper|model\s?y[^a-z]{0,25}(2025|2026)", t, re.I)
    if h and j:
        return "Model 3 Highland y Model Y Juniper (revisa la variante en la ficha)"
    if h:
        return "Model 3 Highland (revisa la variante en la ficha)"
    if j:
        return "Model Y Juniper (revisa la variante en la ficha)"
    return "Tesla Model 3 / Model Y (consulta la compatibilidad en la ficha)"


def categoria(t):
    for patron, emoji, nombre in CATEGORIAS:
        if re.search(patron, t, re.I):
            return emoji, nombre
    return "🔧", "Accesorio"


def titulo_corto(t, n=110):
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) <= n:
        return t
    return t[:n].rsplit(" ", 1)[0].rstrip(",;:-") + "…"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    hoy = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    raw = json.loads((AQUI / "aliexpress_raw.json").read_text(encoding="utf-8"))
    prods, precios, imgs = [], {}, {}
    cuenta = {"total": len(raw), "solo S/X/Cybertruck": 0, "no es Model 3/Y": 0, "sin precio": 0, "activos": 0, "pausados": 0}
    for x in sorted(raw, key=lambda r: (-int(r.get("v") or 0), r["id"])):
        t = x["t"]
        if SOLO_SXC.search(t) and not TRES_Y.search(t):
            cuenta["solo S/X/Cybertruck"] += 1
            continue
        if not TRES_Y.search(t) and not re.search(r"tesla", t, re.I):
            cuenta["no es Model 3/Y"] += 1
            continue
        if not x.get("p"):
            cuenta["sin precio"] += 1
            continue
        pid = "ae" + str(x["id"])
        emoji, cat = categoria(t)
        activo = bool(x.get("l")) and bool(NUEVOS.search(t))
        ventas = int(x.get("v") or 0)
        desc = f"{cat} para Tesla en AliExpress (envío a España)."
        if ventas:
            desc += f" {ventas:,} pedidos según AliExpress.".replace(",", ".")
        prods.append({
            "asin": pid,
            "tienda": "aliexpress",
            "emoji": emoji,
            "titulo": titulo_corto(t),
            "descripcion": desc,
            "modelos": modelos(t),
            "url": x.get("l") or f"https://es.aliexpress.com/item/{x['id']}.html",
            "comision": x.get("c"),
            "ventas30": ventas,
            "pausado": not activo,
        })
        precios[pid] = {"p": int(x["p"]), "d": 1, "f": hoy}
        if x.get("img"):
            imgs[pid] = x["img"]
        cuenta["activos" if activo else "pausados"] += 1
    for nombre, datos in (("productos_aliexpress.json", prods), ("precios_aliexpress.json", precios), ("imagenes_aliexpress.json", imgs)):
        (AQUI / nombre).write_text(json.dumps(datos, ensure_ascii=False, indent=1 if nombre.startswith("productos") else None), encoding="utf-8")
    print(json.dumps(cuenta, ensure_ascii=False))


if __name__ == "__main__":
    main()

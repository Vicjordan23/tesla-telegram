#!/usr/bin/env python3
"""Convierte tesery_productos.tsv (sacado de tesery.com/es-es/products.json con Chrome, filtrado por etiquetas
Model Y Juniper / Model 3 Highland / Model Y Standard / New Model Y) en:
  productos_tesery.json  (catalogo que leen publicar_siguiente.py, publicar_facebook.py y publicar_instagram.py)
  precios_tesery.json    ({id: {p: centimos minimos, d: 1 si hay varias variantes con distinto precio, f: fecha}})
  imagenes_tesery.json   ({id: url de la foto principal}, para Instagram)

Columnas del TSV (separadas por |): handle|titulo|precio_min|precio_max|disponible|etiquetas|imagen
Enlace de afiliado (el que genera el panel affiliate.tesery.com): <url>?ref=AccesoriosTesla&utm_medium=affiliate&utm_source=goaffpro
Descuento de Vic: 5 % con el codigo ACCESORIOSTESLA. Comision del programa: 2 %.
Excluye lo que solo nombra Cybertruck, Model S o Model X (ya no se venden en Espana).

Uso (desde proyecto/):  python tesery_importar.py [AAAA-MM-DD]
"""
import json
import re
import sys
from datetime import date
from pathlib import Path
from urllib.parse import quote

AQUI = Path(__file__).resolve().parent
BASE = "https://www.tesery.com/es-es/products/"
REF = "?ref=AccesoriosTesla&utm_medium=affiliate&utm_source=goaffpro"

CATEGORIAS = [
    (r"parasol|sunshade|techo solar|techo de cristal", "☀️", "Parasol"),
    (r"ambiental|ambient|luz|luces|led|iluminaci", "💡", "Iluminación"),
    (r"alfombrilla|alfombra|floor", "🧽", "Alfombrillas"),
    (r"protector de pantalla|vidrio templado|cristal templado", "📱", "Protector de pantalla"),
    (r"volante|yoke", "🎛️", "Volante"),
    (r"carga|cargador|nacs|cable|adaptador|usb|magsafe", "🔌", "Carga y conexión"),
    (r"reposabrazos|consola|organizador|almacenamiento|caja|bandeja|cajón|gancho", "🗄️", "Almacenamiento y organización"),
    (r"pedal", "🦶", "Pedales"),
    (r"guardabarros|salpicadero|aleta", "🛞", "Protección exterior"),
    (r"puerta|manija|manilla|umbral", "🚪", "Puertas"),
    (r"maletero|frunk|portón|trasero", "🧳", "Maletero"),
    (r"asiento|reposacabezas|funda", "💺", "Asientos"),
    (r"rueda|llanta|neumático|tapacubos|válvula", "🛞", "Ruedas"),
    (r"cámara|espejo|retrovisor", "📷", "Cámaras y espejos"),
    (r"altavoz|audio|sonido", "🔊", "Audio"),
    (r"fibra de carbono|alerón|spoiler|difusor|emblema|adhesivo|vinilo|película|pegatina", "🏁", "Estética y protección"),
    (r"soporte|móvil|teléfono|tablet", "📱", "Soportes"),
]


def modelos(titulo, tags):
    t = {x.strip().lower() for x in tags.split(";") if x.strip()}
    juniper = bool(t & {"model y juniper", "new model y", "model y standard"})
    highland = "model 3 highland" in t
    if juniper and highland:
        return "Model Y Juniper y Model 3 Highland"
    if juniper:
        return "Model Y Juniper"
    if highland:
        return "Model 3 Highland"
    return "Tesla (consulta la compatibilidad en la ficha)"


def categoria(titulo):
    for patron, emoji, nombre in CATEGORIAS:
        if re.search(patron, titulo, re.I):
            return emoji, nombre
    return "🔧", "Accesorio"


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    hoy = sys.argv[1] if len(sys.argv) > 1 else date.today().isoformat()
    filas = [l.split("|") for l in (AQUI / "tesery_productos.tsv").read_text(encoding="utf-8-sig").splitlines() if l.count("|") >= 6]
    prods, precios, imgs, vistos = [], {}, {}, set()
    descartados = {"solo S/X/Cybertruck": 0, "sin precio": 0, "repetido": 0}
    for handle, titulo, pmin, pmax, disp, tags, img in [f[:7] for f in filas]:
        if handle in vistos:
            descartados["repetido"] += 1
            continue
        if re.search(r"cybertruck|model\s?[sx]\b|model\s?s\s*/\s*x", titulo, re.I) and not re.search(r"model\s?[3y]\b|highland|juniper|3\s*/\s*y|y\s*/\s*3", titulo, re.I):
            descartados["solo S/X/Cybertruck"] += 1
            continue
        if not pmin.isdigit() or int(pmin) <= 0:
            descartados["sin precio"] += 1
            continue
        vistos.add(handle)
        pid = f"TESERY-{handle}"
        emoji, cat = categoria(titulo)
        prods.append({
            "asin": pid,
            "tienda": "tesery",
            "url": f"{BASE}{handle}{REF}",
            "emoji": emoji,
            "titulo": titulo.strip(),
            "descripcion": f"{cat} de Tesery para tu Tesla.",
            "modelos": modelos(titulo, tags),
            "pausado": disp != "1" or bool(re.search(r"halloween|calabaza", titulo, re.I)),
        })
        precios[pid] = {"p": int(pmin), "d": 1 if pmax != pmin else 0, "f": hoy}
        if img.startswith("http"):  # Instagram pide JPEG y proporcion 0,8-1,91: lienzo cuadrado blanco via wsrv.nl
            imgs[pid] = "https://wsrv.nl/?url=" + quote(img, safe="") + "&output=jpg&w=1080&h=1080&fit=contain&cbg=white&q=90"
    (AQUI / "productos_tesery.json").write_text(json.dumps(prods, ensure_ascii=False, indent=1), encoding="utf-8")
    (AQUI / "precios_tesery.json").write_text(json.dumps(precios, ensure_ascii=False), encoding="utf-8")
    (AQUI / "imagenes_tesery.json").write_text(json.dumps(imgs, ensure_ascii=False), encoding="utf-8")
    act = sum(not p["pausado"] for p in prods)
    print(f"{len(prods)} productos ({act} activos) de {len(filas)} filas; descartados: {descartados}")


if __name__ == "__main__":
    main()

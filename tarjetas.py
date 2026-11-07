#!/usr/bin/env python3
"""Genera un carrusel de 4 tarjetas (1080x1350, PNG) por producto con Pillow, sin fotos de Amazon.

Uso:  python tarjetas.py B0GKJZGGWZ [otro_asin ...]   (sin argumentos: la franja actual, como Telegram)
Salida: tarjetas/<ASIN>_1.png ... _4.png
Tarjetas: 1 titulo, 2 compatibilidad, 3 lo que dicen los compradores, 4 donde conseguirlo.
"""
import json
import random
import sys
import textwrap
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

AQUI = Path(__file__).resolve().parent
SALIDA = AQUI / "tarjetas"
W, H = 1080, 1350
FONDO, ROJO, BLANCO, GRIS = (16, 17, 20), (227, 25, 55), (255, 255, 255), (170, 172, 180)
NEGRITA = ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
NORMAL = ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"]


def fuente(lista, tam):
    for f in lista:
        try:
            return ImageFont.truetype(f, tam)
        except OSError:
            continue
    return ImageFont.load_default()


def sin_emoji(t):
    return "".join(c for c in t if ord(c) < 0x2000 or ord(c) in (0x2026, 0x20AC)).strip()


def base(num, total=4):
    img = Image.new("RGB", (W, H), FONDO)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 14], fill=ROJO)
    d.text((72, 70), "ACCESORIOS TESLA ESPAÑA", font=fuente(NEGRITA, 34), fill=ROJO)
    d.text((W - 72, 70), f"{num}/{total}", font=fuente(NORMAL, 34), fill=GRIS, anchor="ra")
    d.rectangle([72, H - 120, W - 72, H - 118], fill=(50, 52, 58))
    d.text((72, H - 95), "t.me/teslaaccesorios", font=fuente(NORMAL, 32), fill=GRIS)
    return img, d


def bloque(d, texto, y, tam, color, ancho_car, negrita=True, interlinea=1.25, x=72):
    f = fuente(NEGRITA if negrita else NORMAL, tam)
    for linea in textwrap.wrap(texto, ancho_car) or [""]:
        d.text((x, y), linea, font=f, fill=color)
        y += int(tam * interlinea)
    return y


def generar(p, opinion):
    SALIDA.mkdir(exist_ok=True)
    titulo, modelos, desc = sin_emoji(p["titulo"]), sin_emoji(p["modelos"]), sin_emoji(p["descripcion"])
    imagenes = []

    img, d = base(1)
    y = bloque(d, titulo, 420, 92, BLANCO, 16, interlinea=1.15)
    d.rectangle([72, y + 30, 272, y + 38], fill=ROJO)
    bloque(d, desc, y + 90, 40, GRIS, 38, negrita=False)
    imagenes.append(img)

    img, d = base(2)
    d.text((72, 360), "COMPATIBLE CON", font=fuente(NEGRITA, 44), fill=ROJO)
    bloque(d, modelos, 450, 78, BLANCO, 20, interlinea=1.2)
    imagenes.append(img)

    img, d = base(3)
    d.text((72, 360), "LO QUE DICEN LOS COMPRADORES", font=fuente(NEGRITA, 44), fill=ROJO)
    if opinion:
        bloque(d, opinion.replace("Los compradores", "Compradores"), 450, 46, BLANCO, 34, negrita=False, interlinea=1.4)
        d.text((72, H - 190), "Resumen de las opiniones de Amazon.es", font=fuente(NORMAL, 30), fill=GRIS)
    else:
        bloque(d, desc, 450, 52, BLANCO, 30, negrita=False, interlinea=1.4)
    imagenes.append(img)

    img, d = base(4)
    d.text((72, 360), "DÓNDE CONSEGUIRLO", font=fuente(NEGRITA, 44), fill=ROJO)
    y = bloque(d, "Enlace directo a Amazon.es en el canal de Telegram", 450, 70, BLANCO, 22, interlinea=1.2)
    d.text((72, y + 40), "t.me/teslaaccesorios", font=fuente(NEGRITA, 64), fill=ROJO)
    bloque(d, "Enlace de afiliado de Amazon: a ti no te cuesta nada más.", y + 170, 34, GRIS, 52, negrita=False)
    imagenes.append(img)

    salida = []
    for i, im in enumerate(imagenes, 1):
        r = SALIDA / f"{p['asin']}_{i}.jpg"
        im.convert("RGB").save(r, quality=92)  # Instagram solo acepta JPEG
        salida.append(r)
    return salida


def main():
    productos = [p for p in json.loads((AQUI / "productos.json").read_text(encoding="utf-8")) if not p.get("pausado")]
    try:
        ops = json.loads((AQUI / "opiniones.json").read_text(encoding="utf-8"))
    except Exception:
        ops = {}
    asins = sys.argv[1:]
    if asins == ["--todas"]:
        asins = [p["asin"] for p in productos]
    elif not asins:
        orden = sorted(p["asin"] for p in productos)
        random.Random(2026).shuffle(orden)
        asins = [orden[int(time.time() // 1800) % len(orden)]]
    for a in asins:
        p = next(x for x in productos if x["asin"] == a)
        for r in generar(p, ops.get(a, "")):
            print(r)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Historial minimo de precios para detectar BAJADAS REALES (solo datos guardados, nada inventado).

Se ejecuta justo despues de actualizar_precios_web.py (workflow "Actualizar precios"): compara los precios actuales
(precios.json, precios_tesery.json, precios_aliexpress.json) con lo guardado en historial_precios.json y registra:
  p    precio actual (centimos, el de la tienda, sin codigo)        f    fecha de ese precio
  ant  precio anterior distinto (si cambio)  fant  su fecha         fc   dia en que se detecto el cambio
  alta dia en que el producto aparecio por primera vez (solo si ya existia historial: asi no hay falsas novedades)
Los publicadores (publicar_siguiente.py) leen este archivo: «ha bajado» solo si ant > p y fc es reciente.

Uso:  python historial_precios.py [--hoy AAAA-MM-DD] [--prueba]
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
ARCHIVOS = ("precios.json", "precios_tesery.json", "precios_aliexpress.json")
SALIDA = "historial_precios.json"


def aplicar(hist, precios, hoy):
    """Actualiza hist con un conjunto de precios {id: {p, d, f}} observado en la fecha hoy. Devuelve (cambios, altas)."""
    cambios = altas = 0
    nuevo_historial = "_inicio" in hist
    for pid, d in precios.items():
        h = hist.get(pid)
        if h is None:
            hist[pid] = {"p": d["p"], "f": d["f"]}
            if nuevo_historial:
                hist[pid]["alta"] = hoy
                altas += 1
        elif h["p"] != d["p"]:
            h["ant"], h["fant"], h["p"], h["f"], h["fc"] = h["p"], h["f"], d["p"], d["f"], hoy
            cambios += 1
        else:
            h["f"] = d["f"]
    return cambios, altas


def main():
    args = sys.argv[1:]
    hoy = args[args.index("--hoy") + 1] if "--hoy" in args else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    f = AQUI / SALIDA
    hist = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    primera_vez = "_inicio" not in hist
    total_c = total_a = 0
    for nombre in ARCHIVOS:
        try:
            precios = json.loads((AQUI / nombre).read_text(encoding="utf-8"))
        except Exception as e:
            print(f"{nombre}: no se pudo leer ({e})")
            continue
        c, a = aplicar(hist, precios, hoy)
        total_c += c
        total_a += a
        print(f"{nombre}: {len(precios)} precios, {c} cambios, {a} altas")
    if primera_vez:
        hist["_inicio"] = hoy
    bajadas = sum(1 for k, h in hist.items() if k != "_inicio" and h.get("ant") and h["ant"] > h["p"] and h.get("fc") == hoy)
    print(f"Historial: {len(hist) - 1} productos; hoy {bajadas} bajadas, {total_c} cambios, {total_a} altas")
    if "--prueba" in args:
        print("Modo prueba: no se escribe nada.")
        return
    f.write_text(json.dumps(hist, ensure_ascii=False, separators=(",", ":"), sort_keys=True), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()

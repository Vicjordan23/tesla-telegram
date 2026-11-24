#!/usr/bin/env python3
"""Actualiza precios_temu.json con los precios leidos del panel de afiliados de Temu.

Temu no tiene API: la tarea semanal (lunes) abre el panel de afiliados en Chrome, busca los productos de Tesla,
lee el «Precio de afiliado» de cada uno y escribe un JSON con la lista:
  [{"codigo": "egx31wo9tyr", "precio": "4,02"}, ...]      (codigo = lo que va tras temu.to/k/ ; precio en euros)

Uso:
  python actualizar_temu.py datos.json            aplica los precios (escribe precios_temu.json)
  python actualizar_temu.py datos.json --prueba   solo muestra los cambios

Reglas: solo se tocan productos que ya estan en productos_temu.json; los que no aparecen en datos.json NO se
actualizan (su fecha queda vieja y la web los oculta a los 10 dias); un cambio de precio de mas del 60 % se
rechaza y se avisa (probable lectura mala o cambio de variante). Imprime un resumen y sale con 1 si hay avisos.
"""
import json
import sys
from datetime import date
from pathlib import Path

AQUI = Path(__file__).resolve().parent


def euros_a_centimos(texto):
    return int(round(float(str(texto).replace("€", "").replace(".", "").replace(",", ".").strip()) * 100))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    prueba = "--prueba" in sys.argv
    if not args:
        sys.exit(__doc__)
    datos = json.loads(Path(args[0]).read_text(encoding="utf-8"))
    productos = json.loads((AQUI / "productos_temu.json").read_text(encoding="utf-8"))
    por_codigo = {p["url"].rsplit("/", 1)[-1]: p["asin"] for p in productos}
    precios = json.loads((AQUI / "precios_temu.json").read_text(encoding="utf-8"))
    hoy = date.today().isoformat()
    avisos, cambios, vistos = [], 0, set()
    for d in datos:
        cod = d["codigo"].strip()
        pid = por_codigo.get(cod)
        if not pid:
            avisos.append(f"{cod}: no esta en productos_temu.json (ignorado)")
            continue
        try:
            nuevo = euros_a_centimos(d["precio"])
        except Exception:
            avisos.append(f"{cod}: precio ilegible {d.get('precio')!r}")
            continue
        vistos.add(pid)
        viejo = precios.get(pid, {}).get("p")
        if viejo and abs(nuevo - viejo) / viejo > 0.60:
            avisos.append(f"{cod}: cambio de {viejo / 100:.2f} a {nuevo / 100:.2f} euros (>60 %), NO aplicado")
            continue
        if viejo != nuevo:
            cambios += 1
            print(f"{pid}: {(viejo or 0) / 100:.2f} -> {nuevo / 100:.2f} EUR")
        precios[pid] = {"p": nuevo, "d": 0, "f": hoy}
    for pid in precios:
        if pid not in vistos:
            avisos.append(f"{pid}: no salio en el panel esta semana (fecha sin actualizar)")
    print(f"{len(vistos)} actualizados, {cambios} con precio nuevo, {len(avisos)} avisos")
    for a in avisos:
        print("AVISO:", a)
    if not prueba:
        (AQUI / "precios_temu.json").write_text(json.dumps(precios, ensure_ascii=False), encoding="utf-8")
    sys.exit(1 if avisos else 0)


if __name__ == "__main__":
    main()

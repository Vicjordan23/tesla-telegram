#!/usr/bin/env python3
"""Publica el SIGUIENTE producto de productos.json en el canal de Telegram.

Pensado para ejecutarse cada 30 minutos (Programador de tareas de Windows).
Solo usa la biblioteca estandar. Las claves van en .env (nunca en este archivo).

Uso:
  python publicar_siguiente.py            publica el siguiente (respeta VENTANA)
  python publicar_siguiente.py --prueba   muestra el mensaje sin enviarlo
  python publicar_siguiente.py --forzar   publica aunque este fuera de la ventana
  python publicar_siguiente.py --aviso    envia el aviso de afiliado (para fijarlo)
"""
import html
import json
import os
import random
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
TAG = "teslaaccesorios-21"
FACEBOOK = "https://www.facebook.com/profile.php?id=61596316649956"
AVISO = (
    "🚗⚡ <b>Accesorios Tesla Model 3 y Model Y</b>\n\n"
    "Cada 30 minutos, un accesorio para tu Tesla de tres tiendas: Amazon.es, Jowua y Hansshow.\n\n"
    "🏷️ Descuentos: 5 % en Jowua con el código ACCESORIOSTESLA y 20 % en Hansshow con el código VICTOR.\n\n"
    "<i>Enlaces de afiliado. En calidad de Afiliado de Amazon, obtengo ingresos por las compras adscritas "
    "que cumplen los requisitos. En Jowua y Hansshow también puedo recibir una comisión. "
    "El precio para ti no sube.</i>"
)


def leer_env():
    datos = {}
    f = AQUI / ".env"
    if f.exists():
        for linea in f.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea and not linea.startswith("#") and "=" in linea:
                k, v = linea.split("=", 1)
                datos[k.strip()] = v.strip().strip('"').strip("'")
    return datos


def dentro_de_ventana(texto):
    """VENTANA=08:00-23:30 (vacio = todo el dia)."""
    if not texto:
        return True
    ini, fin = texto.split("-")
    try:
        from zoneinfo import ZoneInfo
        ahora = datetime.now(ZoneInfo("Europe/Madrid")).strftime("%H:%M")
    except Exception:  # sin base de zonas horarias: hora local del equipo
        ahora = datetime.now().strftime("%H:%M")
    return ini.strip() <= ahora <= fin.strip()


def url_producto(asin):
    return f"https://www.amazon.es/dp/{asin}?tag={TAG}"


TIENDAS = ("amazon", "jowua", "hansshow", "tesery", "evdance")
# Turno de 134 franjas de 30 min: ciclo de 7 (Amazon, Jowua y Hansshow 2 veces cada una y Tesery 1: comision del 2 %) x19 y EVDANCE 1 sola (envio a Espana caro)
TURNO = ("amazon", "jowua", "hansshow", "amazon", "jowua", "hansshow", "tesery") * 19 + ("evdance",)  # 134 franjas: EVDANCE 1 vez (~cada 2,8 dias; 11 productos = vuelta de ~1 mes)
BOTONES = {"amazon": "🛒 Ver en Amazon", "jowua": "🛒 Ver en Jowua", "hansshow": "🛒 Ver en Hansshow", "tesery": "🛒 Ver en Tesery", "evdance": "🛒 Ver en EVDANCE"}


def tienda_de(p):
    return p.get("tienda", "amazon")


DESCUENTOS = {"amazon": 0.0, "jowua": 0.05, "hansshow": 0.20, "tesery": 0.05, "evdance": 0.20}  # descuento de cada tienda con su codigo
CODIGOS = {"jowua": "ACCESORIOSTESLA", "hansshow": "VICTOR", "tesery": "ACCESORIOSTESLA", "evdance": "EVEU20"}


def linea_precio(p):
    """Precio FINAL (con el descuento de la tienda) a partir de precios.json (se actualiza cada semana). '' si no hay precio."""
    d = None
    for nombre in ("precios.json", "precios_tesery.json"):  # Tesery tiene su propio archivo de precios
        try:
            d = d or json.loads((AQUI / nombre).read_text(encoding="utf-8")).get(p["asin"])
        except Exception:
            pass
    if not d:
        return ""
    t = tienda_de(p)
    dto = DESCUENTOS.get(t, 0)
    final = int(d["p"] * (1 - dto) + 0.5)

    def eur(c):
        return f"{c // 100:,}".replace(",", ".") + f",{c % 100:02d} €"

    desde = "Desde " if d.get("d") else ""
    dia = d["f"][8:10] + "/" + d["f"][5:7]
    if dto:
        return f"💶 {desde}{eur(final)} con el código {CODIGOS[t]} (precio en tienda: {eur(d['p'])}; precio del {dia})"
    return f"💶 {desde}{eur(final)} (precio del {dia}; puede variar)"


def construir(p):
    tienda = tienda_de(p)
    url = url_producto(p["asin"]) if tienda == "amazon" else p["url"]
    texto = (
        f"{p.get('emoji', '🔥')} <b>{html.escape(p['titulo'])}</b>\n\n"
        f"{html.escape(p['descripcion'])}\n\n"
        f"✅ {html.escape(p['modelos'])}"
    )
    lp = linea_precio(p)
    if lp:
        texto += "\n\n" + lp
    if tienda == "jowua":  # tienda Jowua: descuento (sin precios) y aviso de afiliado
        texto += (
            "\n\n🏷️ 5 % de descuento con el código ACCESORIOSTESLA (con este enlace se aplica solo)"
        )
    elif tienda == "hansshow":  # Hansshow: cupon de afiliado de Victor (el enlace lleva su codigo bg_ref)
        texto += "\n\n🏷️ 20 % de descuento con el código VICTOR al pagar"
    elif tienda == "tesery":  # Tesery (GoAffPro): codigo de Vic, 5 %
        texto += "\n\n🏷️ 5 % de descuento con el código ACCESORIOSTESLA al pagar"
    elif tienda == "evdance":  # EVDANCE (Awin): codigo de la tienda UE
        texto += "\n\n🏷️ Con el código EVEU20 hasta 20 % de descuento en la tienda. Consulta el envío a España en la ficha."
    return texto, url


def enviar(token, chat, texto, url, boton="🛒 Ver en Amazon"):
    cuerpo = {
        "chat_id": chat,
        "text": texto,
        "parse_mode": "HTML",
        "link_preview_options": {"url": url, "prefer_large_media": True, "show_above_text": True},
        "reply_markup": {"inline_keyboard": [
            [{"text": boton, "url": url}],
            [{"text": "📘 Síguenos en Facebook", "url": FACEBOOK}],
        ]},
    }
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=json.dumps(cuerpo).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def siguiente_sin_estado(productos):
    """Para GitHub Actions (no guarda archivos): el producto depende de la hora.
    Cada franja de 30 min toca el siguiente de una lista barajada con semilla fija,
    asi no se repite hasta completar la vuelta."""
    # Cada franja de 30 min toca una tienda (Amazon, Jowua, Hansshow, por turnos = 1/3 cada una) y dentro de
    # ella el siguiente de su lista barajada (semilla 2026). Misma logica en Facebook.
    franja = int(time.time() // 1800)
    turno = [t for t in TURNO if any(tienda_de(p) == t for p in productos)]
    pos = franja % len(turno)
    tienda = turno[pos]
    lista = sorted(p["asin"] for p in productos if tienda_de(p) == tienda)
    random.Random(2026).shuffle(lista)
    k = (franja // len(turno)) * turno.count(tienda) + turno[:pos].count(tienda)  # EVDANCE pesa 1/7 (envio caro a Espana)
    return lista[k % len(lista)]


def siguiente(productos):
    f = AQUI / "estado.json"
    estado = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}
    asins = [p["asin"] for p in productos]
    cola = [a for a in estado.get("cola", []) if a in asins]
    if not cola:  # nueva vuelta: orden aleatorio, sin repetir el ultimo
        cola = asins[:]
        random.shuffle(cola)
        if cola and cola[0] == estado.get("ultimo") and len(cola) > 1:
            cola[0], cola[-1] = cola[-1], cola[0]
    asin = cola.pop(0)
    return asin, {"cola": cola, "ultimo": asin}, f


def main():
    try:
        sys.stdout.reconfigure(encoding="utf-8")  # emojis en la consola de Windows
    except Exception:
        pass
    args = set(sys.argv[1:])
    env = leer_env()
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "VENTANA"):  # las variables de entorno mandan
        if os.environ.get(k):
            env[k] = os.environ[k]
    productos = json.loads((AQUI / "productos.json").read_text(encoding="utf-8"))
    for nombre in ("productos_jowua.json", "productos_hansshow.json", "productos_tesery.json", "productos_evdance.json"):  # otras tiendas de afiliado
        extra = AQUI / nombre
        if extra.exists():
            productos += json.loads(extra.read_text(encoding="utf-8"))
    productos = [p for p in productos if not p.get("pausado")]
    token, chat = env.get("TELEGRAM_BOT_TOKEN", ""), env.get("TELEGRAM_CHAT_ID", "")

    if "--aviso" in args:
        if "--prueba" in args:
            print(AVISO)
            return
        print(enviar(token, chat, AVISO, "https://www.amazon.es/")["ok"])
        return

    if "--forzar" not in args and not dentro_de_ventana(env.get("VENTANA", "")):
        print("Fuera de la ventana horaria; no se publica.")
        return

    sin_estado = bool(os.environ.get("GITHUB_ACTIONS"))
    if sin_estado:
        asin, nuevo_estado, f_estado = siguiente_sin_estado(productos), None, None
    else:
        asin, nuevo_estado, f_estado = siguiente(productos)
    p = next(x for x in productos if x["asin"] == asin)
    texto, url = construir(p)

    if "--prueba" in args:
        print(texto)
        print("\nBOTON ->", url)
        return

    if not token or not chat:
        sys.exit("Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en .env")
    res = enviar(token, chat, texto, url, BOTONES[tienda_de(p)])
    if res.get("ok"):
        if not sin_estado:
            f_estado.write_text(json.dumps(nuevo_estado), encoding="utf-8")
            with (AQUI / "registro.log").open("a", encoding="utf-8") as log:
                log.write(f"{datetime.now():%Y-%m-%d %H:%M} OK {asin}\n")
        print("Publicado", asin)
    else:
        sys.exit(f"Telegram devolvio error: {res}")


if __name__ == "__main__":
    main()

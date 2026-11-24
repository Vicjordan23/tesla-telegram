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
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
import zlib
from traducir import a_espanol
import marca
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
TAG = "teslatelegram-21"  # ID de seguimiento de Amazon propio de este canal (24/11/2026): sus clics y ventas salen por separado en el informe de Afiliados
FACEBOOK = "https://www.facebook.com/profile.php?id=61596316649956"
AVISO = (
    "🔥 <b>CHOLLESLA: los chollos para tu Tesla</b> 🔥\n\n"
    "⚡ Un accesorio nuevo cada 30 minutos para Model 3 y Model Y, con el precio final ya rebajado.\n"
    "🏪 Amazon.es, AliExpress, Jowua, Hansshow, Tesery y EVDANCE, todo en un sitio.\n"
    "🏷️ Códigos de descuento: ACCESORIOSTESLA (Jowua y Tesery), VICTOR (Hansshow) y EVEU20 (EVDANCE).\n\n"
    "👉 <b>Mira TODOS los chollos, busca por modelo, guarda los tuyos y crea alertas gratis:</b>\n"
    f"🌐 {marca.web_utm('telegram', 'aviso')}\n\n"
    "<i>Enlaces de afiliado. En calidad de Afiliado de Amazon, obtengo ingresos por las compras adscritas "
    "que cumplen los requisitos. El precio para ti no sube.</i>"
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


TIENDAS = ("amazon", "jowua", "hansshow", "tesery", "evdance", "aliexpress", "temu")
# Turno de 134 franjas de 30 min: ciclo de 7 (Amazon, Jowua y Hansshow 2 veces cada una y Tesery 1: comision del 2 %) x19 y EVDANCE 1 sola (envio a Espana caro)
TURNO = ("amazon", "jowua", "hansshow", "amazon", "jowua", "hansshow", "tesery", "aliexpress", "aliexpress", "temu") * 15 + ("evdance",)  # 151 franjas: ciclo de 9 (AliExpress 2 de 9, comision ~9 %) x15 y EVDANCE 1 vez
BOTONES = {"amazon": "🛒 Comprar en Amazon", "jowua": "🛒 Comprar en Jowua", "hansshow": "🛒 Comprar en Hansshow", "tesery": "🛒 Comprar en Tesery", "evdance": "🛒 Comprar en EVDANCE", "aliexpress": "🛒 Comprar en AliExpress", "temu": "🛒 Comprar en Temu"}


def tienda_de(p):
    return p.get("tienda", "amazon")


DESCUENTOS = {"amazon": 0.0, "jowua": 0.05, "hansshow": 0.20, "tesery": 0.05, "evdance": 0.20, "aliexpress": 0.0, "temu": 0.0}  # descuento de cada tienda con su codigo
CODIGOS = {"jowua": "ACCESORIOSTESLA", "hansshow": "VICTOR", "tesery": "ACCESORIOSTESLA", "evdance": "EVEU20"}


def con_precio(productos):
    """Regla de Vic: producto sin precio = no se publica. Si no se puede leer ningun precio, no se filtra (para no parar todo)."""
    ids = set()
    for nombre in ("precios.json", "precios_tesery.json", "precios_aliexpress.json", "precios_temu.json"):
        try:
            ids |= set(json.loads((AQUI / nombre).read_text(encoding="utf-8")))
        except Exception:
            pass
    return [p for p in productos if p["asin"] in ids] if ids else productos


ESTRELLA = ["B0H11V8456", "B0FC21DNGX", "B0FCC6MMTV", "B0GC5TXB1L", "B0F7JXXSZS", "B0HHK2P5SX"]  # mas clics en Afiliados (20/11/2026)


def lista_tienda(productos, tienda):
    """Lista rotativa de una tienda: todos los productos una vez (barajados, semilla 2026) y despues, otra vez,
    los de precio igual o superior a la mediana de la tienda (barajados, semilla 2027): los caros dan mas comision
    y salen el doble. IDENTICA en publicar_siguiente.py, publicar_facebook.py y publicar_instagram.py."""
    precios = {}
    for nombre in ("precios.json", "precios_tesery.json", "precios_aliexpress.json", "precios_temu.json"):
        try:
            precios.update(json.loads((AQUI / nombre).read_text(encoding="utf-8")))
        except Exception:
            pass
    base = sorted(p["asin"] for p in productos if tienda_de(p) == tienda)
    random.Random(2026).shuffle(base)
    valores = sorted(precios[a]["p"] for a in base if a in precios)
    if len(valores) < 4:
        return base
    mediana = valores[len(valores) // 2]
    caros = sorted(a for a in base if a in precios and precios[a]["p"] >= mediana)
    random.Random(2027).shuffle(caros)
    lista = base + caros
    # Productos con clics reales (informe de Afiliados 20/11/2026): salen 2 veces mas por vuelta, al principio y a mitad.
    estrella = [a for a in ESTRELLA if a in base and a in precios]
    if estrella:
        mitad = len(lista) // 2
        lista = estrella + lista[:mitad] + estrella + lista[mitad:]
    return lista


def _precios_de(archivos):
    datos = {}
    for nombre in archivos:
        try:
            datos.update(json.loads((AQUI / nombre).read_text(encoding="utf-8")))
        except Exception:
            pass
    return datos


def _json(nombre):
    try:
        return json.loads((AQUI / nombre).read_text(encoding="utf-8"))
    except Exception:
        return {}


def eur(c):
    return f"{c // 100:,}".replace(",", ".") + f",{c % 100:02d} €"


def _fecha(f):
    return f[8:10] + "/" + f[5:7]


def _esc(t):
    return html.escape(t, quote=False)


def _final(c, tienda):
    return int(c * (1 - DESCUENTOS.get(tienda, 0)) + 0.5)


def datos_precio(p):
    """Precio de un producto: {'tienda','p','final','dto','desde','f'} o None. Fuente: precios*.json (los actualiza el workflow Actualizar precios)."""
    d = _precios_de(("precios.json", "precios_tesery.json", "precios_aliexpress.json", "precios_temu.json")).get(p["asin"])
    if not d:
        return None
    t = tienda_de(p)
    return {"tienda": t, "p": d["p"], "final": _final(d["p"], t), "dto": DESCUENTOS.get(t, 0), "desde": bool(d.get("d")), "f": d["f"]}


def _dias(desde, hasta):
    return (datetime.strptime(hasta, "%Y-%m-%d") - datetime.strptime(desde, "%Y-%m-%d")).days


def bajada_real(p, pr, hoy=None):
    """BAJADA con datos reales: historial_precios.json (lo escribe historial_precios.py tras cada actualizacion de precios).
    Solo si el precio actual es menor que el anterior guardado, el producto no es 'Desde' (minimo de variantes), la baja se
    detecto hace <= 7 dias y es de al menos 5 % y 1 EUR. Devuelve {'antes','ahora','pct','f_antes'} (precios FINALES) o None."""
    h = _json("historial_precios.json").get(p["asin"])
    if not h or not pr or pr["desde"] or not h.get("ant") or h["p"] != pr["p"] or h["ant"] <= h["p"]:
        return None
    hoy = hoy or datetime.utcnow().strftime("%Y-%m-%d")
    try:
        dias = _dias(h["fc"], hoy)
        if _dias(h["fant"], h["fc"]) > 21:  # el precio anterior es demasiado viejo para compararlo
            return None
    except Exception:
        return None
    antes, ahora = _final(h["ant"], pr["tienda"]), pr["final"]
    if dias > 7 or antes - ahora < 100 or (antes - ahora) * 100 < 5 * antes:
        return None
    return {"antes": antes, "ahora": ahora, "pct": round((antes - ahora) * 100 / antes), "f_antes": h.get("fant") or ""}


def es_novedad(p, hoy=None):
    """Novedad = producto que entro en los precios DESPUES de empezar el historial (campo alta, <= 14 dias)."""
    alta = _json("historial_precios.json").get(p["asin"], {}).get("alta")
    if not alta:
        return False
    hoy = hoy or datetime.utcnow().strftime("%Y-%m-%d")
    try:
        return 0 <= _dias(alta, hoy) <= 14
    except Exception:
        return False


PACK_RE = re.compile(r"\b(pack|set|kit|juego|combo|lote|bundle|conjunto)\b|\b\d+\s*(piezas|pcs|uds|unidades|pzas)\b", re.I)
PEDIDOS_RE = re.compile(r"([\d.]+) pedidos seg[uú]n AliExpress", re.I)


def tipo_de(p, baja):
    """bajada (dato real) > novedad (dato real) > opinion (Amazon con resumen en opiniones.json) > pedidos (AliExpress con >=1.000 pedidos segun AliExpress) > pack > chollo."""
    if baja:
        return "bajada"
    if es_novedad(p):
        return "novedad"
    t = tienda_de(p)
    if t == "amazon" and _json("opiniones.json").get(p["asin"]):
        return "opinion"
    if t == "aliexpress":
        m = PEDIDOS_RE.search(p.get("descripcion", ""))
        if m and int(m.group(1).replace(".", "")) >= 1000:
            return "pedidos"
    if PACK_RE.search(p.get("titulo", "")):
        return "pack"
    return "chollo"


def _var(p, lista):
    """Variante de plantilla estable por producto (mismo producto = mismo texto en cada ejecucion)."""
    return lista[zlib.crc32(p["asin"].encode()) % len(lista)]


TITULARES = {
    "bajada": ["🔴🔥 <b>BAJADA DE PRECIO</b> 🔥🔴", "🔴💥 <b>¡HA BAJADO!</b> 💥🔴", "📉🔴 <b>BAJÓ EL PRECIO</b> 🔴📉"],
    "novedad": ["🟢🆕 <b>NOVEDAD EN CHOLLESLA</b> 🆕🟢", "🟢✨ <b>NUEVO CHOLLO PARA TU TESLA</b> ✨🟢"],
    "opinion": ["💬🟢 <b>OPINIONES REALES DE COMPRADORES</b> 🟢💬", "🗣️✅ <b>LO CUENTAN QUIENES YA LO TIENEN</b> ✅🗣️"],
    "pedidos": ["🏆🟢 <b>DE LOS MÁS PEDIDOS</b> 🟢🏆", "🏆🔥 <b>MUCHOS PEDIDOS EN ALIEXPRESS</b> 🔥🏆"],
    "pack": ["🎁🟡 <b>PACK CHOLLAZO</b> 🟡🎁", "📦🔥 <b>TODO EN UNO, AL MEJOR PRECIO</b> 🔥📦"],
    "chollo": ["🔥🟡 <b>CHOLLO PARA TU TESLA</b> 🟡🔥", "💥✅ <b>CHOLLAZO DEL MOMENTO</b> ✅💥", "🟡🔥 <b>OFERTA PARA TU MODEL 3 / Y</b> 🔥🟡"],
}
AVISO_AMAZON = "En calidad de Afiliado de Amazon, obtengo ingresos por las compras adscritas que cumplen los requisitos."


def _semaforo(tienda):
    """Semaforo del descuento de la tienda: verde 20 %, amarillo 5 %, nada sin codigo."""
    dto = DESCUENTOS.get(tienda, 0)
    return "🟢" if dto >= 0.2 else ("🟡" if dto > 0 else "")


def bloque_precio(pr, baja):
    """Lineas de precio con el PRECIO FINAL destacado (tras el descuento de la tienda)."""
    t, desde = pr["tienda"], ("Desde " if pr["desde"] else "")
    lineas = []
    if baja:
        lineas.append(
            f"📉 Antes <s>{eur(baja['antes'])}</s>" + (f" ({_fecha(baja['f_antes'])})" if baja["f_antes"] else "")
            + f" ➜ ahora <b>{eur(baja['ahora'])}</b> (-{baja['pct']} %, ahorras {eur(baja['antes'] - baja['ahora'])})"
        )
    if pr["dto"]:
        lineas.append(f"💶 PRECIO FINAL: <s>{eur(pr['p'])}</s> ➜ <b>{desde}{eur(pr['final'])}</b>")
        lineas.append(f"{_semaforo(t)} -{round(pr['dto'] * 100)} % con el código <code>{CODIGOS[t]}</code> (toca para copiar) · ahorras {eur(pr['p'] - pr['final'])}")
    elif not baja:
        lineas.append(f"💶 PRECIO: <b>{desde}{eur(pr['final'])}</b>")
    else:
        lineas.append(f"💶 PRECIO FINAL: <b>{eur(pr['final'])}</b>")
    return "\n".join(lineas)


def nota_tienda(t):
    if t == "jowua":
        return "🟡 Con este enlace el 5 % se aplica solo."
    if t in ("hansshow", "tesery"):
        return "✍️ Pon el código al pagar."
    if t == "evdance":
        return "🚚 Tienda de la UE: mira el envío a España en la ficha antes de pagar."
    if t == "aliexpress":
        return "🚚 Revisa la variante y el envío en la ficha."
    if t == "temu":
        return "🚚 Revisa la variante y el envío en la ficha."
    return ""


def construir(p, max_len=None):
    """Mensaje de chollo en HTML de Telegram: titular con semaforo segun el tipo (bajada / novedad / opinion / pack / chollo),
    precio final destacado, codigo de la tienda y modelos. Todo viene de los JSON: nada inventado.
    max_len = limite del pie de foto (1024 menos el pie): se acorta la descripcion y, si hace falta, la opinion y el titulo."""
    tienda = tienda_de(p)
    url = url_producto(p["asin"]) if tienda == "amazon" else p["url"]
    pr = datos_precio(p)
    baja = bajada_real(p, pr)
    titular = _var(p, TITULARES[tipo_de(p, baja)])
    titulo_es = html.unescape(a_espanol(p["titulo"]))  # algunos titulos de tienda traen &amp; ya escapado
    desc = re.sub(r",? bien valorado en Amazon\.es \(\d+ estrellas o más\)", "", html.unescape(a_espanol(p["descripcion"]))).strip()  # sin notas ni estrellas (regla de Vic)
    if desc in ("Accesorio para tu Tesla.", "Accesorio para tu Tesla"):  # frase generica sin informacion
        desc = ""
    modelos = _esc(p["modelos"])
    opinion = _json("opiniones.json").get(p["asin"], "") if tienda == "amazon" else ""
    notas = []
# aviso de afiliado: va en la descripcion del canal (Vic, 23/11/2026), no en cada post

    def armar(titulo, desc_txt, op_txt):
        partes = [titular, f"{p.get('emoji', '🔥')} <b>{_esc(titulo)}</b>"]
        if pr:
            partes.append(bloque_precio(pr, baja))
        if desc_txt:
            partes.append(_esc(desc_txt))
        partes.append(f"✅ {modelos}")
        if op_txt:
            partes.append(f"💬 Lo que dicen los compradores en Amazon: {_esc(op_txt)}")
        if nota_tienda(tienda):
            partes.append(nota_tienda(tienda))
        return "\n\n".join(partes + notas)

    texto = armar(titulo_es, desc, opinion)
    if max_len and len(texto) > max_len:
        quitar = len(texto) - max_len
        desc = recortar(desc, len(desc) - quitar - 2) if len(desc) - quitar - 2 > 20 else ""
        texto = armar(titulo_es, desc, opinion)
    if max_len and len(texto) > max_len:
        quitar = len(texto) - max_len
        opinion = recortar(opinion, len(opinion) - quitar - 2) if len(opinion) - quitar - 2 > 20 else ""
        texto = armar(titulo_es, desc, opinion)
    if max_len and len(texto) > max_len:
        quitar = len(texto) - max_len
        titulo_es = recortar(titulo_es, max(20, len(titulo_es) - quitar - 2))
        texto = armar(titulo_es, desc, opinion)
    return texto, url


def _telegram(token, metodo, cuerpo, cabecera="application/json", datos=None):
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{metodo}",
        data=datos if datos is not None else json.dumps(cuerpo).encode("utf-8"),
        headers={"Content-Type": cabecera},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read().decode("utf-8"))
        except Exception:
            return {"ok": False, "description": str(e)}


def _subir_foto(token, chat, imagen, caption, teclado):
    """Descarga la foto, le pone el logo de Chollesla y la sube a Telegram."""
    foto = marca.con_logo(marca.descargar(imagen))
    borde = uuid.uuid4().hex
    campos = {"chat_id": chat, "caption": caption, "parse_mode": "HTML", "reply_markup": json.dumps(teclado)}
    crlf = b"\r\n"
    cuerpo = b""
    for k, v in campos.items():
        cuerpo += f"--{borde}".encode() + crlf + f'Content-Disposition: form-data; name="{k}"'.encode() + crlf + crlf + str(v).encode("utf-8") + crlf
    cuerpo += f"--{borde}".encode() + crlf + b'Content-Disposition: form-data; name="photo"; filename="foto.jpg"' + crlf + b"Content-Type: image/jpeg" + crlf + crlf + foto + crlf + f"--{borde}--".encode() + crlf
    return _telegram(token, "sendPhoto", None, f"multipart/form-data; boundary={borde}", cuerpo)


def recortar(texto, n=1024):
    """Telegram limita el pie de foto a 1024 caracteres: se recorta la descripcion, no el precio ni el aviso."""
    return texto if len(texto) <= n else texto[: n - 1].rsplit(" ", 1)[0] + "…"


# El pie es un enlace con UTM (anclado a «chollesla.es»): para el limite de 1024 cuenta solo el texto visible
PIE_VISIBLE = f"🌐 Más chollos: {marca.WEB_CORTA}"
PIE = f'🌐 Más chollos: <a href="{html.escape(marca.web_utm("telegram", "pie"), quote=True)}">{html.escape(marca.WEB_CORTA, quote=False)}</a>'
LIMITE_TEXTO = 1024 - len(PIE_VISIBLE) - 2  # pie de foto de Telegram: 1024 caracteres con el pie


def enviar(token, chat, texto, url, boton="🛒 Comprar en Amazon", imagen=None):
    """Publica SIEMPRE con foto (sendPhoto). Si no hay foto o no se puede enviar, no publica nada (regla de Vic, 20/11/2026).
    La foto lleva el logo de Chollesla. Botones: Comprar (enlace de afiliado de SU tienda) y Mas chollos (chollesla.es) + Facebook.
    El pie con la web va en el texto de TODAS las publicaciones. 'texto' ya viene acortado por construir(max_len=LIMITE_TEXTO)."""
    teclado = {"inline_keyboard": [
        [{"text": boton, "url": url}],
        [{"text": "🔥 Más chollos en chollesla.es", "url": marca.web_utm("telegram", "boton")}],
        [{"text": "📘 Síguenos en Facebook", "url": FACEBOOK}],
    ]}
    if not imagen:  # solo el aviso fijo (--aviso) va sin foto
        return _telegram(token, "sendMessage", {"chat_id": chat, "text": texto, "parse_mode": "HTML", "reply_markup": teclado})
    caption = texto + "\n\n" + PIE  # construir() ya dejo el texto dentro de LIMITE_TEXTO (no recortar aqui: partiria las etiquetas HTML)
    if len(texto) + 2 + len(PIE_VISIBLE) > 1024:  # Telegram cuenta el texto visible, no el HTML del enlace del pie
        raise ValueError(f"Pie de foto de {len(texto) + 2 + len(PIE_VISIBLE)} caracteres (> 1024)")
    return _subir_foto(token, chat, imagen, caption, teclado)


def imagen_de(asin):
    for nombre in ("imagenes_ig.json", "imagenes_tesery.json", "imagenes_aliexpress.json", "imagenes_temu.json"):
        try:
            u = json.loads((AQUI / nombre).read_text(encoding="utf-8")).get(asin)
        except Exception:
            u = None
        if u:
            return u
    return None


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
    lista = lista_tienda(productos, tienda)  # los caros (>= mediana de la tienda) salen el doble
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
    for nombre in ("productos_jowua.json", "productos_hansshow.json", "productos_tesery.json", "productos_evdance.json", "productos_aliexpress.json", "productos_temu.json"):  # otras tiendas de afiliado
        extra = AQUI / nombre
        if extra.exists():
            productos += json.loads(extra.read_text(encoding="utf-8"))
    productos = con_precio([p for p in productos if not p.get("pausado")])
    token, chat = env.get("TELEGRAM_BOT_TOKEN", ""), env.get("TELEGRAM_CHAT_ID", "")

    if "--aviso" in args:
        if "--prueba" in args:
            print(AVISO)
            return
        print(enviar(token, chat, AVISO, marca.web_utm("telegram", "aviso"), "🌐 Ver todos los chollos")["ok"])
        return

    if "--forzar" not in args and not dentro_de_ventana(env.get("VENTANA", "")):
        print("Fuera de la ventana horaria; no se publica.")
        return

    sin_estado = bool(os.environ.get("GITHUB_ACTIONS"))
    if sin_estado:
        asin, nuevo_estado, f_estado = siguiente_sin_estado(productos), None, None
    else:
        asin, nuevo_estado, f_estado = siguiente(productos)
    asin = os.environ.get("PRODUCTO_FORZADO") or asin  # prueba manual de un producto concreto
    p = next(x for x in productos if x["asin"] == asin)
    texto, url = construir(p, LIMITE_TEXTO)
    imagen = imagen_de(asin)

    if "--prueba" in args:
        print(texto)
        print("\nBOTON ->", url, "\nIMAGEN ->", imagen)
        return

    if not imagen:  # regla de Vic: nada se publica sin foto (la rotacion sigue igual que en Facebook e Instagram)
        print(f"Sin imagen del producto para {asin}; no se publica en esta franja.")
        return

    if not token or not chat:
        sys.exit("Falta TELEGRAM_BOT_TOKEN o TELEGRAM_CHAT_ID en .env")
    res = enviar(token, chat, texto, url, BOTONES[tienda_de(p)], imagen)
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

"""Marca Chollesla para las publicaciones: enlaces y logo sobre la foto del producto.

WEB es la direccion que aparece en TODAS las publicaciones. Cuando chollesla.es este activo basta con
cambiar WEB (o definir la variable de entorno WEB_URL) y todos los canales la usan.
"""
import io
import os
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
WEB = os.environ.get("WEB_URL") or "https://chollesla.es"
CANAL = "https://t.me/teslaaccesorios"
WEB_CORTA = WEB.replace("https://", "").replace("http://", "").rstrip("/")
CANAL_CORTO = "t.me/teslaaccesorios"
# Linea que cierra TODOS los textos (Telegram, Facebook, Instagram y X)
PIE_TEXTO = f"🌐 Más chollos: {WEB}\n✈️ Canal de Telegram: {CANAL}"
PIE_TELEGRAM = f"🌐 Más chollos: {WEB}"  # en Telegram no se enlaza el canal: ya estan dentro
PIE_X = f"🌐 {WEB}\n✈️ {CANAL}"


def con_logo(foto_bytes):
    """Devuelve la foto (JPEG) con una franja inferior blanca con el logo de Chollesla.
    Si algo falla devuelve la foto original: una publicacion nunca se pierde por el logo."""
    try:
        from PIL import Image
        foto = Image.open(io.BytesIO(foto_bytes)).convert("RGB")
        ancho = max(foto.width, 600)
        if foto.width != ancho:
            foto = foto.resize((ancho, int(foto.height * ancho / foto.width)))
        logo = Image.open(AQUI / "marca" / "logo-letras.png").convert("RGB")
        alto_barra = max(int(ancho * 0.13), 70)
        alto_logo = int(alto_barra * 0.78)
        logo = logo.resize((int(logo.width * alto_logo / logo.height), alto_logo))
        lienzo = Image.new("RGB", (foto.width, foto.height + alto_barra), (255, 255, 255))
        lienzo.paste(foto, (0, 0))
        lienzo.paste(logo, ((foto.width - logo.width) // 2, foto.height + (alto_barra - alto_logo) // 2))
        salida = io.BytesIO()
        lienzo.save(salida, "JPEG", quality=90)
        return salida.getvalue()
    except Exception as e:  # sin Pillow, foto corrupta, etc.
        print("Logo no aplicado:", e)
        return foto_bytes


def descargar(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def subir_foto_facebook(foto, campos, token, pagina="me"):
    """Sube una foto (bytes) a la pagina de Facebook con multipart. Devuelve el JSON de respuesta (con 'id')."""
    import json
    import uuid
    borde = uuid.uuid4().hex
    crlf = b"\r\n"
    cuerpo = b""
    for k, v in {**campos, "access_token": token}.items():
        cuerpo += f"--{borde}".encode() + crlf + f'Content-Disposition: form-data; name="{k}"'.encode() + crlf + crlf + str(v).encode("utf-8") + crlf
    cuerpo += (f"--{borde}".encode() + crlf + b'Content-Disposition: form-data; name="source"; filename="foto.jpg"' + crlf
               + b"Content-Type: image/jpeg" + crlf + crlf + foto + crlf + f"--{borde}--".encode() + crlf)
    req = urllib.request.Request(f"https://graph.facebook.com/v21.0/{pagina}/photos", data=cuerpo,
                                 headers={"Content-Type": f"multipart/form-data; boundary={borde}"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.loads(r.read().decode())


def url_publica_con_logo(imagen_url, token):
    """Para Instagram (exige una URL publica): descarga la foto, le pone el logo, la sube a Facebook sin publicarla
    y devuelve su URL publica. Si algo falla devuelve la URL original: la publicacion no se pierde por el logo."""
    import json
    import urllib.parse
    try:
        foto = con_logo(descargar(imagen_url))
        sube = subir_foto_facebook(foto, {"published": "false"}, token)
        q = urllib.parse.urlencode({"fields": "images", "access_token": token})
        with urllib.request.urlopen(f"https://graph.facebook.com/v21.0/{sube['id']}?{q}", timeout=30) as r:
            imagenes = json.loads(r.read().decode()).get("images") or []
        if imagenes:
            return imagenes[0]["source"]
    except Exception as e:
        print("Foto con logo no subida, se usa la original:", e)
    return imagen_url

"""Marca Chollesla para las publicaciones: enlaces y logo sobre la foto del producto.

WEB es la direccion que aparece en TODAS las publicaciones. Cuando chollesla.es este activo basta con
cambiar WEB (o definir la variable de entorno WEB_URL) y todos los canales la usan.
"""
import io
import os
import urllib.request
from pathlib import Path

AQUI = Path(__file__).resolve().parent
WEB = os.environ.get("WEB_URL") or "https://chollesla.victor-martin-juanas.workers.dev"
CANAL = "https://t.me/teslaaccesorios"
WEB_CORTA = WEB.replace("https://", "").replace("http://", "").rstrip("/")
CANAL_CORTO = "t.me/teslaaccesorios"
# Linea que cierra TODOS los textos (Telegram, Facebook, Instagram y X)
PIE_TEXTO = f"🌐 Más chollos: {WEB}\n✈️ Canal de Telegram: {CANAL}"
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

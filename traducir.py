"""Traduce al español lo que venga en otro idioma (títulos de AliExpress, Hansshow, Tesery... en inglés u holandés).
Solo biblioteca estándar. Si el texto ya está en español, o el traductor falla, devuelve el original (nunca rompe la publicación)."""
import json
import urllib.parse
import urllib.request

_CACHE = {}


def a_espanol(texto):
    texto = (texto or "").strip()
    if not texto or len(texto) < 4:
        return texto
    if texto in _CACHE:
        return _CACHE[texto]
    resultado = texto
    try:
        url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=auto&tl=es&dt=t&q=" + urllib.parse.quote(texto)
        with urllib.request.urlopen(url, timeout=15) as r:
            datos = json.loads(r.read().decode("utf-8"))
        idioma = datos[2] if len(datos) > 2 else "es"
        traducido = "".join(trozo[0] for trozo in datos[0] if trozo and trozo[0]).strip()
        if idioma != "es" and traducido:
            resultado = traducido
    except Exception:
        pass
    _CACHE[texto] = resultado
    return resultado

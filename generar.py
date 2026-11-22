#!/usr/bin/env python3
"""Tarea semanal (decisión 3): elige el mejor banner y póster de las series más populares y escribe imagenes.json.

La app descarga ese archivo; si una serie no está, usa sus reglas del móvil.
Necesita macOS 15 (usa Vision para caras, texto y estética) y las variables TVDB_KEY y, si hace falta, TVDB_PIN.

Uso:  python3 generar.py --series 1000 --salida salida/imagenes.json
"""
import argparse, colorsys, json, os, re, subprocess, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from PIL import Image

AQUI = os.path.dirname(os.path.abspath(__file__))
TVDB = 'https://api4.thetvdb.com/v4'
PROMO = re.compile(r"\b(19|20)\d\d\b|\b\d{1,2}[:.]\d{2}\b|new (series|season)|watch now|streaming|only on|premiere|coming|season \d|temporada|saison|estreno|netflix|hbo|prime|disney|hulu|apple|tv\+|max\b|original series", re.I)
PESOS = json.load(open(os.path.join(AQUI, 'pesos.json')))

# ---------- utilidades ----------
def http_json(url, token=None, datos=None):
    h = {'Content-Type': 'application/json', 'User-Agent': 'Nextisode-imagenes/1.0'}
    if token: h['Authorization'] = 'Bearer ' + token
    req = urllib.request.Request(url, data=json.dumps(datos).encode() if datos else None, headers=h)
    for intento in range(4):
        try:
            return json.load(urllib.request.urlopen(req, timeout=30))
        except urllib.error.HTTPError as e:
            if e.code == 429: time.sleep(2 + intento * 3); continue
            if e.code == 404: return None
            raise
        except Exception:
            time.sleep(1 + intento)
    return None

def login():
    clave, pin = os.environ.get('TVDB_KEY') or os.environ.get('EXPO_PUBLIC_TVDB_KEY'), os.environ.get('TVDB_PIN') or os.environ.get('EXPO_PUBLIC_TVDB_PIN')
    if not clave: sys.exit('Falta TVDB_KEY')
    r = http_json(TVDB + '/login', datos={'apikey': clave, **({'pin': pin} if pin else {})})
    return r['data']['token']

def compilar_vision(dir_bin):
    os.makedirs(dir_bin, exist_ok=True)
    for n in ('analiza', 'estetica'):
        b, s = os.path.join(dir_bin, n), os.path.join(AQUI, 'vision', n + '.swift')
        if not os.path.exists(b) or os.path.getmtime(b) < os.path.getmtime(s):
            subprocess.run(['swiftc', '-O', s, '-o', b], check=True)
    return os.path.join(dir_bin, 'analiza'), os.path.join(dir_bin, 'estetica')

# ---------- lista de series populares (TVmaze, CC BY-SA) ----------
def populares(n):
    """Series con más seguidores en TVmaze («weight»), con id de TheTVDB."""
    todas, pagina = [], 0
    while pagina < 400:
        p = http_json(f'https://api.tvmaze.com/shows?page={pagina}')
        if not p: break
        todas += [(s.get('weight') or 0, s['externals'].get('thetvdb'), s['name']) for s in p if s['externals'].get('thetvdb')]
        pagina += 1
    todas.sort(key=lambda x: -x[0])
    return [(tvdb, nombre) for _, tvdb, nombre in todas[:n]]

# ---------- rasgos de cada imagen (los mismos que el modelo v2) ----------
def dhash(im):
    g = np.asarray(im.convert('L').resize((17, 16)), dtype=float)
    return (g[:, 1:] > g[:, :-1]).flatten()

def color(f):
    a = np.asarray(Image.open(f).convert('RGB').resize((64, 64)), dtype=float)
    rg = a[..., 0] - a[..., 1]; yb = 0.5 * (a[..., 0] + a[..., 1]) - a[..., 2]
    return (np.sqrt(rg.std()**2 + yb.std()**2) + 0.3 * np.sqrt(rg.mean()**2 + yb.mean()**2)) / 100, a.mean() / 255

def analizar(f, analiza, estetica):
    """Vision imagen por imagen (con varias a la vez se cuelga) y con caché al lado: cada semana solo se analizan las nuevas."""
    c = f + '.vision.json'
    if os.path.exists(c):
        d = json.load(open(c)); return d['v'], tuple(d['e']) if d['e'] else None
    try:
        v = json.loads(subprocess.run([analiza, f], capture_output=True, text=True, timeout=60).stdout.strip() or 'null')
        p = subprocess.run([estetica, f], capture_output=True, text=True, timeout=60).stdout.strip().rsplit(' ', 2)
        e = (float(p[1]), p[2] == 'true') if len(p) == 3 and p[1] != 'error' else None
    except Exception:
        return None, None
    json.dump({'v': v, 'e': e}, open(c, 'w'))
    return v, e

def puntuar(x, tipo):
    w, P = PESOS[tipo]['pesos'], PESOS[tipo]['reglas']
    r = sum(w[k] * x.get(k, 0.0) for k in w)
    r += P['estetica'] * x['estetica'] + P['reciente'] * x['reciente']
    if x['bn']: r -= P['bn']
    if x['utilitaria']: r -= P['util']
    if tipo == 'banner' and x['sin_caras']: r -= P['banner_sin_caras']
    if tipo == 'poster' and x['sin_caras'] and x['mucho_texto'] > 0.3: r -= P['solo_logo']
    if x['promo']: r -= P['promo']
    return r

def procesar(tvdb, nombre, token, cache, analiza, estetica):
    base = http_json(f'{TVDB}/series/{tvdb}', token)
    arts = http_json(f'{TVDB}/series/{tvdb}/artworks', token)
    if not base or not arts: return None
    base, arts = base['data'], arts['data']['artworks'] or []
    orig = base.get('originalLanguage')
    palabras = {w.lower() for w in re.findall(r"[A-Za-zÀ-ÿ0-9']{3,}", nombre + ' ' + (base.get('name') or ''))} - {'the', 'los', 'las', 'que'}
    d = os.path.join(cache, str(tvdb)); os.makedirs(d, exist_ok=True)
    res = {}
    for tipo_num, tipo in ((1, 'banner'), (2, 'poster')):
        # Solo imágenes sin texto o en el idioma original / inglés (las demás no se enseñan nunca).
        grupo = [a for a in arts if a['type'] == tipo_num and a.get('language') in (None, orig, 'eng')]
        # Las 20 más votadas como candidatas (casi nunca gana una sin votos y así se ahorra análisis).
        grupo = sorted(grupo, key=lambda a: -(a.get('score') or 0))[:20]
        if not grupo: continue
        ids = sorted(a['id'] for a in grupo); scores = sorted((a.get('score') or 0) for a in grupo)
        archivos = {}
        for a in grupo:
            f = os.path.join(d, f"{a['id']}.jpg")
            if not os.path.exists(f):
                try: urllib.request.urlretrieve(a.get('thumbnail') or a['image'], f)
                except Exception: continue
            archivos[a['id']] = f
        if not archivos: continue
        vis, est = {}, {}
        for f in archivos.values():
            v, e = analizar(f, analiza, estetica)
            if v: vis[os.path.basename(f)] = v
            if e: est[f] = e
        mejor = None
        vistos = []
        for a in grupo:
            f = archivos.get(a['id'])
            v = vis.get(f"{a['id']}.jpg") if f else None
            if not v: continue
            try: h = dhash(Image.open(f))
            except Exception: continue
            if any((h != o).sum() < 6 for o in vistos): continue  # duplicadas
            vistos.append(h)
            caras = v['caras']; textos = ' '.join(t['t'] for t in v['textos']).lower()
            colorido, brillo = color(f); e, util = est.get(f, (0.0, False)); lang = a.get('language')
            x = {
                'titulo': float(any(w in textos for w in palabras)), 'caras': min(len(caras), 8) / 8,
                'cara_max': max([c['w'] * c['h'] for c in caras], default=0) * 4, 'sin_caras': float(not caras),
                'promo': float(bool(PROMO.search(textos))), 'mucho_texto': min(sum(t['area'] for t in v['textos']), 0.4) / 0.4,
                'colorido': colorido, 'bn': float(colorido < 0.12), 'brillo': brillo,
                'idioma_original': float(lang == orig), 'idioma_ingles': float(lang == 'eng'), 'sin_idioma': float(lang is None),
                'reciente': ids.index(a['id']) / max(len(ids) - 1, 1), 'votos': scores.index(a.get('score') or 0) / max(len(scores) - 1, 1),
                'resolucion': min(a.get('width') or 0, 2000) / 2000, 'temporada': 0.0, 'estetica': e, 'utilitaria': float(util),
            }
            p = puntuar(x, tipo)
            if not mejor or p > mejor[0]: mejor = (p, a, caras)
        if mejor:
            _, a, caras = mejor
            item = {'url': a['image']}
            if tipo == 'poster' and caras:  # encuadre por la cara más grande (para el vídeo resumen)
                c = max(caras, key=lambda c: c['w'] * c['h'])
                item['focoX'], item['focoY'] = round(c['x'], 3), round(c['y'], 3)
            res[tipo] = item
    return res or None

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--series', type=int, default=1000)
    ap.add_argument('--salida', default=os.path.join(AQUI, 'salida', 'imagenes.json'))
    ap.add_argument('--cache', default=os.path.join(AQUI, 'cache'))
    ap.add_argument('--hilos', type=int, default=8)
    ap.add_argument('--ids', help='ids de TheTVDB separados por comas (para pruebas)')
    ap.add_argument('--minutos', type=float, default=0, help='a partir de aquí no se analizan series nuevas (0 = sin límite)')
    ap.add_argument('--dias', type=int, default=28, help='días que vale el resultado guardado de una serie')
    a = ap.parse_args()
    analiza, estetica = compilar_vision(os.path.join(a.cache, 'bin'))
    token = login()
    lista = [(int(i), '') for i in a.ids.split(',')] if a.ids else populares(a.series)
    print(f'{len(lista)} series', flush=True)
    salida = {}
    with ThreadPoolExecutor(a.hilos) as ex:
        for (tvdb, nombre), r in zip(lista, ex.map(lambda s: _con_cache(s[0], s[1], token, a, analiza, estetica), lista)):
            if r: salida[str(tvdb)] = r
            print(('✓ ' if r else '· ') + (nombre or str(tvdb)), flush=True)
    # Las elegidas a mano por el usuario mandan sobre el modelo.
    for k, v in json.load(open(os.path.join(AQUI, 'manuales.json')))['series'].items():
        salida[k] = {**salida.get(k, {}), **{t: v[t] for t in ('banner', 'poster') if t in v}}
    os.makedirs(os.path.dirname(a.salida), exist_ok=True)
    json.dump({'version': 1, 'generado': time.strftime('%Y-%m-%d'), 'series': salida}, open(a.salida, 'w'), separators=(',', ':'), ensure_ascii=False)
    print(f'{len(salida)} series en {a.salida} ({os.path.getsize(a.salida) // 1024} KB)')

INICIO = time.time()

def _con_cache(tvdb, nombre, token, a, analiza, estetica):
    """Resultado guardado de la serie si vale todavía; si no, se analiza mientras quede tiempo.
    Así una ejecución que no llega a todas deja hecho lo que ha podido y la siguiente sigue por ahí."""
    f = os.path.join(a.cache, str(tvdb), 'resultado.json')
    try:
        if time.time() - os.path.getmtime(f) < a.dias * 86400: return json.load(open(f))['r']
    except Exception: pass
    if a.minutos and time.time() - INICIO > a.minutos * 60:
        try: return json.load(open(f))['r']  # caducado, pero mejor que nada
        except Exception: return None
    r = _seguro(procesar, tvdb, nombre, token, a.cache, analiza, estetica)
    if r is not None:
        os.makedirs(os.path.dirname(f), exist_ok=True)
        json.dump({'r': r}, open(f, 'w'))
    return r

def _seguro(f, *args):
    try: return f(*args)
    except Exception as e:
        print('error', args[0], e, file=sys.stderr); return None

if __name__ == '__main__':
    main()

# Tarea semanal de imágenes (decisión 3)

`generar.py` elige el mejor **banner** (para las listas) y **póster** (para el vídeo resumen, con encuadre por la cara más grande) de las series más populares, con el modelo v2 entrenado con tus elecciones (`pesos.json`). Escribe `salida/imagenes.json`:

```json
{"version":1,"generado":"2026-11-16","series":{"79126":{"banner":{"url":"…"},"poster":{"url":"…","focoX":0.73,"focoY":0.21}}}}
```

La app descarga ese archivo y, si una serie no está, usa sus reglas del móvil.

## Requisitos
- macOS 15 o posterior (usa Vision para caras, texto y estética), `swiftc`, Python 3 con `numpy` y `Pillow`.
- `TVDB_KEY` (y `TVDB_PIN` si la clave lo pide). En local las toma de `.env`.

## Uso
```bash
set -a; . ../../.env; set +a
python3 generar.py --series 1000              # las 1000 más populares de TVmaze
python3 generar.py --ids 79126,383203         # prueba con ids de TheTVDB
```

## Tiempos medidos (16/11/2026)
- 6 series (210 imágenes): 1 minuto con 8 hilos.
- Primera pasada de 1000 series: unas 3 horas. Después cada semana solo analiza las imágenes nuevas (caché en `cache/`), así que tarda minutos.
- Vision se cuelga si se le pasan muchas imágenes en una sola llamada: por eso analiza una a una.

## Dónde se ejecuta
Necesita un Mac (Vision). Opciones gratis: el propio Mac del usuario con una tarea programada, o GitHub Actions con un ejecutor macOS en un repositorio **público** (en uno privado los minutos de macOS se acaban enseguida).
El archivo se publica en fuentepatos.com (pedir permiso al orquestador antes de subir nada a la web).

"""
subir_a_supabase.py — ABC Gaming
=================================

Toma juegos_para_web.csv (la salida de filtrar_catalogo_abc_gaming_CORREGIDO.py)
y reemplaza todo el contenido de la tabla `juegos_web` en Supabase por los
datos frescos. Pensado para correr automáticamente al final del GitHub
Action, así la web (Lovable) siempre muestra el catálogo del día sin que
nadie tenga que importar nada a mano.

Necesita dos variables de entorno (se configuran como Secrets en GitHub):
    SUPABASE_URL              -> ej. https://abcxyzabc.supabase.co
    SUPABASE_SERVICE_ROLE_KEY -> la "service_role" key (NO la "anon" key),
                                  la encontrás en Supabase: Project Settings
                                  -> API -> Project API keys -> service_role.
                                  Esta key tiene permisos para escribir aunque
                                  la tabla tenga Row Level Security activado.

Uso:
    python subir_a_supabase.py --csv juegos_para_web.csv --tabla juegos_web
"""

import argparse
import os
import sys

import pandas as pd
import requests

COLUMNAS_TABLA = [
    "fuente", "tienda", "nombre", "nombre_limpio", "precio_original",
    "moneda", "precio_uyu", "plataforma", "link", "nombre_key",
    "demanda", "competitividad", "score_venta", "nivel",
    "costo_uyu", "precio_venta_uyu", "ganancia_uyu", "margen_sobre_venta",
]

TAMANO_LOTE = 500  # filas por request, para no mandar 6000 filas en un solo POST


def cargar_csv(ruta_csv):
    df = pd.read_csv(ruta_csv)
    df.columns = COLUMNAS_TABLA[: len(df.columns)]
    # NaN no es JSON válido -> lo convertimos a None (se guarda como NULL)
    df = df.where(pd.notnull(df), None)
    return df.to_dict(orient="records")


def borrar_todo(base_url, headers, tabla):
    url = f"{base_url}/rest/v1/{tabla}?id=gte.0"
    r = requests.delete(url, headers=headers, timeout=30)
    if r.status_code not in (200, 204):
        print(f"[ERROR] No se pudo vaciar la tabla '{tabla}': {r.status_code} {r.text}")
        sys.exit(1)
    print(f"[OK] Tabla '{tabla}' vaciada.")


def insertar_filas(base_url, headers, tabla, filas):
    url = f"{base_url}/rest/v1/{tabla}"
    total = len(filas)
    for i in range(0, total, TAMANO_LOTE):
        lote = filas[i:i + TAMANO_LOTE]
        r = requests.post(url, headers=headers, json=lote, timeout=60)
        if r.status_code not in (200, 201):
            print(f"[ERROR] Falló la inserción del lote {i}-{i+len(lote)}: {r.status_code} {r.text}")
            sys.exit(1)
        print(f"[OK] Insertadas filas {i + 1} a {min(i + TAMANO_LOTE, total)} de {total}")


def main():
    ap = argparse.ArgumentParser(description="Sube un catálogo CSV a una tabla de Supabase")
    ap.add_argument("--csv", required=True, help="Ruta al CSV (ej. juegos_para_web.csv)")
    ap.add_argument("--tabla", default="juegos_web", help="Nombre de la tabla en Supabase")
    args = ap.parse_args()

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")

    if not supabase_url or not supabase_key:
        print("[ERROR] Faltan las variables de entorno SUPABASE_URL y/o SUPABASE_SERVICE_ROLE_KEY.")
        sys.exit(1)

    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal",
    }

    print(f"Leyendo {args.csv}...")
    filas = cargar_csv(args.csv)
    print(f"{len(filas)} filas a subir a la tabla '{args.tabla}'.")

    borrar_todo(supabase_url, headers, args.tabla)
    insertar_filas(supabase_url, headers, args.tabla, filas)

    print("[OK] Catálogo actualizado en Supabase.")


if __name__ == "__main__":
    main()

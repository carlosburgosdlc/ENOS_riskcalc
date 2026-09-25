#!/usr/bin/env python3
"""Descarga el ONI oficial de NOAA CPC y regenera superninio/datos/oni.json.

Uso: python3 scripts/update_oni.py
Fuente: https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt (ERSSTv5)
"""
import datetime as dt
import json
import pathlib
import urllib.request

URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
SEASONS = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND", "NDJ"]
OUT = pathlib.Path(__file__).resolve().parents[1] / "superninio" / "datos" / "oni.json"


def main() -> None:
    text = urllib.request.urlopen(URL, timeout=60).read().decode()
    oni: dict[int, list] = {}
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 4 or parts[0] not in SEASONS:
            continue
        oni.setdefault(int(parts[1]), [None] * 12)[SEASONS.index(parts[0])] = float(parts[3])
    if len(oni) < 70:
        raise SystemExit(f"Respuesta inesperada de CPC ({len(oni)} años)")
    data = {"meta": {"provisional": False, "fuente": URL, "actualizado": dt.date.today().isoformat()},
            "oni": {str(y): v for y, v in sorted(oni.items())}}
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    print(f"ONI actualizado: {min(oni)}-{max(oni)} -> {OUT}")


if __name__ == "__main__":
    main()

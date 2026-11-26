"""Buduje app/resources/places.tsv.gz z danych GeoNames (CC BY 4.0, https://www.geonames.org).

Użycie:
    python tools/build_places.py <cities1000.zip> <countryInfo.txt>
"""
import gzip
import io
import sys
import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "app" / "resources" / "places.tsv.gz"


def main(zip_path: str, country_info: str) -> None:
    countries = {}
    for line in Path(country_info).read_text("utf-8").splitlines():
        if line.startswith("#") or not line.strip():
            continue
        parts = line.split("\t")
        countries[parts[0]] = parts[4]
    rows = []
    with zipfile.ZipFile(zip_path) as zf:
        with zf.open("cities1000.txt") as fh:
            for line in io.TextIOWrapper(fh, "utf-8"):
                p = line.rstrip("\n").split("\t")
                name, lat, lon, cc = p[1], float(p[4]), float(p[5]), p[8]
                rows.append(f"{lat:.4f}\t{lon:.4f}\t{name}\t{cc}")
    with gzip.open(OUT, "wt", encoding="utf-8", compresslevel=9) as out:
        for cc, cname in sorted(countries.items()):
            out.write(f"#C\t{cc}\t{cname}\n")
        out.write("\n".join(rows))
    print(f"{len(rows)} miejscowości -> {OUT} ({OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])

"""Ustalanie miasta i kraju na podstawie współrzędnych GPS — całkowicie offline.

Dane: GeoNames cities1000 (CC BY 4.0, https://www.geonames.org) — ok. 170 tys.
miejscowości powyżej 1000 mieszkańców, wbudowane w aplikację (resources/places.tsv.gz).
"""
from __future__ import annotations

import gzip
import math
import sys
import threading
from pathlib import Path

from app.i18n import is_english, tr

# Polskie nazwy krajów i miast — używane tylko w polskim interfejsie
# (po angielsku: nazwy z GeoNames). To dane, nie tekst do tr().
COUNTRY_PL = {
    "PL": "Polska", "DE": "Niemcy", "CZ": "Czechy", "SK": "Słowacja", "UA": "Ukraina",  # i18n: ignore
    "LT": "Litwa", "LV": "Łotwa", "EE": "Estonia", "BY": "Białoruś", "RU": "Rosja",  # i18n: ignore
    "AT": "Austria", "CH": "Szwajcaria", "IT": "Włochy", "FR": "Francja", "ES": "Hiszpania",  # i18n: ignore
    "PT": "Portugalia", "GB": "Wielka Brytania", "IE": "Irlandia", "NL": "Holandia",
    "BE": "Belgia", "LU": "Luksemburg", "DK": "Dania", "SE": "Szwecja", "NO": "Norwegia",
    "FI": "Finlandia", "IS": "Islandia", "HU": "Węgry", "RO": "Rumunia", "BG": "Bułgaria",  # i18n: ignore
    "GR": "Grecja", "TR": "Turcja", "HR": "Chorwacja", "SI": "Słowenia", "RS": "Serbia",  # i18n: ignore
    "BA": "Bośnia i Hercegowina", "ME": "Czarnogóra", "MK": "Macedonia Północna",  # i18n: ignore
    "AL": "Albania", "MT": "Malta", "CY": "Cypr", "MD": "Mołdawia", "GE": "Gruzja",  # i18n: ignore
    "AM": "Armenia", "AZ": "Azerbejdżan", "EG": "Egipt", "TN": "Tunezja", "MA": "Maroko",  # i18n: ignore
    "US": "Stany Zjednoczone", "CA": "Kanada", "MX": "Meksyk", "BR": "Brazylia",
    "AR": "Argentyna", "CN": "Chiny", "JP": "Japonia", "IN": "Indie", "TH": "Tajlandia",
    "VN": "Wietnam", "ID": "Indonezja", "AU": "Australia", "NZ": "Nowa Zelandia",
    "AE": "Zjednoczone Emiraty Arabskie", "IL": "Izrael", "JO": "Jordania", "ZA": "RPA",
    "KE": "Kenia", "TZ": "Tanzania", "DO": "Dominikana", "CU": "Kuba", "SC": "Seszele",
    "MV": "Malediwy", "LK": "Sri Lanka", "KR": "Korea Południowa", "SG": "Singapur",  # i18n: ignore
    "MY": "Malezja", "PH": "Filipiny", "VA": "Watykan", "SM": "San Marino", "MC": "Monako",
    "AD": "Andora", "LI": "Liechtenstein",
}

CITY_PL = {
    ("PL", "Warsaw"): "Warszawa", ("IT", "Rome"): "Rzym", ("IT", "Milan"): "Mediolan",
    ("IT", "Venice"): "Wenecja", ("IT", "Naples"): "Neapol", ("IT", "Florence"): "Florencja",
    ("DE", "Munich"): "Monachium", ("DE", "Cologne"): "Kolonia", ("CZ", "Prague"): "Praga",
    ("AT", "Vienna"): "Wiedeń", ("GB", "London"): "Londyn", ("FR", "Paris"): "Paryż",  # i18n: ignore
    ("BE", "Brussels"): "Bruksela", ("DK", "Copenhagen"): "Kopenhaga",
    ("LT", "Vilnius"): "Wilno", ("UA", "Lviv"): "Lwów", ("UA", "Kyiv"): "Kijów",  # i18n: ignore
    ("ES", "Seville"): "Sewilla", ("PT", "Lisbon"): "Lizbona", ("GR", "Athens"): "Ateny",
    ("HU", "Budapest"): "Budapeszt", ("SE", "Stockholm"): "Sztokholm", ("NL", "The Hague"): "Haga",
}

_CELL = 0.5  # stopnie


def _resource_path() -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parents[2]))
    return base / "app" / "resources" / "places.tsv.gz"


class Geocoder:
    _instance: "Geocoder | None" = None
    _lock = threading.Lock()

    def __init__(self, path: Path | None = None):
        self.grid: dict[tuple[int, int], list[tuple[float, float, str, str]]] = {}
        self.countries: dict[str, str] = {}
        self.available = False
        path = path or _resource_path()
        try:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                for line in fh:
                    if line.startswith("#C\t"):
                        _, cc, name = line.rstrip("\n").split("\t", 2)
                        self.countries[cc] = name
                        continue
                    parts = line.rstrip("\n").split("\t")
                    if len(parts) != 4:
                        continue
                    lat, lon = float(parts[0]), float(parts[1])
                    key = (int(math.floor(lat / _CELL)), int(math.floor(lon / _CELL)))
                    self.grid.setdefault(key, []).append((lat, lon, parts[2], parts[3]))
            self.available = True
        except OSError:
            self.available = False

    @classmethod
    def shared(cls) -> "Geocoder":
        with cls._lock:
            if cls._instance is None:
                cls._instance = Geocoder()
            return cls._instance

    def country_name(self, cc: str) -> str:
        if is_english():
            return self.countries.get(cc) or cc
        return COUNTRY_PL.get(cc) or self.countries.get(cc) or cc

    def lookup(self, lat: float, lon: float) -> str | None:
        """Zwraca np. „Kraków, Polska” albo „okolice: Mielno, Polska”."""
        if not self.available:
            return None
        ci, cj = int(math.floor(lat / _CELL)), int(math.floor(lon / _CELL))
        best = None
        best_d = 1e18
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for plat, plon, name, cc in self.grid.get((ci + di, cj + dj), ()):
                    d = _haversine_km(lat, lon, plat, plon)
                    if d < best_d:
                        best_d, best = d, (name, cc)
        if best is None or best_d > 60:
            return None
        name, cc = best
        if not is_english():
            name = CITY_PL.get((cc, name), name)
        place = f"{name}, {self.country_name(cc)}"
        if best_d > 4:
            return tr("okolice: {place}", place=place)
        return place


def _haversine_km(lat1, lon1, lat2, lon2) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def map_url(lat: float, lon: float) -> str:
    return f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=15/{lat:.6f}/{lon:.6f}"

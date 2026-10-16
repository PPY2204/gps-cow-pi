"""Trajectory export services for GIS (QGIS, GeoJSON) and clean dataset analysis."""
import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Union


def export_clean_csv(
    input_csv_path: Union[str, Path],
    output_csv_path: Union[str, Path],
) -> int:
    """Filter processed CSV to keep only validated, accepted GPS points."""
    in_p = Path(input_csv_path)
    out_p = Path(output_csv_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    count = 0
    with open(in_p, "r", encoding="utf-8") as f_in, open(out_p, "w", newline="", encoding="utf-8") as f_out:
        reader = csv.DictReader(f_in)
        fieldnames = reader.fieldnames or []
        writer = csv.DictWriter(f_out, fieldnames=fieldnames)
        writer.writeheader()

        for row in reader:
            if row.get("accepted") == "1":
                writer.writerow(row)
                count += 1
    return count


def export_geojson(
    input_csv_path: Union[str, Path],
    output_geojson_path: Union[str, Path],
) -> Dict[str, Any]:
    """Convert accepted GPS measurements into standard GeoJSON FeatureCollection."""
    in_p = Path(input_csv_path)
    out_p = Path(output_geojson_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    coordinates: List[List[float]] = []
    features: List[Dict[str, Any]] = []

    with open(in_p, "r", encoding="utf-8") as f_in:
        reader = csv.DictReader(f_in)
        for row in reader:
            if row.get("accepted") != "1":
                continue

            lat_str = row.get("latitude")
            lon_str = row.get("longitude")
            if not lat_str or not lon_str:
                continue

            lat = float(lat_str)
            lon = float(lon_str)
            alt = float(row.get("altitude") or 0.0)
            coordinates.append([lon, lat, alt])

            # Point feature
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lon, lat, alt],
                    },
                    "properties": {
                        "utc_time": row.get("utc_time"),
                        "timestamp": row.get("timestamp"),
                        "speed_kmh": float(row.get("speed_kmh") or 0.0),
                        "behavior_state": row.get("behavior_state"),
                        "satellites": int(row.get("satellites") or 0),
                        "hdop": float(row.get("hdop") or 0.0),
                    },
                }
            )

    # Add whole trajectory LineString as first feature
    if coordinates:
        line_feature = {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coordinates,
            },
            "properties": {
                "name": in_p.stem,
                "total_points": len(coordinates),
            },
        }
        features.insert(0, line_feature)

    geojson_doc = {
        "type": "FeatureCollection",
        "features": features,
    }

    with open(out_p, "w", encoding="utf-8") as f_out:
        json.dump(geojson_doc, f_out, indent=2)

    return {"total_exported_points": len(coordinates), "file": str(out_p)}

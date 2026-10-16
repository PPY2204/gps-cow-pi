from pathlib import Path
import json
import pytest
from human_gps.domain.models import SubjectProfile
from human_gps.services.export import export_clean_csv, export_geojson
from human_gps.services.replay import ReplayService


def test_full_replay_and_export_pipeline(tmp_path: Path):
    fixture_path = Path("tests/fixtures/nmea/valid_epoch.txt")
    output_dir = tmp_path / "processed"

    # 1. Run Replay
    replay = ReplayService(
        filepath=fixture_path,
        profile=SubjectProfile.cow_default(),
        subject_id="TEST-COW-99",
        output_dir=output_dir,
        realtime_delay=False,
    )
    summary = replay.run()

    assert summary["total_epochs"] >= 3
    assert summary["accepted_epochs"] >= 3
    assert summary["fix_rate_percent"] == 100.0

    csv_path = Path(summary["output_csv"])
    assert csv_path.exists()
    assert csv_path.stat().st_size > 0

    # 2. Test Clean CSV Export
    clean_csv = tmp_path / "clean.csv"
    exported_count = export_clean_csv(csv_path, clean_csv)
    assert exported_count >= 3

    # 3. Test GeoJSON Export
    geojson_path = tmp_path / "trajectory.geojson"
    geo_res = export_geojson(csv_path, geojson_path)
    assert geo_res["total_exported_points"] >= 3

    with open(geojson_path, "r", encoding="utf-8") as f:
        geo_data = json.load(f)
        assert geo_data["type"] == "FeatureCollection"
        assert len(geo_data["features"]) >= 4  # 1 LineString + at least 3 Points
        assert geo_data["features"][0]["geometry"]["type"] == "LineString"
        assert geo_data["features"][1]["geometry"]["type"] == "Point"

"""Command Line Interface (CLI) entrypoint for human_gps."""
import argparse
from pathlib import Path
import sys
import time
from typing import Optional

from human_gps.acquisition.reconnect import ResilientStreamReader
from human_gps.device.session import SessionManager
from human_gps.domain.enums import MountType, SubjectType
from human_gps.domain.models import GPSMeasurement, SubjectProfile
from human_gps.services.export import export_clean_csv, export_geojson
from human_gps.services.recorder import RecorderService
from human_gps.services.replay import ReplayService


def get_profile(name: str) -> SubjectProfile:
    name_clean = name.strip().lower()
    if name_clean in ("cow", "bovine", "cattle"):
        return SubjectProfile.cow_default()
    elif name_clean in ("human", "person", "walker"):
        return SubjectProfile.human_default()
    else:
        return SubjectProfile(
            subject_type=SubjectType(name.upper()),
        )


import http.server
import json
import socketserver
import threading


class LiveStatusHandler(http.server.BaseHTTPRequestHandler):
    """Zero-dependency HTTP server serving live status and diagnostic dashboard."""
    recorder_ref: Optional[RecorderService] = None
    is_recording: bool = False  # Standby on boot!

    def log_message(self, format, *args):
        pass  # Suppress console clutter

    def do_GET(self):
        if self.path == "/api/gps" or self.path == "/api/health":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            
            rec = LiveStatusHandler.recorder_ref
            is_rec = LiveStatusHandler.is_recording
            meas = rec.latest_measurement if rec else None
            summary = rec.health.summary() if rec else {}
            live = rec.live_telemetry if rec else {}

            lat = meas.latitude if (meas and meas.latitude is not None) else live.get("latitude")
            lon = meas.longitude if (meas and meas.longitude is not None) else live.get("longitude")
            alt = meas.altitude if (meas and meas.altitude is not None) else live.get("altitude")
            speed = meas.speed_kmh if (meas and meas.speed_kmh is not None) else live.get("speed_kmh")
            sats = live.get("satellites", (meas.satellites if meas else 0))
            hdop = live.get("hdop", (meas.hdop if meas else None))
            fix_q = live.get("fix_quality", (meas.fix_quality.value if meas else "INVALID"))
            behavior = meas.behavior_state.value if meas else "UNKNOWN"
            accepted = meas.is_accepted if meas else False

            data = {
                "online": True,
                "recording": is_rec,
                "session_id": rec.session_mgr.session_id if rec else None,
                "subject_id": rec.session_mgr.metadata.subject_id if rec else "COW-NARO-001",
                "uptime_seconds": summary.get("uptime_seconds", 0),
                "sampling_hz": summary.get("current_sampling_hz", 0.0),
                "total_sentences": summary.get("total_sentences", 0),
                "accepted_epochs": summary.get("accepted_epochs", 0),
                "rejected_epochs": summary.get("rejected_epochs", 0),
                "last_sentence": rec.health.last_sentence if rec else "",
                "latitude": lat,
                "longitude": lon,
                "altitude": alt,
                "speed_kmh": speed,
                "satellites": sats,
                "hdop": hdop,
                "fix_quality": fix_q,
                "behavior": behavior,
                "accepted": accepted,
            }
            self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))
            return

        elif self.path == "/api/record/start":
            LiveStatusHandler.is_recording = True
            session_id = ""
            if LiveStatusHandler.recorder_ref:
                session_id = LiveStatusHandler.recorder_ref.start_new_session()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "recording_started", "session_id": session_id}).encode("utf-8"))
            return

        elif self.path == "/api/record/stop":
            LiveStatusHandler.is_recording = False
            if LiveStatusHandler.recorder_ref:
                LiveStatusHandler.recorder_ref.stop_recording()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "recording_stopped"}).encode("utf-8"))
            return

        elif self.path.startswith("/api/file/delete?file="):
            file_param = self.path.split("/api/file/delete?file=", 1)[1]
            import urllib.parse
            clean_path = Path(urllib.parse.unquote(file_param))
            if clean_path.exists() and clean_path.is_file() and "data" in clean_path.parts:
                try:
                    clean_path.unlink()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Access-Control-Allow-Origin", "*")
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "deleted"}).encode("utf-8"))
                    return
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                    return
            self.send_response(404)
            self.end_headers()
            return

        elif self.path == "/api/files":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()

            files_list = []
            scan_dirs = [
                Path.home() / "naro-gps-nathan" / "data" / "processed",
                Path.home() / "naro-gps-nathan" / "data" / "raw",
                Path("data/processed"),
                Path("data/raw"),
            ]
            seen_names = set()
            for root_dir in scan_dirs:
                if root_dir.exists():
                    for p in sorted(root_dir.rglob("*"), reverse=True):
                        if p.is_file() and p.suffix in [".csv", ".nmea", ".db", ".geojson"] and p.name not in seen_names:
                            seen_names.add(p.name)
                            ftype = "processed" if p.suffix in [".csv", ".geojson"] else ("raw" if p.suffix == ".nmea" else "db")
                            files_list.append({
                                "name": p.name,
                                "type": ftype,
                                "ext": p.suffix.lstrip("."),
                                "path": str(p.as_posix()),
                                "size_kb": round(p.stat().st_size / 1024, 1),
                                "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p.stat().st_mtime)),
                            })
            self.wfile.write(json.dumps(files_list, indent=2).encode("utf-8"))
            return

        elif self.path.startswith("/download?file="):
            file_param = self.path.split("/download?file=", 1)[1]
            import urllib.parse
            clean_path = Path(urllib.parse.unquote(file_param))
            if clean_path.exists() and clean_path.is_file() and "data" in clean_path.parts:
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Disposition", f'attachment; filename="{clean_path.name}"')
                self.send_header("Content-Length", str(clean_path.stat().st_size))
                self.end_headers()
                with open(clean_path, "rb") as f:
                    self.wfile.write(f.read())
                return
            else:
                self.send_response(404)
                self.end_headers()
                return

        # Clean, modern, light-themed web interface
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>NARO GNSS Monitor</title>
  <!-- Leaflet Map CSS & JS -->
  <link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css" />
  <script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
  <style>
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      background-color: #f8fafc;
      color: #0f172a;
      margin: 0;
      padding: 16px;
      font-size: 14px;
      line-height: 1.5;
    }
    .container {
      max-width: 860px;
      margin: 0 auto;
    }
    .card {
      background: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 10px;
      padding: 16px;
      margin-bottom: 16px;
      box-shadow: 0 1px 3px rgba(0,0,0,0.04);
    }
    .card-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 12px;
      border-bottom: 1px solid #f1f5f9;
      padding-bottom: 8px;
    }
    .card-title {
      font-size: 1rem;
      font-weight: 600;
      color: #1e293b;
      margin: 0;
    }
    .badge {
      display: inline-block;
      padding: 3px 10px;
      border-radius: 999px;
      font-size: 11px;
      font-weight: 600;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }
    .badge-standby { background: #f1f5f9; color: #475569; border: 1px solid #cbd5e1; }
    .badge-recording { background: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; }
    .badge-fix-ok { background: #dcfce7; color: #15803d; border: 1px solid #86efac; }
    .badge-fix-no { background: #fef3c7; color: #b45309; border: 1px solid #fcd34d; }

    /* Control Button */
    .btn-action {
      width: 100%;
      padding: 12px;
      border-radius: 8px;
      font-size: 15px;
      font-weight: 600;
      border: none;
      cursor: pointer;
      transition: background-color 0.15s ease;
      color: #ffffff;
    }
    .btn-start { background-color: #16a34a; }
    .btn-start:hover { background-color: #15803d; }
    .btn-stop { background-color: #dc2626; }
    .btn-stop:hover { background-color: #b91c1c; }

    /* KPI Metrics Grid */
    .metrics-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 12px;
    }
    @media (max-width: 600px) {
      .metrics-grid { grid-template-columns: repeat(2, 1fr); }
    }
    .metric-box {
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 10px 12px;
    }
    .metric-label {
      font-size: 11px;
      color: #64748b;
      font-weight: 500;
      text-transform: uppercase;
      margin-bottom: 4px;
    }
    .metric-val {
      font-size: 18px;
      font-weight: 700;
      color: #0f172a;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
    }
    .info-list {
      display: flex;
      flex-direction: column;
      gap: 8px;
      font-size: 13px;
    }
    .info-row {
      display: flex;
      justify-content: space-between;
      border-bottom: 1px solid #f8fafc;
      padding-bottom: 4px;
    }
    .info-label { color: #64748b; }
    .info-value { font-weight: 600; font-family: ui-monospace, SFMono-Regular, monospace; }

    /* Map Styling */
    #map {
      height: 380px;
      width: 100%;
      border-radius: 8px;
      border: 1px solid #cbd5e1;
      background: #e2e8f0;
    }
    .map-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-top: 8px;
      font-size: 12px;
      color: #64748b;
    }
    .btn-secondary {
      background: #ffffff;
      border: 1px solid #cbd5e1;
      color: #334155;
      padding: 5px 12px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
    }
    .btn-secondary:hover { background: #f1f5f9; }

    /* Raw NMEA Stream */
    .nmea-box {
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 12px;
      background: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 6px;
      padding: 8px 12px;
      color: #0369a1;
      word-break: break-all;
      overflow-x: auto;
    }

    /* Filter Tabs & Table */
    .filter-tabs {
      display: flex;
      gap: 6px;
      margin-bottom: 12px;
      overflow-x: auto;
    }
    .tab-btn {
      background: #f1f5f9;
      color: #64748b;
      border: 1px solid #e2e8f0;
      padding: 6px 14px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 500;
      cursor: pointer;
      white-space: nowrap;
    }
    .tab-btn.active {
      background: #0284c7;
      color: #ffffff;
      border-color: #0284c7;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    th {
      text-align: left;
      padding: 8px;
      background: #f8fafc;
      color: #64748b;
      font-weight: 600;
      border-bottom: 1px solid #e2e8f0;
    }
    td {
      padding: 10px 8px;
      border-bottom: 1px solid #f1f5f9;
      vertical-align: middle;
    }
    .tag-pill {
      display: inline-block;
      padding: 2px 7px;
      border-radius: 4px;
      font-size: 10px;
      font-weight: 600;
      margin-right: 6px;
    }
    .tag-csv { background: #dcfce7; color: #166534; }
    .tag-raw { background: #e0f2fe; color: #075985; }
    .tag-db { background: #f3e8ff; color: #6b21a8; }
    .btn-link {
      color: #0284c7;
      text-decoration: none;
      font-weight: 500;
      margin-right: 12px;
      font-size: 12px;
    }
    .btn-link:hover { text-decoration: underline; }
    .btn-link-del { color: #dc2626; cursor: pointer; border: none; background: none; font-size: 12px; font-weight: 500; }
    .btn-link-del:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="container">
    <!-- Status & Recording Control -->
    <div class="card">
      <div class="card-header">
        <div>
          <h1 class="card-title">NARO GNSS Tracking System</h1>
          <div style="font-size: 12px; color: #64748b; margin-top: 2px;">
            Subject: <strong id="subject">--</strong> &bull; Session: <span id="session">--</span>
          </div>
        </div>
        <span id="badge" class="badge badge-standby">STANDBY</span>
      </div>
      <div>
        <button id="btn-rec" class="btn-action btn-start" onclick="toggleRecording()">
          Start Recording
        </button>
      </div>
    </div>

    <!-- Real-time Trajectory Map -->
    <div class="card">
      <div class="card-header">
        <h2 class="card-title">Live Field Map</h2>
        <button class="btn-secondary" onclick="recenterMap()">Recenter Map</button>
      </div>
      <div id="map"></div>
      <div class="map-bar">
        <span id="map-status">Initializing map layers...</span>
        <span id="track-stats">Recorded: 0 points</span>
      </div>
    </div>

    <!-- Live Telemetry KPI -->
    <div class="card">
      <div class="card-header">
        <h2 class="card-title">Live Telemetry</h2>
        <span id="fix-badge" class="badge badge-fix-no">NO FIX</span>
      </div>
      <div class="metrics-grid">
        <div class="metric-box">
          <div class="metric-label">Satellites</div>
          <div id="sats" class="metric-val">0</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">HDOP Noise</div>
          <div id="hdop" class="metric-val">--</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">Speed</div>
          <div id="speed" class="metric-val">-- km/h</div>
        </div>
        <div class="metric-box">
          <div class="metric-label">Rate</div>
          <div id="hz" class="metric-val">0.0 Hz</div>
        </div>
      </div>
      <div class="info-list">
        <div class="info-row">
          <span class="info-label">Coordinates</span>
          <span id="coords" class="info-value">Waiting for GPS lock...</span>
        </div>
        <div class="info-row">
          <span class="info-label">Altitude</span>
          <span id="alt" class="info-value">--</span>
        </div>
        <div class="info-row">
          <span class="info-label">Behavior State</span>
          <span id="behavior" class="info-value">--</span>
        </div>
      </div>
    </div>

    <!-- Live NMEA Stream -->
    <div class="card">
      <div class="card-header">
        <h2 class="card-title">Live NMEA Sentence</h2>
      </div>
      <div id="raw" class="nmea-box">Waiting for serial stream...</div>
    </div>

    <!-- Recorded Data Management -->
    <div class="card">
      <div class="card-header">
        <h2 class="card-title">Recorded Data Files</h2>
        <button class="btn-secondary" onclick="fetchFiles()">Refresh</button>
      </div>
      <div class="filter-tabs">
        <button class="tab-btn active" onclick="setFilter('all', this)">All Files (<span id="cnt-all">0</span>)</button>
        <button class="tab-btn" onclick="setFilter('processed', this)">Processed CSV (<span id="cnt-csv">0</span>)</button>
        <button class="tab-btn" onclick="setFilter('raw', this)">Raw NMEA (<span id="cnt-raw">0</span>)</button>
        <button class="tab-btn" onclick="setFilter('db', this)">Database (<span id="cnt-db">0</span>)</button>
      </div>
      <div style="overflow-x: auto;">
        <table>
          <thead>
            <tr>
              <th>File Name</th>
              <th>Size</th>
              <th style="text-align: right;">Action</th>
            </tr>
          </thead>
          <tbody id="files-tbody">
            <tr><td colspan="3" style="text-align: center; color: #94a3b8; padding: 16px;">Loading files...</td></tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>

  <script>
    let isRec = false;
    let map = null;
    let marker = null;
    let polyline = null;
    let mapCentered = false;
    let trackPoints = [];
    let allFiles = [];
    let currentFilter = 'all';

    // Initialize Leaflet Map with Street and Satellite layers
    function initMap() {
      try {
        if (typeof L === 'undefined') {
          document.getElementById('map-status').innerText = 'Leaflet script loading...';
          setTimeout(initMap, 500);
          return;
        }

        // Layer 1: OpenStreetMap Standard
        const osmLayer = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
          maxZoom: 19,
          attribution: '&copy; OpenStreetMap contributors'
        });

        // Layer 2: Esri Satellite World Imagery (High-res aerial imagery for field/pasture)
        const satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
          maxZoom: 19,
          attribution: '&copy; Esri World Imagery'
        });

        // Layer 3: CartoDB Positron (Ultra-clean light map)
        const cartoLight = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
          maxZoom: 19,
          attribution: '&copy; CartoDB'
        });

        map = L.map('map', {
          center: [36.03, 140.13],
          zoom: 16,
          layers: [osmLayer]
        });

        // Base maps layer switcher
        const baseMaps = {
          "Street Map (OSM)": osmLayer,
          "Satellite (Aerial)": satelliteLayer,
          "Clean Light": cartoLight
        };
        L.control.layers(baseMaps).addTo(map);

        // Path polyline
        polyline = L.polyline([], {
          color: '#2563eb',
          weight: 4,
          opacity: 0.85
        }).addTo(map);

        document.getElementById('map-status').innerText = 'Map ready (Select Street / Satellite top-right)';
      } catch (err) {
        document.getElementById('map-status').innerText = 'Map tile loading paused (Offline mode active).';
      }
    }

    function recenterMap() {
      if (marker && map) {
        map.setView(marker.getLatLng(), 17);
      }
    }

    // Telemetry Polling (Runs every 1 second)
    async function updateTelemetry() {
      try {
        const res = await fetch('/api/gps');
        const d = await res.json();

        // Update recording state & button
        isRec = !!d.recording;
        updateRecButton(isRec);

        // Header info
        document.getElementById('subject').innerText = d.subject_id || '--';
        document.getElementById('session').innerText = d.session_id || 'Standby (Click Start to begin)';
        
        // Metrics
        document.getElementById('sats').innerText = d.satellites != null ? d.satellites : 0;
        document.getElementById('hdop').innerText = d.hdop != null ? d.hdop.toFixed(2) : '--';
        document.getElementById('speed').innerText = d.speed_kmh != null ? d.speed_kmh.toFixed(1) + ' km/h' : '-- km/h';
        document.getElementById('hz').innerText = (d.sampling_hz || 0).toFixed(1) + ' Hz';
        document.getElementById('alt').innerText = d.altitude != null ? d.altitude.toFixed(1) + ' m' : '--';
        document.getElementById('behavior').innerText = d.behavior || '--';
        document.getElementById('raw').innerText = d.last_sentence || 'Listening for NMEA sentences...';

        // Fix Badge
        const fixBadge = document.getElementById('fix-badge');
        const hasCoords = d.latitude != null && d.longitude != null;
        if (hasCoords && d.satellites >= 4) {
          fixBadge.className = 'badge badge-fix-ok';
          fixBadge.innerText = `${d.fix_quality || 'FIX OK'} (${d.satellites} Sats)`;
          document.getElementById('coords').innerText = `${d.latitude.toFixed(6)}° N, ${d.longitude.toFixed(6)}° E`;

          // Update Map
          if (map) {
            const pos = [d.latitude, d.longitude];
            if (!marker) {
              marker = L.circleMarker(pos, {
                radius: 8,
                fillColor: '#2563eb',
                color: '#ffffff',
                weight: 2,
                opacity: 1,
                fillOpacity: 0.9
              }).addTo(map);
              marker.bindPopup(`<strong>${d.subject_id}</strong><br>Speed: ${d.speed_kmh || 0} km/h`);
            } else {
              marker.setLatLng(pos);
            }

            polyline.addLatLng(pos);
            trackPoints.push(pos);
            document.getElementById('track-stats').innerText = `Recorded: ${trackPoints.length} points`;

            if (!mapCentered) {
              map.setView(pos, 17);
              mapCentered = true;
            }
          }
        } else {
          fixBadge.className = 'badge badge-fix-no';
          fixBadge.innerText = `${d.fix_quality || 'NO FIX'} (${d.satellites || 0} Sats)`;
          if (!hasCoords) {
            document.getElementById('coords').innerText = 'Searching for satellites...';
          }
        }

        // Recording Status Badge
        const badge = document.getElementById('badge');
        if (isRec) {
          badge.className = 'badge badge-recording';
          badge.innerText = 'RECORDING';
        } else {
          badge.className = 'badge badge-standby';
          badge.innerText = 'STANDBY';
        }

      } catch (err) {
        document.getElementById('badge').className = 'badge badge-standby';
        document.getElementById('badge').innerText = 'DISCONNECTED';
      }
    }

    // Toggle Recording
    async function toggleRecording() {
      const endpoint = isRec ? '/api/record/stop' : '/api/record/start';
      await fetch(endpoint);
      isRec = !isRec;
      updateRecButton(isRec);
      if (isRec && polyline) {
        polyline.setLatLngs([]);
        trackPoints = [];
      }
      setTimeout(fetchFiles, 600);
    }

    function updateRecButton(rec) {
      const btn = document.getElementById('btn-rec');
      if (btn) {
        if (rec) {
          btn.className = 'btn-action btn-stop';
          btn.innerText = 'Stop Recording';
        } else {
          btn.className = 'btn-action btn-start';
          btn.innerText = 'Start Recording';
        }
      }
    }

    // File Management
    async function fetchFiles() {
      try {
        const res = await fetch('/api/files');
        allFiles = await res.json();

        // Update counts
        document.getElementById('cnt-all').innerText = allFiles.length;
        document.getElementById('cnt-csv').innerText = allFiles.filter(f => f.type === 'processed').length;
        document.getElementById('cnt-raw').innerText = allFiles.filter(f => f.type === 'raw').length;
        document.getElementById('cnt-db').innerText = allFiles.filter(f => f.type === 'db').length;

        renderFiles();
      } catch (e) {}
    }

    function setFilter(type, el) {
      currentFilter = type;
      document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
      if (el) el.classList.add('active');
      renderFiles();
    }

    function renderFiles() {
      const tbody = document.getElementById('files-tbody');
      const filtered = currentFilter === 'all' ? allFiles : allFiles.filter(f => f.type === currentFilter);

      if (filtered.length === 0) {
        tbody.innerHTML = '<tr><td colspan="3" style="text-align: center; color: #94a3b8; padding: 18px;">No files found in this category.</td></tr>';
        return;
      }

      tbody.innerHTML = filtered.map(f => {
        let tagClass = 'tag-raw';
        let tagLabel = 'RAW NMEA';
        if (f.type === 'processed') {
          tagClass = 'tag-csv';
          tagLabel = 'CLEAN CSV';
        } else if (f.type === 'db') {
          tagClass = 'tag-db';
          tagLabel = 'DATABASE';
        }

        return `
          <tr>
            <td>
              <div><span class="tag-pill ${tagClass}">${tagLabel}</span><strong>${f.name}</strong></div>
              <div style="font-size: 11px; color: #64748b; margin-top: 2px;">${f.modified}</div>
            </td>
            <td style="font-family: ui-monospace, monospace; white-space: nowrap;">${f.size_kb} KB</td>
            <td style="text-align: right; white-space: nowrap;">
              <a class="btn-link" href="/download?file=${encodeURIComponent(f.path)}">Download</a>
              <button class="btn-link-del" onclick="deleteFile('${encodeURIComponent(f.path)}')">Delete</button>
            </td>
          </tr>
        `;
      }).join('');
    }

    async function deleteFile(encodedPath) {
      if (!confirm('Permanently delete this file?')) return;
      try {
        await fetch('/api/file/delete?file=' + encodedPath);
        fetchFiles();
      } catch (e) {
        alert('Failed to delete file');
      }
    }

    // Startup
    initMap();
    setInterval(updateTelemetry, 1000);
    updateTelemetry();
    fetchFiles();
  </script>
</body>
</html>"""
        self.wfile.write(html.encode("utf-8"))


def start_monitor_server(port: int = 8000) -> Optional[socketserver.TCPServer]:
    try:
        class ReuseTCPServer(socketserver.TCPServer):
            allow_reuse_address = True

        server = ReuseTCPServer(("0.0.0.0", port), LiveStatusHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        return server
    except Exception as e:
        print(f"Warning: Could not bind web monitor on port {port}: {e}")
        return None


def cmd_record(args: argparse.Namespace) -> int:
    """Run live GPS acquisition directly to SD card with optional instant web monitor."""
    profile = get_profile(args.profile)
    mount = MountType(args.mount.upper()) if hasattr(MountType, args.mount.upper()) else MountType.COLLAR

    print(f"=== Starting GPS Acquisition & Telemetry ===")
    print(f"Port:       {args.port}")
    print(f"Baud rate:  {args.baud}")
    print(f"Profile:    {profile.subject_type.value} (Max speed: {profile.max_speed_kmh} km/h)")
    print(f"Subject ID: {args.subject_id}")
    print(f"Mount Type: {mount.value}")
    print("Mode:       STANDBY (Telemetry active, click [Start Recording] on Web to save files)")

    session_mgr = SessionManager(
        device_id=args.device_id,
        subject_id=args.subject_id,
        subject_type=profile.subject_type,
        mount_type=mount,
        sampling_rate_hz=args.hz,
    )

    # Always anchor data directories to ~/naro-gps-nathan/data or project root, never relative to current cwd!
    base_data = Path.home() / "naro-gps-nathan" / "data"
    raw_path = Path(args.raw_dir) if Path(args.raw_dir).is_absolute() else base_data / "raw"
    processed_path = Path(args.processed_dir) if Path(args.processed_dir).is_absolute() else base_data / "processed"

    recorder = RecorderService(
        session_mgr=session_mgr,
        profile=profile,
        raw_dir=raw_path,
        processed_dir=processed_path,
        min_satellites=args.min_sats,
        max_hdop=args.max_hdop,
        enable_sqlite=getattr(args, "enable_db", False),
        is_recording=False,  # Standby by default until user triggers recording
    )

    web_server = None
    if getattr(args, "web", False):
        LiveStatusHandler.recorder_ref = recorder
        LiveStatusHandler.is_recording = False
        web_server = start_monitor_server(port=args.web_port)
        print(f"Web Monitor: http://0.0.0.0:{args.web_port} (Open in phone browser to inspect without SSH)")

    print("Press Ctrl+C to stop recording.")

    mac_addr = getattr(args, "mac", None) or os.environ.get("NARO_DROGGER_MAC")
    reader = ResilientStreamReader(
        port=args.port,
        baud_rate=args.baud,
        timeout=2.0,
        reconnect_delay_seconds=3.0,
        mac_address=mac_addr,
    )

    # Print realtime line on terminal so user sees data streaming immediately
    last_print_time = [0.0]

    def on_measurement_tick(m: GPSMeasurement):
        t_now = time.time()
        if t_now - last_print_time[0] >= 1.0:  # print once per second
            last_print_time[0] = t_now
            sats = m.satellites
            hdop = f"{m.hdop:.1f}" if m.hdop is not None else "--"
            speed = f"{m.speed_kmh:.1f}" if m.speed_kmh is not None else "--"
            fix = m.fix_quality.value
            status_str = "FIX OK" if m.is_accepted else "REJECTED"
            rec_tag = "REC" if recorder.is_recording else "STANDBY"
            print(f"[{m.utc_time}] [{rec_tag}] Sats:{sats:2d} | HDOP:{hdop:>4s} | Fix:{fix} | Speed:{speed:>4s}km/h | {status_str} | {m.behavior_state.value}")

    recorder.on_measurement = on_measurement_tick

    try:
        recorder.run_stream(reader.stream_lines())
    except KeyboardInterrupt:
        print("\nStopping acquisition cleanly...")
    finally:
        if web_server:
            try:
                web_server.shutdown()
            except Exception:
                pass
        reader.stop()
        recorder.close()
        summary = recorder.health.summary()
        print("\n=== Session Summary ===")
        for k, v in summary.items():
            print(f"  {k}: {v}")
    return 0


def cmd_replay(args: argparse.Namespace) -> int:
    """Run replay test from recorded fixture file."""
    profile = get_profile(args.profile)
    filepath = Path(args.file)

    print(f"=== Replaying GPS Stream ===")
    print(f"Source file: {filepath}")
    print(f"Profile:     {profile.subject_type.value} (Max speed: {profile.max_speed_kmh} km/h)")
    print(f"Realtime:    {args.realtime} ({args.hz} Hz)")

    replay = ReplayService(
        filepath=filepath,
        profile=profile,
        subject_id=args.subject_id,
        output_dir=Path(args.output_dir),
        realtime_delay=args.realtime,
        simulated_hz=args.hz,
    )

    summary = replay.run()
    print("\n=== Replay Finished Successfully ===")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Start standalone web dashboard for inspecting past logs and downloading files."""
    print(f"=== Starting NARO GPS Web Server ===")
    print(f"Dashboard available at: http://0.0.0.0:{args.port} (or http://{args.host}:{args.port})")
    print("Press Ctrl+C to stop.")
    server = start_monitor_server(port=args.port)
    if not server:
        return 1
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping server...")
        server.shutdown()
def cmd_export(args: argparse.Namespace) -> int:
    """Export processed CSV to GeoJSON or clean CSV."""
    in_p = Path(args.input)
    fmt = args.format.lower()

    if fmt == "geojson":
        out_p = Path(args.output) if args.output else in_p.with_suffix(".geojson")
        res = export_geojson(in_p, out_p)
        print(f"Exported {res['total_exported_points']} points to GeoJSON: {out_p}")
    else:
        out_p = Path(args.output) if args.output else in_p.parent / f"{in_p.stem}_clean.csv"
        count = export_clean_csv(in_p, out_p)
        print(f"Exported {count} clean accepted points to: {out_p}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gps",
        description="human_gps: Modular IoT GPS Acquisition and Kinematic Tracking for Field Research",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Command: serve
    srv = subparsers.add_parser("serve", help="Start standalone web dashboard to view files and logs")
    srv.add_argument("--host", default="0.0.0.0", help="Host (default: 0.0.0.0)")
    srv.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    srv.set_defaults(func=cmd_serve)

    # Command: record
    rec = subparsers.add_parser("record", help="Start live recording from GPS serial port to disk")
    rec.add_argument("--port", default="/dev/rfcomm0", help="Serial port (default: /dev/rfcomm0)")
    rec.add_argument("--mac", default=None, help="Bluetooth MAC address of Drogger (e.g. 94:51:DC:57:BE:12)")
    rec.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    rec.add_argument("--profile", default="cow", choices=["cow", "human"], help="Subject profile")
    rec.add_argument("--subject-id", default="COW-001", help="Identifier of animal or human")
    rec.add_argument("--device-id", default="PI-ZERO-01", help="Device hostname / ID")
    rec.add_argument("--mount", default="COLLAR", help="Mount type (COLLAR, BACKPACK, HARNESS)")
    rec.add_argument("--hz", type=int, default=10, help="Target sampling rate in Hz")
    rec.add_argument("--min-sats", type=int, default=4, help="Min satellites threshold")
    rec.add_argument("--max-hdop", type=float, default=5.0, help="Max HDOP threshold")
    rec.add_argument("--raw-dir", default="data/raw", help="Directory for raw NMEA")
    rec.add_argument("--processed-dir", default="data/processed", help="Directory for processed data")
    rec.add_argument("--enable-db", action="store_true", help="Enable SQLite store alongside CSV (default: False, CSV only)")
    rec.add_argument("--web", action="store_true", help="Launch lightweight instant HTTP monitor dashboard")
    rec.add_argument("--web-port", type=int, default=8000, help="Web monitor port (default: 8000)")
    rec.set_defaults(func=cmd_record)

    # Command: replay
    rep = subparsers.add_parser("replay", help="Replay an NMEA fixture through the pipeline")
    rep.add_argument("--file", "-f", required=True, help="Path to raw NMEA text file")
    rep.add_argument("--profile", default="cow", choices=["cow", "human"], help="Subject profile")
    rep.add_argument("--subject-id", default="SIM-001", help="Simulated subject ID")
    rep.add_argument("--output-dir", default="data/processed", help="Output directory for processed CSV")
    rep.add_argument("--realtime", action="store_true", help="Simulate real-time rate delay")
    rep.add_argument("--hz", type=float, default=10.0, help="Simulated Hz rate")
    rep.set_defaults(func=cmd_replay)

    # Command: export
    exp = subparsers.add_parser("export", help="Export processed trajectory")
    exp.add_argument("--input", "-i", required=True, help="Processed session CSV")
    exp.add_argument("--format", choices=["geojson", "clean-csv"], default="geojson", help="Export format")
    exp.add_argument("--output", "-o", default=None, help="Output destination path")
    exp.set_defaults(func=cmd_export)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()

# human_gps: Modular IoT GPS Acquisition & Kinematic Tracking Engine

Hệ thống IoT thu nhận dữ liệu định vị GNSS/GPS dạng **Modular Monolith**, thiết kế tối ưu hóa cho **Raspberry Pi Zero 2 W (512MB RAM)** kết hợp máy thu GNSS **DG-PRO1S** qua Bluetooth SPP (`/dev/rfcomm0`).

Dự án hỗ trợ chuyển động đa đối tượng (**Con người, Bò thịt/Bò sữa NARO, Gia súc/Động vật khác**) với bộ lọc động học và phân loại hành vi tự động.

---

## 1. Kiến trúc Hệ thống

```text
DG-PRO1S GNSS (10 Hz)
   ↓ Bluetooth SPP (/dev/rfcomm0)
[Acquisition Layer] ResilientStreamReader (Tự phục hồi kết nối có backoff)
   ↓ Raw NMEA strings
[Protocol Layer] Checksum Verify & Sentence Router (GGA / VTG / RMC)
   ↓
[Pipeline Layer]
   ├── Synchronizer (Ghép cặp GGA + VTG thành một epoch đồng nhất)
   ├── MeasurementBuilder (Tính khoảng cách Haversine liên epoch)
   ├── QualityValidator (Kiểm tra Fix, Số vệ tinh, HDOP, Tọa độ)
   └── KinematicFilter (Bộ lọc động học theo SubjectProfile: Human vs Cow)
   ↓
[Storage Layer]
   ├── RawStore (Ghi raw .log/nmea 100% không mất mát)
   ├── CSVStore (Ghi CSV kèm cờ validation & lý do reject để audit)
   └── SQLiteStore (Ghi SQLite có indexing sẵn sàng truy vấn)
   ↓
[Export & Analysis]
   ├── Clean CSV
   └── GeoJSON FeatureCollection (LineString + Points cho QGIS / Web Map)
```

---

## 2. Insights Cấu trúc: Human vs. Cow vs. Other Animals

Khi theo dõi định vị trên thực địa:
1. **Kinematic Limits (Giới hạn vật lý)**:
   - **Bò (Bovine)**: Tốc độ tối đa $\le 25$ km/h, gia tốc tối đa $\le 3$ m/s². Bất kỳ bước nhảy tọa độ nào vượt ngưỡng này được phân loại ngay là dị biệt vệ tinh (`SPEED_EXCEEDED` / `ACCEL_EXCEEDED`).
   - **Người (Human)**: Tốc độ chạy nước rút có thể đạt 30–35 km/h, gia tốc và độ đổi hướng linh hoạt hơn nhiều.
2. **GPS Wandering & Stationary Jitter Suppression (Khử trôi khi đứng yên)**:
   - Bò dành nhiều giờ nằm nghỉ ngơi/nhai lại (rumination). Nhiễu đa đường (multipath) khiến tọa độ GPS dao động liên tục dù bò không di chuyển, gây ra quãng đường ảo (fake distance).
   - Hệ thống tích hợp cơ chế tự động triệt tiêu: Khi vận tốc dưới ngưỡng tĩnh (`stationary_speed_kmh`) và khoảng cách dịch chuyển nhỏ hơn `min_movement_threshold_m`, điểm đo được gán nhãn `JITTER_SUPPRESSED` và quãng đường delta được đặt về 0.0m.
3. **Behavior Classification (Phân loại hành vi tự động)**:
   - Gán nhãn trực tiếp: `RESTING` (nghỉ ngơi/nằm), `GRAZING` (gặm cỏ 0.3–1.8 km/h), `WALKING` (di chuyển), `RUNNING` (chạy).

---

## 3. Cài đặt & Hướng dẫn sử dụng

### 3.1. Cài đặt trên Raspberry Pi hoặc Máy tính
```bash
# Clone hoặc copy project
cd gps-nathan

# Cài đặt môi trường ảo (khuyến nghị dùng uv hoặc venv tiêu chuẩn)
uv sync
# Hoặc: python3 -m venv .venv && source .venv/bin/activate && pip install -e .
```

### 3.2. Thu thập dữ liệu thực tế trên Raspberry Pi (`record`)
```bash
# Thu thập dữ liệu bò đeo vòng cổ (Collar)
gps record --port /dev/rfcomm0 --profile cow --subject-id COW-NARO-042 --mount COLLAR

# Hoặc thu thập dữ liệu người đi bộ/chạy kiểm tra
gps record --port /dev/rfcomm0 --profile human --subject-id HUMAN-NATHAN --mount BACKPACK
```

### 3.3. Replay Test giả lập không cần phần cứng (`replay`)
Chạy trực tiếp file log NMEA mẫu để kiểm tra toàn bộ pipeline:
```bash
gps replay --file tests/fixtures/nmea/valid_epoch.txt --profile cow --subject-id COW-SIM-01
```

### 3.4. Xuất dữ liệu bản đồ GeoJSON cho QGIS / Web (`export`)
```bash
gps export --input data/processed/SESSION_XXXX.csv --format geojson --output data/exports/trajectory.geojson
```

---

## 4. Chạy Kiểm thử Tự động (Testing)

```bash
uv run pytest -v
```
Toàn bộ 20 bài test đơn vị (Unit Tests) và tích hợp (Integration Tests) bao phủ:
- Checksum verification
- Coordinate conversions (DDMM.MMMM -> Decimal Degrees)
- GGA / VTG / RMC sentence parsers
- Kinematic filters cho Bò vs Người
- Jitter suppression khi nằm nhai lại
- Replay pipeline & GeoJSON export

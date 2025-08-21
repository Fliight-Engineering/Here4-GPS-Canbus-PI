#!/usr/bin/env python3

"""
Here4 GNSS CSV Analyzer
-----------------------
Reads a CSV with columns (case-insensitive):
  ts_unix, nid, lat_deg, lon_deg, alt_m

Outputs to the chosen directory:
  - here4_gnss_clean.csv         (adds local EN offsets, dt, distance, speed)
  - here4_gnss_summary.json      (key stats)
  - gnss_scatter_xy.png          (local EN scatter)
  - gnss_altitude_time.png       (altitude vs time)
  - gnss_speed_time.png          (instantaneous speed vs time)
  - gnss_speed_hist.png          (speed histogram)

Usage:
  python3 here4_gnss_analyze.py path/to/here4_gnss.csv --out out_dir
Optional:
  --tz Australia/Sydney  (timezone for time axis)
  --dpi 150              (plot resolution)
"""
import os, sys, json, math, argparse
from datetime import timezone
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

def analyze(csv_path: str, out_dir: str, tz_name: str = "Australia/Sydney", dpi: int = 150) -> dict:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV not found: {csv_path}")
    os.makedirs(out_dir, exist_ok=True)

    # Load
    df = pd.read_csv(csv_path)

    # Case-insensitive column mapping
    col_map = {c.lower(): c for c in df.columns}
    required = ["ts_unix", "nid", "lat_deg", "lon_deg", "alt_m"]
    missing = [c for c in required if c not in col_map]
    if missing:
        raise ValueError(f"Missing required columns: {missing}. Found: {list(df.columns)}")

    ts = col_map["ts_unix"]
    nid = col_map["nid"]
    lat = col_map["lat_deg"]
    lon = col_map["lon_deg"]
    alt = col_map["alt_m"]

    # Types
    for c in [ts, lat, lon, alt]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df[nid] = pd.to_numeric(df[nid], errors="coerce").astype("Int64")

    # Clean
    df = df.dropna(subset=[ts, lat, lon, alt]).copy()
    if df.empty:
        raise ValueError("CSV has no valid rows after cleaning.")

    df = df.sort_values(ts).reset_index(drop=True)

    # Datetime (local tz)
    try:
        df["t_dt"] = pd.to_datetime(df[ts], unit="s", utc=True).dt.tz_convert(tz_name)
    except Exception:
        # Fallback to naive UTC if timezone not available
        df["t_dt"] = pd.to_datetime(df[ts], unit="s", utc=True)

    # Local tangent plane around median
    R = 6371000.0  # meters
    lat0 = np.deg2rad(df[lat].median())
    lon0 = np.deg2rad(df[lon].median())
    lat_rad = np.deg2rad(df[lat].to_numpy())
    lon_rad = np.deg2rad(df[lon].to_numpy())
    df["x_east_m"] = (lon_rad - lon0) * math.cos(lat0) * R
    df["y_north_m"] = (lat_rad - lat0) * R

    # Distances & speed
    def haversine_m(lat1, lon1, lat2, lon2):
        phi1 = np.deg2rad(lat1); phi2 = np.deg2rad(lat2)
        dphi = phi2 - phi1; dlmb = np.deg2rad(lon2 - lon1)
        a = np.sin(dphi/2.0)**2 + np.cos(phi1)*np.cos(phi2)*np.sin(dlmb/2.0)**2
        return 2*R*np.arcsin(np.minimum(1, np.sqrt(a)))

    df["dt_s"] = df[ts].diff()
    dist = np.r_[np.nan, haversine_m(df[lat].to_numpy()[:-1], df[lon].to_numpy()[:-1],
                                     df[lat].to_numpy()[1:],  df[lon].to_numpy()[1:])]
    df["dist_m"] = dist
    df["speed_mps"] = df["dist_m"] / df["dt_s"]

    # Summary stats
    n = len(df)
    t0 = df["t_dt"].iloc[0]
    t1 = df["t_dt"].iloc[-1]
    duration_s = float(df[ts].iloc[-1] - df[ts].iloc[0]) if n > 1 else 0.0

    sample_dt = df["dt_s"].dropna()
    median_dt = float(sample_dt.median()) if not sample_dt.empty else float("nan")
    mean_dt   = float(sample_dt.mean()) if not sample_dt.empty else float("nan")
    fps_med   = (1.0/median_dt) if median_dt and median_dt > 0 else float("nan")
    fps_mean  = (1.0/mean_dt) if mean_dt and mean_dt > 0 else float("nan")

    r_xy = np.sqrt(df["x_east_m"]**2 + df["y_north_m"]**2)
    hrms = float(np.sqrt(np.mean(r_xy**2)))
    r68  = float(np.percentile(r_xy, 68))
    r95  = float(np.percentile(r_xy, 95))
    rmax = float(np.max(r_xy))

    alt_vals = df[alt].to_numpy()
    alt_mean = float(np.mean(alt_vals))
    alt_std  = float(np.std(alt_vals, ddof=1)) if n > 1 else float("nan")
    alt_p05  = float(np.percentile(alt_vals, 5))
    alt_p95  = float(np.percentile(alt_vals, 95))

    spd = df["speed_mps"].replace([np.inf, -np.inf], np.nan)
    speed_med = float(spd.median(skipna=True)) if spd.notna().any() else float("nan")
    speed_p95 = float(spd.quantile(0.95)) if spd.notna().any() else float("nan")
    speed_max = float(np.nanmax(spd)) if spd.notna().any() else float("nan")

    nid_counts = df[nid].value_counts(dropna=True).to_dict()
    nid_counts = {int(k): int(v) for k, v in nid_counts.items()}

    summary = {
        "rows": int(n),
        "time_start_local": str(t0),
        "time_end_local": str(t1),
        "duration_s": duration_s,
        "sampling_dt_median_s": median_dt,
        "sampling_dt_mean_s": mean_dt,
        "sampling_rate_hz_median": fps_med,
        "sampling_rate_hz_mean": fps_mean,
        "lat_center_deg": float(np.rad2deg(lat0)),
        "lon_center_deg": float(np.rad2deg(lon0)),
        "horiz_jitter_hrms_m": hrms,
        "horiz_jitter_r68_m": r68,
        "horiz_jitter_r95_m": r95,
        "horiz_jitter_max_m": rmax,
        "altitude_mean_m": alt_mean,
        "altitude_std_m": alt_std,
        "altitude_p05_m": alt_p05,
        "altitude_p95_m": alt_p95,
        "speed_mps_median": speed_med,
        "speed_mps_p95": speed_p95,
        "speed_mps_max": speed_max,
        "node_id_counts": nid_counts,
    }

    # Save clean CSV
    clean_csv = os.path.join(out_dir, "here4_gnss_clean.csv")
    df_out = df[[ts, "t_dt", nid, lat, lon, alt, "x_east_m", "y_north_m", "dt_s", "dist_m", "speed_mps"]].copy()
    df_out.to_csv(clean_csv, index=False)

    # Save JSON
    summary_json = os.path.join(out_dir, "here4_gnss_summary.json")
    with open(summary_json, "w") as f:
        json.dump(summary, f, indent=2)

    # Plots
    scatter_png = os.path.join(out_dir, "gnss_scatter_xy.png")
    alt_png     = os.path.join(out_dir, "gnss_altitude_time.png")
    spd_png     = os.path.join(out_dir, "gnss_speed_time.png")
    hist_png    = os.path.join(out_dir, "gnss_speed_hist.png")

    # 1) XY scatter
    plt.figure()
    plt.scatter(df["x_east_m"], df["y_north_m"], s=5)
    plt.gca().set_aspect('equal', adjustable='box')
    plt.xlabel("East (m)"); plt.ylabel("North (m)")
    plt.title("Here4 GNSS scatter (local EN)")
    plt.tight_layout(); plt.savefig(scatter_png, dpi=dpi); plt.close()

    # 2) Altitude vs time
    plt.figure()
    plt.plot(df["t_dt"], df[alt])
    plt.xlabel("Time (local)"); plt.ylabel("Altitude (m)")
    plt.title("Altitude vs Time")
    plt.tight_layout(); plt.savefig(alt_png, dpi=dpi); plt.close()

    # 3) Speed vs time
    plt.figure()
    plt.plot(df["t_dt"], df["speed_mps"])
    plt.xlabel("Time (local)"); plt.ylabel("Speed (m/s)")
    plt.title("Instantaneous speed vs Time")
    plt.tight_layout(); plt.savefig(spd_png, dpi=dpi); plt.close()

    # 4) Speed histogram
    spd_vals = spd.to_numpy()
    spd_vals = spd_vals[np.isfinite(spd_vals)]
    if spd_vals.size > 0:
        plt.figure()
        plt.hist(spd_vals, bins=50)
        plt.xlabel("Speed (m/s)"); plt.ylabel("Count")
        plt.title("Speed distribution")
        plt.tight_layout(); plt.savefig(hist_png, dpi=dpi); plt.close()

    return {
        "summary_json": summary_json,
        "clean_csv": clean_csv,
        "scatter_png": scatter_png,
        "alt_png": alt_png,
        "speed_png": spd_png,
        "speed_hist_png": hist_png,
        "summary": summary,
    }

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="Input GNSS CSV (ts_unix, nid, lat_deg, lon_deg, alt_m)")
    ap.add_argument("--out", default=".", help="Output directory (default: current dir)")
    ap.add_argument("--tz", default="Australia/Sydney", help="Timezone for time axis (default: Australia/Sydney)")
    ap.add_argument("--dpi", type=int, default=150, help="DPI for PNGs (default: 150)")
    args = ap.parse_args()

    res = analyze(args.csv, args.out, tz_name=args.tz, dpi=args.dpi)
    print("Wrote:")
    for k in ["summary_json", "clean_csv", "scatter_png", "alt_png", "speed_png", "speed_hist_png"]:
        print(" -", res[k])
    print("\nSummary:")
    print(json.dumps(res["summary"], indent=2))

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
here4_live_tui.py
-----------------
Lightweight live terminal view (no ROS 2 dependency).

Shows GNSS Fix/Fix2 (lat, lon, alt, speed) and Auxiliary (DOPs, sats).
Optionally logs a CSV while running.

Usage:
  # bring up CAN
  sudo ip link set can1 down
  sudo ip link set can1 type can bitrate 1000000
  sudo ip link set can1 up

  # caps for your venv python OR run with sudo
  sudo setcap 'cap_net_raw,cap_net_admin+eip' "$(readlink -f ./venv/bin/python3)"

  ./venv/bin/python3 here4_live_tui.py --can-if can1 --bitrate 1000000 --node-id 125
  # optional logging:
  ./venv/bin/python3 here4_live_tui.py --log-csv here4_live_log.csv
"""
import time, math, os, sys, curses, argparse, csv
import dronecan
from dronecan.node import Node
from dronecan.driver.python_can import PythonCAN
from dronecan.app.node_monitor import NodeMonitor
from dronecan.app.dynamic_node_id import CentralizedServer

def norm3(vx, vy, vz):
    return math.sqrt(vx*vx + vy*vy + vz*vz)

def run(stdscr, can_if, bitrate, my_id, log_csv=None):
    drv = PythonCAN(can_if, bustype='socketcan', bitrate=bitrate)
    dc  = Node(drv, node_id=my_id)
    mon = NodeMonitor(dc)
    alloc = CentralizedServer(dc, mon)

    # state for UI
    state = {
        "lat": float('nan'), "lon": float('nan'), "alt": float('nan'),
        "speed": float('nan'), "sats_used": None, "sats_visible": None,
        "pdop": float('nan'), "hdop": float('nan'), "vdop": float('nan'),
        "last_nid": None
    }

    # optional CSV logging
    writer = None
    if log_csv:
        new = not os.path.exists(log_csv)
        f = open(log_csv, "a", newline="")
        writer = csv.writer(f)
        if new:
            writer.writerow(["ts_unix","nid","lat_deg","lon_deg","alt_m",
                             "sats_used","pdop","speed_mps"])

    def on_fix_common(m, nid):
        state["last_nid"] = nid
        la = getattr(m, "latitude_deg_1e8", None)
        lo = getattr(m, "longitude_deg_1e8", None)
        altmm = getattr(m, "height_msl_mm", getattr(m, "height_mm", None))
        if la is not None and lo is not None:
            state["lat"] = la / 1e8
            state["lon"] = lo / 1e8
            state["alt"] = (altmm / 1000.0) if isinstance(altmm, (int, float)) else float('nan')

        # Velocity: prefer 'ned_velocity' (m/s). If only components exist, assume m/s.
        ned = getattr(m, "ned_velocity", None)
        if isinstance(ned, (list, tuple)) and len(ned) == 3:
            state["speed"] = norm3(float(ned[0]), float(ned[1]), float(ned[2]))
        else:
            vn = getattr(m, "north_velocity", None)
            ve = getattr(m, "east_velocity",  None)
            vd = getattr(m, "down_velocity",  None)
            if all(isinstance(v, (int, float)) for v in (vn, ve, vd)):
                state["speed"] = norm3(float(vn), float(ve), float(vd))

        su = getattr(m, "sats_used", None)
        if isinstance(su, int): state["sats_used"] = su
        pd = getattr(m, "pdop", None)
        if isinstance(pd, (int, float)): state["pdop"] = float(pd)

        if writer:
            t = time.time()
            writer.writerow([f"{t:.3f}", nid,
                             f"{state['lat']:.9f}", f"{state['lon']:.9f}", f"{state['alt']:.3f}",
                             state["sats_used"], f"{state['pdop']:.2f}", f"{state['speed']:.3f}"])

    def on_fix2(e): on_fix_common(e.message, e.transfer.source_node_id)
    def on_fix (e): on_fix_common(e.message, e.transfer.source_node_id)

    def on_aux(e):
        m = e.message
        sv = getattr(m, "sats_visible", None)
        if isinstance(sv, int): state["sats_visible"] = sv
        for k in ["pdop","hdop","vdop"]:
            v = getattr(m, k, None)
            if isinstance(v, (int, float)):
                state[k] = float(v)

    dc.add_handler(dronecan.uavcan.equipment.gnss.Auxiliary, on_aux)
    try: dc.add_handler(dronecan.uavcan.equipment.gnss.Fix2, on_fix2)
    except AttributeError: pass
    try: dc.add_handler(dronecan.uavcan.equipment.gnss.Fix,  on_fix)
    except AttributeError: pass

    stdscr.nodelay(True)
    curses.curs_set(0)
    last_draw = 0.0
    try:
        while True:
            dc.spin(0.0)
            now = time.time()
            if now - last_draw > 0.1:
                last_draw = now
                stdscr.erase()
                stdscr.addstr(0, 0, f"Here4 Live (DroneCAN @ {bitrate} bps)   q=quit")
                stdscr.addstr(2, 0, f"NID: {state['last_nid']}   Sats used/vis: {state['sats_used']}/{state['sats_visible']}")
                stdscr.addstr(3, 0, f"Lat: {state['lat']:.7f}  Lon: {state['lon']:.7f}  Alt: {state['alt']:.2f} m")
                stdscr.addstr(4, 0, f"Speed: {state['speed']:.2f} m/s   PDOP: {state['pdop']:.2f}  HDOP: {state['hdop']:.2f}  VDOP: {state['vdop']:.2f}")
                stdscr.refresh()
            ch = stdscr.getch()
            if ch in (ord('q'), ord('Q')):
                break
            time.sleep(0.005)
    finally:
        if writer:
            f.close()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--can-if", default="can1")
    ap.add_argument("--bitrate", type=int, default=1000000)
    ap.add_argument("--node-id", type=int, default=125)
    ap.add_argument("--log-csv", default=None)
    args = ap.parse_args()
    curses.wrapper(run, args.can_if, args.bitrate, args.node_id, args.log_csv)

if __name__ == "__main__":
    main()

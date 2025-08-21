# here4_listener.py
import csv, time, os, signal, sys
import dronecan
from dronecan.node import Node
from dronecan.driver.python_can import PythonCAN
from dronecan.app.node_monitor import NodeMonitor
from dronecan.app.dynamic_node_id import CentralizedServer

MY_ID = 125
LOG_GNSS = "here4_gnss.csv"
LOG_AUX  = "here4_gnss_aux.csv"   # sats & DOPs (optional file)

# --- CAN @ 1M via explicit driver (avoids bitrate parsing quirks) ---
drv = PythonCAN('can1', bustype='socketcan', bitrate=1000000)
node = Node(drv, node_id=MY_ID)

# --- Dynamic node-ID allocator ---
mon = NodeMonitor(node)
alloc = CentralizedServer(node, mon)
print("Dynamic Node-ID allocator enabled")

# --- CSVs ---
new_g = not os.path.exists(LOG_GNSS)
gnssf = open(LOG_GNSS, "a", newline="")
g = csv.writer(gnssf)
if new_g:
    g.writerow(["ts_unix","nid","lat_deg","lon_deg","alt_m",
            "sats_used","status","mode","sub_mode","pdop","speed_mps"])



new_a = not os.path.exists(LOG_AUX)
auxf = open(LOG_AUX, "a", newline="")
a = csv.writer(auxf)
if new_a:
    a.writerow(["ts_unix", "nid", "sats_used", "sats_visible", "pdop", "hdop", "vdop", "gdop"])

def _close_and_exit(*_):
    try: gnssf.close()
    except: pass
    try: auxf.close()
    except: pass
    print("\nLog files closed.")
    sys.exit(0)

signal.signal(signal.SIGINT,  _close_and_exit)
signal.signal(signal.SIGTERM, _close_and_exit)

# --- Decoders ---
printed_yaml = {"Fix": False, "Fix2": False}
last_print = 0.0

def _print_once_yaml(name, msg, nid):
    if not printed_yaml.get(name, False):
        try:
            print(f"[YAML once] {name} from nid={nid}:\n{dronecan.to_yaml(msg)}")
        except Exception as e:
            print(f"[YAML once] {name} YAML error: {e}")
        printed_yaml[name] = True

def on_fix_common(name, e):
    global last_print
    m   = e.message
    nid = e.transfer.source_node_id
    lat = getattr(m, "latitude_deg_1e8", None)
    lon = getattr(m, "longitude_deg_1e8", None)
    altmm = getattr(m, "height_msl_mm", getattr(m, "height_mm", None))
    if lat is None or lon is None:
        return
    lat = lat / 1e8
    lon = lon / 1e8
    alt = (altmm / 1000.0) if isinstance(altmm, (int, float)) else float("nan")
    sats_used = getattr(m, "sats_used", None)
    status    = getattr(m, "status",    None)   # 0..?
    mode      = getattr(m, "mode",      None)   # 0=SINGLE, 3=RTK Fixed (vendor-dependent enums)
    sub_mode  = getattr(m, "sub_mode",  None)
    pdop_f2   = getattr(m, "pdop", float("nan"))
    
    ned = getattr(m, "ned_velocity", None)
    if isinstance(ned, (list, tuple)) and len(ned) == 3:
        speed = (ned[0]**2 + ned[1]**2 + ned[2]**2) ** 0.5
    else:
        speed = float("nan")



    t = time.time()
    if t - last_print > 0.2:  # ~5 Hz
        last_print = t
        print(f"GNSS[{name}]: lat={lat:.7f} lon={lon:.7f} alt_m={alt:.2f} "
      f"sats={sats_used} mode={mode} status={status} PDOP={pdop_f2:.2f} v={speed:.2f} m/s")

    g.writerow([f"{t:.3f}", nid, f"{lat:.9f}", f"{lon:.9f}", f"{alt:.3f}",
            sats_used, status, mode, sub_mode,
            f"{pdop_f2:.2f}", f"{speed:.3f}"])

    gnssf.flush()
    _print_once_yaml(name, m, nid)

def on_fix2(e): on_fix_common("Fix2", e)
def on_fix (e): on_fix_common("Fix",  e)

def on_aux(e):
    m = e.message
    t = time.time()
    nid = e.transfer.source_node_id
    pdop = getattr(m, "pdop", float("nan"))
    hdop = getattr(m, "hdop", float("nan"))
    vdop = getattr(m, "vdop", float("nan"))
    gdop = getattr(m, "gdop", float("nan"))
    used = getattr(m, "sats_used", 0)
    vis  = getattr(m, "sats_visible", 0)
    print(f"DOPs: PDOP={pdop:.2f} HDOP={hdop:.2f} VDOP={vdop:.2f} GDOP={gdop:.2f}  sats used/vis: {used}/{vis}")
    a.writerow([f"{t:.3f}", nid, used, vis, f"{pdop:.2f}", f"{hdop:.2f}", f"{vdop:.2f}", f"{gdop:.2f}"])
    auxf.flush()

# NodeStatus (ignore our own to cut chatter)
def on_status(e):
    src = e.transfer.source_node_id
    if src == MY_ID:
        return
    s = e.message
    print(f"NodeStatus: nid={src} uptime={s.uptime_sec}s health={s.health} mode={s.mode}")

node.add_handler(dronecan.uavcan.protocol.NodeStatus, on_status)
node.add_handler(dronecan.uavcan.equipment.gnss.Auxiliary, on_aux)

for typ, cb in (("Fix2", on_fix2), ("Fix", on_fix)):
    try:
        node.add_handler(getattr(dronecan.uavcan.equipment.gnss, typ), cb)
    except AttributeError:
        pass

print("Listening… Ctrl-C to stop")
while True:
    node.spin(0.2)

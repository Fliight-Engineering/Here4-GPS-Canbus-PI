# cantest.py
import dronecan
from dronecan.node import Node
from dronecan.driver.python_can import PythonCAN
from dronecan.app.node_monitor import NodeMonitor
from dronecan.app.dynamic_node_id import CentralizedServer

MY_ID = 125
HERE4_ID = 124  # assigned by allocator (from your logs)

# --- bring up node on classic 1M ---
drv = PythonCAN('can1', bustype='socketcan', bitrate=1000000)
node = Node(drv, node_id=MY_ID)

# Allocator + monitor
mon = NodeMonitor(node)
alloc = CentralizedServer(node, mon)
print("Dynamic Node-ID allocator enabled")

# ---------- helpers ----------
def find_types_by_id(dtid: int):
    """Return list[(name, type)] where default_data_type_id == dtid"""
    out = []
    for name, typ in getattr(dronecan, "DATATYPES", {}).items():
        try:
            if int(getattr(typ, "default_data_type_id")) == dtid:
                out.append((name, typ))
        except Exception:
            pass
    return out

def attach_yaml_printer_for_id(dtid: int, label=""):
    matches = find_types_by_id(dtid)
    if not matches:
        print(f"[mapper] No DSDL type found for DataTypeID {dtid}")
        return
    for name, typ in matches:
        def _h(evt, _name=name):
            # evt.message is a typed object; pretty-print as YAML
            try:
                print(f"{label}{_name} (nid={evt.transfer.source_node_id}):")
                print(dronecan.to_yaml(evt.message))
            except Exception as ex:
                print(f"{label}{_name} decode error:", ex)
        node.add_handler(typ, _h)
        print(f"[mapper] Attached handler for {name} (DTID={dtid})")

# ---------- baseline decoders ----------
def on_status(e):
    src = e.transfer.source_node_id
    if src == MY_ID:
        return
    m = e.message
    print(f"NodeStatus: nid={src} uptime={m.uptime_sec}s health={m.health} mode={m.mode}")
node.add_handler(dronecan.uavcan.protocol.NodeStatus, on_status)

def on_fix(e):
    m = e.message
    lat = m.latitude_deg_1e8 / 1e8
    lon = m.longitude_deg_1e8 / 1e8
    altmm = getattr(m, "height_msl_mm", None)
    alt = (altmm / 1000.0) if altmm is not None else float('nan')
    print(f"GNSS: lat={lat:.7f} lon={lon:.7f} alt_m={alt}")
for typ in ("Fix2", "Fix"):
    try:
        node.add_handler(getattr(dronecan.uavcan.equipment.gnss, typ), on_fix)
    except AttributeError:
        pass

def on_allocation(e):
    print("Allocation message received")
node.add_handler(dronecan.uavcan.protocol.dynamic_node_id.Allocation, on_allocation)

# ---------- attach decoders for what you saw ----------
# 0x03E9 == 1001 decimal
attach_yaml_printer_for_id(0x03E9, label="[here4] ")

# Optional: attach another if you spot new type IDs later:
# attach_yaml_printer_for_id(0x0424)  # example

print("Listening… Ctrl-C to stop")
while True:
    node.spin(0.5)

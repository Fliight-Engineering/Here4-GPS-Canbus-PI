# here4_listener.py
#
# This script listens for DroneCAN messages from a Here4 GPS module, 
# decodes GNSS data, and logs it to a CSV file.
# It also acts as a DroneCAN dynamic node ID allocation server to assign an ID to the Here4.

import csv, time, os
import dronecan
from dronecan.node import Node
from dronecan.driver.python_can import PythonCAN
from dronecan.app.node_monitor import NodeMonitor
from dronecan.app.dynamic_node_id import CentralizedServer

# --- Configuration ---
# The node ID for this script. Pick any ID that is not used by another device on the bus.
MY_ID = 125
# The name of the CSV file to log GNSS data to.
LOG = "here4_gnss.csv"

# --- CAN Bus Setup ---
# Explicitly create a python-can driver instance for a SocketCAN interface.
# This avoids issues with the automatic bitrate parser in some versions of dronecan.
# Replace 'can1' with your actual CAN interface name.
drv = PythonCAN('can1', bustype='socketcan', bitrate=1000000)

# Create a DroneCAN node instance.
node = Node(drv, node_id=MY_ID)

# --- Dynamic Node ID Allocation ---
# The Here4 GPS uses dynamic node ID allocation by default.
# This script needs to act as a master to assign an ID to the Here4.
# The CentralizedServer class handles this automatically.
mon = NodeMonitor(node)
alloc = CentralizedServer(node, mon)
print("Dynamic Node-ID allocator enabled")

# --- CSV Logger Setup ---
# Check if the log file already exists. If not, write a header row.
new_file = not os.path.exists(LOG)
csvf = open(LOG, "a", newline="")
writer = csv.writer(csvf)
if new_file:
    writer.writerow(["ts_unix", "nid", "lat_deg", "lon_deg", "alt_m"])

# --- Message Handlers ---

# A dictionary to keep track of whether we have printed the YAML for a message type.
# This is used to avoid spamming the console with the same information.
printed_yaml = {"Fix": False, "Fix2": False}
# A timestamp to throttle console prints to about 5 Hz.
last_print = 0.0

def _print_once_yaml(name, msg, nid):
    """Prints the YAML representation of a message once."""
    if not printed_yaml.get(name, False):
        print(f"[YAML once] {name} from nid={nid}:\n{dronecan.to_yaml(msg)}")
        printed_yaml[name] = True

def on_fix_common(name, e):
    """A common handler for both Fix and Fix2 messages."""
    global last_print
    m   = e.message
    nid = e.transfer.source_node_id

    # Decode latitude, longitude, and altitude safely, as the field names can vary.
    lat = getattr(m, "latitude_deg_1e8", None)
    lon = getattr(m, "longitude_deg_1e8", None)
    altmm = getattr(m, "height_msl_mm", getattr(m, "height_mm", None))
    if lat is None or lon is None:
        return

    # Scale the values to the correct units.
    lat = lat / 1e8
    lon = lon / 1e8
    alt = (altmm / 1000.0) if isinstance(altmm, (int, float)) else float("nan")

    # Throttle console prints to about 5 Hz.
    t = time.time()
    if t - last_print > 0.2:
        print(f"GNSS[{name}]: lat={lat:.7f} lon={lon:.7f} alt_m={alt:.2f}")
        last_print = t

    # Always log the data to the CSV file.
    writer.writerow([f"{t:.3f}", nid, f"{lat:.9f}", f"{lon:.9f}", f"{alt:.3f}"])
    csvf.flush() # Ensure data is written to disk immediately.

    # Print the full message structure in YAML format once to help with debugging.
    _print_once_yaml(name, m, nid)

# Create specific handlers for Fix and Fix2 that call the common handler.
def on_fix2(e): on_fix_common("Fix2", e)
def on_fix (e): on_fix_common("Fix",  e)

# def on_aux(e):
#     a = e.message
#     print(
#         f"DOPs: PDOP={a.pdop:.2f} HDOP={a.hdop:.2f} VDOP={a.vdop:.2f} "
#         f"GDOP={a.gdop:.2f}  sats: used={a.sats_used} vis={a.sats_visible}"
#     )

# node.add_handler(dronecan.uavcan.equipment.gnss.Auxiliary, on_aux)
# --- Register Handlers ---

# Register a handler for NodeStatus messages.
node.add_handler(dronecan.uavcan.protocol.NodeStatus,
                 lambda e: print(f"NodeStatus: nid={e.transfer.source_node_id} "
                                 f"uptime={e.message.uptime_sec}s "
                                 f"health={e.message.health} mode={e.message.mode}"))

# Register handlers for both Fix and Fix2 messages.
# The try/except block handles cases where one of the message types is not defined in the DSDL.
for typ, cb in (("Fix2", on_fix2), ("Fix", on_fix)):
    try:
        node.add_handler(getattr(dronecan.uavcan.equipment.gnss, typ), cb)
    except AttributeError:
        pass

# --- Main Loop ---
print("Listening… Ctrl-C to stop")
try:
    while True:
        # Spin the node to process incoming messages and run background tasks.
        # The timeout value determines how often the loop runs.
        node.spin(0.2)
finally:
    # Close the CSV file gracefully on exit.
    csvf.close()
    print("\nLog file closed.")


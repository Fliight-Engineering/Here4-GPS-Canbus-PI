# Here4 DroneCAN Listener Documentation

## 1. Overview

This project provides a Python script (`here4_listener.py`) to listen for DroneCAN messages from a Here4 GPS module connected to a Raspberry Pi via a CAN interface. The script decodes and prints `NodeStatus` and GNSS `Fix` messages, and logs the GNSS data to a CSV file.

A key feature of this script is its ability to act as a DroneCAN dynamic node ID allocation server. The Here4 GPS requires a master on the bus to assign it a node ID before it will start broadcasting its data. This script fulfills that role.

## 2. Hardware Setup

1.  **Raspberry Pi & CAN HAT:** This project was tested with a Raspberry Pi and a Waveshare 2-CH CAN-FD HAT. Ensure your CAN HAT is properly installed and configured.
2.  **Connections:**
    *   Connect the Here4 GPS to one of the CAN channels on your HAT. In this project, `can1` was used.
    *   Provide 5V power and a common ground to the Here4.
    *   Connect the CAN-H and CAN-L wires.
    *   Ensure the CAN bus has approximately 60-120 Ω termination.

## 3. Software Setup

1.  **Enable CAN on Raspberry Pi:**
    Follow the instructions for your specific CAN HAT to enable the `can` interfaces in the Raspberry Pi OS. This usually involves editing `/boot/config.txt` to load the correct overlays for your hardware (e.g., `mcp251xfd`).

2.  **Install Dependencies:**
    It is recommended to use a Python virtual environment.
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
    Install the necessary Python libraries:
    ```bash
    pip install dronecan python-can
    ```
    Install the `can-utils` for debugging:
    ```bash
    sudo apt-get update
    sudo apt-get install can-utils
    ```

3.  **Bring up the CAN Interface:**
    Bring up your CAN interface. This example uses `can1` with a bitrate of 1M (1,000,000 bps), which is standard for DroneCAN on classic CAN.
    ```bash
    sudo ip link set can1 up type can bitrate 1000000
    ```

## 4. Running the Listener

With your virtual environment activated and the CAN interface up, simply run the script:

```bash
python3 here4_listener.py
```

## 5. Output

The script generates two primary forms of output: live messages printed to the console and detailed log files in CSV format.

### Console Output

*   **Allocator Status:** The script will first print `Dynamic Node-ID allocator enabled`.
*   **NodeStatus:** You will see periodic heartbeat messages from the Here4, indicating its uptime and operational mode.
    ```
    NodeStatus: nid=124 uptime=10s health=0 mode=0
    ```
*   **GNSS Data:** The script will print decoded latitude, longitude, and altitude at a throttled rate (~5 Hz).
    ```
    GNSS[Fix2]: lat=40.7127760 lon=-74.0059740 alt_m=10.50
    ```
*   **YAML Dump:** The first time a `Fix` or `Fix2` message is received, its entire structure will be printed in YAML format. This is useful for inspecting all the available fields in the message.

### Log Files

The script generates two CSV files:

*   **`here4_gnss.csv`**: The primary log, containing the core position data.
*   **`here4_gnss_aux.csv`**: An auxiliary log, containing data about the quality and reliability of the GNSS fix.

## 6. Understanding the Data

### `here4_gnss.csv` - The Position Log

This is the main data log, designed for easy analysis or plotting.

| Column    | Description                                            |
|-----------|--------------------------------------------------------|
| `ts_unix` | UNIX timestamp when the message was received.          |
| `nid`     | The source node ID of the GPS (e.g., 124).             |
| `lat_deg` | The final, calculated latitude in decimal degrees.     |
| `lon_deg` | The final, calculated longitude in decimal degrees.    |
| `alt_m`   | The final altitude in meters above mean sea level.     |

### `here4_gnss_aux.csv` - The Quality Log

This file provides data to assess the quality and reliability of the position in the main log.

| Column         | Description                                                                                             |
|----------------|---------------------------------------------------------------------------------------------------------|
| `ts_unix`      | UNIX timestamp, for correlating with the main log.                                                      |
| `nid`          | The source node ID of the GPS.                                                                          |
| `sats_used`    | The number of satellites used in the position solution.                                                 |
| `sats_visible` | The total number of satellites visible to the receiver.                                                 |
| `pdop`         | **P**osition **D**ilution **o**f **P**recision (3D). An overall measure of fix quality.                   |
| `hdop`         | **H**orizontal **D**ilution **o**f **P**recision (2D). The reliability of the latitude/longitude.         |
| `vdop`         | **V**ertical **D**ilution **o**f **P**recision. The reliability of the altitude.                          |
| `gdop`         | **G**eometric **D**ilution **o**f **P**recision. Relates to the geometry of the visible satellites.       |

**Note on DOP values:** Dilution of Precision is a critical indicator of GPS fix quality. It reflects how errors in the satellite measurements will affect the final position calculation. **Lower DOP values are better.** A `pdop` under 2.0 is generally considered good for non-precision applications.

### Detailed YAML Output (from Console)

The one-time YAML dump on the console provides a deep look into the `uavcan.equipment.gnss.Fix2` message structure. This is invaluable for debugging or extending the script.

**Key Fields from the YAML Dump:**

*   `latitude_deg_1e8` / `longitude_deg_1e8`: The raw integer values from the GPS. These are divided by 1e8 (100,000,000) to get the final decimal degrees.
*   `height_msl_mm`: Height above Mean Sea Level in millimeters.
*   `sats_used: 29`: Shows the actual number of satellites being used (in this example, 29), which indicates a very strong signal.
*   `status: 3`: A status code of `3` indicates a full 3D Fix, which is the highest quality fix.
*   `covariance`: A series of numbers representing the statistical uncertainty (variance) of the position and velocity. Smaller numbers indicate higher confidence.



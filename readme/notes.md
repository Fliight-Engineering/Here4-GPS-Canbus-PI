# Hardware

- Raspberry Pi + Waveshare 2-CH CAN FD HAT (MCP2517FD + MCP2518FD, 40 MHz).
- CAN transceivers: FD-capable on the HAT.
- DJI Here4 GPS connected to CAN_0 screw terminal (maps to can1 in Linux).
- Bench: 5 V on pin 4, GND on pin 6, CANH/CANL wired, short twisted pair, ~60 Ω termination across H↔L.

# Driver & Overlay

- Enabled SPI + mcp251xfd overlays.
- dmesg confirmed:
```bash
mcp251xfd spi1.0 can0: MCP2517FD rev0.0 (40 MHz)
mcp251xfd spi0.0 can1: MCP2518FD rev0.0 (40 MHz)
```


# Commands tested

---

### General interface mgmt
```bash
# show CAN interfaces
ip link | grep can

# bring down/up
sudo ip link set can0 down
sudo ip link set can0 up
```

### CAN-FD bring-up
```bash
# setup can0 or can1 for FD, 500k arb / 8M data, BRS on
sudo ip link set dev can0 type can \
  bitrate 1000000 sample-point 0.875 \
  dbitrate 8000000 dsample-point 0.70 \
  fd on berr-reporting on restart-ms 100
sudo ip link set canX up
```

### Classic CAN bring-up

```bash
# 1 Mbit/s (Here4 default)
sudo ip link set dev canX type can bitrate 1000000 berr-reporting on restart-ms 100
sudo ip link set canX up

# alternative: 500k classic
sudo ip link set dev canX type can bitrate 500000 berr-reporting on restart-ms 100
sudo ip link set canX up
```

### Listen-only mode (sniff without TX)

```bash
sudo ip link set dev canX type can bitrate 1000000 listen-only on berr-reporting on restart-ms 100
sudo ip link set canX up
```


### Dump traffic

```bash
candump -tz canX
```
- On can1 @ 1 M classic, Here4 frames appeared:
```bash 
can1 105E7100 [8] 01 29 00 2C 00 16 51 D0
```

### Generate test traffic
```bash
# classic CAN, 8-byte payloads
sudo cangen canX -L 8 -g 0 -n 1000

# CAN-FD, 16-byte payloads, BRS on
sudo cangen canX -f -b -L 16 -n 1
```


### Inspect interface stats

```bash
ip -details -statistics link show canX
```
- Key fields: state, error counters, bitrate/dbitrate, bus state.





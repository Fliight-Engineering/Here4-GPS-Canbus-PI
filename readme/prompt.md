I’m testing DJI Here4 GPS on a Raspberry Pi using a Waveshare 2-CH CAN-FD HAT. 
Here’s the setup:

- Pi + Waveshare HAT with MCP2517FD (spi1.0 → can0) and MCP2518FD (spi0.0 → can1), 40 MHz.
- The Here4 is connected to the CAN_0 screw terminal, which maps to OS `can1`.
- Power: 5 V from Pi header, GND common, CANH/L wired, ~60 Ω termination.
- Driver: mcp251xfd, overlays configured, dmesg shows both controllers probed.
- Goal: sniff and verify Here4 output, first in Classic CAN (SN65HVD230 compatible) at 1 M, then eventually CAN-FD 500k/8M.

Commands I’ve already tested:
- Bring-up CAN-FD:
  `sudo ip link set dev canX type can bitrate 500000 dbitrate 8000000 fd on …`
- Bring-up Classic 1M:
  `sudo ip link set dev canX type can bitrate 1000000 …`
- Listen-only sniff:
  `sudo ip link set dev canX type can bitrate 1000000 listen-only on …`
- Dump traffic: `candump -tz canX`
- Generate traffic: `cangen canX -L 8 …` (classic), `cangen -f -b -L 16 …` (FD)
- Inspect stats: `ip -details -statistics link show canX`

Observation:
- On `can1` at 1 M classic, I see repeating extended-ID frames from Here4 (DroneCAN).
- On CAN-FD settings, no traffic observed (as expected, since current wiring is classic transceiver).


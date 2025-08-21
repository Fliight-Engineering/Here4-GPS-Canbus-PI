#!/usr/bin/env python3
"""
here4_ros2_pub.py
-----------------
Bridge Here4 (DroneCAN) GNSS -> ROS 2 topics.

Publishes:
  /fix                 sensor_msgs/NavSatFix
  /gps/vel             geometry_msgs/TwistStamped   (from Fix2 velocities)
  /gps/dop             diagnostic_msgs/DiagnosticArray (PDOP/HDOP/VDOP, sats)
  /gps/sats_used       std_msgs/UInt32
  /gps/sats_visible    std_msgs/UInt32
  /gps/pdop            std_msgs/Float32
  /gps/hdop            std_msgs/Float32
  /gps/vdop            std_msgs/Float32

Usage:
  # bring up CAN
  sudo ip link set can1 down
  sudo ip link set can1 type can bitrate 1000000
  sudo ip link set can1 up

  # caps for your venv python OR run with sudo
  sudo setcap 'cap_net_raw,cap_net_admin+eip' "$(readlink -f ./venv/bin/python3)"

  # ROS 2 env (Humble/Jazzy/etc.)
  source /opt/ros/humble/setup.bash

  # deps
  pip install dronecan python-can

  ./venv/bin/python3 here4_ros2_pub.py --can-if can1 --bitrate 1000000 --node-id 125
"""
import argparse
import rclpy
from rclpy.node import Node as RclNode

from std_msgs.msg import UInt32, Float32
from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
from sensor_msgs.msg import NavSatFix, NavSatStatus
from geometry_msgs.msg import TwistStamped

import dronecan
from dronecan.node import Node as DcNode
from dronecan.driver.python_can import PythonCAN
from dronecan.app.node_monitor import NodeMonitor
from dronecan.app.dynamic_node_id import CentralizedServer

def ned_to_enu(vn, ve, vd):
    # NED -> ENU: x=E(=ve), y=N(=vn), z=U(=-vd)
    return ve, vn, -vd

class Here4Bridge(RclNode):
    def __init__(self, can_if: str, bitrate: int, my_id: int):
        super().__init__('here4_dronecan_bridge')
        # DroneCAN
        self.dc_drv = PythonCAN(can_if, bustype='socketcan', bitrate=bitrate)
        self.dc     = DcNode(self.dc_drv, node_id=my_id)
        self.mon    = NodeMonitor(self.dc)
        self.alloc  = CentralizedServer(self.dc, self.mon)
        self.get_logger().info("DroneCAN allocator enabled")

        # ROS pubs
        self.pub_fix   = self.create_publisher(NavSatFix,      '/fix',               10)
        self.pub_twist = self.create_publisher(TwistStamped,   '/gps/vel',           10)
        self.pub_diag  = self.create_publisher(DiagnosticArray,'/gps/dop',           10)
        self.pub_su    = self.create_publisher(UInt32,         '/gps/sats_used',     10)
        self.pub_sv    = self.create_publisher(UInt32,         '/gps/sats_visible',  10)
        self.pub_pdop  = self.create_publisher(Float32,        '/gps/pdop',          10)
        self.pub_hdop  = self.create_publisher(Float32,        '/gps/hdop',          10)
        self.pub_vdop  = self.create_publisher(Float32,        '/gps/vdop',          10)

        # cache last aux
        self.last_aux = dict(pdop=float('nan'), hdop=float('nan'), vdop=float('nan'),
                             gdop=float('nan'), used=0, vis=0)

        # Handlers
        self.dc.add_handler(dronecan.uavcan.protocol.NodeStatus, self._on_status)
        try: self.dc.add_handler(dronecan.uavcan.equipment.gnss.Fix2, self._on_fix2)
        except AttributeError: pass
        try: self.dc.add_handler(dronecan.uavcan.equipment.gnss.Fix,  self._on_fix)
        except AttributeError: pass
        self.dc.add_handler(dronecan.uavcan.equipment.gnss.Auxiliary, self._on_aux)

        # pump DroneCAN from ROS timer
        self.timer = self.create_timer(0.01, self._spin_dc)  # 100 Hz

    def _spin_dc(self):
        self.dc.spin(0.0)

    def _on_status(self, e):
        # ignore our own node status
        if e.transfer.source_node_id == self.dc.node_id:
            return

    def _on_fix_common(self, m, src_id):
        # NavSatFix
        fix = NavSatFix()
        now = self.get_clock().now().to_msg()
        fix.header.stamp = now
        fix.header.frame_id = 'gps'

        # lat/lon/alt
        lat = getattr(m, 'latitude_deg_1e8', None)
        lon = getattr(m, 'longitude_deg_1e8', None)
        altmm = getattr(m, 'height_msl_mm', getattr(m, 'height_mm', None))
        if lat is None or lon is None:
            return
        fix.latitude  = lat / 1e8
        fix.longitude = lon / 1e8
        fix.altitude  = (altmm / 1000.0) if isinstance(altmm, (int, float)) else float('nan')

        # covariance if present
        cov = getattr(m, 'position_covariance', None)
        if isinstance(cov, (list, tuple)) and len(cov) == 9:
            fix.position_covariance = [float(x) for x in cov]
            fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_KNOWN
        else:
            fix.position_covariance_type = NavSatFix.COVARIANCE_TYPE_UNKNOWN

        # basic status (you can map mode/status to RTK later)
        fix.status.status = NavSatStatus.STATUS_FIX
        fix.status.service = NavSatStatus.SERVICE_GPS
        self.pub_fix.publish(fix)

        # Velocity: prefer vector (m/s); else components (assume m/s)
        ned = getattr(m, 'ned_velocity', None)
        if isinstance(ned, (list, tuple)) and len(ned) == 3:
            vn, ve, vd = float(ned[0]), float(ned[1]), float(ned[2])
        else:
            vn = getattr(m, 'north_velocity', None)
            ve = getattr(m, 'east_velocity',  None)
            vd = getattr(m, 'down_velocity',  None)
            if not all(isinstance(v, (int, float)) for v in (vn, ve, vd)):
                vn = ve = vd = None

        if vn is not None:
            vx, vy, vz = ned_to_enu(vn, ve, vd)
            tw = TwistStamped()
            tw.header = fix.header
            tw.twist.linear.x = vx
            tw.twist.linear.y = vy
            tw.twist.linear.z = vz
            self.pub_twist.publish(tw)

        # Sats/PDOP (Fix2 preferred)
        su = getattr(m, 'sats_used', None)
        pd = getattr(m, 'pdop', None)
        if isinstance(su, int):     self.pub_su.publish(UInt32(data=su))
        if isinstance(pd, (int,float)): self.pub_pdop.publish(Float32(data=float(pd)))

        # DiagnosticArray snapshot (mix Fix2 + last Aux)
        diag = DiagnosticArray()
        diag.header = fix.header
        st = DiagnosticStatus()
        st.name = "Here4 GNSS DOPs"
        st.level = DiagnosticStatus.OK
        st.message = "OK"
        st.values = [
            KeyValue(key="PDOP", value=str(pd if isinstance(pd,(int,float)) else self.last_aux['pdop'])),
            KeyValue(key="HDOP", value=str(self.last_aux['hdop'])),
            KeyValue(key="VDOP", value=str(self.last_aux['vdop'])),
            KeyValue(key="GDOP", value=str(self.last_aux['gdop'])),
            KeyValue(key="sats_used", value=str(su if isinstance(su,int) else self.last_aux['used'])),
            KeyValue(key="sats_visible", value=str(self.last_aux['vis'])),
        ]
        diag.status = [st]
        self.pub_diag.publish(diag)

    def _on_fix2(self, e):
        self._on_fix_common(e.message, e.transfer.source_node_id)

    def _on_fix(self, e):
        self._on_fix_common(e.message, e.transfer.source_node_id)

    def _on_aux(self, e):
        m = e.message
        pdop = getattr(m, 'pdop', float('nan'))
        hdop = getattr(m, 'hdop', float('nan'))
        vdop = getattr(m, 'vdop', float('nan'))
        gdop = getattr(m, 'gdop', float('nan'))
        used = getattr(m, 'sats_used', 0)
        vis  = getattr(m, 'sats_visible', 0)
        self.last_aux.update(pdop=pdop, hdop=hdop, vdop=vdop, gdop=gdop, used=used, vis=vis)

        if isinstance(hdop, (int, float)): self.pub_hdop.publish(Float32(data=float(hdop)))
        if isinstance(vdop, (int, float)): self.pub_vdop.publish(Float32(data=float(vdop)))
        if isinstance(pdop, (int, float)): self.pub_pdop.publish(Float32(data=float(pdop)))
        if isinstance(used, int):          self.pub_su.publish(UInt32(data=int(used)))
        if isinstance(vis, int):           self.pub_sv.publish(UInt32(data=int(vis)))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--can-if', default='can1')
    parser.add_argument('--bitrate', type=int, default=1000000)
    parser.add_argument('--node-id', type=int, default=125)
    args = parser.parse_args()

    rclpy.init()
    node = Here4Bridge(args.can_if, args.bitrate, args.node_id)
    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()

if __name__ == '__main__':
    main()

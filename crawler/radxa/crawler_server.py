#!/usr/bin/env python3
"""
Pipecrawler - Radxa server: camera stream + drive bridge in one process.

    python3 crawler_server.py

  * Camera: GStreamer, hardware H.264, raw byte-stream on TCP port 5000.
    Restarted automatically if it dies.
  * Drive bridge: TCP port 5001.  One client (crawler/laptop/drive.py on the laptop)
    sends M / STOP / ZERO / PING lines; they go straight to the RP2040 over
    UART, and the RP2040's E telemetry lines come straight back.
    If the client disconnects, the bridge sends STOP immediately.  The RP2040's
    own 0.5 s watchdog backs that up if this program dies.

Protocol is documented in crawler/rp2040/main.py.
"""

import argparse
import socket
import subprocess
import threading
import time

import serial

GST = ("gst-launch-1.0 -q v4l2src device=/dev/video-camera0 ! "
       "video/x-raw,format=NV12,width=1280,height=720 ! "
       "mpph264enc gop=30 header-mode=1 ! h264parse config-interval=-1 ! "
       "video/x-h264,stream-format=byte-stream,alignment=au ! "
       "tcpserversink host=0.0.0.0 port={port} sync=false")

ALLOWED = (b"M", b"STOP", b"ZERO", b"PING")


class Bridge:
    def __init__(self, ser):
        self.ser = ser
        self.ser_lock = threading.Lock()
        self.client = None
        self.client_lock = threading.Lock()

    def to_rp2040(self, line):
        with self.ser_lock:
            self.ser.write(line + b"\n")

    def uart_reader(self):
        """RP2040 -> current client, line by line."""
        while True:
            line = self.ser.readline()
            if not line:
                continue
            with self.client_lock:
                c = self.client
            if c:
                try:
                    c.sendall(line)
                except OSError:
                    pass                # client loop notices and cleans up

    def serve_client(self, conn, addr):
        print("client connected:", addr[0])
        conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        with self.client_lock:
            self.client = conn
        buf = b""
        try:
            while True:
                data = conn.recv(256)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    line = line.strip()
                    if line.split(b" ", 1)[0].upper() in ALLOWED:
                        self.to_rp2040(line)
                if len(buf) > 256:
                    buf = b""
        except OSError:
            pass
        finally:
            self.to_rp2040(b"STOP")
            with self.client_lock:
                self.client = None
            conn.close()
            print("client gone - motors stopped")


def camera_keeper(port):
    """Keep the GStreamer pipeline running; restart it if it exits."""
    while True:
        proc = subprocess.Popen(GST.format(port=port).split(),
                                stderr=subprocess.DEVNULL)
        print("camera streaming on port", port)
        proc.wait()
        print("camera pipeline exited (code %s) - restarting in 2 s" % proc.returncode)
        time.sleep(2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uart", default="/dev/ttyS4")
    ap.add_argument("--video-port", type=int, default=5000)
    ap.add_argument("--ctrl-port", type=int, default=5001)
    ap.add_argument("--no-camera", action="store_true")
    args = ap.parse_args()

    ser = serial.Serial(args.uart, 115200, timeout=0.5)
    bridge = Bridge(ser)
    bridge.to_rp2040(b"STOP")
    threading.Thread(target=bridge.uart_reader, daemon=True).start()

    if not args.no_camera:
        threading.Thread(target=camera_keeper, args=(args.video_port,),
                         daemon=True).start()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("0.0.0.0", args.ctrl_port))
    srv.listen(1)
    print("drive bridge on port", args.ctrl_port, "- Ctrl-C to quit")

    try:
        while True:
            conn, addr = srv.accept()
            bridge.serve_client(conn, addr)     # one driver at a time
    except KeyboardInterrupt:
        pass
    finally:
        bridge.to_rp2040(b"STOP")
        print("\nstopped")


if __name__ == "__main__":
    main()

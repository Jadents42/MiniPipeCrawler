"""
Pipecrawler driver station - live camera + tank controls in one window.

    python running\\laptop\\drive.py

Needs running/radxa/crawler_server.py running on the Radxa.  Keys only work
while this window is focused; click away and the crawler stops.

     Q  W  E  R        Q / W  left / right forward  SLOW
     A  S  D  F        E / R  left / right forward  100%
                       A / S  left / right back     SLOW
     Space = stop      D / F  left / right back     100%
     Esc   = quit
"""

import argparse
import glob
import os
import shutil
import socket
import subprocess
import threading
import time

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
import pygame  # noqa: E402

VIDEO_W, VIDEO_H = 960, 540         # stream is 1280x720, scaled down to fit
HUD_H = 90
SEND_HZ = 20                        # RP2040 watchdog needs one every 0.5 s


def find_ffmpeg():
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    hits = glob.glob(os.path.expandvars(
        r"%LOCALAPPDATA%\Microsoft\WinGet\Packages\Gyan.FFmpeg*\*\bin\ffmpeg.exe"))
    if not hits:
        raise SystemExit("ffmpeg not found - winget install --id Gyan.FFmpeg -e --source winget")
    return hits[0]


class Video:
    """Decodes the Radxa's H.264 stream with ffmpeg; keeps only the newest frame."""

    def __init__(self, host, port):
        self.url = "tcp://%s:%d" % (host, port)
        self.frame = None
        self.frame_time = 0.0
        self.ffmpeg = find_ffmpeg()
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        size = VIDEO_W * VIDEO_H * 3
        while True:
            proc = subprocess.Popen(
                [self.ffmpeg, "-hide_banner", "-loglevel", "error",
                 "-fflags", "nobuffer", "-flags", "low_delay",
                 "-probesize", "32", "-analyzeduration", "0",
                 "-f", "h264", "-i", self.url,
                 "-vf", "scale=%d:%d" % (VIDEO_W, VIDEO_H),
                 "-fps_mode", "passthrough",
                 "-pix_fmt", "rgb24", "-f", "rawvideo", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            while True:
                data = proc.stdout.read(size)
                if len(data) < size:
                    break
                self.frame = data
                self.frame_time = time.time()
            proc.kill()
            time.sleep(1)               # stream not up yet / dropped - retry


class Link:
    """TCP link to crawler_server.py; parses E telemetry into speeds."""

    def __init__(self, host, port):
        self.addr = (host, port)
        self.sock = None
        self.counts = (0, 0)
        self.speed = (0.0, 0.0)         # counts/s, smoothed
        self.last_rx = 0.0
        threading.Thread(target=self._run, daemon=True).start()

    def send(self, line):
        s = self.sock
        if s:
            try:
                s.sendall(line.encode() + b"\n")
            except OSError:
                self.sock = None

    def _run(self):
        while True:
            try:
                s = socket.create_connection(self.addr, timeout=2)
                s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                s.settimeout(1)
                self.sock = s
                self._read(s)
            except OSError:
                pass
            self.sock = None
            time.sleep(1)

    def _read(self, s):
        buf = b""
        prev = None
        while True:
            try:
                data = s.recv(1024)
            except socket.timeout:
                continue
            if not data:
                return
            buf += data
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                p = line.split()
                if len(p) != 6 or p[0] != b"E":
                    continue
                ms, l, r = int(p[1]), int(p[2]), int(p[3])
                self.counts = (l, r)
                self.last_rx = time.time()
                if prev and ms > prev[0]:
                    dt = (ms - prev[0]) / 1000.0
                    vl, vr = (l - prev[1]) / dt, (r - prev[2]) / dt
                    a = 0.3
                    self.speed = (self.speed[0] + a * (vl - self.speed[0]),
                                  self.speed[1] + a * (vr - self.speed[1]))
                prev = (ms, l, r)


def tread(keys, fwd_slow, fwd_fast, back_slow, back_fast, slow):
    fwd = 100 if keys[fwd_fast] else (slow if keys[fwd_slow] else 0)
    back = 100 if keys[back_fast] else (slow if keys[back_slow] else 0)
    return fwd - back


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="192.168.137.2")
    ap.add_argument("--video-port", type=int, default=5000)
    ap.add_argument("--ctrl-port", type=int, default=5001)
    ap.add_argument("--slow", type=int, default=75, help="slow-key duty, percent")
    ap.add_argument("--no-video", action="store_true")
    args = ap.parse_args()

    pygame.init()
    screen = pygame.display.set_mode((VIDEO_W, VIDEO_H + HUD_H))
    pygame.display.set_caption("Pipecrawler")
    font = pygame.font.SysFont("consolas", 18)
    big = pygame.font.SysFont("consolas", 28, bold=True)
    clock = pygame.time.Clock()

    video = None if args.no_video else Video(args.host, args.video_port)
    link = Link(args.host, args.ctrl_port)

    left = right = 0
    t_send = 0.0
    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE:
                running = False

        keys = pygame.key.get_pressed()
        if not pygame.key.get_focused() or keys[pygame.K_SPACE]:
            left = right = 0
        else:
            left = tread(keys, pygame.K_q, pygame.K_e, pygame.K_a, pygame.K_d, args.slow)
            right = tread(keys, pygame.K_w, pygame.K_r, pygame.K_s, pygame.K_f, args.slow)

        now = time.time()
        if now - t_send >= 1.0 / SEND_HZ:
            t_send = now
            link.send("M %d %d" % (left, right))

        # -- draw --
        screen.fill((15, 15, 18))
        if video and video.frame and now - video.frame_time < 2:
            img = pygame.image.frombuffer(video.frame, (VIDEO_W, VIDEO_H), "RGB")
            screen.blit(img, (0, 0))
        else:
            msg = "video off" if not video else "waiting for camera..."
            t = big.render(msg, True, (120, 120, 130))
            screen.blit(t, t.get_rect(center=(VIDEO_W // 2, VIDEO_H // 2)))

        y = VIDEO_H + 8
        linked = link.sock is not None and now - link.last_rx < 1
        status = ("LINK OK", (80, 200, 120)) if linked else ("NO LINK", (230, 80, 80))
        screen.blit(big.render(status[0], True, status[1]), (12, y))
        for i, (name, duty, spd) in enumerate((("LEFT ", left, link.speed[0]),
                                               ("RIGHT", right, link.speed[1]))):
            col = (240, 200, 60) if duty else (200, 200, 200)
            screen.blit(font.render("%s duty %+4d%%   %+6.0f counts/s"
                                    % (name, duty, spd), True, col),
                        (200, y + 4 + i * 24))
        screen.blit(font.render("QW/AS slow %d%%   ER/DF 100%%   Space stop   Esc quit"
                                % args.slow, True, (130, 130, 140)), (12, y + 56))
        if not pygame.key.get_focused():
            screen.blit(font.render("CLICK HERE TO DRIVE", True, (230, 80, 80)),
                        (VIDEO_W - 220, y + 4))

        pygame.display.flip()
        clock.tick(60)

    link.send("STOP")
    time.sleep(0.1)
    pygame.quit()


if __name__ == "__main__":
    main()

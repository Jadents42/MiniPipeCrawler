# Pipecrawler live camera viewer (low latency).
#
# Start the stream on the Radxa first:
#   gst-launch-1.0 v4l2src device=/dev/video-camera0 ! video/x-raw,format=NV12,width=1280,height=720 ! mpph264enc ! h264parse config-interval=-1 ! video/x-h264,stream-format=byte-stream,alignment=au ! tcpserversink host=0.0.0.0 port=5000 sync=false
#
# Then from the repo root:   .\old\laptop\cam.ps1

param([string]$Radxa = "192.168.137.2", [int]$Port = 5000)

$ffplay = (Get-Command ffplay -ErrorAction SilentlyContinue).Source
if (-not $ffplay) {
    $ffplay = Get-ChildItem "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\Gyan.FFmpeg*\*\bin\ffplay.exe" -ErrorAction SilentlyContinue |
        Select-Object -First 1 -ExpandProperty FullName
}
if (-not $ffplay) { throw "ffplay not found - install with: winget install --id Gyan.FFmpeg -e --source winget" }

& $ffplay -hide_banner -loglevel warning -window_title "Pipecrawler cam" `
    -f h264 -fflags nobuffer -flags low_delay -framedrop `
    -probesize 32 -analyzeduration 0 -sync ext "tcp://${Radxa}:${Port}"

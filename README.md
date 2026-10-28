# XMeye NVR for Home Assistant

One integration for a Xiongmai / XMeye NVR:

* **Live cameras** for every NVR channel (main stream, plus a hidden sub-stream camera),
  with low-latency WebRTC through Home Assistant's built-in go2rtc.
* **HomeKit-ready**: the cameras' stream comes from go2rtc's local RTSP restream, so
  Home Assistant's HomeKit Bridge can expose them (video copied, no transcoding) while
  the NVR sees one connection per stream.
* **Recordings stay on the NVR.** Nothing is recorded into Home Assistant. A sidebar
  panel shows them on a timeline with motion events and thumbnails and plays them on demand.

Talks the NVR's own DVRIP protocol (port 34567, what the XMeye app uses) for recordings
and its RTSP server (port 554) for live video. Tested on an NBD88X16S-KL-V3 NVR,
firmware V4.03.R11, with H.264 cameras, on Home Assistant 2026.10.

## The NVR panel

**Grid:** the newest motion events of all cameras along the top (thumbnail and time),
and a live tile for every camera below (sub stream, muted). Click a tile or an event to
open that camera.

**Single camera:**

* Big player: live main stream (WebRTC, sound on demand) or a recording.
* Timeline of the selected day: continuous recording in grey, motion in blue. Click to
  play from that moment. Scroll to zoom, drag to pan, or use the + / − buttons.
  Playback goes on into the next file.
* Event list with thumbnails (adjacent motion files merged into one event). A day picker
  covers every day the NVR has footage for. The **Live** button returns to the live view.
* Camera chips, previous / next camera, mute and fullscreen.

The panel works on phones too. The event list moves below the player.

## Install

1. Copy `custom_components/xmeye` to `<config>/custom_components/`, or add this repository
   to HACS as a custom repository (category *Integration*).
2. Restart Home Assistant, then **Settings → Devices & services → Add integration → XMeye NVR**.
3. Enter the NVR's host, the DVRIP port (34567), the RTSP port (554), user and password.
   The password is stored only in the config entry.

**Options:** camera names (the NVR's channel titles by default; an empty name hides the
channel), and whether H.265 recordings are transcoded to H.264 for playback.

## HomeKit

Add a **HomeKit Bridge** in *accessory mode* for a camera entity (one per camera) and set
its video codec to *copy*. The camera's stream source is
`rtsp://127.0.0.1:18554/xmeye-nvr-<serial>-<channel>` (go2rtc's restream). HomeKit,
WebRTC viewers and snapshots therefore share the same NVR connection.

Without the built-in go2rtc (e.g. a core install without the go2rtc binary), the cameras
use the NVR's RTSP URL directly.

## How playback works

Starting playback logs in to the NVR and downloads the file from the requested second
(`OPPlayBack` `DownloadStart`). The integration strips the NVR's frame headers, wraps
the H.264 in MPEG-TS, and HA's ffmpeg turns it into HLS (video copied, G.711 → AAC). Short
clips start in about 2 s. A 2560×1440 stream downloads about 2.5× faster than real time.
The segments sit in a temporary directory only while someone is watching. They are
deleted 2 minutes after the last request, and at shutdown and startup.

Thumbnails are the first I-frame two seconds into an event (one short download each).
They are kept in memory.

See [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) for the protocol details and the design.

## Test without an NVR

```
python tools/mock_nvr.py some-recording.xm --port 34599   # login admin / test
```

Add the integration with host `127.0.0.1`, port `34599`. The mock lists a recording every
10 minutes on channels 1 and 9 and streams the given file (any file in the NVR's frame
format) for every download. It has no RTSP server, so live tiles stay empty.

## Caveats

* Seeking inside a recording works within what has already been downloaded. Clicking
  the timeline starts a new download at that point instead.
* Video timing comes from the frame rate in the NVR's frame header. A camera that
  reports 20 fps but sends 19.7 plays about 1 % fast.
* Only H.264 has been tested. The H.265 path (copy with `hvc1` tag, or libx264
  transcode) is untested.

## Third-party code

`custom_components/xmeye/frontend/hls.light.min.js` is [hls.js](https://github.com/video-dev/hls.js)
1.5.20, Apache License 2.0 (see `hls.js.LICENSE`).

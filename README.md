# XMeye Full NVR for Home Assistant

<img src="custom_components/xmeye/brand/icon.png" width="96" align="right" alt="">

One integration for a Xiongmai / XMeye NVR:

* **Live cameras** for every NVR channel (main stream, plus a hidden sub-stream camera),
  with low-latency WebRTC through Home Assistant's built-in go2rtc.
* **HomeKit** without transcoding: switch cameras on in the panel's settings and pair them
  with the code shown there. A dedicated go2rtc serves them to Apple Home.
* **Motion sensors** per camera from the NVR's live alarm stream (`binary_sensor.<camera>_motion`;
  a person sensor is created disabled, for cameras that report people to the NVR).
* **NVR settings** in the panel: recording mode per camera (always / motion only / off),
  motion detection and sensitivity, disk usage and how many days the disk holds.
* **Recordings stay on the NVR.** Nothing is recorded into Home Assistant. A sidebar
  panel shows them on a timeline with motion events and thumbnails and plays them on demand.

Talks the NVR's own DVRIP protocol (port 34567, what the XMeye app uses) for recordings
and its RTSP server (port 554) for live video. Tested on an NBD88X16S-KL-V3 NVR,
firmware V4.03.R11, with H.264 and H.265 cameras, on Home Assistant OS 2026.10.

## The panel (sidebar → XMeye Full NVR)

**Grid:** the newest motion events of all cameras along the top (thumbnail and time),
and a live tile for every camera below (sub stream, muted). Choose the layout next to
*Cameras*: **All** (every camera fits on the screen, also on a phone), **1** or **2**
columns (scrolling). Click a tile or an event to open that camera.

**Single camera:**

* Big player: live main stream (WebRTC, sound on demand) or a recording.
* Timeline of the selected day: continuous recording in grey, motion in blue. Click to
  play from that moment. Scroll to zoom, drag to pan, or use the + / − buttons.
  Playback goes on into the next file.
* Playback speed 1×, 2×, 4×, 6×, 12×, 24×.
* **Events** tab (motion, with thumbnails) and **Recordings** tab (everything, per hour).
  A day picker covers every day the NVR has footage for. The **Live** button returns to the
  live view.
* Camera chips, previous / next camera, mute and fullscreen.

**Settings** (admins): disk, retention and bitrate per camera, recording mode, motion
detection, HomeKit on/off with pairing code.

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

Home Assistant's own go2rtc runs without its HomeKit module, so the integration starts a
second go2rtc just for HomeKit. Nothing has to be installed. It uses the go2rtc that comes
with Home Assistant OS and the container image. On other installs it downloads the pinned
go2rtc 1.9.14 release from GitHub once (checked by SHA-256) into `.storage`. It listens on port 51830 (HomeKit) and 51831 (SRTP video). Only the HomeKit
pairing endpoints are reachable from the network; go2rtc's API and streams are not. It
reads the main streams from HA's go2rtc RTSP restream, so H.264 video is passed through and
the NVR still sees one connection per stream. HomeKit only takes H.264. For H.265 cameras
go2rtc converts the video to 1080p H.264 with ffmpeg while someone watches in the Home app
(about real time for a 2560×1440 camera on an x86 box). Each camera can also use its
**sub stream**, which is often H.264, so nothing is converted, at a lower resolution.
Sound is converted to Opus.

1. Panel → **Settings** → turn **HomeKit** on for a camera.
2. Apple Home → **Add Accessory → More options**, pick the camera and enter the code
   shown in the panel.

The panel shows when a camera is paired and can unpair it (a new code is created). Turn a
camera off and on only when needed: go2rtc restarts on every change, which interrupts
pairing in progress.

## Recording time and disk

The panel's settings show how many days the disk holds. That figure is disk size ÷
(sum of the cameras' bitrates). *Motion only* recording for quiet cameras, or a lower
bitrate in a camera's own settings, makes it last longer.

## H.265 cameras

* **Recordings:** browsers that decode H.265 (Safari, Chrome/Edge with hardware decoding)
  get the video unchanged. For others the integration converts it to H.264 (libx264, about
  3× real time at 2560×1440 on an x86 Home Assistant box). Turn that off in the integration
  options if no browser of yours needs it.
* **Live:** WebRTC in the browser carries H.265 only where the browser supports it (Safari,
  recent Chrome with hardware decoding). The grid uses the sub stream, which is often H.264.
* **HomeKit:** converted to H.264, see above. Apple's newer camera spec (the *HomeKit Secure
  Video Open Source Compatibility Guide*, a developer preview from June 2026, tvOS 27 hubs)
  adds H.265. go2rtc does not support it yet (only an experimental pull request,
  AlexxIT/go2rtc#2343). The integration will switch to it once go2rtc ships it.

## HomeKit Secure Video (recording to iCloud)

Not supported yet. HomeKit Secure Video needs the camera accessory to provide a recording stream
and motion to the home hub. The official go2rtc release (1.9.15) only does live view.
HKSV exists only in that experimental pull request and in forks. The integration
already has the motion events (from the NVR's alarm stream) to feed it. HKSV is planned for
when go2rtc supports it. Until then the recordings stay on the NVR and play in the panel.

## How playback works

Starting playback logs in to the NVR and downloads the file from the requested second
(`OPPlayBack` `DownloadStart`). The integration strips the NVR's frame headers, wraps
the H.264 in MPEG-TS, and HA's ffmpeg turns it into HLS (video copied, G.711 → AAC). Short
clips start in about 2 s. A 2560×1440 stream downloads about 2.5× faster than real time.
The segments sit in a temporary directory only while someone is watching. They are
deleted 2 minutes after the last request, and at shutdown and startup.

Video timing comes from the NVR's per-I-frame time stamps (the frame rate in the header
is not always right). For 1–2× the browser speeds up playback. From 4× the server sends
only key frames on a compressed time line. Downloads from the NVR run at about
1 MB/s, so the real top speed is about 8 Mbit/s ÷ the camera's bitrate: a 0.5 Mbit/s camera
does 24×, a 5 Mbit/s camera about 1.5×.

Thumbnails are the first I-frame two seconds into an event (one short download each).
They are kept in memory.

Motion events come from the NVR's live alarm stream and are stored in Home Assistant (times
only, 14 days). For the time before that, short motion-tagged files are used. Long `[M]`
files from continuous recording don't say when the motion happened.

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
* Fast playback is limited by the NVR's download speed (see above).
* Only H.264 has been tested. The H.265 path (copy with `hvc1` tag, or libx264
  transcode) is untested.

## Third-party code

`custom_components/xmeye/frontend/hls.light.min.js` is [hls.js](https://github.com/video-dev/hls.js)
1.5.20, Apache License 2.0 (see `hls.js.LICENSE`).

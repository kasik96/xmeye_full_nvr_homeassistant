# Development notes

## DVRIP (port 34567)

* 20-byte little-endian header `<BB2xIIBBHI>`: `0xFF`, version 1, 2 reserved bytes, session id,
  sequence, total / current packet, message id, body length. JSON body ends with `\n\0`.
  The reply id is the request id + 1. After login every request carries `"SessionID": "0x%08X"`.
* Login 1000: `{EncryptType:"MD5", LoginType:"DVRIP-Web", UserName, PassWord:<sofia hash>}`. The Sofia hash is
  MD5 of the password folded into 8 characters: `chars[(d[2i] + d[2i+1]) % 62]` over `0-9A-Za-z`.
  Ret 203 = wrong password. Keep-alive 1006 every `AliveInterval` seconds.
* 1020 `SystemInfo`, 1048 `ChannelTitle`, 1042 `NetWork.ChnStatus` (`Status: "NoConfig"` = no camera).
* 1446 `OPSCalendar {Year, Month, Event:"*", FileType:"h264", Rev:""}` → `Mask`, bit (day − 1). Not per channel.
* 1440 `OPFileQuery {BeginTime, EndTime, Channel (0-based), DriverTypeMask:"0x0000FFFF", Event:"*", Type:"h264",
  StreamType:"0x00000000"}` → at most 64 files. Next page: `BeginTime` = latest `EndTime` of the page. Ret 119 = none.
  File names look like `/idea0/2026-10-28/009/21.59.26-21.59.42[M][@2f0f][0].h264`: `[M]` motion, `[R]` regular,
  `[H]` manual, `[A]` alarm. `FileLength` is in KB (hex string).
* Download: log in on a fresh control connection. On a second connection set the header session id to the
  control session and send 1424 `OPPlayBack {Action:"Claim", StartTime, EndTime, Parameter:{PlayMode:"ByName",
  FileName, StreamType:0, Value:0, TransMode:"TCP"}}`. Then send 1420 with `Action:"DownloadStart"` on the
  control connection. Data arrives as 1426 packets on the second connection, and an empty packet ends it.
  Stop with `DownloadStop`. A `StartTime` inside the file seeks there. `PlayMode:"ByTime"` ignores the channel.
* Media frames (little endian):

  | Start | Header | Fields |
  |---|---|---|
  | `00 00 01 FC` / `FE` | 16 | I-frame: [4] low nibble codec (2 H.264, 3 H.265 — both verified), [5] fps, [6]/[7] size / 8, [8..11] packed date, [12..15] length |
  | `00 00 01 FD` | 8 | P-frame: [4..7] length |
  | `00 00 01 FA` | 8 | Audio: [4] codec (0x0E A-law, 0x0A µ-law), [6..7] length |
  | `00 00 01 F9` | 8 | Info: [6..7] length |

  The payload is Annex-B. On garbage, resync on the next `00 00 01 F9..FE`.

* Alarms: on a separate logged-in connection send 1500 `{Name:""}`. Messages 1504 then arrive:
  `{"AlarmInfo":{"Channel":<0-based>,"Event":"VideoMotion"|"appEventHumanDetectAlarm","Status":"Start"|"Stop",
  "StartTime":…}}`, plus the current state right after subscribing. Keep-alive as usual. Verified: the channel
  matches `WorkState.AlarmState.VideoMotion` bit n.
* Config: 1042 get / 1040 set. Use `Record.[i]` (`RecordMode` `ConfigRecord|ManualRecord|ClosedRecord`, `Mask[day][0]`
  bit 1 regular, 2 motion, 4 alarm, `TimeSection[day][0]` `"1 00:00:00-24:00:00"`) and `Detect.MotionDetect.[i]`
  (`Enable`, `Level` 1–6). 1020 `StorageInfo` (`TotalSpace`/`RemainSpace` MB hex, `OldStartTime`), `WorkState`
  (`ChannelState[i].Bitrate` kbit/s).
* `OPPlayBack` `Start` is paced in real time. `Fast` with `Value` did not speed it up reliably. `OPFileQuery`
  `StreamType` 1 (sub stream) found nothing: this NVR records the main stream only.

## Live

RTSP `rtsp://<host>:554/user=<u>&password=<p>&channel=<1-based>&stream=<0 main|1 sub>.sdp?`.
When HA manages go2rtc (`hass.data["go2rtc"].url == http://localhost:11984/`), the integration adds a
`xmeye-nvr-<serial>-<ch>[-sub]` stream per source over the go2rtc API and re-adds missing streams every
minute. The camera's `stream_source` is the restream `rtsp://127.0.0.1:18554/<name>`. The name must not be
`xmeye_<unique id>`, because HA's go2rtc WebRTC provider uses that name for the camera itself. A collision
makes a stream that reads from itself.

## Playback pipeline (`playback.py`)

1. `DVRIPClient.download()` from the requested second to the end of the file. The video clock is built from the
   I-frames' 1-second time stamps (frame rate measured over ≥ 6 s; gaps > 10 s jump the clock). From 4× only
   I-frames are passed, with PTS divided by the speed.
2. `FrameParser` splits the frames. The first 50 video frames are buffered to learn fps, codec and whether
   there is audio.
3. Video → `tsmux.TsMuxer` (MPEG-TS, PTS = frame × 90000 / fps) → ffmpeg stdin. Audio (raw G.711) goes to
   a second pipe, and gaps are padded with silence up to the video clock. Raw H.264 on a pipe has no
   timestamps. ffmpeg then stops reading the other input, and the pipeline stalls.
4. ffmpeg → HLS (fMP4, 4 s segments, EVENT playlist) in a temp dir. `/api/xmeye/hls/<token>/…` serves it
   without HA auth: the random token is the authorization, like HA's own stream URLs. The playlist is
   returned once two segments exist, with `#EXT-X-START:TIME-OFFSET=0` so players start at the beginning.

## HomeKit (`homekit.py`)

A second go2rtc (`shutil.which("go2rtc")`) runs with `.storage/xmeye_homekit_go2rtc.yaml`: modules `api`, `homekit`,
`rtsp`, `srtp`. `api.listen` is `:51830` with `allow_paths` limited to the HAP endpoints, the RTSP server is off,
SRTP is on `:51831` (HA's go2rtc has 8443). Streams are `hk_<serial>_<ch>` pointing at HA's restream. go2rtc writes
the pairings back into that file; the integration keeps them when it rewrites it. Per-camera on/off and PIN live in
`.storage/xmeye.homekit`. go2rtc's mDNS only answers queries (no announcements).

Each HomeKit stream has `[rtsp restream, ffmpeg:<name>#video=h264, ffmpeg:<name>#audio=opus]`: go2rtc takes the
first source whose codecs HomeKit accepts, so H.264 is passed through and H.265 is transcoded on demand (`exec`
allowed for `ffmpeg` only). go2rtc patches pairings into its YAML in place and breaks on PyYAML's default style
(lists at the key's indent, long lines wrapped), so the file is written with indented lists and no wrapping, and
only rewritten (and go2rtc restarted) when it changes. Without a system go2rtc, the pinned 1.9.14 release is
downloaded and checked against SHA-256 (amd64, arm64, arm).

## Panel API

| WebSocket | Returns |
|---|---|
| `xmeye/cameras` | cameras with `entry_id`, `channel`, `name`, `entity_id`, `sub_entity_id` |
| `xmeye/day {entry_id, channel, date?}` | `recordings`, `events` (merged motion), `days` with footage |
| `xmeye/events {hours, limit}` | recent events of all cameras |
| `xmeye/play {entry_id, channel, time, speed, hevc}` (`hevc`: the browser decodes H.265, so no transcoding) | HLS `url`, `begin`, `end`, `speed` the server applied (1 or ≥ 4) |
| `xmeye/nvr {entry_id}` (admin) | system, storage, work state, record and motion config, titles |
| `xmeye/settings_set {entry_id, channel, record?, motion_enabled?, motion_level?}` (admin) | writes to the NVR |
| `xmeye/homekit`, `xmeye/homekit_set {key, enabled?, reset?}` (admin) | HomeKit status / switch / unpair |
| `xmeye/probe {entry_id, channel, time, seconds}` (admin) | diagnostics: real frame rate and download speed |

`GET /api/xmeye/thumb/<entry_id>/<channel>/<YYYYmmddHHMMSS>.jpg` (HA auth) returns an event thumbnail.

The panel (`frontend/xmeye-panel.js`) is a plain web component without a build step. Live video uses HA's
`camera/webrtc/*` WebSocket API, falling back to `camera/stream` HLS. Recordings play through hls.js
(native HLS on Safari).

## Testing

`tools/mock_nvr.py` serves login, system info, titles, channel status, calendar, file queries and downloads.
Run it with a capture in the NVR frame format. A local HA dev install with this repo's `custom_components`
covers the config flow, the panel, thumbnails and playback.

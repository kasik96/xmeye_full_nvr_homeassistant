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
  | `00 00 01 FC` / `FE` | 16 | I-frame: [4] low nibble codec (2 H.264, 3 H.265), [5] fps, [6]/[7] size / 8, [8..11] packed date, [12..15] length |
  | `00 00 01 FD` | 8 | P-frame: [4..7] length |
  | `00 00 01 FA` | 8 | Audio: [4] codec (0x0E A-law, 0x0A µ-law), [6..7] length |
  | `00 00 01 F9` | 8 | Info: [6..7] length |

  The payload is Annex-B. On garbage, resync on the next `00 00 01 F9..FE`.

## Live

RTSP `rtsp://<host>:554/user=<u>&password=<p>&channel=<1-based>&stream=<0 main|1 sub>.sdp?`.
When HA manages go2rtc (`hass.data["go2rtc"].url == http://localhost:11984/`), the integration adds a
`xmeye-nvr-<serial>-<ch>[-sub]` stream per source over the go2rtc API and re-adds missing streams every
minute. The camera's `stream_source` is the restream `rtsp://127.0.0.1:18554/<name>`. The name must not be
`xmeye_<unique id>`, because HA's go2rtc WebRTC provider uses that name for the camera itself. A collision
makes a stream that reads from itself.

## Playback pipeline (`playback.py`)

1. `DVRIPClient.download()` from the requested second to the end of the file.
2. `FrameParser` splits the frames. The first 50 video frames are buffered to learn fps, codec and whether
   there is audio.
3. Video → `tsmux.TsMuxer` (MPEG-TS, PTS = frame × 90000 / fps) → ffmpeg stdin. Audio (raw G.711) goes to
   a second pipe, and gaps are padded with silence up to the video clock. Raw H.264 on a pipe has no
   timestamps. ffmpeg then stops reading the other input, and the pipeline stalls.
4. ffmpeg → HLS (fMP4, 4 s segments, EVENT playlist) in a temp dir. `/api/xmeye/hls/<token>/…` serves it
   without HA auth: the random token is the authorization, like HA's own stream URLs. The playlist is
   returned once two segments exist, with `#EXT-X-START:TIME-OFFSET=0` so players start at the beginning.

## Panel API

| WebSocket | Returns |
|---|---|
| `xmeye/cameras` | cameras with `entry_id`, `channel`, `name`, `entity_id`, `sub_entity_id` |
| `xmeye/day {entry_id, channel, date?}` | `recordings`, `events` (merged motion), `days` with footage |
| `xmeye/events {hours, limit}` | recent events of all cameras |
| `xmeye/play {entry_id, channel, time}` | HLS `url`, `begin`, `end` of the file being played |

`GET /api/xmeye/thumb/<entry_id>/<channel>/<YYYYmmddHHMMSS>.jpg` (HA auth) returns an event thumbnail.

The panel (`frontend/xmeye-panel.js`) is a plain web component without a build step. Live video uses HA's
`camera/webrtc/*` WebSocket API, falling back to `camera/stream` HLS. Recordings play through hls.js
(native HLS on Safari).

## Testing

`tools/mock_nvr.py` serves login, system info, titles, channel status, calendar, file queries and downloads.
Run it with a capture in the NVR frame format. A local HA dev install with this repo's `custom_components`
covers the config flow, the panel, thumbnails and playback.

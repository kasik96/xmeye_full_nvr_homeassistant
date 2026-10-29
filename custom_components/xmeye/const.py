"""Constants for the XMeye Full NVR integration."""

from datetime import timedelta

DOMAIN = "xmeye"

DEFAULT_PORT = 34567
CONF_RTSP_PORT = "rtsp_port"
DEFAULT_RTSP_PORT = 554

CONF_TRANSCODE_H265 = "transcode_h265"
DEFAULT_TRANSCODE_H265 = True
# {"<1-based channel>": name}; "" hides the channel
CONF_NAMES = "names"

# HLS playback sessions
HLS_SEGMENT_SECONDS = 4
MAX_SESSIONS = 6
SESSION_IDLE = 120  # s without a request before a session's temp files go
PLAYLIST_WAIT = 25  # s to wait for the first segments

# How long file lists are cached
CACHE_TODAY = 30
CACHE_PAST = 600

# Motion files closer than this are one event
EVENT_MERGE_GAP = timedelta(seconds=5)
# Longer [M] files are continuous recording, not a motion clip
MOTION_FILE_MAX = 600
# a start this close to the end of a file has no key frame left: use the next file
FILE_TAIL = timedelta(seconds=10)

# Event thumbnails
THUMB_CACHE = 800
THUMB_WIDTH = 480
THUMB_OFFSET = 2  # s into the event, the first frames are pre-record

PANEL_URL = "/xmeye_static"

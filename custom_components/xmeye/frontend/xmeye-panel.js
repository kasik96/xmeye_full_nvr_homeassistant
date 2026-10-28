// XMeye Full NVR panel: live grid, single camera with recordings timeline and events.
// Plain web component, no build step. Live video uses HA's camera WebRTC
// (go2rtc); recordings are HLS sessions from the integration, played with hls.js.

const DAY = 86400;
const SPEEDS = [1, 2, 4, 6, 12, 24];
const SERVER_SPEED = 4; // from here on the server sends key frames only
const GRID_LAYOUTS = [
  ["fit", "All", "All cameras on screen"],
  ["1", "1", "One column"],
  ["2", "2", "Two columns"],
];
const MIN_SPAN = 300;

const css = `
:host { display:block; height:100%; background:#0f1012; color:#e8e8ea;
  font-family: var(--paper-font-body1_-_font-family, Roboto, system-ui, sans-serif); }
* { box-sizing:border-box; }
[hidden] { display:none !important; }
button { font:inherit; color:inherit; background:none; border:0; cursor:pointer; }
.app { display:flex; flex-direction:column; height:100vh; height:100dvh; }
header { display:flex; align-items:center; gap:8px; height:56px; padding:0 12px; flex:none;
  border-bottom:1px solid #1f2125; }
header h1 { font-size:19px; font-weight:400; margin:0 10px 0 2px; letter-spacing:.3px; white-space:nowrap; }
header .logo { width:30px; height:30px; border-radius:8px; margin-left:4px; }
.icon { width:40px; height:40px; border-radius:50%; display:grid; place-items:center; }
.icon:hover { background:#1d1f23; }
.icon svg { width:22px; height:22px; fill:currentColor; }
.spacer { flex:1; }
.seg { display:flex; background:#1a1c20; border-radius:20px; padding:3px; }
.seg button { padding:6px 14px; border-radius:16px; font-size:13px; color:#aab; white-space:nowrap; }
@media (max-width: 600px) {
  header { gap:4px; padding:0 6px; }
  header h1 { display:none; }
  .seg button { padding:6px 11px; }
  h2 { font-size:17px; margin:12px 12px 6px; }
  .strip { padding:0 12px 6px; min-height:112px; }
  .ev, .ev .th { width:120px; } .ev .th { height:84px; }
  .gridwrap { padding:0 12px 12px; }
  .camhead { padding-right:12px; }
  .tile .name { top:6px; right:8px; font-size:11px; }
  .left { padding:8px; }
  .bar .icon.prev, .bar .icon.next { display:none; }
}
.seg button.on { background:#2d6cdf; color:#fff; }
main { flex:1; min-height:0; overflow:hidden; container-type:size; }
main.scroll { overflow:auto; container-type:inline-size; }
.gridview { display:flex; flex-direction:column; height:100%; }
.gridwrap { flex:1; min-height:0; display:flex; justify-content:center; align-items:flex-start; padding:0 16px 16px; }
.gridview.flow { height:auto; }
.gridview.flow .gridwrap { flex:none; }
.camhead { display:flex; align-items:center; justify-content:space-between; padding-right:16px; flex:none; }
.small-seg button { padding:4px 11px; font-size:12px; }
h2 { font-size:20px; font-weight:400; margin:14px 16px 8px; flex:none; }
.strip { display:flex; gap:10px; overflow-x:auto; padding:0 16px 6px; scrollbar-width:thin; flex:none; min-height:128px; }
.ev { flex:none; width:140px; text-align:center; font-size:12px; color:#bbb; }
.ev .th { width:140px; height:100px; border-radius:10px; background:#1b1d21 center/cover; position:relative;
  overflow:hidden; }
.ev .th img { width:100%; height:100%; object-fit:cover; display:block; }
.ev .cam { position:absolute; left:6px; bottom:5px; font-size:11px; color:#fff;
  text-shadow:0 1px 3px #000; }
.ev div.t { margin-top:6px; }
.grid { display:grid; gap:10px; }
.tile { position:relative; aspect-ratio:16/9; border-radius:12px; overflow:hidden; background:#000;
  cursor:pointer; }
.tile video, .tile img.poster { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }
.tile .name { position:absolute; top:10px; right:12px; font-size:14px; font-weight:500;
  letter-spacing:.6px; text-transform:uppercase; text-shadow:0 1px 4px #000; display:flex;
  align-items:center; gap:6px; }
.dot { width:9px; height:9px; border-radius:50%; background:#e5484d; display:inline-block; }
.dot.off { background:#666; }
.single { display:flex; height:100%; }
.left { flex:1; display:flex; flex-direction:column; min-width:0; min-height:0; padding:12px; gap:10px; }
.chips { display:flex; gap:6px; overflow-x:auto; flex:none; scrollbar-width:none; }
.chip { padding:6px 12px; border-radius:16px; background:#1a1c20; font-size:13px; white-space:nowrap; }
.chip.on { background:#2d6cdf; color:#fff; }
.player { position:relative; flex:1; min-height:160px; width:100%; background:#000; border-radius:12px; overflow:hidden; }
.player:fullscreen { border-radius:0; }
.speed { background:#0008; color:#fff; border:1px solid #fff4; border-radius:14px; padding:4px 8px; font:inherit; font-size:13px; }
.player video { position:absolute; inset:0; width:100%; height:100%; object-fit:contain; background:#000; }
.bar { position:absolute; left:0; right:0; bottom:0; display:flex; align-items:center; gap:10px;
  padding:10px 12px; background:linear-gradient(transparent, rgba(0,0,0,.75)); }
.bar .ttl { font-size:15px; } .bar .sub { font-size:12px; color:#bbb; }
.bar .icon { width:36px; height:36px; }
.msg { position:absolute; inset:0; display:grid; place-items:center; color:#aaa; font-size:14px;
  pointer-events:none; }
.tl { flex:none; background:#16181b; border-radius:12px; padding:8px 12px 10px; user-select:none; }
.tlhead { display:flex; align-items:center; gap:6px; font-size:13px; color:#bbb; margin-bottom:6px; }
.tlhead .date { min-width:118px; text-align:center; color:#e8e8ea; }
.tlhead select { background:#1f2226; color:#e8e8ea; border:0; border-radius:6px; padding:3px 6px; }
.track { position:relative; height:38px; background:#0f1012; border-radius:6px; overflow:hidden;
  cursor:pointer; touch-action:none; }
.seg-r { position:absolute; top:10px; height:18px; background:#3a3f47; }
.seg-m { position:absolute; top:6px; height:26px; background:#2d6cdf; border-radius:2px; }
.cursor { position:absolute; top:0; bottom:0; width:2px; background:#ff5c5c; pointer-events:none; }
.hover { position:absolute; top:0; bottom:0; width:1px; background:#fff8; pointer-events:none; }
.hovert { position:absolute; top:-1px; transform:translateX(-50%); font-size:10px; background:#000c;
  padding:1px 4px; border-radius:3px; pointer-events:none; white-space:nowrap; }
.ticks { position:relative; height:14px; font-size:10px; color:#777; }
.ticks span { position:absolute; transform:translateX(-50%); }
aside { width:340px; flex:none; border-left:1px solid #1f2125; display:flex; flex-direction:column; min-height:0; }
.tabs { display:flex; flex:none; border-bottom:1px solid #1f2125; }
.tabs button { flex:1; padding:14px 0 12px; font-size:13px; letter-spacing:1px; color:#9ab; text-transform:uppercase;
  border-bottom:2px solid transparent; }
.tabs button.on { color:#fff; border-color:#2d6cdf; }
.list { flex:1; overflow-y:auto; padding:6px 10px 24px; }
.item { display:flex; gap:10px; padding:8px; border-radius:10px; cursor:pointer; align-items:center; }
.item:hover { background:#1a1c20; } .item.on { background:#1d2a44; }
.item .meta { width:86px; flex:none; font-size:13px; } .item .meta div+div { color:#999; font-size:12px; margin-top:2px; }
.item .th { flex:1; aspect-ratio:16/9; border-radius:8px; background:#1b1d21; overflow:hidden; }
.item .th img { width:100%; height:100%; object-fit:cover; display:block; }
.empty { color:#777; font-size:13px; padding:16px; }
.kind { display:inline-block; font-size:10px; padding:1px 6px; border-radius:8px; background:#2d6cdf33; color:#9cf; margin-top:4px; }
.settings { max-width:1100px; margin:0 auto; padding:8px 16px 32px; }
.card { background:#16181b; border-radius:12px; padding:14px 16px; margin:12px 0; }
.card h3 { margin:0 0 10px; font-size:15px; font-weight:500; }
.stats { display:flex; flex-wrap:wrap; gap:22px; font-size:13px; color:#aaa; }
.stats b { display:block; color:#fff; font-size:20px; font-weight:400; }
.bar2 { height:8px; background:#0f1012; border-radius:4px; overflow:hidden; margin-top:10px; }
.bar2 div { height:100%; background:#2d6cdf; }
table { width:100%; border-collapse:collapse; font-size:13px; }
th { text-align:left; color:#8a93a3; font-weight:400; padding:6px 8px; white-space:nowrap; }
td { padding:8px; border-top:1px solid #22252a; vertical-align:middle; }
td select { background:#1f2226; color:#e8e8ea; border:0; border-radius:6px; padding:5px 6px; font:inherit; }
.pin { font-family:ui-monospace,monospace; font-size:14px; letter-spacing:1px; }
.ok { color:#4ade80; } .muted { color:#888; } .err { color:#f87171; }
.small { font-size:12px; color:#888; }
.btn { padding:5px 10px; border-radius:14px; background:#23262b; font-size:12px; }
.btn:hover { background:#2d3138; }
.switch { position:relative; width:38px; height:22px; border-radius:11px; background:#3a3f47; flex:none; display:inline-block; vertical-align:middle; }
.switch::after { content:""; position:absolute; top:3px; left:3px; width:16px; height:16px; border-radius:50%; background:#fff; transition:left .15s; }
.switch.on { background:#2d6cdf; } .switch.on::after { left:19px; }
@container (max-width: 760px) {
  .settings { padding:4px 10px 24px; }
  table, tbody, tr, td { display:block; width:100%; }
  tr.head { display:none; }
  tr.cam { background:#1b1e22; border-radius:10px; margin:10px 0; padding:4px 12px; }
  td { border:0; padding:8px 0; display:flex; align-items:center; justify-content:space-between; gap:12px; }
  td.name { font-size:16px; font-weight:500; border-bottom:1px solid #2a2e34; }
  td[data-label]::before { content:attr(data-label); color:#8a93a3; }
  td.hk { flex-wrap:wrap; }
  .stats { gap:14px; } .stats b { font-size:17px; }
}
.live { position:absolute; right:12px; top:12px; background:#000a; color:#fff; border:1px solid #fff6;
  border-radius:18px; padding:6px 14px 6px 10px; font-size:13px; display:flex; align-items:center; gap:6px; }
.live:hover { background:#000d; border-color:#fff; }
.live svg { width:16px; height:16px; fill:currentColor; }
.badge { position:absolute; left:12px; top:12px; background:#f59e0b; color:#111; font-size:11px; font-weight:600;
  letter-spacing:1px; padding:3px 8px; border-radius:6px; }
.live.hidden { display:none; }
@container (max-width: 820px) {
  .single { flex-direction:column; height:auto; }
  .left { flex:none; }
  .player { flex:none; aspect-ratio:16/9; min-height:0; }
  aside { width:auto; border-left:0; border-top:1px solid #1f2125; }
  .item .th { flex:none; width:160px; }
}
`;

const ICONS = {
  menu: "M3,6H21V8H3V6M3,11H21V13H3V11M3,16H21V18H3V16Z",
  grid: "M3,11H11V3H3M3,21H11V13H3M13,21H21V13H13M13,3V11H21V3",
  single: "M4,4H20A2,2 0 0,1 22,6V18A2,2 0 0,1 20,20H4A2,2 0 0,1 2,18V6A2,2 0 0,1 4,4Z",
  mute: "M12,4L9.91,6.09L12,8.18M4.27,3L3,4.27L7.73,9H3V15H7L12,20V13.27L16.25,17.53C15.58,18.04 14.83,18.46 14,18.7V20.77C15.38,20.45 16.63,19.82 17.68,18.96L19.73,21L21,19.73L12,10.73M19,12C19,12.94 18.8,13.82 18.46,14.64L19.97,16.15C20.62,14.91 21,13.5 21,12C21,7.72 18,4.14 14,3.23V5.29C16.89,6.15 19,8.83 19,12M16.5,12C16.5,10.23 15.5,8.71 14,7.97V10.18L16.45,12.63C16.5,12.43 16.5,12.21 16.5,12Z",
  sound: "M14,3.23V5.29C16.89,6.15 19,8.83 19,12C19,15.17 16.89,17.84 14,18.7V20.77C18,19.86 21,16.28 21,12C21,7.72 18,4.14 14,3.23M16.5,12C16.5,10.23 15.5,8.71 14,7.97V16C15.5,15.29 16.5,13.76 16.5,12M3,9V15H7L12,20V4L7,9H3Z",
  full: "M5,5H10V7H7V10H5V5M14,5H19V10H17V7H14V5M17,14H19V19H14V17H17V14M10,17V19H5V14H7V17H10Z",
  prev: "M15.41,16.58L10.83,12L15.41,7.41L14,6L8,12L14,18L15.41,16.58Z",
  next: "M8.59,16.58L13.17,12L8.59,7.41L10,6L16,12L10,18L8.59,16.58Z",
  zoomin: "M19,13H13V19H11V13H5V11H11V5H13V11H19V13Z",
  zoomout: "M19,13H5V11H19V13Z",
  back: "M12,2A10,10 0 1,0 22,12A10,10 0 0,0 12,2M12,20A8,8 0 1,1 20,12A8,8 0 0,1 12,20M12,7A5,5 0 1,0 17,12A5,5 0 0,0 12,7Z",
};
const icon = (name) =>
  `<svg viewBox="0 0 24 24"><path d="${ICONS[name]}"/></svg>`;

const pad = (n) => String(n).padStart(2, "0");
const secOfDay = (s) => {
  const [h, m, x] = s.slice(11, 19).split(":").map(Number);
  return h * 3600 + m * 60 + x;
};
const toStamp = (date, sec) => {
  sec = Math.max(0, Math.min(DAY - 1, Math.floor(sec)));
  return `${date} ${pad(Math.floor(sec / 3600))}:${pad(Math.floor(sec / 60) % 60)}:${pad(sec % 60)}`;
};
const addSeconds = (stamp, s) => {
  const d = new Date(stamp.replace(" ", "T"));
  d.setSeconds(d.getSeconds() + s);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
};
const hhmm = (s) => s.slice(11, 16);
const dur = (a, b) => {
  const s = Math.max(0, (new Date(b.replace(" ", "T")) - new Date(a.replace(" ", "T"))) / 1000);
  if (s >= 3600) return `${Math.floor(s / 3600)}h${pad(Math.floor(s / 60) % 60)}m`;
  if (s >= 60) return `${Math.floor(s / 60)}m${pad(Math.round(s % 60))}s`;
  return `${Math.round(s)}s`;
};
const today = () => {
  const d = new Date();
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};
const dayLabel = (iso) => {
  if (iso === today()) return "Today";
  const d = new Date(iso + "T12:00:00");
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "numeric" });
};

/** Live view of a camera entity over HA's WebRTC API. */
class LiveStream {
  constructor(hass, entityId, video) {
    this.hass = hass;
    this.entityId = entityId;
    this.video = video;
    this.closed = false;
    this.start().catch(() => this.startHls().catch((err) => this.onError?.(err)));
  }

  async start() {
    const conn = this.hass.connection;
    const cfg = await conn.sendMessagePromise({
      type: "camera/webrtc/get_client_config",
      entity_id: this.entityId,
    });
    if (this.closed) return;
    const pc = (this.pc = new RTCPeerConnection(cfg.configuration));
    pc.addTransceiver("video", { direction: "recvonly" });
    pc.addTransceiver("audio", { direction: "recvonly" });
    const stream = new MediaStream();
    pc.ontrack = (ev) => {
      stream.addTrack(ev.track);
      if (this.video.srcObject !== stream) this.video.srcObject = stream;
      this.video.play().catch(() => {});
    };
    let sessionId = null;
    const pending = [];
    const sendCandidate = (c) =>
      conn.sendMessagePromise({
        type: "camera/webrtc/candidate",
        entity_id: this.entityId,
        session_id: sessionId,
        candidate: c,
      }).catch(() => {});
    pc.onicecandidate = (ev) => {
      if (!ev.candidate) return;
      const c = ev.candidate.toJSON();
      sessionId ? sendCandidate(c) : pending.push(c);
    };
    pc.onconnectionstatechange = () => {
      if (["failed", "closed"].includes(pc.connectionState) && !this.closed) this.restart();
    };
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    this.unsub = await conn.subscribeMessage(
      async (msg) => {
        if (msg.type === "session") {
          sessionId = msg.session_id;
          pending.splice(0).forEach(sendCandidate);
        } else if (msg.type === "answer") {
          await pc.setRemoteDescription({ type: "answer", sdp: msg.answer });
        } else if (msg.type === "candidate") {
          await pc.addIceCandidate(msg.candidate).catch(() => {});
        } else if (msg.type === "error") {
          this.startHls().catch((err) => this.onError?.(err));
        }
      },
      { type: "camera/webrtc/offer", entity_id: this.entityId, offer: offer.sdp }
    );
  }

  /** HA's own HLS stream, for cameras without WebRTC. */
  async startHls() {
    this.stop();
    const res = await this.hass.connection.sendMessagePromise({
      type: "camera/stream",
      entity_id: this.entityId,
    });
    if (this.closed) return;
    this.hlsMode = true;
    this.hls = await attachHls(this.video, res.url, { liveSyncDurationCount: 2 });
  }

  restart() {
    if (this.hlsMode) return;
    this.stop();
    this.closed = false;
    clearTimeout(this.retry);
    this.retry = setTimeout(() => !this.closed && this.start().catch(() => {}), 3000);
  }

  stop() {
    const unsub = this.unsub;
    this.unsub = null;
    Promise.resolve()
      .then(() => unsub?.())
      .catch(() => {});
    this.pc?.close();
    this.pc = null;
    this.hls?.destroy();
    this.hls = null;
  }

  close() {
    this.closed = true;
    clearTimeout(this.retry);
    this.stop();
    this.video.srcObject = null;
  }
}

let hlsLoader = null;
function loadHls(url) {
  if (window.Hls) return Promise.resolve(window.Hls);
  hlsLoader ??= new Promise((resolve, reject) => {
    const s = document.createElement("script");
    s.src = url;
    s.onload = () => resolve(window.Hls);
    s.onerror = reject;
    document.head.appendChild(s);
  });
  return hlsLoader;
}

let hlsUrl = "/xmeye_static/hls.light.min.js";

/** H.265 in fMP4 (MSE) or native HLS: then recordings are not transcoded. */
function canPlayHevc() {
  const type = 'video/mp4; codecs="hvc1.1.6.L153.B0"';
  try {
    if (window.MediaSource?.isTypeSupported(type)) return true;
  } catch (err) { /* old browser */ }
  return document.createElement("video").canPlayType(type) === "probably";
}
let logoUrl = "/xmeye_static/logo.png";

/** Play an HLS URL in a <video>; returns the hls.js instance (or null). */
async function attachHls(video, url, options = {}) {
  if (video.canPlayType("application/vnd.apple.mpegurl") && !window.MediaSource) {
    video.src = url;
    video.play().catch(() => {});
    return null;
  }
  const Hls = await loadHls(hlsUrl);
  if (!Hls.isSupported()) {
    video.src = url;
    video.play().catch(() => {});
    return null;
  }
  const hls = new Hls(options);
  hls.loadSource(url);
  hls.attachMedia(video);
  video.play().catch(() => {});
  return hls;
}

function alertBox(root, text) {
  const el = document.createElement("div");
  el.className = "card err";
  el.textContent = text;
  root.prepend(el);
  setTimeout(() => el.remove(), 6000);
}

class XMeyePanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this.cameras = [];
    this.events = [];
    this.view = "grid";
    this.current = null; // index into cameras
    this.day = null; // {date, days, recordings, events}
    this.date = today();
    this.playing = null; // {begin, end, url}
    this.muted = true;
    this.speed = 1;
    this.tab = "events";
    // grid layout: "fit" (all cameras on screen), "1" or "2" columns
    this.layout = "fit";
    try {
      this.layout = localStorage.getItem("xmeye.gridLayout") || "fit";
    } catch (err) { /* private mode */ }
    this.tl = { start: 0, span: DAY };
    this.live = new Map(); // key -> LiveStream
    this.thumbs = new Map(); // url -> objectURL
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first) this.init();
  }
  get hass() { return this._hass; }
  set narrow(v) { this._narrow = v; this.shadowRoot.querySelector(".menu")?.toggleAttribute("hidden", !v); }
  set panel(p) {
    this._panel = p;
    if (p?.config?.hls) hlsUrl = p.config.hls;
    if (p?.config?.logo) logoUrl = p.config.logo;
  }

  async init() {
    this.shadowRoot.innerHTML = `<style>${css}</style><div class="app"></div>`;
    try {
      const res = await this.hass.connection.sendMessagePromise({ type: "xmeye/cameras" });
      this.cameras = res.cameras;
    } catch (err) {
      this.cameras = [];
    }
    const params = new URLSearchParams(location.search);
    const cam = this.cameras.findIndex((c) => `${c.entry_id}-${c.channel}` === params.get("camera"));
    if (cam >= 0) this.openCamera(cam);
    else if (params.get("view") === "settings" && this.hass.user?.is_admin) this.showSettings();
    else this.showGrid();
    this.refreshEvents();
    this.eventsTimer = setInterval(() => this.refreshEvents(), 60000);
  }

  connectedCallback() {
    if (this._hass && !this.shadowRoot.querySelector(".app")) this.init();
    this.tick = setInterval(() => this.onTick(), 500);
    this.onVisibility = () => this.updateLiveForVisibility();
    document.addEventListener("visibilitychange", this.onVisibility);
  }

  disconnectedCallback() {
    clearInterval(this.tick);
    clearTimeout(this.hkTimer);
    this.resizeObserver?.disconnect();
    clearInterval(this.eventsTimer);
    document.removeEventListener("visibilitychange", this.onVisibility);
    this.closeLive();
    this.stopPlayback();
    this.shadowRoot.innerHTML = "";
  }

  updateLiveForVisibility() {
    if (document.hidden) this.closeLive();
    else if (this.view === "grid") this.showGrid();
    else if (!this.playing) this.startMainLive();
  }

  closeLive(except) {
    for (const [key, s] of this.live) {
      if (key === except) continue;
      s.close();
      this.live.delete(key);
    }
  }

  header(extra = "") {
    return `<header>
      <button class="icon menu" ${this._narrow ? "" : "hidden"}>${icon("menu")}</button>
      <img class="logo" src="${logoUrl}" alt="">
      <h1>XMeye Full NVR</h1>
      <div class="seg">
        <button data-view="grid" class="${this.view === "grid" ? "on" : ""}">Grid</button>
        <button data-view="single" class="${this.view === "single" ? "on" : ""}">Single</button>
        ${this.hass.user?.is_admin ? `<button data-view="settings" class="${this.view === "settings" ? "on" : ""}">Settings</button>` : ""}
      </div>
      <div class="spacer"></div>${extra}
    </header>`;
  }

  bindHeader(root) {
    root.querySelector(".menu")?.addEventListener("click", () =>
      this.dispatchEvent(new Event("hass-toggle-menu", { bubbles: true, composed: true }))
    );
    root.querySelectorAll("[data-view]").forEach((b) =>
      b.addEventListener("click", () => {
        if (b.dataset.view === "grid") this.showGrid();
        else if (b.dataset.view === "settings") this.showSettings();
        else this.openCamera(this.current ?? 0);
      })
    );
  }

  // ---------------------------------------------------------------- grid

  showGrid() {
    this.view = "grid";
    this.stopPlayback();
    this.closeLive();
    history.replaceState(null, "", location.pathname);
    const app = this.shadowRoot.querySelector(".app");
    app.innerHTML = `${this.header()}
      <main class="${this.layout === "fit" ? "" : "scroll"}"><div class="gridview ${this.layout === "fit" ? "" : "flow"}">
        <h2>Events</h2><div class="strip"></div>
        <div class="camhead"><h2>Cameras</h2>
          <div class="seg small-seg">${GRID_LAYOUTS.map(([v, label, title]) => `<button data-layout="${v}" title="${title}" class="${this.layout === v ? "on" : ""}">${label}</button>`).join("")}</div>
        </div>
        <div class="gridwrap"><div class="grid">${this.cameras
          .map(
            (c, i) => `<div class="tile" data-i="${i}">
              <img class="poster" alt="">
              <video muted autoplay playsinline></video>
              <div class="name">${c.name}<span class="dot off"></span></div>
            </div>`
          )
          .join("")}</div></div>
        ${this.cameras.length ? "" : `<div class="empty">No cameras. Add the XMeye Full NVR integration first.</div>`}
      </div></main>`;
    this.bindHeader(app);
    app.querySelectorAll(".tile").forEach((tile) => {
      const cam = this.cameras[tile.dataset.i];
      const poster = tile.querySelector("img");
      const pic = this.hass.states[cam.sub_entity_id || cam.entity_id]?.attributes.entity_picture;
      poster.onerror = () => poster.remove();
      if (pic) poster.src = pic;
      else poster.remove();
      tile.addEventListener("click", () => this.openCamera(Number(tile.dataset.i)));
      const video = tile.querySelector("video");
      video.addEventListener("playing", () => {
        poster.remove();
        tile.querySelector(".dot").classList.remove("off");
      });
      const entity = cam.sub_entity_id || cam.entity_id;
      if (entity && !document.hidden) this.live.set(`grid-${entity}`, new LiveStream(this.hass, entity, video));
    });
    this.renderStrip();
    app.querySelectorAll("[data-layout]").forEach((b) =>
      b.addEventListener("click", () => {
        this.layout = b.dataset.layout;
        try {
          localStorage.setItem("xmeye.gridLayout", this.layout);
        } catch (err) { /* private mode */ }
        this.showGrid();
      })
    );
    this.fitGrid();
    this.resizeObserver?.disconnect();
    this.resizeObserver = new ResizeObserver(() => this.fitGrid());
    this.resizeObserver.observe(app.querySelector(".gridwrap"));
  }

  narrowLayout() {
    return this.clientWidth < 820;
  }

  /** Largest 16:9 tiles that fit all cameras into the space without scrolling. */
  fitGrid() {
    const wrap = this.shadowRoot.querySelector(".gridwrap");
    const grid = wrap?.querySelector(".grid");
    if (!grid) return;
    const n = this.cameras.length || 1;
    const gap = this.narrowLayout() ? 6 : 10;
    grid.style.gap = `${gap}px`;
    if (this.layout !== "fit") {
      grid.style.gridTemplateColumns = `repeat(${this.layout}, minmax(0, 1fr))`;
      grid.style.width = "100%";
      return;
    }
    const W = wrap.clientWidth - (this.narrowLayout() ? 24 : 32);
    const H = wrap.clientHeight - 12;
    if (H < 80) return;
    let best = { w: 0, cols: 1 };
    for (let cols = 1; cols <= n; cols++) {
      const rows = Math.ceil(n / cols);
      const w = Math.min((W - gap * (cols - 1)) / cols, ((H - gap * (rows - 1)) / rows) * (16 / 9));
      if (w > best.w) best = { w, cols };
    }
    grid.style.gridTemplateColumns = `repeat(${best.cols}, ${Math.floor(best.w)}px)`;
    grid.style.width = "auto";
  }

  async refreshEvents() {
    try {
      const res = await this.hass.connection.sendMessagePromise({ type: "xmeye/events", hours: 24, limit: 40 });
      this.events = res.events;
    } catch (err) {
      return;
    }
    this.renderStrip();
  }

  camIndex(ev) {
    return this.cameras.findIndex((c) => c.entry_id === ev.entry_id && c.channel === ev.channel);
  }

  renderStrip() {
    const strip = this.shadowRoot.querySelector(".strip");
    if (!strip) return;
    if (!this.events.length) {
      strip.innerHTML = `<div class="empty">No motion in the last 24 hours.</div>`;
      return;
    }
    strip.innerHTML = this.events
      .map((ev, i) => {
        const cam = this.cameras[this.camIndex(ev)];
        return `<div class="ev" data-i="${i}"><div class="th"><img alt="" data-thumb="${this.thumbUrl(ev.entry_id, ev.channel, ev.begin)}"><span class="cam">${cam?.name ?? ""}</span></div>
          <div class="t">${this.fmtTime(ev.begin)}</div></div>`;
      })
      .join("");
    strip.querySelectorAll(".ev").forEach((el) =>
      el.addEventListener("click", () => {
        const ev = this.events[el.dataset.i];
        const i = this.camIndex(ev);
        if (i >= 0) this.openCamera(i, ev.begin);
      })
    );
    this.lazyThumbs(strip);
  }

  fmtTime(stamp) {
    const d = new Date(stamp.replace(" ", "T"));
    return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
  }

  thumbUrl(entryId, channel, begin) {
    return `/api/xmeye/thumb/${entryId}/${channel}/${begin.replace(/\D/g, "")}.jpg`;
  }

  lazyThumbs(root) {
    this.observer?.disconnect();
    this.observer = new IntersectionObserver(
      (entries) =>
        entries.forEach((e) => {
          if (!e.isIntersecting) return;
          this.observer.unobserve(e.target);
          this.loadThumb(e.target);
        }),
      { root: null, rootMargin: "200px" }
    );
    root.querySelectorAll("img[data-thumb]").forEach((img) => this.observer.observe(img));
  }

  async loadThumb(img) {
    const url = img.dataset.thumb;
    if (this.thumbs.has(url)) {
      img.src = this.thumbs.get(url);
      return;
    }
    try {
      const resp = await this.hass.fetchWithAuth(url);
      if (!resp.ok) return;
      const obj = URL.createObjectURL(await resp.blob());
      this.thumbs.set(url, obj);
      img.src = obj;
    } catch (err) { /* no thumbnail */ }
  }

  // ------------------------------------------------------------ settings

  async showSettings() {
    this.view = "settings";
    this.stopPlayback();
    this.closeLive();
    history.replaceState(null, "", `${location.pathname}?view=settings`);
    const app = this.shadowRoot.querySelector(".app");
    app.innerHTML = `${this.header()}<main class="scroll"><div class="settings"><div class="empty">Loading NVR settings…</div></div></main>`;
    this.bindHeader(app);
    const conn = this.hass.connection;
    const entries = [...new Set(this.cameras.map((c) => c.entry_id))];
    try {
      this.nvr = {};
      for (const id of entries) this.nvr[id] = await conn.sendMessagePromise({ type: "xmeye/nvr", entry_id: id });
      this.homekit = await conn.sendMessagePromise({ type: "xmeye/homekit" });
    } catch (err) {
      app.querySelector(".settings").innerHTML = `<div class="empty err">Could not read the NVR: ${err.message}</div>`;
      return;
    }
    this.renderSettings();
  }

  recordMode(rec) {
    if (!rec || rec.error) return "?";
    if (rec.RecordMode === "ClosedRecord") return "off";
    if (rec.RecordMode === "ManualRecord") return "manual";
    const mask = parseInt(rec.Mask?.[0]?.[0] ?? "0", 16);
    return mask & 1 ? "always" : mask & 6 ? "motion" : "off";
  }

  renderSettings() {
    const root = this.shadowRoot.querySelector(".settings");
    if (!root || this.view !== "settings") return;
    const hk = this.homekit ?? { cameras: [] };
    let html = "";
    for (const [entryId, st] of Object.entries(this.nvr)) {
      const cams = this.cameras.filter((c) => c.entry_id === entryId);
      const parts = (st.storage || []).flatMap((d) => d.Partition || []).filter((p) => parseInt(p.TotalSpace, 16) > 0);
      const total = parts.reduce((a, p) => a + parseInt(p.TotalSpace, 16), 0) / 1024;
      const free = parts.reduce((a, p) => a + parseInt(p.RemainSpace, 16), 0) / 1024;
      const oldest = parts.map((p) => p.OldStartTime).filter((t) => t && !t.startsWith("0000")).sort()[0];
      const days = oldest ? (Date.now() - new Date(oldest.replace(" ", "T"))) / 864e5 : null;
      const rates = (st.work?.ChannelState || []).map((c) => c.Bitrate || 0);
      const kbps = rates.reduce((a, b) => a + b, 0);
      const perDay = (kbps * 1000 / 8 * 86400) / 1e9;
      html += `<div class="card"><h3>${st.system?.HardWare ?? "NVR"} <span class="small">firmware ${st.system?.SoftWareVersion ?? "?"}</span></h3>
        <div class="stats">
          <div><b>${total.toFixed(0)} GB</b>disk${free < 1 ? ", full (overwriting)" : `, ${free.toFixed(0)} GB free`}</div>
          <div><b>${days ? days.toFixed(1) : "?"} days</b>of recordings (oldest ${oldest ?? "?"})</div>
          <div><b>${(kbps / 1000).toFixed(1)} Mbit/s</b>all cameras · ${perDay.toFixed(0)} GB/day</div>
        </div>
        <div class="bar2"><div style="width:${total ? (100 * (total - free)) / total : 0}%"></div></div>
      </div>
      <div class="card"><h3>Cameras</h3><table>
        <tr class="head"><th>Camera</th><th>Bitrate</th><th>Recording</th><th>Motion detection</th><th>Sensitivity</th><th>HomeKit</th></tr>
        ${cams
          .map((c) => {
            const i = c.channel - 1;
            const mode = this.recordMode(st.record?.[i]);
            const motion = st.motion?.[i] ?? {};
            const h = hk.cameras.find((x) => x.entry_id === entryId && x.channel === c.channel);
            const opt = (v, label) => `<option value="${v}" ${mode === v ? "selected" : ""}>${label}</option>`;
            return `<tr class="cam" data-entry="${entryId}" data-ch="${c.channel}">
              <td class="name">${c.name}</td>
              <td data-label="Bitrate"><span>${((rates[i] || 0) / 1000).toFixed(1)} Mbit/s <span class="small">· ${(((rates[i] || 0) * 1000 / 8 * 86400) / 1e9).toFixed(1)} GB/day</span></span></td>
              <td data-label="Recording"><select data-set="record">${mode === "manual" ? opt("manual", "Always (manual)") : ""}${opt("always", "Always")}${opt("motion", "Motion only")}${opt("off", "Off")}</select></td>
              <td data-label="Motion detection"><span class="switch ${motion.Enable ? "on" : ""}" data-set="motion_enabled" role="switch"></span></td>
              <td data-label="Sensitivity"><select data-set="motion_level">${[1, 2, 3, 4, 5, 6].map((l) => `<option ${l === motion.Level ? "selected" : ""}>${l}</option>`).join("")}</select></td>
              <td class="hk" data-label="HomeKit">${h ? `<span class="switch ${h.enabled ? "on" : ""}" data-hk="${h.key}" role="switch"></span>
                ${h.enabled ? `<div class="small">${h.paired ? `<span class="ok">Paired</span> · <button class="btn" data-hkreset="${h.key}">Unpair</button>` : `Code <span class="pin">${h.pin}</span>`}</div>` : ""}` : `<span class="muted">—</span>`}</td>
            </tr>`;
          })
          .join("")}
      </table>
      <p class="small">Recording and motion detection are written to the NVR. Recording <i>Always</i> keeps everything; <i>Motion only</i> makes the disk last much longer.</p>
      </div>`;
    }
    html += `<div class="card"><h3>HomeKit</h3><div class="small">
      ${hk.available ? (hk.running ? `<span class="ok">Running</span>` : `<span class="muted">Off</span>`) : `<span class="err">Not available</span>`}
      ${hk.error ? ` · <span class="err">${hk.error}</span>` : ""}<br>
      Turn a camera on, then in the Apple Home app choose <b>Add Accessory → More options</b>, pick the camera and enter its code.
      Video goes straight from the NVR stream (no transcoding), via a dedicated go2rtc on port ${hk.port}.</div></div>`;
    root.innerHTML = html;
    const conn = this.hass.connection;
    const reload = async () => {
      try {
        for (const id of Object.keys(this.nvr)) this.nvr[id] = await conn.sendMessagePromise({ type: "xmeye/nvr", entry_id: id });
      } catch (err) { /* keep old */ }
      this.renderSettings();
    };
    const write = async (tr, field, value) => {
      try {
        await conn.sendMessagePromise({
          type: "xmeye/settings_set", entry_id: tr.dataset.entry, channel: Number(tr.dataset.ch), [field]: value,
        });
      } catch (err) {
        alertBox(root, `Could not change the NVR: ${err.message}`);
      }
      reload();
    };
    root.querySelectorAll("select[data-set]").forEach((el) =>
      el.addEventListener("change", () => {
        const v = el.dataset.set === "motion_level" ? Number(el.value) : el.value;
        if (el.value !== "manual") write(el.closest("tr"), el.dataset.set, v);
      })
    );
    root.querySelectorAll(".switch[data-set]").forEach((el) =>
      el.addEventListener("click", () => write(el.closest("tr"), el.dataset.set, !el.classList.contains("on")))
    );
    const hkSet = async (msg) => {
      try {
        this.homekit = await conn.sendMessagePromise({ type: "xmeye/homekit_set", ...msg });
      } catch (err) {
        alertBox(root, `HomeKit: ${err.message}`);
      }
      this.renderSettings();
    };
    root.querySelectorAll("[data-hk]").forEach((el) =>
      el.addEventListener("click", () => hkSet({ key: el.dataset.hk, enabled: !el.classList.contains("on") }))
    );
    root.querySelectorAll("[data-hkreset]").forEach((el) =>
      el.addEventListener("click", () => hkSet({ key: el.dataset.hkreset, reset: true }))
    );
    clearTimeout(this.hkTimer);
    if (hk.cameras.some((c) => c.enabled && !c.paired)) {
      // pick up a new pairing without a manual refresh
      this.hkTimer = setTimeout(async () => {
        try {
          this.homekit = await conn.sendMessagePromise({ type: "xmeye/homekit" });
        } catch (err) { /* ignore */ }
        this.renderSettings();
      }, 5000);
    }
  }

  // -------------------------------------------------------------- single

  async openCamera(index, at = null) {
    if (!this.cameras.length) return;
    const changed = this.view !== "single" || this.current !== index;
    this.view = "single";
    this.current = index;
    const cam = this.cameras[index];
    history.replaceState(null, "", `${location.pathname}?camera=${cam.entry_id}-${cam.channel}`);
    if (changed) {
      this.stopPlayback();
      this.closeLive();
      this.renderSingle();
    }
    const date = at ? at.slice(0, 10) : this.date;
    await this.loadDay(date);
    if (at) this.play(at);
    else if (!this.playing) this.startMainLive();
  }

  renderSingle() {
    const cam = this.cameras[this.current];
    const app = this.shadowRoot.querySelector(".app");
    app.innerHTML = `${this.header()}
      <main><div class="single">
        <div class="left">
          <div class="chips">${this.cameras
            .map((c, i) => `<button class="chip ${i === this.current ? "on" : ""}" data-i="${i}">${c.name}</button>`)
            .join("")}</div>
          <div class="player">
            <video playsinline autoplay muted></video>
            <div class="msg"></div>
            <div class="bar">
              <span class="dot"></span>
              <div><div class="ttl">${cam.name}</div><div class="sub">Live</div></div>
              <div class="spacer"></div>
              <select class="speed" title="Playback speed">${SPEEDS.map((v) => `<option value="${v}" ${v === this.speed ? "selected" : ""}>${v}×</option>`).join("")}</select>
              <button class="icon prev" title="Previous camera">${icon("prev")}</button>
              <button class="icon next" title="Next camera">${icon("next")}</button>
              <button class="icon mute" title="Sound">${icon(this.muted ? "mute" : "sound")}</button>
              <button class="icon full" title="Fullscreen">${icon("full")}</button>
            </div>
            <span class="badge" hidden>PLAYBACK</span>
            <button class="live hidden" title="Stop playback and go back to the live view">${icon("back")}Back to live</button>
          </div>
          <div class="tl">
            <div class="tlhead">
              <button class="icon dprev" title="Previous day">${icon("prev")}</button>
              <button class="icon dnext" title="Next day">${icon("next")}</button>
              <select class="days"></select>
              <div class="spacer"></div>
              <button class="icon zout" title="Zoom out">${icon("zoomout")}</button>
              <button class="icon zin" title="Zoom in">${icon("zoomin")}</button>
            </div>
            <div class="track"><div class="hover" hidden></div><div class="hovert" hidden></div><div class="cursor" hidden></div></div>
            <div class="ticks"></div>
          </div>
        </div>
        <aside>
          <div class="tabs"><button data-tab="events" class="${this.tab === "events" ? "on" : ""}">Events</button><button data-tab="recordings" class="${this.tab === "recordings" ? "on" : ""}">Recordings</button></div>
          <div class="list"></div>
        </aside>
      </div></main>`;
    this.bindHeader(app);
    const $ = (s) => app.querySelector(s);
    this.video = $(".player video");
    this.video.muted = this.muted;
    app.querySelectorAll(".chip").forEach((b) =>
      b.addEventListener("click", () => this.openCamera(Number(b.dataset.i)))
    );
    const step = (d) => this.openCamera((this.current + d + this.cameras.length) % this.cameras.length);
    $(".prev").addEventListener("click", () => step(-1));
    $(".next").addEventListener("click", () => step(1));
    $(".mute").addEventListener("click", () => {
      this.muted = !this.muted;
      this.video.muted = this.muted;
      $(".mute").innerHTML = icon(this.muted ? "mute" : "sound");
    });
    $(".full").addEventListener("click", () => {
      const p = $(".player");
      document.fullscreenElement ? document.exitFullscreen() : p.requestFullscreen?.();
    });
    $(".live").addEventListener("click", () => {
      this.stopPlayback();
      this.loadDay(today());
      this.startMainLive();
    });
    this.video.addEventListener("ended", () => this.playNext());
    $(".dprev").addEventListener("click", () => this.shiftDay(1));
    $(".dnext").addEventListener("click", () => this.shiftDay(-1));
    $(".days").addEventListener("change", (e) => this.loadDay(e.target.value));
    $(".zin").addEventListener("click", () => this.zoom(0.5));
    $(".zout").addEventListener("click", () => this.zoom(2));
    this.bindTrack($(".track"));
    $(".speed").addEventListener("change", (e) => this.setSpeed(Number(e.target.value)));
    app.querySelectorAll("[data-tab]").forEach((b) =>
      b.addEventListener("click", () => {
        this.tab = b.dataset.tab;
        app.querySelectorAll("[data-tab]").forEach((x) => x.classList.toggle("on", x === b));
        this.renderEvents();
      })
    );
    if (this.narrowLayout()) $("main").classList.add("scroll");
  }

  setStatus(text, live) {
    const sub = this.shadowRoot.querySelector(".bar .sub");
    if (sub) sub.textContent = text;
    this.shadowRoot.querySelector(".bar .dot")?.classList.toggle("off", !live);
    this.shadowRoot.querySelector(".live")?.classList.toggle("hidden", !!live);
    const badge = this.shadowRoot.querySelector(".badge");
    if (badge) badge.hidden = !!live;
  }

  setMessage(text) {
    const el = this.shadowRoot.querySelector(".msg");
    if (el) el.textContent = text || "";
  }

  startMainLive() {
    const cam = this.cameras[this.current];
    if (!cam?.entity_id || !this.video || document.hidden) return;
    this.closeLive();
    this.setStatus("Live", true);
    this.setMessage("Connecting…");
    const onPlaying = () => this.setMessage("");
    this.video.addEventListener("playing", onPlaying, { once: true });
    const live = new LiveStream(this.hass, cam.entity_id, this.video);
    live.onError = (err) => this.setMessage(`Live view failed: ${err.message}`);
    this.live.set("main", live);
  }

  async loadDay(date) {
    const cam = this.cameras[this.current];
    this.date = date;
    try {
      this.day = await this.hass.connection.sendMessagePromise({
        type: "xmeye/day",
        entry_id: cam.entry_id,
        channel: cam.channel,
        date,
      });
    } catch (err) {
      this.day = { date, days: [], recordings: [], events: [] };
      this.setMessage(`NVR error: ${err.message}`);
    }
    if (this.cameras[this.current] !== cam) return;
    const sel = this.shadowRoot.querySelector(".days");
    if (sel) {
      sel.innerHTML = this.day.days
        .map((d) => `<option value="${d}" ${d === date ? "selected" : ""}>${dayLabel(d)}</option>`)
        .join("");
    }
    this.renderTrack();
    this.renderEvents();
  }

  shiftDay(back) {
    const days = this.day?.days ?? [];
    const i = days.indexOf(this.date);
    const next = days[i + back];
    if (next) this.loadDay(next);
  }

  /** Recording blocks of the day: touching files merged, split at full hours. */
  recordingBlocks() {
    const blocks = [];
    for (const r of this.day?.recordings ?? []) {
      const last = blocks[blocks.length - 1];
      if (last && secOfDay(r.begin) - secOfDay(last.end) <= 2 && r.begin.slice(0, 13) === last.begin.slice(0, 13)) {
        last.end = r.end;
      } else {
        blocks.push({ begin: r.begin, end: r.end, kind: r.kind });
      }
    }
    return blocks.reverse();
  }

  renderEvents() {
    const list = this.shadowRoot.querySelector(".list");
    if (!list) return;
    const cam = this.cameras[this.current];
    const recordings = this.tab === "recordings";
    const items = recordings ? this.recordingBlocks() : this.day?.events ?? [];
    list.innerHTML = items.length
      ? items
          .map(
            (ev, i) => `<div class="item" data-i="${i}">
              <div class="meta"><div>${this.fmtTime(ev.begin)}${recordings ? `–${this.fmtTime(ev.end)}` : ""}</div><div>${dur(ev.begin, ev.end)}</div>
              ${recordings && ev.kind !== "regular" ? `<span class="kind">${ev.kind}</span>` : ""}</div>
              <div class="th"><img alt="" data-thumb="${this.thumbUrl(cam.entry_id, cam.channel, ev.begin)}"></div>
            </div>`
          )
          .join("")
      : `<div class="empty">${recordings ? "No recordings" : "No motion"} on ${dayLabel(this.date)}.</div>`;
    list.querySelectorAll(".item").forEach((el) =>
      el.addEventListener("click", () => this.play(items[el.dataset.i].begin))
    );
    this.lazyThumbs(list);
  }

  // ------------------------------------------------------------ timeline

  renderTrack() {
    const track = this.shadowRoot.querySelector(".track");
    if (!track) return;
    track.querySelectorAll(".seg-r, .seg-m").forEach((e) => e.remove());
    const { start, span } = this.tl;
    const pos = (s) => ((s - start) / span) * 100;
    const add = (cls, a, b) => {
      if (b < start || a > start + span) return;
      const el = document.createElement("div");
      el.className = cls;
      el.style.left = `${pos(a)}%`;
      el.style.width = `${Math.max(0.15, pos(b) - pos(a))}%`;
      track.prepend(el);
    };
    // merge touching files so a busy day stays a few hundred divs
    const merged = [];
    for (const r of this.day?.recordings ?? []) {
      const a = secOfDay(r.begin);
      const b = r.end.slice(0, 10) === this.date ? secOfDay(r.end) : DAY;
      const last = merged[merged.length - 1];
      if (last && a - last[1] <= 2) last[1] = Math.max(last[1], b);
      else merged.push([a, b]);
    }
    merged.forEach(([a, b]) => add("seg-r", a, b));
    for (const ev of this.day?.events ?? []) {
      const a = secOfDay(ev.begin);
      const b = ev.end.slice(0, 10) === this.date ? secOfDay(ev.end) : DAY;
      add("seg-m", a, b);
    }
    const ticks = this.shadowRoot.querySelector(".ticks");
    const stepH = span > 43200 ? 3 * 3600 : span > 14400 ? 3600 : span > 3600 ? 900 : 300;
    let html = "";
    for (let t = Math.ceil(start / stepH) * stepH; t <= start + span; t += stepH) {
      html += `<span style="left:${pos(t)}%">${pad(Math.floor(t / 3600) % 24)}:${pad(Math.floor(t / 60) % 60)}</span>`;
    }
    ticks.innerHTML = html;
    this.updateCursor();
  }

  zoom(factor, center) {
    const { start, span } = this.tl;
    const c = center ?? this.cursorSec() ?? start + span / 2;
    const newSpan = Math.min(DAY, Math.max(MIN_SPAN, span * factor));
    let newStart = c - ((c - start) / span) * newSpan;
    newStart = Math.max(0, Math.min(DAY - newSpan, newStart));
    this.tl = { start: newStart, span: newSpan };
    this.renderTrack();
  }

  bindTrack(track) {
    const secAt = (x) => {
      const r = track.getBoundingClientRect();
      return this.tl.start + ((x - r.left) / r.width) * this.tl.span;
    };
    const hover = track.querySelector(".hover");
    const hovert = track.querySelector(".hovert");
    let drag = null;
    track.addEventListener("pointermove", (e) => {
      const r = track.getBoundingClientRect();
      const s = secAt(e.clientX);
      hover.hidden = hovert.hidden = false;
      hover.style.left = hovert.style.left = `${e.clientX - r.left}px`;
      hovert.textContent = toStamp(this.date, s).slice(11, 19);
      if (drag) {
        const dx = ((e.clientX - drag.x) / r.width) * this.tl.span;
        if (Math.abs(e.clientX - drag.x) > 4) drag.moved = true;
        this.tl.start = Math.max(0, Math.min(DAY - this.tl.span, drag.start - dx));
        this.renderTrack();
      }
    });
    track.addEventListener("pointerleave", () => (hover.hidden = hovert.hidden = true));
    track.addEventListener("pointerdown", (e) => {
      drag = { x: e.clientX, start: this.tl.start, moved: false };
      track.setPointerCapture(e.pointerId);
    });
    track.addEventListener("pointerup", (e) => {
      const d = drag;
      drag = null;
      if (d && !d.moved) this.play(toStamp(this.date, secAt(e.clientX)));
    });
    track.addEventListener(
      "wheel",
      (e) => {
        e.preventDefault();
        this.zoom(e.deltaY > 0 ? 1.25 : 0.8, secAt(e.clientX));
      },
      { passive: false }
    );
  }

  cursorSec() {
    const now = this.currentStamp();
    if (!now || now.slice(0, 10) !== this.date) return null;
    return secOfDay(now);
  }

  currentStamp() {
    if (this.playing && this.video) {
      // with server-side speed-up the media time line is compressed
      const factor = this.playing.speed || 1;
      return addSeconds(this.playing.begin, Math.floor((this.video.currentTime || 0) * factor));
    }
    if (this.view === "single" && this.date === today()) {
      const d = new Date();
      return toStamp(today(), d.getHours() * 3600 + d.getMinutes() * 60 + d.getSeconds());
    }
    return null;
  }

  updateCursor() {
    const cursor = this.shadowRoot.querySelector(".cursor");
    if (!cursor) return;
    const s = this.cursorSec();
    const { start, span } = this.tl;
    cursor.hidden = s == null || s < start || s > start + span;
    if (!cursor.hidden) cursor.style.left = `${((s - start) / span) * 100}%`;
  }

  onTick() {
    if (this.view !== "single") return;
    this.updateCursor();
    if (this.playing) {
      const now = this.currentStamp();
      this.setStatus(`Playback · ${now.slice(0, 10) === today() ? "" : dayLabel(now.slice(0, 10)) + " "}${now.slice(11, 19)}`, false);
      this.markActiveEvent(now);
    }
  }

  markActiveEvent(now) {
    const events = this.day?.events ?? [];
    this.shadowRoot.querySelectorAll(".item").forEach((el) => {
      const ev = events[el.dataset.i];
      el.classList.toggle("on", !!ev && ev.begin <= now && now <= ev.end);
    });
  }

  // ------------------------------------------------------------ playback

  async play(stamp) {
    const cam = this.cameras[this.current];
    this.closeLive();
    this.stopPlayback();
    this.setStatus(`Playback · ${stamp.slice(11, 19)}`, false);
    this.setMessage("Loading recording…");
    const token = (this.playToken = Symbol("play"));
    let res;
    try {
      res = await this.hass.connection.sendMessagePromise({
        type: "xmeye/play",
        entry_id: cam.entry_id,
        channel: cam.channel,
        time: stamp,
        speed: this.speed >= SERVER_SPEED ? this.speed : 1,
        hevc: canPlayHevc(),
      });
    } catch (err) {
      this.setMessage(`NVR error: ${err.message}`);
      return;
    }
    if (token !== this.playToken) return;
    if (!res) {
      this.setMessage("No recording at this time.");
      return;
    }
    if (res.begin.slice(0, 10) !== this.date) await this.loadDay(res.begin.slice(0, 10));
    this.playing = res;
    const video = this.video;
    video.srcObject = null;
    video.muted = this.muted;
    const done = () => {
      this.setMessage("");
      this.applyRate();
    };
    video.addEventListener("playing", done, { once: true });
    const hls = await attachHls(video, res.url, { startPosition: 0, manifestLoadingTimeOut: 30000 });
    if (token !== this.playToken) {
      hls?.destroy();
      return;
    }
    this.hls = hls;
    hls?.on(window.Hls.Events.ERROR, (_e, data) => {
      if (data.fatal) this.setMessage("Playback failed.");
    });
    // keep the zoomed timeline around the playback position
    const s = secOfDay(res.begin);
    if (s < this.tl.start || s > this.tl.start + this.tl.span) this.zoom(1, s);
  }

  /** Browser rate for what the server does not speed up itself. */
  applyRate() {
    if (!this.video || !this.playing) return;
    this.video.playbackRate = this.speed / (this.playing.speed || 1);
  }

  setSpeed(speed) {
    this.speed = speed;
    if (!this.playing) return;
    const serverNow = this.playing.speed || 1;
    const serverWanted = speed >= SERVER_SPEED ? speed : 1;
    if (serverNow === serverWanted) this.applyRate();
    else this.play(this.currentStamp());
  }

  playNext() {
    if (!this.playing) return;
    const next = addSeconds(this.playing.end, 1);
    if (next.slice(0, 10) !== this.playing.end.slice(0, 10)) return;
    this.play(next);
  }

  stopPlayback() {
    this.playToken = null;
    this.hls?.destroy();
    this.hls = null;
    if (this.video) {
      this.video.removeAttribute("src");
      this.video.load();
    }
    this.playing = null;
  }
}

if (!customElements.get("xmeye-panel")) customElements.define("xmeye-panel", XMeyePanel);

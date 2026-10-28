// XMeye NVR panel: live grid, single camera with recordings timeline and events.
// Plain web component, no build step. Live video uses HA's camera WebRTC
// (go2rtc); recordings are HLS sessions from the integration, played with hls.js.

const DAY = 86400;
const MIN_SPAN = 300;

const css = `
:host { display:block; height:100%; background:#0f1012; color:#e8e8ea;
  font-family: var(--paper-font-body1_-_font-family, Roboto, system-ui, sans-serif); }
* { box-sizing:border-box; }
[hidden] { display:none !important; }
button { font:inherit; color:inherit; background:none; border:0; cursor:pointer; }
.app { display:flex; flex-direction:column; height:100%; }
header { display:flex; align-items:center; gap:8px; height:56px; padding:0 12px; flex:none;
  border-bottom:1px solid #1f2125; }
header h1 { font-size:20px; font-weight:400; margin:0 8px 0 4px; letter-spacing:.3px; }
.icon { width:40px; height:40px; border-radius:50%; display:grid; place-items:center; }
.icon:hover { background:#1d1f23; }
.icon svg { width:22px; height:22px; fill:currentColor; }
.spacer { flex:1; }
.seg { display:flex; background:#1a1c20; border-radius:20px; padding:3px; }
.seg button { padding:6px 14px; border-radius:16px; font-size:13px; color:#aab; }
.seg button.on { background:#2d6cdf; color:#fff; }
main { flex:1; overflow:auto; container-type:inline-size; }
h2 { font-size:22px; font-weight:400; margin:18px 16px 10px; }
.strip { display:flex; gap:10px; overflow-x:auto; padding:0 16px 8px; scrollbar-width:thin; }
.ev { flex:none; width:140px; text-align:center; font-size:12px; color:#bbb; }
.ev .th { width:140px; height:100px; border-radius:10px; background:#1b1d21 center/cover; position:relative;
  overflow:hidden; }
.ev .th img { width:100%; height:100%; object-fit:cover; display:block; }
.ev .cam { position:absolute; left:6px; bottom:5px; font-size:11px; color:#fff;
  text-shadow:0 1px 3px #000; }
.ev div.t { margin-top:6px; }
.grid { display:grid; gap:12px; padding:0 16px 24px;
  grid-template-columns: repeat(auto-fill, minmax(min(100%, 380px), 1fr)); }
.tile { position:relative; aspect-ratio:16/9; border-radius:12px; overflow:hidden; background:#000;
  cursor:pointer; }
.tile video, .tile img.poster { position:absolute; inset:0; width:100%; height:100%; object-fit:cover; }
.tile .name { position:absolute; top:10px; right:12px; font-size:14px; font-weight:500;
  letter-spacing:.6px; text-transform:uppercase; text-shadow:0 1px 4px #000; display:flex;
  align-items:center; gap:6px; }
.dot { width:9px; height:9px; border-radius:50%; background:#e5484d; display:inline-block; }
.dot.off { background:#666; }
.single { display:flex; min-height:100%; }
.left { flex:1; display:flex; flex-direction:column; min-width:0; padding:12px; gap:10px; }
.chips { display:flex; gap:6px; overflow-x:auto; flex:none; scrollbar-width:none; }
.chip { padding:6px 12px; border-radius:16px; background:#1a1c20; font-size:13px; white-space:nowrap; }
.chip.on { background:#2d6cdf; color:#fff; }
.player { position:relative; flex:none; width:100%; aspect-ratio:16/9;
  max-height:calc(100vh - 230px); background:#000; border-radius:12px; overflow:hidden; }
.player:fullscreen { max-height:none; border-radius:0; }
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
aside { width:340px; flex:none; border-left:1px solid #1f2125; display:flex; flex-direction:column;
  height:calc(100vh - 56px); position:sticky; top:0; }
aside .head { padding:14px 16px 8px; font-size:13px; letter-spacing:1px; color:#9ab; text-transform:uppercase; }
.list { flex:1; overflow-y:auto; padding:0 10px 80px; }
.item { display:flex; gap:10px; padding:8px; border-radius:10px; cursor:pointer; align-items:center; }
.item:hover { background:#1a1c20; } .item.on { background:#1d2a44; }
.item .meta { width:86px; flex:none; font-size:13px; } .item .meta div+div { color:#999; font-size:12px; margin-top:2px; }
.item .th { flex:1; aspect-ratio:16/9; border-radius:8px; background:#1b1d21; overflow:hidden; }
.item .th img { width:100%; height:100%; object-fit:cover; display:block; }
.empty { color:#777; font-size:13px; padding:16px; }
.live { position:absolute; right:12px; top:12px; background:#fff; color:#d33; border-radius:20px;
  padding:8px 16px; font-weight:500; box-shadow:0 2px 8px #0008; }
.live.hidden { display:none; }
@container (max-width: 820px) {
  .single { flex-direction:column; }
  .player { max-height:none; }
  aside { width:auto; height:auto; position:static; border-left:0; border-top:1px solid #1f2125; }
  .list { padding-bottom:16px; }
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
      <h1>NVR</h1>
      <div class="seg">
        <button data-view="grid" class="${this.view === "grid" ? "on" : ""}">Grid</button>
        <button data-view="single" class="${this.view === "single" ? "on" : ""}">Single</button>
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
      <main>
        <h2>Events</h2><div class="strip"></div>
        <h2>Cameras</h2>
        <div class="grid">${this.cameras
          .map(
            (c, i) => `<div class="tile" data-i="${i}">
              <img class="poster" alt="">
              <video muted autoplay playsinline></video>
              <div class="name">${c.name}<span class="dot off"></span></div>
            </div>`
          )
          .join("")}</div>
        ${this.cameras.length ? "" : `<div class="empty">No cameras. Add the XMeye NVR integration first.</div>`}
      </main>`;
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
              <button class="icon prev" title="Previous camera">${icon("prev")}</button>
              <button class="icon next" title="Next camera">${icon("next")}</button>
              <button class="icon mute" title="Sound">${icon(this.muted ? "mute" : "sound")}</button>
              <button class="icon full" title="Fullscreen">${icon("full")}</button>
            </div>
            <button class="live hidden">● Live</button>
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
        <aside><div class="head">Events</div><div class="list"></div></aside>
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
  }

  setStatus(text, live) {
    const sub = this.shadowRoot.querySelector(".bar .sub");
    if (sub) sub.textContent = text;
    this.shadowRoot.querySelector(".bar .dot")?.classList.toggle("off", !live);
    this.shadowRoot.querySelector(".live")?.classList.toggle("hidden", !!live);
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

  renderEvents() {
    const list = this.shadowRoot.querySelector(".list");
    if (!list) return;
    const cam = this.cameras[this.current];
    const events = this.day?.events ?? [];
    list.innerHTML = events.length
      ? events
          .map(
            (ev, i) => `<div class="item" data-i="${i}">
              <div class="meta"><div>${this.fmtTime(ev.begin)}</div><div>${dur(ev.begin, ev.end)}</div></div>
              <div class="th"><img alt="" data-thumb="${this.thumbUrl(cam.entry_id, cam.channel, ev.begin)}"></div>
            </div>`
          )
          .join("")
      : `<div class="empty">No motion on ${dayLabel(this.date)}.</div>`;
    list.querySelectorAll(".item").forEach((el) =>
      el.addEventListener("click", () => this.play(events[el.dataset.i].begin))
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
      return addSeconds(this.playing.begin, Math.floor(this.video.currentTime || 0));
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
    const done = () => this.setMessage("");
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

customElements.define("xmeye-panel", XMeyePanel);

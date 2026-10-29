// NVR settings: the NVR's own configuration, section by section, so the XMeye /
// VMS apps are not needed. Loaded by xmeye-panel.js when Settings opens.
// Stored passwords arrive as SECRET; sending SECRET back keeps them.

const SECRET = "\u2022".repeat(8);
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

export const TABS = [
  ["overview", "Overview"],
  ["cameras", "Cameras"],
  ["recording", "Recording"],
  ["detection", "Detection"],
  ["storage", "Storage"],
  ["network", "Network"],
  ["system", "System"],
  ["users", "Users"],
  ["advanced", "Advanced"],
];

// configs the Advanced tab offers (per-channel ones get .[n])
const KNOWN = [
  "General.General", "General.Location", "General.AutoMaintain", "System.TimeZone",
  "NetWork.NetCommon", "NetWork.NetDHCP", "NetWork.NetDNS", "NetWork.NetNTP", "NetWork.Upnp", "NetWork.RTSP",
  "NetWork.Nat", "NetWork.PMS", "NetWork.NetEmail", "NetWork.NetFTP", "NetWork.NetDDNS", "NetWork.NetIPFilter",
  "NetWork.OnlineUpgrade", "NetWork.DigManagerShow", "NetWork.IPAdaptive", "NetWork.ChnStatus",
  "NetWork.RemoteDeviceV3.[n]", "AVEnc.VideoWidget.[n]", "Camera.Param.[n]", "Record.[n]", "ExtRecord.[n]",
  "Detect.MotionDetect.[n]", "Detect.FaceDetection.[n]", "Detect.CarShapeDetection.[n]", "Detect.BlindDetect.[n]",
  "Detect.LossDetect.[n]", "Alarm.IPCAlarm.[n]", "Storage.StorageNotExist", "Storage.StorageFailure",
  "Storage.StorageLowSpace", "fVideo.Volume.[n]", "fVideo.GUISet", "fVideo.Tour", "Snap",
];

export const CSS = `
.snav { display:flex; gap:4px; overflow-x:auto; padding:4px 0 2px; scrollbar-width:none; }
.snav button { padding:7px 13px; border-radius:16px; font-size:13px; color:#aab; white-space:nowrap; }
.snav button.on { background:#2d6cdf; color:#fff; }
.snav button:hover:not(.on) { background:#1d1f23; }
.spane .card h3 { display:flex; align-items:center; gap:8px; }
.spane .card h3 .small { font-weight:400; }
.chips { display:flex; flex-wrap:wrap; gap:6px; margin:8px 0 4px; }
.chips button { padding:5px 11px; border-radius:14px; background:#1d2024; font-size:12px; color:#ccd; }
.chips button.on { background:#2d6cdf; color:#fff; }
.chips button .off { color:#f87171; }
.form { display:grid; grid-template-columns:repeat(auto-fill, minmax(190px, 1fr)); gap:12px 16px; }
.form label { display:flex; flex-direction:column; gap:4px; font-size:12px; color:#9a9ca6; }
.form label.check { flex-direction:row; align-items:center; gap:8px; font-size:13px; color:#e8e8ea; }
.form label .hint { font-size:11px; color:#777; }
.spane input[type=text], .spane input[type=password], .spane input[type=number], .spane select, .spane textarea {
  font:inherit; font-size:13px; color:#e8e8ea; background:#0f1114; border:1px solid #30333b; border-radius:8px;
  padding:6px 8px; width:100%; min-width:0; }
.spane input[type=checkbox] { width:17px; height:17px; accent-color:#2d6cdf; margin:0; }
.spane input[type=range] { width:100%; accent-color:#2d6cdf; }
.spane input:focus, .spane select:focus, .spane textarea:focus { outline:2px solid #2d6cdf; outline-offset:-1px; }
.spane textarea { font-family:ui-monospace,monospace; font-size:12px; min-height:320px; }
.actions { display:flex; align-items:center; gap:10px; flex-wrap:wrap; margin-top:14px; }
.actions .note { font-size:12px; }
.primary { padding:6px 16px; border-radius:16px; background:#2d6cdf; color:#fff; font-size:13px; }
.primary:hover { background:#3b78e7; }
.primary:disabled, .danger:disabled, .btn:disabled { opacity:.5; cursor:default; }
.danger { padding:6px 16px; border-radius:16px; background:#7f1d1d; color:#fff; font-size:13px; }
.danger:hover { background:#991b1b; }
.kv { display:grid; grid-template-columns:max-content 1fr; gap:4px 16px; font-size:13px; }
.kv span:nth-child(odd) { color:#888; }
.sched { width:100%; font-size:12px; border-collapse:collapse; }
.sched td { padding:4px 4px; border-bottom:1px solid #202328; vertical-align:middle; }
.sched td.day { width:44px; color:#aab; }
.sched .slot { display:flex; align-items:center; gap:6px; flex-wrap:wrap; padding:2px 0; }
.sched .slot input[type=time] { font:inherit; font-size:12px; color:#e8e8ea; background:#0f1114; border:1px solid #30333b;
  border-radius:6px; padding:2px 4px; color-scheme:dark; }
.sched .slot label { display:flex; align-items:center; gap:3px; color:#aab; }
.sched .slot.hidden { display:none; }
.users td, .users th { text-align:left; padding:6px; border-bottom:1px solid #202328; font-size:13px; }
.users th { color:#888; font-weight:500; font-size:12px; }
.modal { position:fixed; inset:0; background:rgba(0,0,0,.6); display:grid; place-items:center; z-index:50; padding:16px; }
.modal .box { background:#17191d; border:1px solid #2a2d33; border-radius:14px; padding:18px; width:min(460px, 100%);
  max-height:90vh; overflow:auto; }
.modal h3 { margin:0 0 10px; font-size:16px; font-weight:500; }
.modal p { font-size:13px; color:#bbb; margin:0 0 12px; }
.rights { display:grid; grid-template-columns:repeat(auto-fill, minmax(170px, 1fr)); gap:4px 10px; font-size:12px; }
.rights label { display:flex; gap:6px; align-items:center; }
`;

const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`);
const clone = (v) => JSON.parse(JSON.stringify(v));

/** NVR addresses are little-endian hex: 0x6401A8C0 = 192.168.1.100 */
export function hexToIp(hex) {
  const n = parseInt(hex, 16) >>> 0;
  return [0, 8, 16, 24].map((s) => (n >>> s) & 255).join(".");
}

export function ipToHex(ip) {
  const p = String(ip).trim().split(".");
  if (p.length !== 4 || p.some((x) => !/^\d{1,3}$/.test(x) || Number(x) > 255)) throw new Error(`"${ip}" is not an IPv4 address`);
  const n = (Number(p[0]) | (Number(p[1]) << 8) | (Number(p[2]) << 16) | (Number(p[3]) << 24)) >>> 0;
  return `0x${n.toString(16).toUpperCase().padStart(8, "0")}`;
}

const hexNum = (v) => parseInt(v ?? "0", 16) || 0;
const toHex = (n) => `0x${(n >>> 0).toString(16).toUpperCase().padStart(8, "0")}`;

function getPath(obj, path) {
  return path.split(".").reduce((o, k) => (o == null ? undefined : o[k]), obj);
}

function setPath(obj, path, value) {
  const keys = path.split(".");
  let o = obj;
  for (const k of keys.slice(0, -1)) o = o[k];
  o[keys.at(-1)] = value;
}

// --- form fields -------------------------------------------------------------
// {path, label, type, options, min, max, hint}
// types: text, int, bool, select, password, ip (hex), hexbool, hexselect, list, range

const F = (path, label, type = "text", extra = {}) => ({ path, label, type, ...extra });

function fieldHtml(f, obj) {
  const v = getPath(obj, f.path);
  if (v === undefined) return "";
  const attrs = `data-path="${esc(f.path)}" data-type="${f.type}"`;
  const hint = f.hint ? `<span class="hint">${esc(f.hint)}</span>` : "";
  switch (f.type) {
    case "bool":
    case "hexbool": {
      const on = f.type === "bool" ? !!v : hexNum(v) !== 0;
      return `<label class="check"><input type="checkbox" ${attrs} ${on ? "checked" : ""}>${esc(f.label)}${hint}</label>`;
    }
    case "select":
    case "hexselect": {
      const cur = f.type === "hexselect" ? hexNum(v) : v;
      const opts = f.options.some(([o]) => String(o) === String(cur)) ? f.options : [[cur, String(cur)], ...f.options];
      return `<label>${esc(f.label)}<select ${attrs}>${opts
        .map(([o, l]) => `<option value="${esc(o)}" ${String(o) === String(cur) ? "selected" : ""}>${esc(l)}</option>`)
        .join("")}</select>${hint}</label>`;
    }
    case "int":
      return `<label>${esc(f.label)}<input type="number" ${attrs} value="${esc(v)}" ${f.min != null ? `min="${f.min}"` : ""} ${f.max != null ? `max="${f.max}"` : ""}>${hint}</label>`;
    case "range":
      return `<label>${esc(f.label)} <output>${esc(v)}</output><input type="range" ${attrs} value="${esc(v)}" min="${f.min ?? 0}" max="${f.max ?? 100}" oninput="this.previousElementSibling.value=this.value">${hint}</label>`;
    case "ip":
      return `<label>${esc(f.label)}<input type="text" ${attrs} value="${esc(hexToIp(v))}" inputmode="decimal">${hint}</label>`;
    case "password":
      return `<label>${esc(f.label)}<input type="password" ${attrs} value="${esc(v)}" autocomplete="new-password">${hint}</label>`;
    case "list":
      return `<label>${esc(f.label)}<input type="text" ${attrs} value="${esc((v || []).filter((x) => x).join(", "))}">${hint}</label>`;
    default:
      return `<label>${esc(f.label)}<input type="text" ${attrs} value="${esc(v)}">${hint}</label>`;
  }
}

function formHtml(fields, obj) {
  return `<div class="form">${fields.map((f) => fieldHtml(f, obj)).join("")}</div>`;
}

/** A copy of `obj` with the values of the inputs in `root`. Throws on bad input. */
function collect(root, obj) {
  const out = clone(obj);
  root.querySelectorAll("[data-path]").forEach((el) => {
    const path = el.dataset.path;
    const old = getPath(out, path);
    let v;
    switch (el.dataset.type) {
      case "bool": v = el.checked; break;
      case "hexbool": v = el.checked ? "0x00000001" : "0x00000000"; break;
      case "hexselect": v = toHex(Number(el.value)); break;
      case "select": v = typeof old === "number" ? Number(el.value) : el.value; break;
      case "int":
      case "range":
        v = Number(el.value);
        if (!Number.isFinite(v)) throw new Error(`${path}: not a number`);
        break;
      case "ip": v = ipToHex(el.value); break;
      case "list": {
        const items = el.value.split(",").map((s) => s.trim()).filter((s) => s);
        v = Array.isArray(old) ? old.map((_, i) => items[i] ?? "") : items;
        break;
      }
      default: v = el.value;
    }
    setPath(out, path, v);
  });
  return out;
}

const OFF_ON = [[0, "Off"], [1, "On"]];
const HOURS = Array.from({ length: 24 }, (_, h) => [h, `${String(h).padStart(2, "0")}:00`]);

// --- the settings ------------------------------------------------------------

export class NvrSettings {
  constructor(panel, pane, entryId) {
    this.panel = panel;
    this.pane = pane;
    this.entry = entryId;
    this.channel = 0;
    this.savers = {};
  }

  get conn() {
    return this.panel.hass.connection;
  }

  call(type, extra = {}) {
    return this.conn.sendMessagePromise({ type: `xmeye/${type}`, entry_id: this.entry, ...extra });
  }

  config(...names) {
    return this.call("config", { names });
  }

  async show(tab) {
    this.tab = tab;
    this.savers = {};
    this.pane.innerHTML = `<div class="empty">Loading…</div>`;
    try {
      await this[`tab_${tab}`]();
    } catch (err) {
      this.pane.innerHTML = `<div class="card err">Could not read the NVR: ${esc(err.message)}</div>`;
    }
  }

  // a card with a form and a Save button bound to `save`
  card(title, body, { save, saveLabel = "Save", hint = "", extra = "" } = {}) {
    const id = save ? `s${Object.keys(this.savers).length}` : "";
    if (save) this.savers[id] = save;
    return `<div class="card" ${id ? `data-card="${id}"` : ""}><h3>${title}</h3>${body}
      ${hint ? `<p class="small">${hint}</p>` : ""}
      ${save || extra ? `<div class="actions">${save ? `<button class="primary" data-save="${id}">${saveLabel}</button>` : ""}${extra}<span class="note"></span></div>` : ""}
    </div>`;
  }

  render(html) {
    this.pane.innerHTML = html;
    this.pane.querySelectorAll("[data-save]").forEach((btn) =>
      btn.addEventListener("click", () => this.run(btn, () => this.savers[btn.dataset.save](btn.closest(".card"))))
    );
  }

  // run an action with the button busy and a note next to it
  async run(btn, action, done = "Saved") {
    const note = btn.closest(".actions")?.querySelector(".note");
    btn.disabled = true;
    if (note) note.textContent = "";
    try {
      const msg = await action();
      if (note) {
        note.className = "note ok";
        note.textContent = typeof msg === "string" ? msg : done;
      }
    } catch (err) {
      if (note) {
        note.className = "note err";
        note.textContent = err.message;
      } else {
        alert(err.message);
      }
    } finally {
      btn.disabled = false;
    }
  }

  async setConfig(name, card, value) {
    return this.call("config_set", { name, value: card ? collect(card, value) : value });
  }

  /** A dialog: resolves to the form's values (or true), or null when cancelled. */
  dialog({ title, text = "", body = "", ok = "OK", danger = false, typed = null }) {
    return new Promise((resolve) => {
      const el = document.createElement("div");
      el.className = "modal";
      el.innerHTML = `<form class="box"><h3>${esc(title)}</h3>${text ? `<p>${text}</p>` : ""}${body}
        ${typed ? `<label class="small">Type <b>${esc(typed)}</b> to confirm<input type="text" name="__typed" autocomplete="off"></label>` : ""}
        <div class="actions"><button type="submit" class="${danger ? "danger" : "primary"}">${esc(ok)}</button>
        <button type="button" class="btn" data-cancel>Cancel</button><span class="note err"></span></div></form>`;
      const form = el.querySelector("form");
      const close = (v) => {
        el.remove();
        resolve(v);
      };
      el.querySelector("[data-cancel]").onclick = () => close(null);
      el.addEventListener("click", (ev) => ev.target === el && close(null));
      form.onsubmit = (ev) => {
        ev.preventDefault();
        const data = Object.fromEntries(new FormData(form));
        if (typed && data.__typed !== typed) {
          el.querySelector(".note").textContent = `Type ${typed} exactly.`;
          return;
        }
        delete data.__typed;
        close(Object.keys(data).length ? data : true);
      };
      this.panel.shadowRoot.append(el);
      el.querySelector("input, select, button")?.focus();
    });
  }

  // camera chips for the per-camera tabs
  async channels() {
    if (!this._channels) {
      const [titles, cfg] = await Promise.all([
        this.call("query", { msg: 1048, name: "ChannelTitle" }),
        this.config("NetWork.ChnStatus"),
      ]);
      const status = cfg["NetWork.ChnStatus"] || [];
      const names = titles.ChannelTitle || [];
      this._channels = names.map((t, i) => ({
        index: i,
        title: String(t).trim(),
        status: status[i]?.Status ?? "?",
        res: status[i]?.CurRes ?? "",
      }));
    }
    return this._channels;
  }

  chipsHtml(chs) {
    return `<div class="chips">${chs
      .map((c) => `<button data-ch="${c.index}" class="${c.index === this.channel ? "on" : ""}">${c.index + 1}. ${esc(c.title || `Channel ${c.index + 1}`)}${c.status === "Connected" ? "" : ` <span class="off">●</span>`}</button>`)
      .join("")}</div>`;
  }

  bindChips() {
    this.pane.querySelectorAll(".chips [data-ch]").forEach((b) =>
      b.addEventListener("click", () => {
        this.channel = Number(b.dataset.ch);
        this.show(this.tab);
      })
    );
  }

  // ------------------------------------------------------------- cameras

  async tab_cameras() {
    const chs = await this.channels();
    const i = this.channel;
    const ch = chs[i];
    const names = [`NetWork.RemoteDeviceV3.[${i}]`, `AVEnc.VideoWidget.[${i}]`, `Camera.Param.[${i}]`, `fVideo.Volume.[${i}]`];
    const cfg = await this.config(...names);
    const [remote, widget, image, volume] = names.map((n) => cfg[n]);
    let html = this.chipsHtml(chs);

    html += this.card(
      `Name <span class="small">${esc(ch.status)}${ch.res ? ` · ${esc(ch.res)}` : ""}</span>`,
      `<div class="form"><label>Name on the NVR<input type="text" data-title value="${esc(ch.title)}" maxlength="31"></label></div>`,
      {
        save: async (card) => {
          const name = card.querySelector("[data-title]").value;
          await this.call("titles_set", { titles: { [i + 1]: name } });
          this._channels = null;
          return "Saved. The app shows the new name after a reload.";
        },
        hint: "Shown on the NVR's screen and in the XMeye app. In this panel a name set in the integration's options wins.",
      }
    );

    if (remote && !remote.error) {
      const dec = remote.Decoder?.[0];
      const fields = [
        F("Enable", "Channel on", "bool"),
        ...(dec
          ? [
              F("Decoder.0.IPAddress", "Camera IP address"),
              F("Decoder.0.Port", "Port", "int", { min: 1, max: 65535 }),
              F("Decoder.0.Protocol", "Protocol", "select", { options: [["ONVIF", "ONVIF"], ["NETIP", "NETIP (Xiongmai)"], ["RTSP", "RTSP"]] }),
              F("Decoder.0.UserName", "User"),
              F("Decoder.0.PassWord", "Password", "password", { hint: "•••• keeps the current one" }),
              F("Decoder.0.StreamType", "Stream", "select", { options: [["MAIN", "Main"], ["SUB", "Sub"]] }),
            ]
          : []),
      ];
      html += this.card("Camera connection", formHtml(fields, remote), {
        save: async (card) => {
          await this.setConfig(`NetWork.RemoteDeviceV3.[${i}]`, card, remote);
          this._channels = null;
        },
        hint: "Where the NVR gets this channel's video from. Changing the IP address or login reconnects the camera.",
      });
    }

    if (widget && !widget.error) {
      const fields = [
        F("ChannelTitleAttribute.EncodeBlend", "Name in the recording", "bool"),
        F("TimeTitleAttribute.EncodeBlend", "Time in the recording", "bool"),
        F("ChannelTitleAttribute.PreviewBlend", "Name on the NVR screen", "bool"),
        F("TimeTitleAttribute.PreviewBlend", "Time on the NVR screen", "bool"),
      ];
      html += this.card("Overlay", formHtml(fields, widget), {
        save: (card) => this.setConfig(`AVEnc.VideoWidget.[${i}]`, card, widget),
      });
    }

    if (image && !image.error) {
      const fields = [
        F("DayNightColor", "Day / night", "hexselect", { options: [[0, "Colour"], [1, "Auto"], [2, "Black and white"]] }),
        F("PictureFlip", "Flip vertically", "hexbool"),
        F("PictureMirror", "Mirror", "hexbool"),
        F("BLCMode", "Backlight compensation", "hexbool"),
        F("RejectFlicker", "Anti-flicker", "hexbool"),
        F("Day_nfLevel", "Noise reduction (day)", "int", { min: 0, max: 5 }),
        F("Night_nfLevel", "Noise reduction (night)", "int", { min: 0, max: 5 }),
        F("AeSensitivity", "Exposure sensitivity", "int", { min: 0, max: 10 }),
      ];
      html += this.card("Image", formHtml(fields, image), {
        save: (card) => this.setConfig(`Camera.Param.[${i}]`, card, image),
        hint: "Passed to the camera. Not every IP camera takes these from the NVR.",
      });
    }

    if (volume && !volume.error) {
      html += this.card("Sound", formHtml([F("LeftVolume", "Volume", "range", { min: 0, max: 100 })], volume), {
        save: (card) => {
          const v = collect(card, volume);
          v.RightVolume = v.LeftVolume;
          return this.setConfig(`fVideo.Volume.[${i}]`, null, v);
        },
      });
    }
    this.render(html);
    this.bindChips();
  }

  // ----------------------------------------------------------- recording

  schedHtml(rec) {
    const rows = DAYS.map((d, day) => {
      const slots = (rec.TimeSection?.[day] || []).map((sec, s) => {
        const m = /^(\d) (\d\d:\d\d):\d\d-(\d\d:\d\d):\d\d$/.exec(sec) || [null, "0", "00:00", "24:00"];
        const on = m[1] === "1";
        const mask = hexNum(rec.Mask?.[day]?.[s]);
        const end = m[3] === "24:00" ? "23:59" : m[3];
        const kind = (bit, label) => `<label><input type="checkbox" data-bit="${bit}" ${mask & bit ? "checked" : ""}>${label}</label>`;
        return `<div class="slot ${on || s === 0 ? "" : "hidden"}" data-day="${day}" data-slot="${s}">
          <label><input type="checkbox" data-on ${on ? "checked" : ""}></label>
          <input type="time" data-from value="${m[2]}"> – <input type="time" data-to value="${end}">
          ${kind(1, "Regular")}${kind(2, "Motion")}${kind(4, "Alarm")}</div>`;
      });
      return `<tr><td class="day">${d}</td><td>${slots.join("")}
        <button class="btn" data-more="${day}">+ period</button></td></tr>`;
    });
    return `<table class="sched">${rows.join("")}</table>`;
  }

  collectSched(card, rec) {
    const out = clone(rec);
    card.querySelectorAll(".slot").forEach((el) => {
      const day = Number(el.dataset.day);
      const s = Number(el.dataset.slot);
      const on = el.querySelector("[data-on]").checked;
      const from = el.querySelector("[data-from]").value || "00:00";
      let to = el.querySelector("[data-to]").value || "23:59";
      if (to === "23:59") to = "24:00";
      if (on && from >= to) throw new Error(`${DAYS[day]}: the period ends before it starts`);
      let mask = 0;
      el.querySelectorAll("[data-bit]").forEach((b) => b.checked && (mask |= Number(b.dataset.bit)));
      out.TimeSection[day][s] = `${on ? 1 : 0} ${from}:00-${to}:00`;
      out.Mask[day][s] = toHex(on ? mask : 0);
    });
    return out;
  }

  async tab_recording() {
    const chs = await this.channels();
    const i = this.channel;
    const name = `Record.[${i}]`;
    const rec = (await this.config(name))[name];
    if (rec.error) throw new Error(rec.error);
    const fields = [
      F("RecordMode", "Recording", "select", { options: [["ConfigRecord", "By schedule"], ["ManualRecord", "Always (manual)"], ["ClosedRecord", "Off"]] }),
      F("PreRecord", "Pre-record (s)", "int", { min: 0, max: 30, hint: "Kept from before an event" }),
      F("PacketLength", "File length (min)", "int", { min: 1, max: 120 }),
      F("Redundancy", "Redundant copy", "bool"),
    ];
    const preset = (label, mask) => `<button class="btn" data-preset="${mask}">${label}</button>`;
    let html = this.chipsHtml(chs);
    html += this.card(
      `Recording · ${esc(chs[i]?.title || `Channel ${i + 1}`)}`,
      `${formHtml(fields, rec)}<h3 style="margin-top:16px">Weekly schedule</h3>
       <div class="actions" style="margin:0 0 8px">${preset("Always, 24/7", 7)}${preset("Motion only, 24/7", 6)}${preset("Nothing", 0)}</div>
       ${this.schedHtml(rec)}`,
      {
        save: async (card) => this.setConfig(name, null, this.collectSched(card, collect(card.querySelector(".form"), rec))),
        extra: `<button class="btn" data-copy>Copy to all cameras</button>`,
        hint: "<i>Regular</i> records all the time in that period, <i>Motion</i> and <i>Alarm</i> only on those events. Motion only makes the disk last much longer.",
      }
    );
    this.render(html);
    this.bindChips();
    const card = this.pane.querySelector("[data-card]");
    card.querySelectorAll("[data-more]").forEach((b) =>
      b.addEventListener("click", () => {
        const next = card.querySelector(`.slot.hidden[data-day="${b.dataset.more}"]`);
        if (next) {
          next.classList.remove("hidden");
          next.querySelector("[data-on]").checked = true;
        }
      })
    );
    card.querySelectorAll("[data-preset]").forEach((b) =>
      b.addEventListener("click", () => {
        const mask = Number(b.dataset.preset);
        card.querySelector('[data-path="RecordMode"]').value = mask ? "ConfigRecord" : "ClosedRecord";
        card.querySelectorAll(".slot").forEach((el) => {
          const first = el.dataset.slot === "0";
          el.classList.toggle("hidden", !first);
          el.querySelector("[data-on]").checked = first && !!mask;
          el.querySelector("[data-from]").value = "00:00";
          el.querySelector("[data-to]").value = "23:59";
          el.querySelectorAll("[data-bit]").forEach((x) => (x.checked = first && !!(mask & Number(x.dataset.bit))));
        });
      })
    );
    const copy = card.querySelector("[data-copy]");
    copy.addEventListener("click", () =>
      this.run(copy, async () => {
        const value = this.collectSched(card, collect(card.querySelector(".form"), rec));
        const targets = chs.filter((c) => c.index !== i && c.status !== "NoConfig");
        if (!(await this.dialog({ title: "Copy to all cameras", text: `Use this recording setup for ${targets.length} other cameras?`, ok: "Copy" }))) return "";
        for (const c of targets) {
          const n = `Record.[${c.index}]`;
          const cur = (await this.config(n))[n];
          await this.setConfig(n, null, { ...cur, ...value });
        }
        return `Copied to ${targets.length} cameras`;
      })
    );
  }

  // ----------------------------------------------------------- detection

  async tab_detection() {
    const chs = await this.channels();
    const i = this.channel;
    const kinds = [
      ["Detect.MotionDetect", "Motion", "Movement in the picture, detected by the NVR."],
      ["Alarm.IPCAlarm", "Camera alarms", "Alarms the camera detects itself, e.g. its own person detection."],
      ["Detect.FaceDetection", "Faces", ""],
      ["Detect.CarShapeDetection", "Vehicles", ""],
      ["Detect.BlindDetect", "Camera covered", "The picture is blocked or covered."],
      ["Detect.LossDetect", "Video loss", "The camera stops sending video."],
    ];
    const names = kinds.map(([n]) => `${n}.[${i}]`);
    const cfg = await this.config(...names);
    let html = this.chipsHtml(chs);
    kinds.forEach(([base, title, hint], k) => {
      const name = names[k];
      const v = cfg[name];
      if (!v || v.error) return;
      const fields = [
        F("Enable", "On", "bool"),
        F("Level", "Sensitivity", "select", { options: [[1, "1 (lowest)"], [2, "2"], [3, "3"], [4, "4"], [5, "5"], [6, "6 (highest)"]] }),
        F("EventHandler.RecordEnable", "Record", "bool"),
        F("EventHandler.RecordLatch", "Keep recording (s)", "int", { min: 10, max: 300 }),
        F("EventHandler.MessageEnable", "Push to the XMeye app", "bool"),
        F("EventHandler.MailEnable", "E-mail", "bool"),
        F("EventHandler.SnapEnable", "Snapshot", "bool"),
        F("EventHandler.BeepEnable", "Beep on the NVR", "bool"),
        F("EventHandler.EventLatch", "Wait between alarms (s)", "int", { min: 0, max: 600 }),
      ];
      html += this.card(title, formHtml(fields, v), { save: (card) => this.setConfig(name, card, v), hint: esc(hint) });
    });
    html += `<p class="small">Motion areas and per-event schedules: Advanced → Detect.MotionDetect.[${i}].</p>`;
    this.render(html);
    this.bindChips();
  }

  // ------------------------------------------------------------- storage

  async tab_storage() {
    const [info, cfg] = await Promise.all([
      this.call("query", { msg: 1020, name: "StorageInfo" }),
      this.config("General.General", "General.AutoMaintain", "Storage.StorageLowSpace", "Storage.StorageNotExist", "Storage.StorageFailure"),
    ]);
    const disks = info.StorageInfo || [];
    let html = "";
    let rows = "";
    disks.forEach((disk, d) => {
      (disk.Partition || []).forEach((p, n) => {
        const total = hexNum(p.TotalSpace) / 1024;
        if (!total) return;
        const free = hexNum(p.RemainSpace) / 1024;
        rows += `<tr><td>Disk ${d + 1}${disk.Partition.length > 1 ? ` · part ${n + 1}` : ""}</td>
          <td>${total.toFixed(0)} GB, ${free.toFixed(0)} GB free</td>
          <td>${p.Status === 0 ? `<span class="ok">OK</span>` : `<span class="err">status ${esc(p.Status)}</span>`}</td>
          <td class="small">${esc(p.OldStartTime)} – ${esc(p.NewEndTime)}</td>
          <td><button class="danger" data-format="${d}:${n}">Format</button></td></tr>`;
      });
    });
    html += this.card("Disks", rows ? `<table class="users"><tr><th>Disk</th><th>Size</th><th>State</th><th>Recordings</th><th></th></tr>${rows}</table>` : `<div class="empty">No disk</div>`, {
      hint: "Formatting erases every recording on that disk.",
    });
    const gen = cfg["General.General"];
    const maint = cfg["General.AutoMaintain"];
    html += this.card(
      "When the disk is full",
      formHtml([F("OverWrite", "Then", "select", { options: [["OverWrite", "Overwrite the oldest recordings"], ["StopRecord", "Stop recording"]] })], gen) +
        formHtml([F("AutoDeleteFilesDays", "Delete recordings older than (days)", "int", { min: 0, max: 365, hint: "0 = keep until the disk is full" })], maint),
      {
        save: async (card) => {
          const [a, b] = card.querySelectorAll(".form");
          await this.setConfig("General.General", a, gen);
          await this.setConfig("General.AutoMaintain", b, maint);
        },
      }
    );
    for (const [name, title, extra] of [
      ["Storage.StorageLowSpace", "Disk almost full", [F("LowerLimit", "Below (% free)", "int", { min: 1, max: 99 })]],
      ["Storage.StorageNotExist", "No disk", []],
      ["Storage.StorageFailure", "Disk error", []],
    ]) {
      const v = cfg[name];
      if (!v || v.error) continue;
      const fields = [F("Enable", "Alarm on", "bool"), ...extra, F("EventHandler.MessageEnable", "Push to the XMeye app", "bool"), F("EventHandler.MailEnable", "E-mail", "bool"), F("EventHandler.BeepEnable", "Beep on the NVR", "bool")];
      html += this.card(title, formHtml(fields, v), { save: (card) => this.setConfig(name, card, v) });
    }
    this.render(html);
    this.pane.querySelectorAll("[data-format]").forEach((b) =>
      b.addEventListener("click", async () => {
        const [disk, partition] = b.dataset.format.split(":").map(Number);
        const ok = await this.dialog({
          title: `Format disk ${disk + 1}?`,
          text: "Every recording on this disk is erased. This cannot be undone.",
          ok: "Format",
          danger: true,
          typed: "FORMAT",
        });
        if (!ok) return;
        b.disabled = true;
        b.textContent = "Formatting…";
        try {
          await this.call("disk_format", { disk, partition });
          b.textContent = "Done";
        } catch (err) {
          b.textContent = "Format";
          b.disabled = false;
          alert(`Format failed: ${err.message}`);
        }
      })
    );
  }

  // ------------------------------------------------------------- network

  async tab_network() {
    const cfg = await this.config(
      "NetWork.NetCommon", "NetWork.NetDHCP", "NetWork.NetDNS", "NetWork.RTSP", "NetWork.NetNTP",
      "NetWork.Upnp", "NetWork.Nat", "NetWork.PMS", "NetWork.NetEmail"
    );
    const common = cfg["NetWork.NetCommon"];
    const dhcp = (cfg["NetWork.NetDHCP"] || []).find?.((x) => x.Interface === "eth0");
    let html = "";
    if (common && !common.error) {
      const fields = [
        F("HostIP", "IP address", "ip"),
        F("Submask", "Subnet mask", "ip"),
        F("GateWay", "Gateway", "ip"),
        F("TCPPort", "Media port (XMeye, this app)", "int", { min: 1, max: 65535 }),
        F("HttpPort", "Web port", "int", { min: 1, max: 65535 }),
        F("UDPPort", "UDP port", "int", { min: 1, max: 65535 }),
        F("TCPMaxConn", "Max. connections", "int", { min: 1, max: 32 }),
        F("TransferPlan", "Network priority", "select", { options: [["Quality", "Quality"], ["Fluency", "Smoothness"], ["AutoAdapt", "Automatic"]] }),
        F("HostName", "Host name"),
      ];
      const dhcpHtml = dhcp ? `<div class="form" style="margin-bottom:12px"><label class="check"><input type="checkbox" data-dhcp ${dhcp.Enable ? "checked" : ""}>Get the address by DHCP</label></div>` : "";
      html += this.card("Address", dhcpHtml + formHtml(fields, common), {
        saveLabel: "Apply…",
        save: async (card) => {
          const value = collect(card, common);
          const useDhcp = card.querySelector("[data-dhcp]")?.checked;
          const ip = hexToIp(value.HostIP);
          const ok = await this.dialog({
            title: "Change the NVR's network settings?",
            text: `The NVR ${useDhcp ? "gets its address by DHCP" : `moves to <b>${esc(ip)}</b>`}, media port ${value.TCPPort}. The app and Home Assistant reconnect there by themselves.
              If the address is wrong for your network, the NVR is only reachable from its own screen.`,
            ok: "Apply",
            danger: true,
          });
          if (!ok) return "";
          const res = await this.call("network_set", { value, ...(dhcp ? { dhcp: !!useDhcp } : {}) });
          return res.moved ? `Applied. Reconnecting to ${res.host}…` : "Applied.";
        },
        hint: "With DHCP on, set a reservation on your router so the address stays the same.",
      });
    }
    const simple = (name, title, fields, hint = "") => {
      const v = cfg[name];
      if (v && !v.error) html += this.card(title, formHtml(fields, v), { save: (card) => this.setConfig(name, card, v), hint });
    };
    simple("NetWork.NetDNS", "DNS", [F("Address", "Primary DNS", "ip"), F("SpareAddress", "Secondary DNS", "ip")]);
    simple("NetWork.RTSP", "RTSP", [F("IsServer", "RTSP server on", "bool"), F("Server.Port", "RTSP port", "int", { min: 1, max: 65535 })],
      "Live video in this app and Home Assistant uses RTSP. After changing the port, change it in the app's or the integration's settings too.");
    simple("NetWork.NetNTP", "Time server (NTP)", [
      F("Enable", "Set the clock from a time server", "bool"),
      F("Server.Name", "Server", "text", { hint: "e.g. pool.ntp.org" }),
      F("Server.Port", "Port", "int"),
      F("UpdatePeriod", "Every (min)", "int", { min: 1, max: 65535 }),
    ]);
    simple("NetWork.Upnp", "UPnP", [F("Enable", "Open ports on the router automatically (UPnP)", "bool")],
      "Off is safer: it exposes the NVR to the internet.");
    simple("NetWork.Nat", "XMeye cloud", [F("NatEnable", "Cloud connection (needed by the XMeye phone app)", "bool")]);
    simple("NetWork.PMS", "Push notifications", [F("Enable", "Send alarms to the XMeye phone app", "bool"), F("PushInterval", "Min. interval (s)", "int", { min: 0 })]);
    simple("NetWork.NetEmail", "E-mail", [
      F("Enable", "Send alarm e-mails", "bool"),
      F("MailServer.Name", "SMTP server"),
      F("Port", "Port", "int"),
      F("UseSSL", "SSL", "bool"),
      F("MailServer.UserName", "User"),
      F("MailServer.Password", "Password", "password", { hint: "•••• keeps the current one" }),
      F("SendAddr", "From"),
      F("Recievers", "To (comma separated)", "list"),
      F("Title", "Subject"),
    ]);
    this.render(html);
  }

  // -------------------------------------------------------------- system

  async tab_system() {
    const [info, time, langs, cfg] = await Promise.all([
      this.call("query", { msg: 1020, name: "SystemInfo" }),
      this.call("time"),
      this.call("query", { msg: 1360, name: "MultiLanguage" }).catch(() => ({})),
      this.config("General.General", "General.Location", "General.AutoMaintain", "System.TimeZone", "NetWork.OnlineUpgrade"),
    ]);
    const si = info.SystemInfo || {};
    let html = "";
    const gen = cfg["General.General"];
    html += this.card(
      "Device",
      `<div class="kv" style="margin-bottom:14px">
        <span>Model</span><span>${esc(si.HardWare)}</span>
        <span>Firmware</span><span>${esc(si.SoftWareVersion)}</span>
        <span>Built</span><span>${esc(si.BuildTime)}</span>
        <span>Channels</span><span>${esc(si.DigChannel)} IP</span></div>` + formHtml([F("MachineName", "Device name")], gen),
      { save: (card) => this.setConfig("General.General", card, gen) }
    );
    const zones = [];
    for (let h = -12; h <= 14; h++) zones.push([-h * 60, `UTC${h >= 0 ? "+" : "−"}${Math.abs(h)}`]);
    const tz = cfg["System.TimeZone"];
    const loc = cfg["General.Location"];
    const dst = (p) => [
      F(`${p}.Month`, "Month", "int", { min: 1, max: 12 }),
      F(`${p}.Day`, "Day", "int", { min: 1, max: 31 }),
      F(`${p}.Hour`, "Hour", "int", { min: 0, max: 23 }),
    ];
    html += this.card(
      "Time",
      `<div class="kv" style="margin-bottom:14px"><span>NVR</span><span data-nvrtime>${esc(time.nvr)}</span>
        <span>This computer</span><span>${esc(time.here)}</span></div>
       ${tz && !tz.error ? `<div data-part="tz">${formHtml([F("timeMin", "Time zone", "select", { options: zones })], tz)}</div>` : ""}
       <div data-part="loc" style="margin-top:12px">${formHtml([
         F("DSTRule", "Summer time", "select", { options: [["On", "On"], ["Off", "Off"]] }),
         F("DateFormat", "Date format", "select", { options: [["YYMMDD", "Year-month-day"], ["MMDDYY", "Month-day-year"], ["DDMMYY", "Day-month-year"]] }),
         F("TimeFormat", "Clock", "select", { options: [["24", "24 hours"], ["12", "12 hours"]] }),
       ], loc)}
       <p class="small" style="margin:10px 0 6px">Summer time starts</p>${formHtml(dst("DSTStart"), loc)}
       <p class="small" style="margin:10px 0 6px">and ends</p>${formHtml(dst("DSTEnd"), loc)}</div>`,
      {
        save: async (card) => {
          const tzPart = card.querySelector('[data-part="tz"]');
          if (tzPart) await this.setConfig("System.TimeZone", tzPart, tz);
          await this.setConfig("General.Location", card.querySelector('[data-part="loc"]'), loc);
        },
        extra: `<button class="btn" data-sync>Set the NVR's clock to this computer's</button>`,
      }
    );
    const maint = cfg["General.AutoMaintain"];
    html += this.card(
      "Automatic restart",
      formHtml([
        F("AutoRebootDay", "Restart", "select", { options: [["Never", "Never"], ["Everyday", "Every day"], ...WEEKDAYS.map((d) => [d, `Every ${d}`])] }),
        F("AutoRebootHour", "At", "select", { options: HOURS }),
      ], maint),
      { save: (card) => this.setConfig("General.AutoMaintain", card, maint) }
    );
    const languages = (langs.MultiLanguage || []).map((l) => [l, l]);
    html += this.card(
      "NVR screen",
      formHtml([
        F("Language", "Language", "select", { options: languages }),
        F("VideoFormat", "Video standard", "select", { options: [["PAL", "PAL (Europe)"], ["NTSC", "NTSC"]] }),
      ], loc) + formHtml([F("VideoOutPut", "Output", "select", { options: [["Auto", "Auto"]] })], gen),
      {
        save: async (card) => {
          const [a, b] = card.querySelectorAll(".form");
          await this.setConfig("General.Location", a, loc);
          await this.setConfig("General.General", b, gen);
        },
      }
    );
    const up = cfg["NetWork.OnlineUpgrade"];
    if (up && !up.error) {
      html += this.card("Firmware updates", formHtml([F("Enable", "Online updates", "bool"), F("AutoCheck", "Check automatically", "bool")], up), {
        save: (card) => this.setConfig("NetWork.OnlineUpgrade", card, up),
      });
    }
    html += this.card("Restart", `<p class="small">Recording stops for about a minute.</p>`, {
      extra: `<button class="danger" data-reboot>Restart the NVR…</button>`,
    });
    this.render(html);
    const sync = this.pane.querySelector("[data-sync]");
    sync.addEventListener("click", () =>
      this.run(sync, async () => {
        const t = await this.call("time_set");
        this.pane.querySelector("[data-nvrtime]").textContent = t.nvr;
        return "Clock set";
      })
    );
    const reboot = this.pane.querySelector("[data-reboot]");
    reboot.addEventListener("click", async () => {
      if (!(await this.dialog({ title: "Restart the NVR?", text: "Recording and live video stop for about a minute.", ok: "Restart", danger: true }))) return;
      this.run(reboot, async () => {
        await this.call("reboot");
        return "Restarting…";
      });
    });
  }

  // --------------------------------------------------------------- users

  async tab_users() {
    const u = await this.call("users");
    const rows = u.users
      .map((x) => `<tr><td><b>${esc(x.Name)}</b>${x.Name === u.me ? ` <span class="small">(this app)</span>` : ""}</td>
        <td>${esc(x.Group)}</td><td class="small">${esc(x.Memo)}</td>
        <td><button class="btn" data-pw="${esc(x.Name)}">Password…</button>
          <button class="btn" data-rights="${esc(x.Name)}">Rights…</button>
          ${x.Name === u.me || x.Reserved ? "" : `<button class="btn" data-del="${esc(x.Name)}">Delete…</button>`}</td></tr>`)
      .join("");
    const groups = u.groups.map((g) => `<option>${esc(g.Name)}</option>`).join("");
    const html =
      this.card("Users", `<table class="users"><tr><th>User</th><th>Group</th><th>Note</th><th></th></tr>${rows}</table>`, {
        hint: "Changing the password of the user this app logs in with updates the app (and Home Assistant) too.",
      }) +
      this.card(
        "Add a user",
        `<div class="form">
          <label>Name<input type="text" data-new="name" maxlength="31" autocomplete="off"></label>
          <label>Password<input type="password" data-new="password" autocomplete="new-password"></label>
          <label>Password again<input type="password" data-new="password2" autocomplete="new-password"></label>
          <label>Group<select data-new="group">${groups}</select></label>
          <label>Note<input type="text" data-new="memo"></label></div>`,
        {
          saveLabel: "Add",
          save: async (card) => {
            const val = (k) => card.querySelector(`[data-new="${k}"]`).value;
            if (!val("name").trim()) throw new Error("Enter a name");
            if (val("password") !== val("password2")) throw new Error("The passwords differ");
            await this.call("user_add", { name: val("name").trim(), password: val("password"), group: val("group"), memo: val("memo") });
            setTimeout(() => this.show("users"), 800);
            return "Added";
          },
        }
      );
    this.render(html);
    this.pane.querySelectorAll("[data-pw]").forEach((b) =>
      b.addEventListener("click", async () => {
        const name = b.dataset.pw;
        const res = await this.dialog({
          title: `Password of ${name}`,
          body: `<div class="form" style="grid-template-columns:1fr">
            <label>Current password<input type="password" name="old" autocomplete="current-password"></label>
            <label>New password<input type="password" name="new" autocomplete="new-password"></label>
            <label>New password again<input type="password" name="new2" autocomplete="new-password"></label></div>`,
          ok: "Change",
        });
        if (!res) return;
        if (res.new !== res.new2) return alert("The new passwords differ.");
        try {
          await this.call("user_password", { user: name, old: res.old, new: res.new });
          alert(name === u.me ? "Password changed. The app reconnects with it." : "Password changed.");
        } catch (err) {
          alert(`Not changed: ${err.message}`);
        }
      })
    );
    this.pane.querySelectorAll("[data-rights]").forEach((b) =>
      b.addEventListener("click", async () => {
        const user = u.users.find((x) => x.Name === b.dataset.rights);
        const have = new Set(user.AuthorityList || []);
        const res = await this.dialog({
          title: `Rights of ${user.Name}`,
          body: `<div class="rights">${u.rights
            .map((r) => `<label><input type="checkbox" name="r:${esc(r)}" ${have.has(r) ? "checked" : ""}>${esc(r)}</label>`)
            .join("")}</div>`,
          ok: "Save",
        });
        if (!res) return;
        const rights = Object.keys(res === true ? {} : res).filter((k) => k.startsWith("r:")).map((k) => k.slice(2));
        try {
          await this.call("user_modify", { user: user.Name, rights });
          this.show("users");
        } catch (err) {
          alert(`Not saved: ${err.message}`);
        }
      })
    );
    this.pane.querySelectorAll("[data-del]").forEach((b) =>
      b.addEventListener("click", async () => {
        const name = b.dataset.del;
        if (!(await this.dialog({ title: `Delete ${name}?`, text: "Apps that log in as this user stop working.", ok: "Delete", danger: true }))) return;
        try {
          await this.call("user_delete", { user: name });
          this.show("users");
        } catch (err) {
          alert(`Not deleted: ${err.message}`);
        }
      })
    );
  }

  // ------------------------------------------------------------ advanced

  async tab_advanced() {
    const chs = await this.channels();
    const opts = KNOWN.flatMap((n) => (n.endsWith(".[n]") ? chs.map((c) => n.replace("[n]", `[${c.index}]`)) : [n]));
    this.advName ??= "General.General";
    const html = this.card(
      "Any setting",
      `<div class="form" style="grid-template-columns:1fr auto"><label>Setting
        <input type="text" list="xm-known" data-adv value="${esc(this.advName)}"></label>
        <label>&nbsp;<button class="btn" data-load>Load</button></label></div>
        <datalist id="xm-known">${opts.map((o) => `<option value="${esc(o)}">`).join("")}</datalist>
        <textarea data-json spellcheck="false" style="margin-top:12px"></textarea>`,
      {
        save: async (card) => {
          let value;
          try {
            value = JSON.parse(card.querySelector("[data-json]").value);
          } catch (err) {
            throw new Error(`Not valid JSON: ${err.message}`);
          }
          const name = this.advName;
          if (name === "NetWork.NetCommon") throw new Error("Use Network → Address for this one.");
          const res = await this.call("config_set", { name, value });
          card.querySelector("[data-json]").value = JSON.stringify(res, null, 2);
        },
        hint: "The raw configuration as the NVR keeps it. Stored passwords show as •••• and are kept when left so. Only settings the other tabs use, and similar ones, can be saved.",
      }
    );
    this.render(html);
    const card = this.pane.querySelector("[data-card]");
    const load = async () => {
      this.advName = card.querySelector("[data-adv]").value.trim();
      const area = card.querySelector("[data-json]");
      area.value = "Loading…";
      const res = await this.config(this.advName);
      area.value = JSON.stringify(res[this.advName], null, 2);
    };
    card.querySelector("[data-load]").addEventListener("click", () => load().catch((err) => alert(err.message)));
    card.querySelector("[data-adv]").addEventListener("keydown", (ev) => ev.key === "Enter" && load());
    load().catch(() => {});
  }
}

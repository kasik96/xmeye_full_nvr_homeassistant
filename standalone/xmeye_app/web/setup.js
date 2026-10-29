import { Connection } from "./connection.js";

const conn = new Connection();
const $ = (sel) => document.querySelector(sel);
const call = (msg) => conn.sendMessagePromise(msg);
let status;

function say(id, text, kind = "") {
  const el = $(id);
  el.textContent = text;
  el.className = `msg ${kind}`;
}

async function refresh() {
  status = await call({ type: "app/status" });
  const s = status.settings;
  $("#dot").className = `dot ${status.connected ? "ok" : status.error ? "err" : ""}`;
  $("#status").textContent = status.error || status.status;
  $("#open").hidden = !s.host;
  $("#version").textContent = `${status.app} ${status.version}`;
  $("#autostart").checked = status.autostart;
  return status;
}

function fillForms() {
  const s = status.settings;
  const nvr = $("#nvr");
  nvr.host.value = s.host;
  nvr.username.value = s.username;
  nvr.port.value = s.port;
  nvr.rtsp_port.value = s.rtsp_port;
  nvr.password.placeholder = s.host ? "saved (leave empty to keep)" : "";
  const access = $("#access");
  access.lan.checked = s.lan;
  access.http_port.value = s.http_port;
  $("#pw-state").textContent = s.web_password ? "(set)" : "(not set)";
  $("#urls").textContent = status.lan_urls.length ? `On other devices open ${status.lan_urls.join(" or ")}` : "";
  $("#cams").transcode_h265.checked = s.transcode_h265;
  showCameras(status.channels);
  const remote = $("#remote");
  remote.tunnel.value = s.tunnel;
  remote.tunnel_hostname.value = s.tunnel_hostname;
  $("#token-state").textContent = status.tunnel_token ? "(saved)" : "";
  remote.tunnel_token.placeholder = status.tunnel_token ? "saved (leave empty to keep)" : "eyJh…";
  $("#service").textContent = `http://localhost:${s.http_port}`;
  showOwn();
  showTunnel();
}

function showOwn() {
  $("#own").hidden = $("#remote").tunnel.value !== "token";
}

const TUNNEL_STATES = { starting: "Connecting to Cloudflare…", connected: "Connected", error: "Not connected" };

function showTunnel() {
  const t = status.tunnel;
  const el = $("#tunnel-state");
  if (t.mode === "off") {
    el.textContent = status.settings.tunnel !== "off" && !status.settings.web_password ? "Set a web password first." : "";
    return;
  }
  const esc = (x) => x.replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`);
  const state = `<span class="${t.state === "connected" ? "ok" : t.state === "error" ? "err" : ""}">${TUNNEL_STATES[t.state] ?? t.state}</span>`;
  const url = t.url ? ` · <a class="url" href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.url)}</a> <button type="button" id="copy-url">Copy</button>` : "";
  el.innerHTML = `${state}${url}${t.error ? ` <span class="err">${esc(t.error)}</span>` : ""}`;
  el.querySelector("#copy-url")?.addEventListener("click", () => navigator.clipboard?.writeText(t.url));
}

function showCameras(channels) {
  const names = status.settings.names;
  $("#cams").hidden = !channels.length;
  $("#cams tbody").innerHTML = channels
    .map(({ channel, title }) => {
      const custom = names[channel];
      const esc = (t) => t.replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`);
      return `<tr data-channel="${channel}" data-title="${esc(title)}">
        <td class="num">${channel}</td>
        <td><input type="text" value="${custom ? esc(custom) : ""}" placeholder="${esc(title)}"
          aria-label="Name of camera ${channel}"></td>
        <td class="show"><input type="checkbox" ${custom === "" ? "" : "checked"}
          aria-label="Show camera ${channel}"></td></tr>`;
    })
    .join("");
}

function nvrDetails(withPassword) {
  const f = $("#nvr");
  const out = { host: f.host.value.trim(), port: Number(f.port.value), rtsp_port: Number(f.rtsp_port.value),
    username: f.username.value };
  if (withPassword) out.password = f.password.value || null;
  return out;
}

$("#test").onclick = async () => {
  say("#nvr-msg", "Connecting…");
  try {
    const d = nvrDetails(true);
    const res = await call({ type: "app/test", ...d, password: d.password });
    say("#nvr-msg", `OK: ${res.model}, ${res.channels.length} cameras`, "ok");
    showCameras(res.channels);
  } catch (err) {
    say("#nvr-msg", err.message, "err");
  }
};

$("#nvr").onsubmit = async (ev) => {
  ev.preventDefault();
  const d = nvrDetails(true);
  if (!status.settings.host && !d.password) return say("#nvr-msg", "Enter the password.", "err");
  say("#nvr-msg", "Connecting…");
  try {
    const res = await call({ type: "app/test", ...d });
    await call({ type: "app/save", nvr: d });
    $("#nvr").password.value = "";
    say("#nvr-msg", `Saved. ${res.model}, ${res.channels.length} cameras.`, "ok");
    for (let i = 0; i < 20; i++) {
      await refresh();
      if (status.connected || status.error) break;
      await new Promise((r) => setTimeout(r, 1000));
    }
    fillForms();
    if (status.connected) say("#nvr-msg", "Connected.", "ok");
  } catch (err) {
    say("#nvr-msg", err.message, "err");
  }
};

$("#cams").onsubmit = async (ev) => {
  ev.preventDefault();
  const names = {};
  for (const row of document.querySelectorAll("#cams tbody tr")) {
    const name = row.querySelector("input[type=text]").value.trim();
    const show = row.querySelector("input[type=checkbox]").checked;
    if (!show) names[row.dataset.channel] = "";
    else if (name && name !== row.dataset.title) names[row.dataset.channel] = name;
  }
  try {
    await call({ type: "app/save", names, transcode_h265: $("#cams").transcode_h265.checked });
    say("#cams-msg", "Saved.", "ok");
    await refresh();
  } catch (err) {
    say("#cams-msg", err.message, "err");
  }
};

$("#access").onsubmit = async (ev) => {
  ev.preventDefault();
  const f = $("#access");
  const msg = { lan: f.lan.checked, http_port: Number(f.http_port.value) };
  if (f.web_password.value) msg.web_password = f.web_password.value;
  try {
    const res = await call({ type: "app/save", ...msg });
    f.web_password.value = "";
    if (res.restart) {
      say("#access-msg", "Saved. Restarting the web server…", "ok");
      conn.closing = true;
      const url = `${location.protocol}//${location.hostname}:${res.port}/setup`;
      setTimeout(() => (location.href = url), 1500);
      return;
    }
    say("#access-msg", "Saved.", "ok");
    await refresh();
    fillForms();
  } catch (err) {
    say("#access-msg", err.message, "err");
  }
};

for (const radio of document.querySelectorAll("#remote [name=tunnel]")) radio.onchange = showOwn;

$("#remote").onsubmit = async (ev) => {
  ev.preventDefault();
  const f = $("#remote");
  const msg = { tunnel: f.tunnel.value, tunnel_hostname: f.tunnel_hostname.value };
  if (f.tunnel_token.value) msg.tunnel_token = f.tunnel_token.value;
  try {
    await call({ type: "app/save", ...msg });
    f.tunnel_token.value = "";
    say("#remote-msg", "Saved.", "ok");
    await refresh();
    fillForms();
  } catch (err) {
    say("#remote-msg", err.message, "err");
  }
};

$("#autostart").onchange = async (ev) => {
  try {
    await call({ type: "app/autostart", enabled: ev.target.checked });
  } catch (err) {
    ev.target.checked = !ev.target.checked;
    alert(err.message);
  }
};

await refresh();
fillForms();
setInterval(async () => {
  const before = status.connected;
  const tunnelBefore = JSON.stringify(status.tunnel);
  await refresh();
  if (status.connected !== before) fillForms();
  else if (JSON.stringify(status.tunnel) !== tunnelBefore) showTunnel();
}, 5000);

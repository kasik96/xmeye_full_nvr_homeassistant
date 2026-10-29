// Runs the integration's panel with a stand-in for Home Assistant's `hass` object.
import { Connection } from "./connection.js";

const conn = new Connection();
const status = await conn.sendMessagePromise({ type: "app/status" });
let cameras = [];
try {
  cameras = (await conn.sendMessagePromise({ type: "xmeye/cameras" })).cameras;
} catch (err) { /* not connected yet */ }

const states = {};
for (const cam of cameras) {
  for (const id of [cam.entity_id, cam.sub_entity_id]) {
    if (id) states[id] = { attributes: { entity_picture: `/api/snapshot/${encodeURIComponent(id)}` } };
  }
}

await import("/panel/xmeye-panel.js");
const panel = document.createElement("xmeye-panel");
const problem = status.error || (status.connected ? "" : status.status);
panel.panel = {
  config: {
    hls: "/panel/hls.light.min.js",
    logo: "/panel/logo.png",
    app_settings: "/setup",
    empty: problem
      ? `${problem} <a href="/setup" style="color:#7ab0ff">Settings</a>`
      : `No cameras. <a href="/setup" style="color:#7ab0ff">Settings</a>`,
  },
};
panel.narrow = false;
panel.hass = {
  connection: conn,
  user: { name: "admin", is_admin: true },
  states,
  fetchWithAuth: (url, init) => fetch(url, { credentials: "same-origin", ...init }),
};
document.body.append(panel);

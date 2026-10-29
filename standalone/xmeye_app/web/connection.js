// The app's WebSocket, with the part of Home Assistant's connection API the panel uses.

export class Connection {
  constructor() {
    this.id = 0;
    this.pending = new Map();
    this.subscriptions = new Map();
    this.ready = new Promise((resolve, reject) => {
      const proto = location.protocol === "https:" ? "wss:" : "ws:";
      const ws = new WebSocket(`${proto}//${location.host}/api/websocket`);
      ws.onopen = () => resolve(ws);
      ws.onerror = () => reject(new Error("Cannot connect to the app"));
      ws.onmessage = (ev) => this.onMessage(JSON.parse(ev.data));
      ws.onclose = () => this.onClose();
    });
  }

  onMessage(msg) {
    if (msg.type === "result") {
      const p = this.pending.get(msg.id);
      this.pending.delete(msg.id);
      if (!p) return;
      if (msg.success) p.resolve(msg.result);
      else p.reject(Object.assign(new Error(msg.error.message), { code: msg.error.code }));
    } else if (msg.type === "event") {
      this.subscriptions.get(msg.id)?.(msg.event);
    }
  }

  // The app went away (quit, restarted, settings changed): reload once it is back.
  onClose() {
    for (const p of this.pending.values()) p.reject(new Error("Connection lost"));
    this.pending.clear();
    if (this.closing) return;
    document.body.insertAdjacentHTML(
      "beforeend",
      `<div style="position:fixed;inset:auto 0 0 0;padding:10px;background:#7c2d12;color:#fff;
        font:14px system-ui,sans-serif;text-align:center;z-index:99">Lost the connection to the app, reconnecting…</div>`
    );
    const retry = async () => {
      try {
        const r = await fetch("/api/ping", { cache: "no-store" });
        if (r.ok) return location.reload();
      } catch (err) { /* not back yet */ }
      setTimeout(retry, 2000);
    };
    setTimeout(retry, 1000);
  }

  async sendMessagePromise(msg) {
    const ws = await this.ready;
    const id = ++this.id;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ ...msg, id }));
    });
  }

  async subscribeMessage(callback, msg) {
    const ws = await this.ready;
    const id = ++this.id;
    this.subscriptions.set(id, callback);
    await new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ ...msg, id }));
    }).catch((err) => {
      this.subscriptions.delete(id);
      throw err;
    });
    return async () => {
      this.subscriptions.delete(id);
      await this.sendMessagePromise({ type: "unsubscribe", subscription: id });
    };
  }
}

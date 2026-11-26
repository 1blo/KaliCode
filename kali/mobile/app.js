/* Kali Code mobile companion - PWA client.
   Speaks the JSON protocol documented in kali/serve.py. */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const log = $("log");
  const input = $("input");
  const sendBtn = $("send");
  const statusEl = $("status");
  const titleEl = $("title");

  let ws = null;
  let token = localStorage.getItem("kali_token") || "";
  let streaming = null;       // active assistant bubble element
  let busy = false;
  let currentSession = localStorage.getItem("kali_session") || null;

  // ---------------------------------------------------------------- helpers
  function esc(s) {
    const t = String(s == null ? "" : s);
    let out = "";
    for (let i = 0; i < t.length; i++) {
      switch (t[i]) {
      case "&": return "&amp;";
      case "<": return "&lt;";
      case ">": return "&gt;";
      case String.fromCharCode(34): return "&quot;";
      case String.fromCharCode(39): return "&#39;";
        default: out += t[i];
      }
    }
    return out;
  }
  function scrollBottom() {
    requestAnimationFrame(() => { log.scrollTop = log.scrollHeight; });
  }

  function addMsg(kind, html, cls) {
    const wrap = document.createElement("div");
    wrap.className = "msg " + kind + (cls ? " " + cls : "");
    wrap.innerHTML = html;
    log.appendChild(wrap);
    scrollBottom();
    return wrap;
  }

  function addText(kind, text, who) {
    const el = addMsg(kind,
      `<div class="who">${esc(who || kind)}</div><div class="bubble"></div>`);
    el.querySelector(".bubble").textContent = text;
    return el;
  }

  function setStatus(text, cls) {
    statusEl.textContent = text;
    statusEl.className = "status " + (cls || "");
  }

  // ------------------------------------------------------------------ lock
  $("token").value = token;
  if (token) { setStatus("connecting", ""); }

  $("connect").onclick = () => {
    token = $("token").value.trim();
    if (!token) { $("lockerr").textContent = "Enter the access token."; return; }
    localStorage.setItem("kali_token", token);
    $("lockerr").textContent = "";
    connect();
  };
  $("token").addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("connect").click();
  });

  // --------------------------------------------------------------- connect
  function connect() {
    if (ws) { try { ws.close(); } catch (e) {} ws = null; }

    const proto = location.protocol === "https:" ? "wss:" : "ws:";
    const url = `${proto}//${location.host}/ws`;
    setStatus("connecting", "");

    try {
      ws = new WebSocket(url);
    } catch (e) {
      $("lockerr").textContent = "Could not open a connection.";
      return;
    }

    ws.onopen = () => {
      ws.send(JSON.stringify({
        type: "hello",
        token,
        session: localStorage.getItem("kali_session") || null,
      }));
    };

    ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      handle(msg);
    };

    ws.onclose = () => {
      setStatus("offline", "off");
      sendBtn.disabled = true;
      busy = false;
      setSendLabel();
    };

    ws.onerror = () => { setStatus("error", "off"); };
  }

  // ---------------------------------------------------------------- handle
  function handle(msg) {
    switch (msg.type) {
      case "ready": {
        $("lock").style.display = "none";
        setStatus("online", "on");
        sendBtn.disabled = false;
        titleEl.textContent = "Kali Code";
        if (msg.cwd) $("hint").textContent = "Workspace: " + msg.cwd;
        if (msg.session) {
          localStorage.setItem("kali_session", msg.session);
          currentSession = msg.session;
        }
        break;
      }
      case "thinking": {
        if (!streaming) {
          const el = addMsg("think", '<div class="bubble"></div>');
          streaming = { el, buf: "" };
        }
        streaming.buf += msg.text || "";
        streaming.el.querySelector(".bubble").textContent = streaming.buf;
        scrollBottom();
        break;
      }
      case "text": {
        if (!streaming) {
          streaming = { el: addMsg("bot", '<div class="bubble"></div>'), buf: "" };
        }
        streaming.el.classList.add("streaming");
        streaming.buf += msg.text || "";
        streaming.el.querySelector(".bubble").textContent = streaming.buf;
        scrollBottom();
        break;
      }
      case "tool_start": {
        closeStreaming();
        addMsg("tool",
          `<span class="name">${esc(msg.name)}</span> <span style="color:var(--dim)">running…</span>`);
        break;
      }
      case "tool_result": {
        const last = log.lastElementChild;
        const out = (msg.output || "").trim();
        if (last && last.classList.contains("tool") && !last.dataset.done) {
          last.dataset.done = "1";
          last.innerHTML = `<span class="name">${esc(msg.name)}</span> ` +
            `<span style="color:var(--dim)">${msg.ok ? "done" : "failed"} in ${msg.elapsed}s</span>` +
            (out ? `<div class="toolout">${esc(out.slice(0, 4000))}</div>` : "");
        } else {
          addMsg("tool",
            `<span class="name">${esc(msg.name)}</span> ` +
            `<span style="color:var(--dim)">${msg.ok ? "done" : "failed"} in ${msg.elapsed}s</span>` +
            (out ? `<div class="toolout">${esc(out.slice(0, 4000))}</div>` : ""));
        }
        scrollBottom();
        break;
      }
      case "tool_denied": {
        closeStreaming();
        addMsg("err", `<div class="bubble">Denied: ${esc(msg.name)} - ${esc(msg.reason)}</div>`);
        break;
      }
      case "permission": {
        closeStreaming();
        showPermission(msg);
        break;
      }
      case "question": {
        closeStreaming();
        showQuestion(msg);
        break;
      }
      case "plan": {
        closeStreaming();
        showPlan(msg);
        break;
      }
      case "error": {
        closeStreaming();
        addText("err", msg.message || "error");
        break;
      }
      case "done": {
        closeStreaming();
        busy = false;
        setSendLabel();
        const usage = msg.usage || {};
        const bits = [];
        if (usage.prompt_tokens) bits.push(`${usage.prompt_tokens} in`);
        if (usage.completion_tokens) bits.push(`${usage.completion_tokens} out`);
        const tail = bits.length ? `  ·  ${bits.join(" / ")} tok` : "";
        $("hint").textContent = `Done in ${msg.elapsed}s${tail}`;
        sendBtn.disabled = false;
        break;
      }
      case "interrupted": {
        closeStreaming();
        busy = false;
        setSendLabel();
        $("hint").textContent = "Interrupted.";
        sendBtn.disabled = false;
        break;
      }
      case "pong": break;
      default: break;
    }
  }

  function closeStreaming() {
    if (streaming) {
      streaming.el.classList.remove("streaming");
      streaming = null;
    }
  }

  // ------------------------------------------------------- permission card
  function showPermission(msg) {
    const card = document.createElement("div");
    card.className = "perm";
    const argText = msg.summary || JSON.stringify(msg.args || {});
    card.innerHTML =
      `<div class="hdr">Permission needed — ${esc(msg.name)}</div>` +
      `<div class="what">${esc(argText)}</div>` +
      `<div class="btns">` +
      `<button class="yes" data-a="allow">Allow</button>` +
      `<button class="always" data-a="always">Always</button>` +
      `<button class="no" data-a="deny">Deny</button>` +
      `</div>`;
    log.appendChild(card);
    scrollBottom();
    card.querySelectorAll("button").forEach((b) => {
      b.onclick = () => {
        send({ type: "reply", id: msg.id, answer: b.dataset.a });
        card.remove();
      };
    });
  }

  // ---------------------------------------------------------- question card
  function showQuestion(msg) {
    const q = msg.question || {};
    const card = document.createElement("div");
    card.className = "perm";
    card.innerHTML = `<div class="hdr">Question</div>` +
      `<div class="what" style="font-family:inherit">${esc(q.question || "")}</div>` +
      `<div class="btns" style="flex-direction:column" id="opts"></div>`;
    log.appendChild(card);
    scrollBottom();

    const opts = card.querySelector("#opts");
    (q.options || []).forEach((o) => {
      const b = document.createElement("button");
      b.style.background = "var(--panel2)";
      b.style.color = "var(--fg)";
      b.textContent = o.label || o.description || String(o);
      b.onclick = () => {
        send({ type: "answer", id: msg.id, value: o.label || String(o) });
        card.remove();
      };
      opts.appendChild(b);
    });
    const free = document.createElement("input");
    free.placeholder = "or type your own answer";
    free.style.cssText = "width:100%;padding:10px;border-radius:8px;border:1px solid var(--border);background:var(--panel);color:var(--fg);";
    free.onkeydown = (e) => {
      if (e.key === "Enter" && free.value.trim()) {
        send({ type: "answer", id: msg.id, value: free.value.trim() });
        card.remove();
      }
    };
    opts.appendChild(free);
  }

  // -------------------------------------------------------------- plan card
  function showPlan(msg) {
    const card = document.createElement("div");
    card.className = "perm";
    card.innerHTML =
      `<div class="hdr">Plan ready for approval</div>` +
      `<div class="what" style="max-height:320px">${esc(msg.plan || "")}</div>` +
      `<div class="btns">` +
      `<button class="yes" data-a="approve">Approve</button>` +
      `<button class="no" data-a="reject">Reject</button>` +
      `</div>`;
    log.appendChild(card);
    scrollBottom();
    card.querySelectorAll("button").forEach((b) => {
      b.onclick = () => {
        send({ type: "reply", id: msg.id, answer: b.dataset.a });
        card.remove();
      };
    });
  }

  // ------------------------------------------------------------------ send
  function send(obj) {
    if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj));
  }

  function setSendLabel() {
    sendBtn.textContent = busy ? "■" : "↑";
    sendBtn.classList.toggle("stop", busy);
  }

  function submit() {
    const text = input.value.trim();
    if (!text || busy || !ws || ws.readyState !== 1) return;
    addText("user", text, "you");
    input.value = "";
    input.style.height = "auto";
    busy = true;
    setSendLabel();
    $("hint").textContent = "Working...";
    send({ type: "prompt", text });
  }

  sendBtn.onclick = () => {
    if (busy) { send({ type: "interrupt" }); return; }
    submit();
  };

  input.addEventListener("input", () => {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 140) + "px";
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  });

  $("reset").onclick = () => {
    send({ type: "reset" });
    log.innerHTML = "";
    $("hint").textContent = "New session.";
  };

  // ------------------------------------------------------- notifications
  function notify(title, body) {
    if (!("Notification" in window)) return;
    if (Notification.permission === "granted") {
      new Notification(title, { body: body, icon: "/mobile/icon-192.png", badge: "/mobile/icon-192.png" });
    }
  }

  if ("Notification" in window && Notification.permission === "default") {
    Notification.requestPermission().catch(() => {});
  }

  // wake the socket on visibility change (Render spins down when idle)
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && (!ws || ws.readyState > 1)) connect();
  });

  // ------------------------------------------------------------------ init
  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/mobile/sw.js").catch(() => {});
  }
  if (token) connect();
  else setStatus("locked", "off");
})();

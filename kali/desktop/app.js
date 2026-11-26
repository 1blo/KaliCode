/* Kali Code desktop - the Claude Code "Code tab" client.
   Speaks the JSON protocol documented in kali/serve.py. */
(() => {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const chat = $("chat");

  // ---------------------------------------------------------------- state
  let ws = null;
  // The desktop shell starts the server itself and passes the token in
  // the URL fragment, so there is nothing to type on first run.
  const freshToken = new URLSearchParams(location.hash.slice(1)).get("token") || "";
  let token = freshToken
    || localStorage.getItem("kali_token")
    || "";
  let sessionId = localStorage.getItem("kali_session") || null;
  let sessions = [];
  let cwd = "";
  let model = "";
  let permMode = "default";
  let busy = false;
  let streaming = null;         // {el, buf, kind}
  let toolCards = new Map();    // name -> element
  let viewMode = localStorage.getItem("kali_viewmode") || "normal";
  let pane = "chat";
  let showArchived = false;
  let lastUsage = null;
  let sideHistory = [];
  let attachment = null;

  const MODELS = [
    "stepfun-ai/step-5-preview",
    "moonshotai/kimi-k3.1-pro",
    "minimaxai/minimax-m3.1-flash",
  ];
  const MODE_LABEL = {
    default: "Manual",
    acceptEdits: "Accept edits",
    plan: "Plan",
    auto: "Auto",
    bypassPermissions: "Bypass permissions",
  };
  const VIEW_MODES = ["normal", "thinking", "verbose"];

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
    requestAnimationFrame(() => { chat.scrollTop = chat.scrollHeight; });
  }

  function toast(text, ms = 2200) {
    const t = $("toast");
    t.textContent = text;
    t.classList.remove("hidden");
    clearTimeout(t._timer);
    t._timer = setTimeout(() => t.classList.add("hidden"), ms);
  }

  function send(obj) {
    if (ws && ws.readyState === 1) ws.send(JSON.stringify(obj));
  }

  function fmtModel(m) {
    if (!m) return "model";
    return m.split("/").pop().replace(/-/g, " ");
  }

  function fmtCwd(p) {
    if (!p) return "—";
    const parts = String(p).split(/[\\/]/).filter(Boolean);
    return parts.length > 2 ? "…/" + parts.slice(-2).join("/") : p;
  }

  // ------------------------------------------------------------------ lock
  $("token").value = token;
  if (token) connect();

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
    setStatus("connecting");
    try {
      ws = new WebSocket(`${proto}//${location.host}/ws`);
    } catch (e) {
      $("lockerr").textContent = "Could not open a connection.";
      return;
    }

    ws.onopen = () => {
      send({ type: "hello", token, session: sessionId });
    };

    ws.onmessage = (ev) => {
      let msg;
      try { msg = JSON.parse(ev.data); } catch (e) { return; }
      handle(msg);
    };

    ws.onclose = () => {
      setStatus("offline");
      busy = false;
      setSendLabel();
    };

    ws.onerror = () => setStatus("error");
  }

  function setStatus(kind) {
    const dot = $("statusDot");
    dot.className = "dot" + (kind === "run" ? " run" : kind === "wait" ? " wait"
                        : kind === "err" ? " err" : "");
    $("dRunning").textContent =
      kind === "run" ? "Working…" : kind === "wait" ? "Waiting for you"
      : kind === "offline" ? "Offline" : kind === "err" ? "Error" : "Idle";
  }

  // ---------------------------------------------------------------- handle
  function handle(msg) {
    switch (msg.type) {
      case "ready": {
        $("lock").classList.add("hidden");
        $("app").classList.remove("hidden");
        setStatus("idle");
        sessionId = msg.session;
        localStorage.setItem("kali_session", sessionId);
        cwd = msg.cwd || cwd;
        model = msg.model || model;
        permMode = (msg.meta && msg.meta.permissionMode) || permMode;
        sessions = msg.sessions || sessions;
        renderSessions();
        renderHeader();
        break;
      }
      case "sessions": {
        sessions = msg.sessions || [];
        renderSessions();
        break;
      }
      case "session_meta": {
        const meta = msg.session || {};
        sessions = sessions.map((s) => (s.id === meta.id ? meta : s));
        renderSessions();
        renderHeader();
        break;
      }
      case "thinking": {
        if (viewMode === "normal") break;
        pushStream("think", msg.text || "");
        break;
      }
      case "text": {
        pushStream("bot", msg.text || "");
        break;
      }
      case "tool_start": {
        closeStream();
        if (viewMode === "normal") {
          const el = addToolCard(msg.name, msg.args);
          toolCards.set(msg.name, el);
        } else {
          addToolCard(msg.name, msg.args);
        }
        break;
      }
      case "tool_result": {
        closeStream();
        const el = toolCards.get(msg.name);
        const out = (msg.output || "").trim();
        if (el) {
          toolCards.delete(msg.name);
          el.dataset.done = "1";
          const meta = el.querySelector(".toolmeta");
          if (meta) meta.textContent = `${msg.ok ? "done" : "failed"} in ${msg.elapsed}s`;
          if (out) {
            const box = document.createElement("div");
            box.className = "toolout collapsed";
            box.textContent = out.slice(0, 8000);
            box.onclick = () => box.classList.toggle("collapsed");
            el.appendChild(box);
          }
        } else if (viewMode === "verbose") {
          addToolCard(msg.name, msg.args, msg.ok, msg.elapsed, out);
        }
        scrollBottom();
        break;
      }
      case "tool_denied": {
        closeStream();
        addMsg("err", `<div class="who">denied</div><div class="bubble">${esc(msg.name)} — ${esc(msg.reason || "denied")}</div>`);
        break;
      }
      case "subagent": {
        closeStream();
        addMsg("tool", `<div class="who">subagent</div><div class="bubble">` +
          `<span class="toolname">${esc(msg.description || "")}</span>` +
          (msg.final ? `<div class="toolout">${esc(msg.final.slice(0, 3000))}</div>` : "") +
          `</div>`);
        break;
      }
      case "permission": {
        closeStream();
        showPermission(msg);
        break;
      }
      case "question": {
        closeStream();
        showQuestion(msg);
        break;
      }
      case "plan": {
        closeStream();
        showPlan(msg);
        break;
      }
      case "diff": {
        showDiff(msg.path, msg.diff);
        break;
      }
      case "error": {
        closeStream();
        // The server may have restarted with a new token while a stale
        // one was saved in localStorage. The shell hands the live token
        // in the URL fragment, so retry with it before giving up.
        if (/unauthor|token/i.test(msg.message || "") && freshToken
            && token !== freshToken) {
          token = freshToken;
          localStorage.setItem("kali_token", token);
          connect();
          break;
        }
        addMsg("err", `<div class="who">error</div><div class="bubble">${esc(msg.message || "error")}</div>`);
        setStatus("err");
        break;
      }
      case "done": {
        closeStream();
        busy = false;
        setSendLabel();
        lastUsage = msg.usage || lastUsage;
        updateContext();
        if (msg.meta) {
          sessions = sessions.map((s) => (s.id === msg.meta.id ? msg.meta : s));
          renderSessions();
          renderHeader();
        }
        const el = addMsg("tool", `<div class="who">done</div><div class="bubble">` +
          `<span class="toolmeta">${msg.elapsed || 0}s</span></div>`);
        el.remove();
        refreshChanges();
        break;
      }
      case "interrupted": {
        closeStream();
        busy = false;
        setSendLabel();
        break;
      }
      case "pong": break;
      default: break;
    }
  }

  // ------------------------------------------------------------ rendering
  function addMsg(kind, html) {
    const el = document.createElement("div");
    el.className = "msg " + kind;
    el.innerHTML = html;
    chat.appendChild(el);
    scrollBottom();
    return el;
  }

  function pushStream(kind, text) {
    if (!streaming || streaming.kind !== kind) {
      closeStream();
      const el = document.createElement("div");
      el.className = "msg " + kind + " streaming";
      el.innerHTML = `<div class="who">${kind === "think" ? "thinking" : "kali"}</div><div class="bubble"></div>`;
      chat.appendChild(el);
      streaming = { el, buf: "", kind };
    }
    streaming.buf += text;
    streaming.el.querySelector(".bubble").textContent = streaming.buf;
    scrollBottom();
  }

  function closeStream() {
    if (streaming) {
      streaming.el.classList.remove("streaming");
      streaming = null;
    }
  }

  function argSummary(args) {
    if (!args) return "";
    for (const k of ["command", "file_path", "path", "notebook_path", "url",
                     "pattern", "query", "skill", "description"]) {
      const v = args[k];
      if (typeof v === "string" && v.trim()) {
        const s = v.trim();
        return s.length > 140 ? s.slice(0, 137) + "…" : s;
      }
    }
    try { return JSON.stringify(args).slice(0, 140); } catch (e) { return ""; }
  }

  function addToolCard(name, args, ok, elapsed, out) {
    const el = addMsg("tool",
      `<div class="bubble"><span class="toolname">${esc(name)}</span>` +
      `<span class="toolmeta">${ok !== undefined ? (ok ? "done" : "failed") : "running…"}</span>` +
      `<div class="toolmeta">${esc(argSummary(args))}</div></div>`);
    if (out) {
      const box = document.createElement("div");
      box.className = "toolout collapsed";
      box.textContent = out;
      el.querySelector(".bubble").appendChild(box);
    }
    return el;
  }

  // ------------------------------------------------------- session rail
  function renderSessions() {
    const box = $("sessionList");
    box.innerHTML = "";
    const q = ($("sessionSearch").value || "").toLowerCase();
    const items = sessions.filter((s) => {
      if (!showArchived && s.archived) return false;
      if (q && !String(s.title || "").toLowerCase().includes(q)) return false;
      return true;
    });
    if (!items.length) {
      box.innerHTML = '<div class="empty">No sessions.</div>';
      return;
    }
    for (const s of items) {
      const el = document.createElement("div");
      el.className = "sitem" + (s.id === sessionId ? " active" : "");
      const icon = s.worktree ? "⑂" : (s.archived ? "🗄" : "◆");
      let badge = "";
      if (s.status === "running") badge = '<span class="sbadge run">run</span>';
      else if (s.status === "awaiting_permission") badge = '<span class="sbadge wait">!</span>';
      else if (s.archived) badge = '<span class="sbadge">arch</span>';
      el.innerHTML = `<span class="sicon">${icon}</span>` +
        `<span class="stxt">${esc(s.title || "New session")}</span>${badge}`;
      el.onclick = () => {
        send({ type: "switch_session", session: s.id });
        sessionId = s.id;
        localStorage.setItem("kali_session", s.id);
        chat.innerHTML = "";
        closeStream();
        toolCards.clear();
      };
      el.oncontextmenu = (e) => {
        e.preventDefault();
        sessionMenu(s, e.clientX, e.clientY);
      };
      box.appendChild(el);
    }
  }

  function renderHeader() {
    const s = sessions.find((x) => x.id === sessionId);
    $("sessionTitle").textContent = (s && s.title) || "New session";
    $("dCwd").textContent = fmtCwd((s && s.cwd) || cwd);
    $("dEnv").textContent = "Local";
    $("modelBtn").textContent = fmtModel(model);
    $("modeBtn").textContent = MODE_LABEL[permMode] || permMode;
    $("cwdBtn").textContent = fmtCwd((s && s.cwd) || cwd);
    $("worktreeBtn").classList.toggle("on", !!(s && s.worktree));
  }

  function updateContext() {
    const u = lastUsage || {};
    const used = (u.prompt_tokens || 0) + (u.completion_tokens || 0);
    const limit = 128000;
    const pct = Math.min(100, Math.round((used / limit) * 100));
    $("ctxBtn").textContent = pct + "%";
    $("dCtxVal").textContent = pct + "%";
    $("ctxFill").style.width = pct + "%";
  }

  // ------------------------------------------------------------- cards
  function cardShell(cls, title, key, bodyHtml, buttons) {
    const card = document.createElement("div");
    card.className = "card";
    card.innerHTML = `<div class="cardbox ${cls}">` +
      `<div class="chdr">${esc(title)}${key ? ` <span class="k">${esc(key)}</span>` : ""}</div>` +
      bodyHtml + `<div class="cbtns"></div></div>`;
    chat.appendChild(card);
    scrollBottom();
    const btns = card.querySelector(".cbtns");
    for (const b of buttons) {
      const el = document.createElement("button");
      el.textContent = b.label;
      if (b.cls) el.className = b.cls;
      el.onclick = () => { b.action(); card.remove(); };
      btns.appendChild(el);
    }
    return card;
  }

  function showPermission(msg) {
    setStatus("wait");
    const body = `<div class="cwhat">${esc(msg.summary || JSON.stringify(msg.args || {}))}</div>`;
    cardShell("perm", "Permission needed", msg.name, body, [
      { label: "Allow", cls: "yes", action: () => send({ type: "reply", id: msg.id, answer: "allow" }) },
      { label: "Always allow", cls: "always", action: () => send({ type: "reply", id: msg.id, answer: "always" }) },
      { label: "Deny", cls: "no", action: () => send({ type: "reply", id: msg.id, answer: "deny" }) },
    ]);
  }

  function showQuestion(msg) {
    const q = msg.question || {};
    const body = `<div class="cwhat" style="font-family:inherit">${esc(q.question || "")}</div>`;
    const card = cardShell("question", "Question", "", body, []);
    const btns = card.querySelector(".cbtns");
    btns.style.flexDirection = "column";
    for (const o of (q.options || [])) {
      const b = document.createElement("button");
      b.className = "optrow";
      b.innerHTML = `${esc(o.label || o.description || String(o))}` +
        (o.description ? `<small>${esc(o.description)}</small>` : "");
      b.onclick = () => {
        send({ type: "answer", id: msg.id, value: o.label || String(o) });
        card.remove();
      };
      btns.appendChild(b);
    }
  }

  function showPlan(msg) {
    setStatus("wait");
    const body = `<div class="cwhat" style="max-height:340px">${esc(msg.plan || "")}</div>`;
    $("planText").innerHTML = esc(msg.plan || "");
    cardShell("plan", "Plan ready for approval", "", body, [
      { label: "Approve", cls: "yes", action: () => send({ type: "reply", id: msg.id, answer: "approve" }) },
      { label: "Edit", action: () => send({ type: "reply", id: msg.id, answer: "edit" }) },
      { label: "Reject", cls: "no", action: () => send({ type: "reply", id: msg.id, answer: "reject" }) },
    ]);
  }

  // -------------------------------------------------------------- menus
  let menuCleanup = null;

  function openMenu(anchor, items) {
    closeMenu();
    const menu = $("menu");
    const box = $("menuItems");
    box.innerHTML = "";
    for (const it of items) {
      if (it.sep) { const s = document.createElement("div"); s.className = "msep"; box.appendChild(s); continue; }
      if (it.label) { const l = document.createElement("div"); l.className = "mlabel"; l.textContent = it.label; box.appendChild(l); continue; }
      const el = document.createElement("div");
      el.className = "mitem" + (it.on ? " on" : "");
      el.innerHTML = `<span class="check">${it.on ? "✓" : ""}</span>` +
        `<span>${esc(it.text)}</span>` +
        (it.desc ? `<span class="mdesc">${esc(it.desc)}</span>` : "");
      el.onclick = () => { closeMenu(); it.action(); };
      box.appendChild(el);
    }
    menu.classList.remove("hidden");
    const r = anchor.getBoundingClientRect();
    menu.style.left = Math.min(r.left, window.innerWidth - 240) + "px";
    menu.style.top = (r.bottom + 4) + "px";
    const off = (e) => { if (!menu.contains(e.target)) closeMenu(); };
    setTimeout(() => document.addEventListener("mousedown", off), 0);
    menuCleanup = () => document.removeEventListener("mousedown", off);
  }

  function closeMenu() {
    $("menu").classList.add("hidden");
    if (menuCleanup) { menuCleanup(); menuCleanup = null; }
  }

  function modelMenu() {
    openMenu($("modelBtn"), [
      { label: "Model" },
      ...MODELS.map((m) => ({
        text: fmtModel(m), on: m === model,
        action: () => { send({ type: "set_model", model: m }); model = m; renderHeader(); },
      })),
    ]);
  }

  function modeMenu() {
    const order = ["default", "acceptEdits", "plan", "auto", "bypassPermissions"];
    openMenu($("modeBtn"), [
      { label: "Permission mode" },
      ...order.map((m) => ({
        text: MODE_LABEL[m], on: m === permMode,
        action: () => { send({ type: "set_mode", mode: m }); permMode = m; renderHeader(); },
      })),
    ]);
  }

  function sessionMenu(s, x, y) {
    const menu = $("menu");
    closeMenu();
    const box = $("menuItems");
    box.innerHTML = "";
    const items = [
      { text: "Rename", action: () => renameSession(s) },
      { text: s.archived ? "Unarchive" : "Archive", action: () => archiveSession(s) },
      { text: "Open in files", action: () => { switchPane("files"); } },
    ];
    for (const it of items) {
      const el = document.createElement("div");
      el.className = "mitem";
      el.innerHTML = `<span class="check"></span><span>${esc(it.text)}</span>`;
      el.onclick = () => { closeMenu(); it.action(); };
      box.appendChild(el);
    }
    menu.classList.remove("hidden");
    menu.style.left = x + "px";
    menu.style.top = y + "px";
    const off = (e) => { if (!menu.contains(e.target)) closeMenu(); };
    setTimeout(() => document.addEventListener("mousedown", off), 0);
    menuCleanup = () => document.removeEventListener("mousedown", off);
  }

  function renameSession(s) {
    openModal("Rename session", `<input id="mv" value="${esc(s.title || "")}">`, [
      { label: "Cancel" },
      { label: "Rename", primary: true, action: () => {
        const v = ($("mv").value || "").trim();
        if (v) {
          send({ type: "rename", title: v });
          s.title = v;
          renderSessions();
          renderHeader();
        }
      }},
    ]);
  }

  async function archiveSession(s) {
    try {
      await fetch(`/api/sessions/${s.id}/archive`, { method: "POST" });
      s.archived = !s.archived;
      renderSessions();
    } catch (e) { toast("Archive failed"); }
  }

  // -------------------------------------------------------------- modal
  function openModal(title, bodyHtml, buttons) {
    const m = $("modal");
    $("modalTitle").textContent = title;
    $("modalBody").innerHTML = bodyHtml;
    const bb = $("modalBtns");
    bb.innerHTML = "";
    for (const b of buttons) {
      const el = document.createElement("button");
      el.textContent = b.label;
      if (b.primary) el.className = "primary";
      el.onclick = () => {
        if (!b.action || b.action() !== false) m.classList.add("hidden");
      };
      bb.appendChild(el);
    }
    m.classList.remove("hidden");
  }

  // ---------------------------------------------------------- diff view
  async function refreshChanges() {
    if (!sessionId) return;
    try {
      const r = await fetch(`/api/diff?session=${encodeURIComponent(sessionId)}`);
      if (!r.ok) return;
      const data = await r.json();
      const diffs = data.diffs || [];
      const box = $("diffList");
      box.innerHTML = "";
      let adds = 0, dels = 0;
      if (!diffs.length) {
        box.innerHTML = '<div class="empty">No changes yet.</div>';
      } else {
        for (const d of diffs) {
          const counts = countDiff(d.diff);
          adds += counts.a; dels += counts.d;
          box.appendChild(renderDiffFile(d.path, d.diff, counts));
        }
      }
      $("dChangesVal").textContent = (adds || dels) ? `+${adds} -${dels}` : "No changes";
    } catch (e) { /* ignore */ }
  }

  function countDiff(diff) {
    let a = 0, d = 0;
    for (const line of String(diff || "").split("\n")) {
      if (line.startsWith("+") && !line.startsWith("+++")) a++;
      else if (line.startsWith("-") && !line.startsWith("---")) d++;
    }
    return { a, d };
  }

  function renderDiffFile(path, diff, counts) {
    const box = document.createElement("div");
    box.className = "difffile";
    const head = document.createElement("div");
    head.className = "dfhead";
    head.innerHTML = `<span>${esc(path)}</span><span class="stat">+${counts.a} -${counts.d}</span>`;
    box.appendChild(head);

    let oldLn = 0, newLn = 0;
    for (const line of String(diff || "").split("\n")) {
      const row = document.createElement("div");
      if (line.startsWith("@@")) {
        const m = line.match(/@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@/);
        if (m) { oldLn = parseInt(m[1], 10); newLn = parseInt(m[2], 10); }
        row.className = "diffline hunk";
        row.innerHTML = `<span class="ln"></span><span class="sign"></span>` +
          `<span class="src">${esc(line)}</span>`;
      } else if (line.startsWith("+++") || line.startsWith("---")) {
        continue;
      } else if (line.startsWith("+")) {
        row.className = "diffline add";
        row.innerHTML = `<span class="ln">${newLn++}</span><span class="sign">+</span>` +
          `<span class="src">${esc(line.slice(1))}</span>` +
          `<span class="cmt" title="Comment on this line">+</span>`;
      } else if (line.startsWith("-")) {
        row.className = "diffline del";
        row.innerHTML = `<span class="ln">${oldLn++}</span><span class="sign">-</span>` +
          `<span class="src">${esc(line.slice(1))}</span>` +
          `<span class="cmt" title="Comment on this line">+</span>`;
      } else if (line.length) {
        row.className = "diffline";
        row.innerHTML = `<span class="ln">${newLn++}</span><span class="sign"> </span>` +
          `<span class="src">${esc(line.slice(1))}</span>`;
        oldLn++;
      }
      if (row.className) box.appendChild(row);
    }
    return box;
  }

  function showDiff(path, diff) {
    switchPane("changes");
    refreshChanges();
  }

  // ---------------------------------------------------------- files pane
  async function refreshFiles() {
    if (!cwd) return;
    const tree = $("fileTree");
    try {
      const r = await fetch(`/api/files?cwd=${encodeURIComponent(cwd)}`);
      if (!r.ok) { tree.innerHTML = '<div class="empty">—</div>'; return; }
      const data = await r.json();
      tree.innerHTML = "";
      const walk = (entries, prefix) => {
        for (const e of entries) {
          const el = document.createElement("div");
          if (e.dir) {
            el.className = "fdir";
            el.textContent = "▾ " + e.name;
            tree.appendChild(el);
            if (e.children) walk(e.children, prefix + e.name + "/");
          } else {
            el.className = "ffile";
            el.textContent = e.name;
            el.onclick = () => openFile(prefix + e.name);
            tree.appendChild(el);
          }
        }
      };
      walk(data.entries || [], "");
      if (!(data.entries || []).length) tree.innerHTML = '<div class="empty">—</div>';
    } catch (e) { tree.innerHTML = '<div class="empty">—</div>'; }
  }

  async function openFile(path) {
    try {
      const r = await fetch(`/api/file?cwd=${encodeURIComponent(cwd)}&path=${encodeURIComponent(path)}`);
      if (!r.ok) { $("fileView").innerHTML = '<div class="empty">Cannot read file.</div>'; return; }
      const data = await r.json();
      $("fileView").innerHTML = `<pre>${esc(data.content || "")}</pre>`;
    } catch (e) {
      $("fileView").innerHTML = '<div class="empty">Cannot read file.</div>';
    }
  }

  // -------------------------------------------------------------- panes
  function switchPane(name) {
    pane = name;
    document.querySelectorAll(".ptab").forEach((t) => {
      t.classList.toggle("active", t.dataset.pane === name);
    });
    document.querySelectorAll(".panebody").forEach((b) => {
      b.classList.toggle("show", b.id === "pane-" + name);
    });
    if (name === "changes") refreshChanges();
    if (name === "files") refreshFiles();
  }

  document.querySelectorAll(".ptab[data-pane]").forEach((t) => {
    t.onclick = () => switchPane(t.dataset.pane);
  });

  // ------------------------------------------------------------ controls
  $("newSession").onclick = () => {
    send({ type: "new_session" });
    sessionId = null;
    chat.innerHTML = "";
    closeStream();
    toolCards.clear();
    toast("New session");
  };

  $("sessionSearch").oninput = renderSessions;

  $("toggleArchive").onclick = () => {
    showArchived = !showArchived;
    $("toggleArchive").classList.toggle("on", showArchived);
    renderSessions();
  };

  $("modelBtn").onclick = modelMenu;
  $("modeBtn").onclick = modeMenu;

  $("cwdBtn").onclick = () => {
    openModal("Project folder",
      `<input id="cwdin" value="${esc(cwd)}" placeholder="C:\\path\\to\\project">`,
      [
        { label: "Cancel" },
        { label: "Use folder", primary: true, action: () => {
          const v = ($("cwdin").value || "").trim();
          if (v) {
            cwd = v;
            send({ type: "new_session", cwd: v });
            $("cwdBtn").textContent = fmtCwd(v);
          }
        }},
      ]);
  };

  $("worktreeBtn").onclick = () => {
    const s = sessions.find((x) => x.id === sessionId);
    const on = !(s && s.worktree);
    send({ type: "new_session", worktree: on });
    $("worktreeBtn").classList.toggle("on", on);
    toast(on ? "Starting in a git worktree" : "Starting in the project folder");
  };

  $("envBtn").onclick = () => {
    openMenu($("envBtn"), [
      { label: "Environment" },
      { text: "Local", on: true, action: () => {} },
      { text: "Cloud (coming soon)", action: () => toast("Cloud execution is not available yet") },
      { text: "SSH (coming soon)", action: () => toast("SSH execution is not available yet") },
    ]);
  };

  $("viewMode").onclick = () => {
    const i = VIEW_MODES.indexOf(viewMode);
    viewMode = VIEW_MODES[(i + 1) % VIEW_MODES.length];
    localStorage.setItem("kali_viewmode", viewMode);
    $("viewMode").textContent = viewMode[0].toUpperCase() + viewMode.slice(1);
  };
  $("viewMode").textContent = viewMode[0].toUpperCase() + viewMode.slice(1);

  $("railToggle").onclick = () => {
    $("app").classList.toggle("no-details");
  };

  $("stopAll").onclick = () => send({ type: "interrupt" });

  $("dChanges").onclick = () => switchPane("changes");
  $("dContext").onclick = () => switchPane("chat");

  $("attach").onclick = () => $("fileInput").click();
  $("fileInput").onchange = (e) => {
    const f = e.target.files && e.target.files[0];
    if (!f) return;
    attachment = f.name;
    toast(`Attached ${f.name}`);
    e.target.value = "";
  };

  // ------------------------------------------------------- side chat
  $("sideChat").onclick = () => {
    $("sideChatBox").classList.toggle("hidden");
    $("sideInput").focus();
  };
  $("sideClose").onclick = () => $("sideChatBox").classList.add("hidden");
  $("sideSend").onclick = askSide;
  $("sideInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); askSide(); }
  });

  async function askSide() {
    const q = $("sideInput").value.trim();
    if (!q) return;
    $("sideInput").value = "";
    const log = $("sideLog");
    const qe = document.createElement("div");
    qe.className = "sline q"; qe.textContent = q;
    log.appendChild(qe);
    const ae = document.createElement("div");
    ae.className = "sline a"; ae.textContent = "…";
    log.appendChild(ae);
    log.scrollTop = log.scrollHeight;
    try {
      const r = await fetch("/api/side-chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session: sessionId, question: q }),
      });
      const data = await r.json();
      ae.textContent = data.answer || data.error || "No answer.";
    } catch (e) {
      ae.textContent = "Side chat failed.";
    }
    log.scrollTop = log.scrollHeight;
  }

  // ---------------------------------------------------------- shortcuts
  $("showShortcuts").onclick = () => {
    openModal("Keyboard shortcuts", `
      <table style="width:100%;font-size:12.5px;border-collapse:collapse">
        ${[
          ["Ctrl+N", "New session"], ["Ctrl+Tab", "Next session"],
          ["Ctrl+;", "Side chat"], ["Ctrl+O", "Cycle view mode"],
          ["Ctrl+Shift+M", "Permission mode"], ["Ctrl+Shift+I", "Model"],
          ["Esc", "Stop the response"], ["Enter", "Send"],
          ["Shift+Enter", "New line"], ["Ctrl+Shift+D", "Toggle diff pane"],
        ].map(([k, v]) => `<tr><td style="padding:3px 8px 3px 0;color:var(--accent);font-family:var(--mono)">${k}</td><td>${v}</td></tr>`).join("")}
      </table>`, [{ label: "Close", primary: true }]);
  };

  document.addEventListener("keydown", (e) => {
    const typing = /^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName);
    if (e.key === "Escape") {
      if (!$("modal").classList.contains("hidden")) { $("modal").classList.add("hidden"); return; }
      if (busy) { send({ type: "interrupt" }); return; }
    }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "n") {
      e.preventDefault(); $("newSession").click();
    } else if ((e.ctrlKey || e.metaKey) && e.key === ";") {
      e.preventDefault(); $("sideChat").click();
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "o") {
      e.preventDefault(); $("viewMode").click();
    } else if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "m") {
      e.preventDefault(); modeMenu();
    } else if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "i") {
      e.preventDefault(); modelMenu();
    } else if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === "d") {
      e.preventDefault(); switchPane(pane === "changes" ? "chat" : "changes");
    } else if (e.key === "Tab" && !typing && !$("suggestion").classList.contains("hidden")) {
      e.preventDefault(); acceptSuggestion();
    }
  });

  // ------------------------------------------------------------- prompt
  const input = $("input");
  function autoGrow() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 220) + "px";
  }
  input.addEventListener("input", () => {
    autoGrow();
    $("suggestion").classList.add("hidden");
    if (input.value.trim().startsWith("/")) showSlashMenu();
  });
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); submit(); }
  });

  function setSendLabel() {
    const b = $("send");
    b.textContent = busy ? "■" : "↑";
    b.classList.toggle("stop", busy);
  }

  $("send").onclick = () => {
    if (busy) { send({ type: "interrupt" }); return; }
    submit();
  };

  function submit() {
    let text = input.value.trim();
    if (!text || busy || !ws || ws.readyState !== 1) return;
    if (attachment) { text = `${text}\n\n@${attachment}`; attachment = null; }
    addMsg("user", `<div class="who">you</div><div class="bubble">${esc(text)}</div>`);
    input.value = "";
    autoGrow();
    busy = true;
    setStatus("run");
    setSendLabel();
    send({ type: "prompt", text });
  }

  // ---------------------------------------------------- slash commands
  const SLASH = [
    ["/help", "Show available commands"],
    ["/clear", "Clear the conversation"],
    ["/model", "Choose the model"],
    ["/mode", "Change the permission mode"],
    ["/diff", "Show changed files"],
    ["/plan", "Enter plan mode"],
    ["/compact", "Compact the context"],
    ["/cost", "Show token usage"],
    ["/status", "Show session status"],
    ["/code-review", "Review the pending changes"],
    ["/btw", "Ask a side question"],
  ];

  function showSlashMenu() {
    const q = input.value.trim();
    const hits = SLASH.filter(([c]) => c.startsWith(q)).slice(0, 8);
    if (!hits.length) return;
    const menu = $("menu");
    const box = $("menuItems");
    box.innerHTML = "";
    for (const [cmd, desc] of hits) {
      const el = document.createElement("div");
      el.className = "mitem";
      el.innerHTML = `<span class="check"></span><span style="font-family:var(--mono)">${esc(cmd)}</span>` +
        `<span class="mdesc">${esc(desc)}</span>`;
      el.onclick = () => { closeMenu(); input.value = cmd + " "; input.focus(); };
      box.appendChild(el);
    }
    menu.classList.remove("hidden");
    const r = input.getBoundingClientRect();
    menu.style.left = r.left + "px";
    menu.style.top = (r.top - 6) + "px";
    const off = (e) => { if (!menu.contains(e.target) && e.target !== input) closeMenu(); };
    setTimeout(() => document.addEventListener("mousedown", off), 0);
    menuCleanup = () => document.removeEventListener("mousedown", off);
  }

  // ------------------------------------------------------- suggestions
  function showSuggestion(text) {
    const el = $("suggestion");
    el.textContent = text;
    el.classList.remove("hidden");
    el.onclick = acceptSuggestion;
  }
  function acceptSuggestion() {
    input.value = $("suggestion").textContent;
    $("suggestion").classList.add("hidden");
    input.focus();
    autoGrow();
  }

  // ---------------------------------------------------------------- init
  setSendLabel();
  updateContext();
})();

const $ = (id) => document.getElementById(id);

let cursor = null;

/* 按人筛选：列表与搜索各自独立，空串表示不限 */
const personFilter = { list: "", search: "" };

/* 日期筛选状态：kind = all | today | yesterday | 7d | day */
const filters = {
  list: { kind: "all", day: "" },
  search: { kind: "all", day: "" },
};

const pad = (n) => String(n).padStart(2, "0");

function ymd(d) {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

function shiftDay(base, delta) {
  const d = new Date(base.getFullYear(), base.getMonth(), base.getDate());
  d.setDate(d.getDate() + delta);
  return d;
}

function rangeOf(f) {
  if (f.day) return { start: f.day, end: f.day };
  const today = new Date();
  if (f.kind === "today") return { start: ymd(today), end: ymd(today) };
  if (f.kind === "yesterday") {
    const y = ymd(shiftDay(today, -1));
    return { start: y, end: y };
  }
  if (f.kind === "7d") return { start: ymd(shiftDay(today, -6)), end: ymd(today) };
  return { start: "", end: "" };
}

function rangeQuery(f) {
  const r = rangeOf(f);
  let qs = "";
  if (r.start) qs += `&start=${r.start}`;
  if (r.end) qs += `&end=${r.end}`;
  return qs;
}

function personQuery(scope) {
  const p = personFilter[scope];
  return p ? `&person=${encodeURIComponent(p)}` : "";
}

async function loadPersons() {
  const list = await api("/api/persons?limit=500");
  for (const id of ["person-sel", "s-person-sel"]) {
    const sel = $(id);
    const kept = sel.value;
    sel.innerHTML = "";
    const none = document.createElement("option");
    none.value = "";
    none.textContent = "按人…";
    sel.append(none);
    list.forEach((p) => {
      const opt = document.createElement("option");
      opt.value = p.name;
      opt.textContent = `${p.name}（${p.count}）`;
      sel.append(opt);
    });
    sel.value = kept;
  }
}

/* 日期分组小标题：2026-11-10 → 11月10日 · 周一 */
function dayLabel(day) {
  const parts = (day || "").split("-");
  if (parts.length !== 3) return day;
  const d = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  const week = "日一二三四五六"[d.getDay()];
  return `${Number(parts[1])}月${Number(parts[2])}日 · 周${week}`;
}

function dayHeadEl(day) {
  const li = document.createElement("li");
  li.className = "dayhead";
  li.textContent = dayLabel(day);
  return li;
}

function showTab(name) {
  document.querySelectorAll(".tab").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === name);
  });
  document.querySelectorAll(".panel").forEach((p) => {
    p.classList.toggle("active", p.id === "panel-" + name);
  });
  if (name === "list") loadList(true);
  if (name === "write") $("note").focus();
  if (name === "me") $("question").focus();
}

function fmt(ts) {
  return (ts || "").replace("T", " ").slice(0, 16);
}

function escReg(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/* 把命中的词包成 <mark>，正文永远走 textContent，不拼 HTML */
function fillText(el, text, terms) {
  el.textContent = "";
  const words = (terms || []).filter(Boolean);
  if (!words.length) {
    el.textContent = text;
    return;
  }
  const pattern = new RegExp("(" + words.map(escReg).join("|") + ")", "gi");
  for (const part of text.split(pattern)) {
    if (!part) continue;
    if (words.some((w) => part.toLowerCase() === w.toLowerCase())) {
      const mark = document.createElement("mark");
      mark.textContent = part;
      el.append(mark);
    } else {
      el.append(document.createTextNode(part));
    }
  }
}

const SOURCE_LABEL = { wechat: "微信", qq: "QQ", note: "随手记" };

function sourceLabel(s) {
  return SOURCE_LABEL[s] || s || "";
}

function whoLabel(m) {
  const raw = m.conv || "";
  const isGroup = raw.endsWith("@chatroom");
  const conv = raw && raw !== "自己" && !isGroup ? raw : "";
  const sender = m.sender || "";
  const named =
    sender && sender !== "me" && !sender.startsWith("wxid_") && !sender.endsWith("@chatroom");
  let tail = "";
  if (isGroup) tail = named ? `群 · ${sender}` : "群";
  else if (named && sender !== conv) tail = sender;
  if (conv && tail) return ` · ${conv} · ${tail}`;
  if (conv) return ` · ${conv}`;
  return tail ? ` · ${tail}` : "";
}

function itemEl(m, terms) {
  const li = document.createElement("li");

  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = `${fmt(m.ts)} · ${sourceLabel(m.source)}${whoLabel(m)}`;

  const text = document.createElement("div");
  text.className = "text";
  fillText(text, m.text, terms);

  const actions = document.createElement("div");
  actions.className = "item-actions";
  actions.append(
    actionBtn("编辑", () => editItem(m)),
    actionBtn("删除", () => removeItem(m, li)),
  );

  li.append(meta, text, actions);
  return li;
}

function actionBtn(label, onClick) {
  const b = document.createElement("button");
  b.className = "mini";
  b.textContent = label;
  b.addEventListener("click", onClick);
  return b;
}

async function api(path, options) {
  const res = await fetch(path, options);
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(`${res.status} ${detail.slice(0, 120)}`);
  }
  return res.json();
}

async function refreshStatus() {
  const h = await api("/api/health");
  $("status").textContent = `${h.messages} 条 · ${(h.db_bytes / 1024).toFixed(0)} KB`;
}

function activeTab() {
  const tab = document.querySelector(".tab.active");
  return tab ? tab.dataset.tab : "write";
}

async function refreshCurrent() {
  await refreshStatus();
  const tab = activeTab();
  if (tab === "search") await search();
  if (tab === "list") await loadList(true);
}

function rangeLabel(f) {
  const r = rangeOf(f);
  if (!r.start) return "全部";
  if (r.start === r.end) return r.start;
  return `${r.start} ~ ${r.end}`;
}

async function loadDays() {
  const list = await api("/api/days");
  for (const id of ["day-sel", "s-day-sel"]) {
    const sel = $(id);
    const kept = sel.value;
    sel.innerHTML = "";
    const optAll = document.createElement("option");
    optAll.value = "";
    optAll.textContent = "按日期…";
    sel.append(optAll);
    list.forEach((d) => {
      const opt = document.createElement("option");
      opt.value = d.day;
      opt.textContent = `${d.day}（${d.count}）`;
      sel.append(opt);
    });
    sel.value = kept;
  }
}

async function loadList(reset = true) {
  if (reset) cursor = null;
  const f = filters.list;
  let qs = `?limit=30${rangeQuery(f)}${personQuery("list")}`;
  if (cursor) qs += `&before_id=${cursor}`;
  const rows = await api("/api/messages" + qs);
  const ul = $("list");
  if (reset) {
    ul.innerHTML = "";
    ul.dataset.lastDay = "";
  }
  let lastDay = ul.dataset.lastDay || "";
  rows.forEach((m) => {
    const day = (m.ts || "").slice(0, 10);
    if (day && day !== lastDay) {
      ul.append(dayHeadEl(day));
      lastDay = day;
    }
    ul.append(itemEl(m, []));
  });
  ul.dataset.lastDay = lastDay;
  if (rows.length) cursor = rows[rows.length - 1].id;
  $("more").hidden = rows.length < 30;
  $("list-count").textContent = reset ? `${rangeLabel(f)} · ${rows.length} 条` : "";
  if (reset && !rows.length) {
    ul.innerHTML = '<li class="empty">这段时间还没有记录</li>';
  }
}

async function save() {
  const text = $("note").value.trim();
  if (!text) return;
  const res = await api("/api/messages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text }),
  });
  $("hint").textContent = res.duplicated ? "和之前一条完全一样，跳过了" : "已记下";
  if (!res.duplicated) {
    $("note").value = "";
    refreshStatus();
  }
  setTimeout(() => ($("hint").textContent = ""), 2500);
}

async function editItem(m) {
  const next = window.prompt("改这条记录（清空等于取消）：", m.text);
  if (next === null) return;
  const text = next.trim();
  if (!text || text === m.text) return;
  try {
    await api(`/api/messages/${m.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text }),
    });
    await refreshCurrent();
  } catch (err) {
    window.alert("没改成：" + err.message);
  }
}

async function removeItem(m, li) {
  if (!window.confirm("删掉这条？删了就没了。\n\n" + m.text.slice(0, 40))) return;
  try {
    await api(`/api/messages/${m.id}`, { method: "DELETE" });
    li.remove();
    await refreshStatus();
  } catch (err) {
    window.alert("没删掉：" + err.message);
  }
}

async function search() {
  const q = $("q").value.trim();
  const ul = $("results");
  if (!q) return;
  const terms = q.split(/\s+/).filter(Boolean);
  const rows = await api(
    "/api/search?limit=50&q=" + encodeURIComponent(q) + rangeQuery(filters.search) + personQuery("search"),
  );
  ul.innerHTML = "";
  let lastDay = "";
  rows.forEach((m) => {
    const day = (m.ts || "").slice(0, 10);
    if (day && day !== lastDay) {
      ul.append(dayHeadEl(day));
      lastDay = day;
    }
    ul.append(itemEl(m, terms));
  });
  if (!rows.length) ul.innerHTML = '<li class="empty">这段时间没搜到，换个词或换个日期</li>';
}

function citationEl(c, index) {
  const li = document.createElement("li");
  const meta = document.createElement("div");
  meta.className = "meta";
  meta.textContent = `引用 [${index}] · ${fmt(c.ts)}`;
  const text = document.createElement("div");
  text.className = "text";
  text.textContent = c.text;
  li.append(meta, text);
  return li;
}

async function ask() {
  const q = $("question").value.trim();
  if (!q) return;
  const box = $("answer");
  const ul = $("citations");
  box.hidden = false;
  box.textContent = "…";
  ul.innerHTML = "";
  try {
    const res = await api("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q }),
    });
    box.textContent = res.answer;
    res.citations.forEach((c, i) => ul.append(citationEl(c, i + 1)));
  } catch (err) {
    box.textContent = "没问成：" + err.message;
  }
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch {
    window.prompt("手动复制这条：", text);
    return false;
  }
}

function candidateEl(text) {
  const li = document.createElement("li");
  const body = document.createElement("div");
  body.className = "text";
  body.textContent = text;

  const actions = document.createElement("div");
  actions.className = "item-actions";
  const btn = actionBtn("复制", async () => {
    if (await copyText(text)) {
      btn.textContent = "已复制";
      setTimeout(() => (btn.textContent = "复制"), 1500);
    }
  });
  actions.append(btn);

  li.append(body, actions);
  return li;
}

async function doDraft() {
  const theirs = $("theirs").value.trim();
  const intent = $("intent").value.trim();
  const hint = $("draft-hint");
  const ul = $("drafts");
  if (!theirs) {
    hint.textContent = "先贴对方的话";
    return;
  }
  hint.textContent = "…";
  try {
    const res = await api("/api/draft", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ theirs, intent }),
    });
    ul.innerHTML = "";
    res.candidates.forEach((t) => ul.append(candidateEl(t)));
    hint.textContent = `${res.candidates.length} 条草稿，审完自己发`;
  } catch (err) {
    hint.textContent = "没拟成：" + err.message;
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  document.querySelectorAll(".tab").forEach((b) => {
    b.addEventListener("click", () => showTab(b.dataset.tab));
  });
  $("save").addEventListener("click", save);
  $("note").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) save();
  });
  $("refresh").addEventListener("click", () => loadList(true));
  $("more").addEventListener("click", () => loadList(false));
  $("do-search").addEventListener("click", () => search());
  $("q").addEventListener("keydown", (e) => {
    if (e.key === "Enter") search();
  });
  $("ask").addEventListener("click", ask);
  $("question").addEventListener("keydown", (e) => {
    if (e.key === "Enter") ask();
  });
  $("do-draft").addEventListener("click", doDraft);

  document.querySelectorAll(".chip").forEach((b) => {
    b.addEventListener("click", () => {
      const scope = b.dataset.scope;
      filters[scope] = { kind: b.dataset.kind, day: "" };
      document
        .querySelectorAll(`.chip[data-scope="${scope}"]`)
        .forEach((x) => x.classList.toggle("active", x === b));
      (scope === "list" ? $("day-sel") : $("s-day-sel")).value = "";
      if (scope === "list") loadList(true);
      else if ($("q").value.trim()) search();
    });
  });

  for (const [scope, id] of [
    ["list", "day-sel"],
    ["search", "s-day-sel"],
  ]) {
    $(id).addEventListener("change", (e) => {
      const day = e.target.value;
      filters[scope] = day ? { kind: "day", day } : { kind: "all", day: "" };
      document
        .querySelectorAll(`.chip[data-scope="${scope}"]`)
        .forEach((x) => x.classList.toggle("active", !day && x.dataset.kind === "all"));
      if (scope === "list") loadList(true);
      else if ($("q").value.trim()) search();
    });
  }

  for (const [scope, id] of [
    ["list", "person-sel"],
    ["search", "s-person-sel"],
  ]) {
    $(id).addEventListener("change", (e) => {
      personFilter[scope] = e.target.value;
      if (scope === "list") loadList(true);
      else if ($("q").value.trim()) search();
    });
  }

  refreshStatus();
  await loadDays();
  await loadPersons();

  const askQ = new URLSearchParams(location.search).get("ask");
  if (askQ) {
    $("question").value = askQ;
    showTab("me");
    ask();
    return;
  }
  const q = new URLSearchParams(location.search).get("q");
  const day = new URLSearchParams(location.search).get("day");
  const person = new URLSearchParams(location.search).get("person");
  if (person) {
    personFilter.list = person;
    personFilter.search = person;
    $("person-sel").value = person;
    $("s-person-sel").value = person;
  }
  if (day) {
    filters.list = { kind: "day", day };
    $("day-sel").value = day;
    showTab("list");
  } else if (q) {
    $("q").value = q;
    showTab("search");
    search();
  } else if (location.hash === "#list") {
    showTab("list");
  } else if (location.hash === "#me") {
    showTab("me");
  } else {
    showTab("write");
  }
});

const $ = (id) => document.getElementById(id);
const REFRESH_MS = 20000;

async function api(path, options) {
  const res = await fetch(path, options);
  if (res.status === 401) {
    location.replace("/login");
    throw new Error("需要口令");
  }
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.message || `HTTP ${res.status}`);
  }
  return res.json();
}

function ago(minutes) {
  if (minutes < 1) return "刚刚";
  if (minutes < 60) return `${minutes} 分钟前`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} 小时前`;
  return `${Math.floor(hours / 24)} 天前`;
}

function itemEl(item) {
  const li = document.createElement("li");
  li.className = "witem";

  const head = document.createElement("div");
  head.className = "whead";
  const who = document.createElement("strong");
  who.textContent = item.conv;
  const when = document.createElement("span");
  when.className = "wtime";
  when.textContent = ago(item.minutes_ago);
  head.append(who, when);

  const text = document.createElement("p");
  text.className = "wtext";
  text.textContent = item.text;

  const actions = document.createElement("div");
  actions.className = "wactions";
  const draftBtn = document.createElement("button");
  draftBtn.className = "mini";
  draftBtn.textContent = "拟两句";
  const copyBtn = document.createElement("button");
  copyBtn.className = "mini";
  copyBtn.textContent = "复制原话";
  actions.append(draftBtn, copyBtn);

  const box = document.createElement("div");
  box.className = "wdrafts";
  box.hidden = true;

  copyBtn.addEventListener("click", async () => {
    await copyText(item.text);
    copyBtn.textContent = "已复制";
    setTimeout(() => (copyBtn.textContent = "复制原话"), 1200);
  });

  draftBtn.addEventListener("click", async () => {
    if (!box.hidden) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    box.textContent = "想呢…";
    try {
      const data = await api("/api/draft", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ theirs: item.text, intent: "" }),
      });
      box.textContent = "";
      data.candidates.forEach((line, i) => {
        const row = document.createElement("div");
        row.className = "wdraft";
        const span = document.createElement("span");
        span.textContent = line;
        const btn = document.createElement("button");
        btn.className = "mini";
        btn.textContent = "复制";
        btn.addEventListener("click", async () => {
          await copyText(line);
          btn.textContent = "已复制";
          setTimeout(() => (btn.textContent = "复制"), 1200);
        });
        row.append(span, btn);
        box.append(row);
      });
    } catch (err) {
      box.textContent = err.message;
    }
  });

  li.append(head, text, actions, box);
  return li;
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const ta = document.createElement("textarea");
    ta.value = text;
    document.body.append(ta);
    ta.select();
    document.execCommand("copy");
    ta.remove();
  }
}

async function load() {
  $("wstatus").textContent = "刷新中…";
  try {
    const data = await api("/api/inbox?minutes=2&limit=30");
    const items = data.items || [];
    const list = $("wlist");
    list.textContent = "";
    items.forEach((item) => list.append(itemEl(item)));
    $("wcount").textContent = items.length ? `${items.length} 个` : "空";
    $("wempty").hidden = items.length > 0;
    $("wstatus").textContent = `更新于 ${new Date().toLocaleTimeString("zh-CN", { hour12: false })}`;
  } catch (err) {
    $("wstatus").textContent = err.message;
  }
}

$("wrefresh").addEventListener("click", load);
document.addEventListener("DOMContentLoaded", () => {
  load();
  setInterval(load, REFRESH_MS);
});

/* 只缓存外壳，接口永远走网络：记录是隐私，不往缓存里塞。
 *
 * 导航请求（打开页面）走网络优先：退出登录后服务器会回 303 去登录页，
 * 这一步不能被缓存挡掉；只有断网时才回落到缓存的主壳。
 * 静态资源走「先给缓存、再悄悄更新」（stale-while-revalidate）。
 */
const SHELL = "shell-v3";
const FILES = ["/", "/style.css", "/app.js", "/manifest.webmanifest", "/icon.svg"];

/** 把一份导航响应存成主壳（跳过重定向到登录页的响应，别把登录页当首页缓存） */
function rememberShell(res) {
  if (!res || !res.ok || res.redirected) return;
  if (new URL(res.url).pathname !== "/") return;
  const copy = res.clone();
  caches.open(SHELL).then((c) => c.put("/", copy)).catch(() => {});
}

/** 导航：先问网络；断了才用缓存 */
async function networkFirst(request) {
  try {
    const res = await fetch(request);
    /* 服务器把我们送去别处（比如没登录时 303 到 /login）：
       Service Worker 替浏览器挡下这一跳的话，地址栏不会跟着变，
       所以这里把重定向原样还给浏览器，让它自己跳。 */
    if (res.redirected) return Response.redirect(res.url, 303);
    rememberShell(res);
    return res;
  } catch (err) {
    const hit = await caches.match("/");
    if (hit) return hit;
    throw err;
  }
}

/** 静态资源：缓存立即可用，后台顺手更新 */
async function staleWhileRevalidate(request) {
  const cache = await caches.open(SHELL);
  const hit = await cache.match(request);
  const net = fetch(request)
    .then((res) => {
      if (res && res.ok) cache.put(request, res.clone()).catch(() => {});
      return res;
    })
    .catch(() => hit);
  return hit || net;
}

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(SHELL).then((c) => c.addAll(FILES)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== SHELL).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (e.request.method !== "GET" || url.origin !== location.origin) return;
  if (url.pathname.startsWith("/api/")) return; // 记录相关的一律不缓存

  if (e.request.mode === "navigate") {
    e.respondWith(networkFirst(e.request));
    return;
  }
  e.respondWith(staleWhileRevalidate(e.request));
});

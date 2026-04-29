// ── SafeCam Service Worker ──
const CACHE_NAME = 'safecam-v2';
const STATIC_ASSETS = [
  '/',
  '/static/css/main.css',
  '/static/js/app.js',
  '/static/js/auth.js',
  '/static/js/websocket.js',
  '/static/js/camera-grid.js',
  '/static/js/stats.js',
  '/static/js/alerts.js',
  '/static/js/logs.js',
  '/static/js/camera-mgmt.js',
  '/static/js/user-mgmt.js',
  '/static/js/playback.js',
  '/manifest.json',
];

// 安装事件：缓存静态资源
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      console.log('[SW] 缓存静态资源');
      return cache.addAll(STATIC_ASSETS);
    })
  );
  self.skipWaiting();
});

// 激活事件：清理旧缓存
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    })
  );
  self.clients.claim();
});

// 请求拦截：网络优先，缓存回退
self.addEventListener('fetch', (event) => {
  const { request } = event;

  // 跳过非 GET 请求和 API 请求
  if (request.method !== 'GET') return;
  if (request.url.includes('/api/') || request.url.includes('/video_feed') || request.url.includes('/playback')) {
    return;
  }

  event.respondWith(
    fetch(request)
      .then((response) => {
        // 成功则更新缓存
        if (response && response.status === 200) {
          const responseClone = response.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(request, responseClone);
          });
        }
        return response;
      })
      .catch(() => {
        // 网络失败则从缓存读取
        return caches.match(request).then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }
          // 如果是页面请求，返回离线页面
          if (request.headers.get('accept')?.includes('text/html')) {
            return caches.match('/');
          }
          return new Response('离线模式', { status: 503, statusText: 'Service Unavailable' });
        });
      })
  );
});

// 推送通知事件
self.addEventListener('push', (event) => {
  let data = { title: 'SafeCam 告警', body: '收到新的告警通知' };

  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body,
    icon: '/static/icons/icon-192.png',
    badge: '/static/icons/icon-192.png',
    vibrate: [200, 100, 200],
    data: data.data || {},
    actions: data.actions || [],
    tag: data.tag || 'safecam-alert',
    renotify: true,
  };

  event.waitUntil(
    self.registration.showNotification(data.title, options)
  );
});

// 通知点击事件
self.addEventListener('notificationclick', (event) => {
  event.notification.close();

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      // 如果已有窗口打开，聚焦它
      for (const client of clientList) {
        if (client.url.includes(self.location.origin) && 'focus' in client) {
          return client.focus();
        }
      }
      // 否则打开新窗口
      return clients.openWindow('/');
    })
  );
});

// 后台同步事件（用于离线时缓存告警）
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-alerts') {
    event.waitUntil(syncAlerts());
  }
});

async function syncAlerts() {
  // 这里可以实现离线时缓存的告警同步逻辑
  console.log('[SW] 同步告警数据');
}

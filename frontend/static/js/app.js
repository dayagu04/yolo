// ── 主应用入口 ──
import { checkAuth, showLogin, doLogin } from './auth.js';
import { connectWS, onMessage } from './websocket.js';
import { loadCameras, flashAlertBanner, updateCamStatus, updateCamStats, getCameras } from './camera-grid.js';
import { startStatsPolling, stopStatsPolling } from './stats.js';
import { loadAlerts, changePage, exportCSV } from './alerts.js';
import { addLog } from './logs.js';
import { showCameraManagement, showAddCameraModal, hideAddCameraModal, addCamera, removeCamera } from './camera-mgmt.js';
import { showUserManagement } from './user-mgmt.js';
import { showPlayback, togglePlayback, refreshPlayback } from './playback.js';
import { authFetch } from './auth.js';

let footerInterval = null;

// 暴露全局函数供 HTML onclick 使用
window.switchTab = switchTab;
window.doLogin = doLogin;
window.changePage = changePage;
window.exportCSV = exportCSV;
window.openLightbox = openLightbox;
window.closeLightbox = closeLightbox;
window.showAddCameraModal = showAddCameraModal;
window.hideAddCameraModal = hideAddCameraModal;
window.addCamera = addCamera;
window.removeCamera = removeCamera;
window.togglePlayback = togglePlayback;
window.refreshPlayback = refreshPlayback;

function switchTab(name, btn) {
  document.querySelectorAll('.tab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.tab-btn').forEach(el => el.classList.remove('active'));
  document.getElementById('tab-' + name)?.classList.add('active');
  if (btn) btn.classList.add('active');

  if (name === 'stats') startStatsPolling();
  else stopStatsPolling();

  if (name === 'alerts') loadAlerts(1);
  if (name === 'cameras') showCameraManagement();
  if (name === 'users') showUserManagement();
  if (name === 'playback') showPlayback();
}

function openLightbox(src) {
  document.getElementById('lightbox-img').src = src;
  document.getElementById('lightbox').classList.add('open');
}

function closeLightbox() {
  document.getElementById('lightbox').classList.remove('open');
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeLightbox(); });

function handleMessage(msg) {
  addLog(msg);
  if (msg.type === 'alert') {
    flashAlertBanner(msg.camera_id, msg.message);
    if (document.getElementById('tab-alerts')?.classList.contains('active')) {
      loadAlerts(1);
    }
  }
  if (msg.type === 'status') {
    updateCamStatus(msg.camera_id, msg);
  }
}

function fmtUptime(sec) {
  if (!sec) return '—';
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  return `${h}h ${m}m ${s}s`;
}

async function loadHealth() {
  try {
    const res = await authFetch('/health');
    const data = await res.json();
    document.getElementById('ft-ws').textContent = data.ws_clients ?? '—';
    document.getElementById('ft-uptime').textContent = fmtUptime(data.uptime_sec);
    document.getElementById('ft-db').textContent = data.subsystems?.database ?? '—';
    document.getElementById('ft-redis').textContent = data.subsystems?.redis ?? '—';
    document.getElementById('ft-model').textContent = data.subsystems?.model ?? '—';

    const online = (data.cameras || []).filter(c => c.connected).length;
    const total = data.camera_count || 0;
    const totalAlerts = (data.cameras || []).reduce((s, c) => s + (c.alert_total || 0), 0);
    document.getElementById('stat-total').textContent = totalAlerts;
    document.getElementById('stat-cams').textContent = `${online}`;
    document.getElementById('ft-cams').textContent = `${online}/${total}`;

    (data.cameras || []).forEach(cam => updateCamStats(cam));
  } catch (e) { /* ignore */ }
}

async function bootstrapApp() {
  connectWS();
  onMessage(handleMessage);
  await loadCameras();
  await loadHealth();
  if (footerInterval) clearInterval(footerInterval);
  footerInterval = setInterval(loadHealth, 5000);

  try {
    const res = await authFetch('/api/v1/logs?limit=50');
    const data = await res.json();
    (data.logs || []).reverse().forEach(log => addLog(log));
  } catch (_) { }
}

// ── Init ──
window.addEventListener('DOMContentLoaded', async () => {
  document.getElementById('login-password')?.addEventListener('keydown', e => {
    if (e.key === 'Enter') doLogin();
  });

  if (!await checkAuth()) {
    showLogin();
    return;
  }

  await bootstrapApp();
});

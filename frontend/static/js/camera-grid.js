// ── 摄像头网格模块 ──
import { authFetch } from './auth.js';

let cameras = [];

export function getCameras() { return cameras; }

export async function loadCameras() {
  try {
    const res = await authFetch('/api/v1/cameras');
    const data = await res.json();
    cameras = data.cameras || [];
    renderCameraGrid();
    populateCameraFilter();
    return cameras;
  } catch (e) {
    console.error('loadCameras:', e);
    return [];
  }
}

export function renderCameraGrid() {
  const grid = document.getElementById('camera-grid');
  if (!grid) return;
  if (!cameras.length) {
    grid.innerHTML = '<div class="cam-placeholder">未配置摄像头</div>';
    return;
  }

  grid.innerHTML = '';
  cameras.forEach(cam => {
    const cell = document.createElement('div');
    cell.className = 'camera-cell';
    cell.id = `cam-cell-${cam.id}`;
    cell.ondblclick = () => cell.classList.toggle('expanded');

    cell.innerHTML = `
      <img src="/video_feed?camera_id=${cam.id}" alt="cam${cam.id}"
           onerror="this.style.display='none'; this.nextElementSibling && (this.nextElementSibling.style.display='flex')">
      <div class="cam-overlay">
        <span class="cam-name">${cam.name || 'CAM ' + cam.id}</span>
        <span style="font-size:11px;color:var(--muted);margin-left:4px">${cam.location || ''}</span>
        <span class="cam-status-dot ${cam.connected ? '' : 'offline'}" id="cam-dot-${cam.id}"></span>
      </div>
      <div class="cam-stats">
        <span id="cam-fps-${cam.id}">${(cam.fps || 0).toFixed(1)} fps</span>
        <span id="cam-persons-${cam.id}">\u{1F464} ${cam.active_tracks || 0}</span>
      </div>
      <div class="cam-alert-banner" id="cam-alert-${cam.id}">⚠ 检测到人员入侵</div>
    `;
    grid.appendChild(cell);
  });
}

export function flashAlertBanner(camId, msg) {
  const banner = document.getElementById(`cam-alert-${camId}`);
  if (!banner) return;
  banner.textContent = '⚠ ' + (msg || '检测到人员');
  banner.style.display = 'block';
  setTimeout(() => { banner.style.display = 'none'; }, 4000);
}

export function updateCamStatus(camId, msg) {
  const dot = document.getElementById(`cam-dot-${camId}`);
  if (dot) {
    const connected = msg.data?.camera_connected ?? true;
    dot.className = 'cam-status-dot ' + (connected ? '' : 'offline');
  }
}

export function updateCamStats(cam) {
  const fps = document.getElementById(`cam-fps-${cam.camera_id}`);
  if (fps) fps.textContent = `${(cam.fps || 0).toFixed(1)} fps`;
  const persons = document.getElementById(`cam-persons-${cam.camera_id}`);
  if (persons) persons.textContent = `\u{1F464} ${cam.active_tracks || 0}`;
  const dot = document.getElementById(`cam-dot-${cam.camera_id}`);
  if (dot) dot.className = 'cam-status-dot ' + (cam.connected ? '' : 'offline');
}

function populateCameraFilter() {
  const sel = document.getElementById('f-camera');
  if (!sel) return;
  sel.innerHTML = '<option value="">全部</option>';
  cameras.forEach(cam => {
    const opt = document.createElement('option');
    opt.value = cam.id;
    opt.textContent = `${cam.name || 'CAM ' + cam.id} (${cam.id})`;
    sel.appendChild(opt);
  });
}

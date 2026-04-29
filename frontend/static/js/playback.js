// ── 录像回放模块 ──
import { authFetch } from './auth.js';

let playbackInterval = null;
let isPlaying = false;

export function showPlayback() {
  const container = document.getElementById('tab-playback');
  if (!container) return;

  container.innerHTML = `
    <div class="playback-container">
      <div class="playback-header">
        <h3>录像回放</h3>
        <div class="playback-controls">
          <select id="playback-camera" class="form-select">
            <option value="0">摄像头 0</option>
          </select>
          <select id="playback-duration" class="form-select">
            <option value="5">最近 5 秒</option>
            <option value="10" selected>最近 10 秒</option>
            <option value="30">最近 30 秒</option>
          </select>
          <button id="playback-btn" class="btn btn-primary" onclick="window.togglePlayback()">
            ▶ 播放
          </button>
          <button class="btn btn-secondary" onclick="window.refreshPlayback()">
            ↻ 刷新
          </button>
        </div>
      </div>
      <div class="playback-viewport">
        <img id="playback-img" src="" alt="回放画面" />
        <div class="playback-timeline">
          <div id="playback-progress" class="playback-progress"></div>
        </div>
        <div class="playback-info">
          <span id="playback-status">就绪</span>
          <span id="playback-time"></span>
        </div>
      </div>
    </div>
  `;

  loadCameraOptions();
}

async function loadCameraOptions() {
  try {
    const res = await authFetch('/api/v1/cameras');
    const data = await res.json();
    const select = document.getElementById('playback-camera');
    if (!select) return;
    select.innerHTML = '';
    (data.cameras || []).forEach(cam => {
      const opt = document.createElement('option');
      opt.value = cam.id;
      opt.textContent = cam.name || `摄像头 ${cam.id}`;
      select.appendChild(opt);
    });
  } catch (e) {
    console.error('加载摄像头列表失败:', e);
  }
}

export function togglePlayback() {
  if (isPlaying) {
    stopPlayback();
  } else {
    startPlayback();
  }
}

function startPlayback() {
  const cameraId = document.getElementById('playback-camera')?.value || 0;
  const duration = document.getElementById('playback-duration')?.value || 10;
  const img = document.getElementById('playback-img');
  const btn = document.getElementById('playback-btn');
  const status = document.getElementById('playback-status');

  if (!img) return;

  img.src = `/playback?camera_id=${cameraId}&seconds=${duration}`;
  isPlaying = true;
  if (btn) btn.textContent = '⏸ 暂停';
  if (status) status.textContent = '播放中...';
}

function stopPlayback() {
  const img = document.getElementById('playback-img');
  const btn = document.getElementById('playback-btn');
  const status = document.getElementById('playback-status');

  if (img) img.src = '';
  isPlaying = false;
  if (btn) btn.textContent = '▶ 播放';
  if (status) status.textContent = '已暂停';
}

export function refreshPlayback() {
  if (isPlaying) {
    stopPlayback();
    setTimeout(startPlayback, 100);
  }
}

// ── 告警升级状态模块 ──

export async function loadEscalations() {
  try {
    const res = await authFetch('/api/v1/escalations/pending');
    const data = await res.json();
    return data;
  } catch (e) {
    console.error('加载告警升级失败:', e);
    return [];
  }
}

export async function showEscalationStatus(alertId) {
  try {
    const res = await authFetch(`/api/v1/alerts/${alertId}/escalations`);
    const data = await res.json();
    return data;
  } catch (e) {
    console.error('获取升级历史失败:', e);
    return [];
  }
}

export function renderEscalationBadge(level) {
  const colors = {
    low: '#52c41a',
    medium: '#faad14',
    high: '#ff4d4f',
  };
  const color = colors[level] || '#999';
  return `<span class="escalation-badge" style="background:${color}">${level.toUpperCase()}</span>`;
}

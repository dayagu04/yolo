// ── 摄像头管理模块 ──
import { authFetch } from './auth.js';
import { loadCameras } from './camera-grid.js';

export async function showCameraManagement() {
  const panel = document.getElementById('tab-cameras');
  if (!panel) return;

  try {
    const res = await authFetch('/api/v1/cameras');
    const data = await res.json();
    renderCameraTable(data.cameras || []);
  } catch (e) {
    console.error('load camera mgmt:', e);
  }
}

function renderCameraTable(cameras) {
  const wrap = document.getElementById('cam-mgmt-table');
  if (!wrap) return;

  if (!cameras.length) {
    wrap.innerHTML = '<div class="empty-row">未配置摄像头</div>';
    return;
  }

  wrap.innerHTML = `<table>
    <thead><tr><th>ID</th><th>名称</th><th>位置</th><th>源</th><th>状态</th><th>FPS</th><th>轨迹</th><th>操作</th></tr></thead>
    <tbody>${cameras.map(c => `<tr>
      <td>${c.id}</td>
      <td>${c.name || 'CAM ' + c.id}</td>
      <td>${c.location || '—'}</td>
      <td style="font-family:monospace;font-size:11px">${c.source || c.id}</td>
      <td><span class="status-badge status-${c.connected ? 'online' : 'offline'}">${c.connected ? '在线' : '离线'}</span></td>
      <td>${(c.fps || 0).toFixed(1)}</td>
      <td>${c.active_tracks || 0}</td>
      <td><button class="btn danger" onclick="removeCamera(${c.id})">移除</button></td>
    </tr>`).join('')}</tbody>
  </table>`;
}

export function showAddCameraModal() {
  const modal = document.getElementById('add-camera-modal');
  if (modal) modal.classList.add('open');
}

export function hideAddCameraModal() {
  const modal = document.getElementById('add-camera-modal');
  if (modal) modal.classList.remove('open');
  document.getElementById('add-cam-error').textContent = '';
}

export async function addCamera() {
  const id = parseInt(document.getElementById('add-cam-id').value);
  const source = document.getElementById('add-cam-source').value.trim();
  const name = document.getElementById('add-cam-name').value.trim();
  const location = document.getElementById('add-cam-location').value.trim();
  const errEl = document.getElementById('add-cam-error');

  if (isNaN(id) || !source) { errEl.textContent = 'ID 和源地址必填'; return; }

  try {
    const res = await authFetch(`/api/v1/cameras/${id}/add`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source, name, location }),
    });
    if (!res.ok) {
      const data = await res.json();
      errEl.textContent = data.detail || '添加失败';
      return;
    }
    hideAddCameraModal();
    await loadCameras();
    await showCameraManagement();
  } catch (e) {
    errEl.textContent = '网络错误';
  }
}

export async function removeCamera(cameraId) {
  if (!confirm(`确认移除摄像头 ${cameraId}？`)) return;
  try {
    const res = await authFetch(`/api/v1/cameras/${cameraId}/remove`, { method: 'POST' });
    if (res.ok) {
      await loadCameras();
      await showCameraManagement();
    }
  } catch (e) {
    console.error('removeCamera:', e);
  }
}

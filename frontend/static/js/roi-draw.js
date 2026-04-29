// ── ROI 绘制工具 ──
import { authFetch } from './auth.js';

let canvas, ctx;
let currentPolygon = [];
let allROIs = [];
let selectedCameraId = 0;
let videoImg = null;
let isDrawing = false;

const ROI_COLORS = ['#ff1744', '#00e5ff', '#ff9100', '#00e676', '#7c4dff', '#ffea00'];

export function initROITool(container, cameraId) {
  selectedCameraId = cameraId || 0;

  container.innerHTML = `
    <div class="roi-canvas-container">
      <canvas id="roi-canvas" width="640" height="480"></canvas>
    </div>
    <div class="roi-toolbar">
      <select id="roi-camera-select" class="form-select-sm" onchange="window.roiChangeCamera(this.value)" title="选择摄像头">
        <option value="0">摄像头 0</option>
      </select>
      <select id="roi-type-select" class="form-select-sm" title="区域类型">
        <option value="intrusion">入侵检测</option>
        <option value="loitering">徘徊检测</option>
        <option value="gathering">聚集检测</option>
      </select>
      <input type="text" id="roi-name-input" placeholder="区域名称" class="form-input-sm" style="width:120px">
      <button class="btn btn-sm" onclick="window.roiUndoPoint()">撤销点</button>
      <button class="btn btn-sm danger" onclick="window.roiClearCurrent()">清除当前</button>
      <button class="btn btn-sm primary" onclick="window.roiSave()">保存区域</button>
    </div>
    <div class="roi-list" id="roi-list"></div>
  `;

  canvas = document.getElementById('roi-canvas');
  ctx = canvas.getContext('2d');

  canvas.addEventListener('click', onCanvasClick);
  canvas.addEventListener('mousemove', onCanvasMove);

  loadCameraOptions();
  loadROIs();
}

async function loadCameraOptions() {
  try {
    const res = await authFetch('/api/v1/cameras');
    const data = await res.json();
    const select = document.getElementById('roi-camera-select');
    if (!select) return;
    select.innerHTML = '';
    (data.cameras || []).forEach(cam => {
      const opt = document.createElement('option');
      opt.value = cam.id;
      opt.textContent = cam.name || `摄像头 ${cam.id}`;
      if (cam.id == selectedCameraId) opt.selected = true;
      select.appendChild(opt);
    });
  } catch (e) { console.error(e); }
}

async function loadROIs() {
  try {
    const res = await authFetch(`/api/v1/rois?camera_id=${selectedCameraId}`);
    allROIs = await res.json();
    renderROIList();
    drawAll();
  } catch (e) { console.error(e); }
}

function renderROIList() {
  const wrap = document.getElementById('roi-list');
  if (!wrap) return;
  if (!allROIs.length) {
    wrap.innerHTML = '<div class="muted-text" style="padding:8px;font-size:12px">暂无 ROI 区域</div>';
    return;
  }
  wrap.innerHTML = allROIs.map((roi, i) => {
    const color = ROI_COLORS[i % ROI_COLORS.length];
    const typeLabel = { intrusion: '入侵', loitering: '徘徊', gathering: '聚集' }[roi.roi_type] || roi.roi_type;
    return `
      <div class="roi-item">
        <span class="roi-color" style="background:${color}"></span>
        <span>${roi.name}</span>
        <span class="action-badge">${typeLabel}</span>
        <span class="muted-text">(${roi.polygon.length} 点)</span>
        <button class="btn btn-sm danger" onclick="window.roiDelete(${roi.id})">删除</button>
      </div>
    `;
  }).join('');
}

function onCanvasClick(e) {
  const rect = canvas.getBoundingClientRect();
  const x = Math.round(e.clientX - rect.left);
  const y = Math.round(e.clientY - rect.top);
  currentPolygon.push([x, y]);
  drawAll();
}

function onCanvasMove(e) {
  if (!currentPolygon.length) return;
  const rect = canvas.getBoundingClientRect();
  const x = Math.round(e.clientX - rect.left);
  const y = Math.round(e.clientY - rect.top);
  drawAll(x, y);
}

function drawAll(mouseX, mouseY) {
  ctx.clearRect(0, 0, canvas.width, canvas.height);

  // 绘制视频帧（如果有）
  if (videoImg) {
    ctx.drawImage(videoImg, 0, 0, canvas.width, canvas.height);
  } else {
    ctx.fillStyle = '#1a1a2e';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = '#555';
    ctx.font = '14px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('点击添加顶点，首尾闭合形成区域', canvas.width / 2, canvas.height / 2);
  }

  // 绘制已有 ROI
  allROIs.forEach((roi, i) => {
    const color = ROI_COLORS[i % ROI_COLORS.length];
    drawPolygon(roi.polygon, color, roi.name, 0.15);
  });

  // 绘制当前正在画的多边形
  if (currentPolygon.length) {
    ctx.strokeStyle = '#fff';
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 5]);
    ctx.beginPath();
    currentPolygon.forEach(([x, y], i) => {
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    if (mouseX !== undefined && mouseY !== undefined) {
      ctx.lineTo(mouseX, mouseY);
    }
    ctx.stroke();
    ctx.setLineDash([]);

    // 绘制顶点
    currentPolygon.forEach(([x, y], i) => {
      ctx.fillStyle = i === 0 ? '#ff1744' : '#fff';
      ctx.beginPath();
      ctx.arc(x, y, 4, 0, Math.PI * 2);
      ctx.fill();
    });
  }
}

function drawPolygon(polygon, color, label, alpha) {
  if (!polygon || polygon.length < 3) return;
  ctx.fillStyle = color + Math.round(alpha * 255).toString(16).padStart(2, '0');
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.beginPath();
  polygon.forEach(([x, y], i) => {
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.closePath();
  ctx.fill();
  ctx.stroke();

  if (label) {
    const cx = polygon.reduce((s, p) => s + p[0], 0) / polygon.length;
    const cy = polygon.reduce((s, p) => s + p[1], 0) / polygon.length;
    ctx.fillStyle = color;
    ctx.font = '12px sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText(label, cx, cy);
  }
}

export function roiUndoPoint() {
  currentPolygon.pop();
  drawAll();
}

export function roiClearCurrent() {
  currentPolygon = [];
  drawAll();
}

export async function roiSave() {
  if (currentPolygon.length < 3) {
    alert('至少需要 3 个点形成区域');
    return;
  }
  const name = document.getElementById('roi-name-input')?.value?.trim();
  if (!name) {
    alert('请输入区域名称');
    return;
  }
  const roiType = document.getElementById('roi-type-select')?.value || 'intrusion';

  try {
    const res = await authFetch('/api/v1/rois', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        camera_id: selectedCameraId,
        name: name,
        roi_type: roiType,
        polygon: currentPolygon,
      }),
    });
    if (!res.ok) {
      const data = await res.json();
      alert(data.detail || '保存失败');
      return;
    }
    currentPolygon = [];
    document.getElementById('roi-name-input').value = '';
    await loadROIs();
  } catch (e) {
    alert('网络错误');
  }
}

export async function roiDelete(roiId) {
  if (!confirm('确认删除此 ROI 区域？')) return;
  try {
    await authFetch(`/api/v1/rois/${roiId}`, { method: 'DELETE' });
    await loadROIs();
  } catch (e) { console.error(e); }
}

export function roiChangeCamera(cameraId) {
  selectedCameraId = parseInt(cameraId);
  currentPolygon = [];
  loadROIs();
}

export function loadVideoFrame(imgElement) {
  videoImg = imgElement;
  drawAll();
}

// 暴露全局函数
window.roiUndoPoint = roiUndoPoint;
window.roiClearCurrent = roiClearCurrent;
window.roiSave = roiSave;
window.roiDelete = roiDelete;
window.roiChangeCamera = roiChangeCamera;

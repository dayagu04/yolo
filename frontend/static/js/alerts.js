// ── 告警历史模块 ──
import { authFetch } from './auth.js';

let alertPage = 1;
const ALERT_PAGE_SIZE = 20;
let alertData = [];

export async function loadAlerts(page) {
  alertPage = page;
  const start = document.getElementById('f-start')?.value;
  const end = document.getElementById('f-end')?.value;
  const camId = document.getElementById('f-camera')?.value;
  const level = document.getElementById('f-level')?.value;

  const params = new URLSearchParams({ limit: ALERT_PAGE_SIZE, offset: (page - 1) * ALERT_PAGE_SIZE, order: 'desc' });
  if (start) params.set('start_time', start.replace('T', ' '));
  if (end)   params.set('end_time', end.replace('T', ' '));
  if (camId) params.set('camera_id', camId);
  if (level) params.set('level', level);

  try {
    const res = await authFetch('/api/v1/alerts?' + params);
    if (!res.ok) { renderAlertTable([], 0, 0); return; }
    const data = await res.json();
    alertData = data.alerts || [];
    renderAlertTable(alertData, data.total || 0, page);
  } catch (e) {
    renderAlertTable([], 0, 0);
  }
}

function renderAlertTable(rows, total, page) {
  const tbody = document.getElementById('alert-tbody');
  if (!tbody) return;
  if (!rows.length) {
    tbody.innerHTML = '<tr><td colspan="7" class="empty-row">暂无数据</td></tr>';
  } else {
    tbody.innerHTML = rows.map(r => {
      const levelBadge = `<span class="level-badge level-${r.level}">${{high:'高',medium:'中',low:'低'}[r.level] || r.level}</span>`;
      const thumb = r.screenshot_path
        ? `<img class="thumb" src="/api/v1/alerts/${r.id}/screenshot" onclick="openLightbox('/api/v1/alerts/${r.id}/screenshot')" loading="lazy">`
        : '<span class="muted-text">—</span>';
      return `<tr><td>${r.id}</td><td>${r.created_at || r.timestamp || ''}</td><td>${r.camera_id}</td><td>${r.person_count}</td><td>${r.message || ''}</td><td>${levelBadge}</td><td>${thumb}</td></tr>`;
    }).join('');
  }

  const totalPages = Math.max(1, Math.ceil(total / ALERT_PAGE_SIZE));
  document.getElementById('page-info').textContent = `第 ${page} / ${totalPages} 页，共 ${total} 条`;
  document.getElementById('btn-prev').disabled = page <= 1;
  document.getElementById('btn-next').disabled = page >= totalPages;
}

export function changePage(delta) { loadAlerts(alertPage + delta); }

export function exportCSV() {
  if (!alertData.length) { alert('请先查询数据'); return; }
  const headers = ['ID','时间','摄像头','人数','消息','级别'];
  const rows = alertData.map(r => [r.id, r.created_at || r.timestamp, r.camera_id, r.person_count, `"${(r.message||'').replace(/"/g,'""')}"`, r.level]);
  const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = `alerts_${new Date().toISOString().slice(0,10)}.csv`;
  a.click(); URL.revokeObjectURL(url);
}

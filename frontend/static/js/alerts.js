// ── 告警历史模块 ──
import { authFetch } from './auth.js';
import { toastError, toastWarn } from './toast.js';
import { escapeHtml, formatDate } from './utils.js';

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

  // 清空表格
  tbody.innerHTML = '';

  if (!rows.length) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 8;
    td.className = 'empty-row';
    td.textContent = '暂无数据';
    tr.appendChild(td);
    tbody.appendChild(tr);
  } else {
    rows.forEach(r => {
      const tr = document.createElement('tr');

      // ID 列
      const tdId = document.createElement('td');
      tdId.textContent = r.id;
      tr.appendChild(tdId);

      // 时间列
      const tdTime = document.createElement('td');
      tdTime.textContent = r.created_at || r.timestamp || '';
      tr.appendChild(tdTime);

      // 摄像头 ID 列
      const tdCamera = document.createElement('td');
      tdCamera.textContent = r.camera_id;
      tr.appendChild(tdCamera);

      // 人数列
      const tdCount = document.createElement('td');
      tdCount.textContent = r.person_count;
      tr.appendChild(tdCount);

      // 消息列（使用 escapeHtml 防止 XSS）
      const tdMessage = document.createElement('td');
      tdMessage.textContent = r.message || '';
      tr.appendChild(tdMessage);

      // 级别列
      const tdLevel = document.createElement('td');
      const levelBadge = document.createElement('span');
      levelBadge.className = `level-badge level-${r.level}`;
      levelBadge.textContent = {high:'高',medium:'中',low:'低'}[r.level] || r.level;
      tdLevel.appendChild(levelBadge);
      tr.appendChild(tdLevel);

      // 确认状态列
      const tdAck = document.createElement('td');
      if (r.acknowledged) {
        const ackBadge = document.createElement('span');
        ackBadge.className = 'status-badge status-online';
        ackBadge.title = `由 ${escapeHtml(r.acknowledged_by)} 确认于 ${r.acknowledged_at || ''}`;
        ackBadge.textContent = '已确认';
        tdAck.appendChild(ackBadge);
      } else {
        const ackBtn = document.createElement('button');
        ackBtn.className = 'btn btn-sm';
        ackBtn.textContent = '确认';
        ackBtn.onclick = () => acknowledgeAlert(r.id);
        tdAck.appendChild(ackBtn);
      }
      tr.appendChild(tdAck);

      // 截图列
      const tdThumb = document.createElement('td');
      if (r.screenshot_path) {
        const img = document.createElement('img');
        img.className = 'thumb';
        img.src = `/api/v1/alerts/${r.id}/screenshot`;
        img.loading = 'lazy';
        img.onclick = () => window.openLightbox(`/api/v1/alerts/${r.id}/screenshot`);
        tdThumb.appendChild(img);
      } else {
        const span = document.createElement('span');
        span.className = 'muted-text';
        span.textContent = '—';
        tdThumb.appendChild(span);
      }
      tr.appendChild(tdThumb);

      tbody.appendChild(tr);
    });
  }

  const totalPages = Math.max(1, Math.ceil(total / ALERT_PAGE_SIZE));
  document.getElementById('page-info').textContent = `第 ${page} / ${totalPages} 页，共 ${total} 条`;
  document.getElementById('btn-prev').disabled = page <= 1;
  document.getElementById('btn-next').disabled = page >= totalPages;
}

export function changePage(delta) { loadAlerts(alertPage + delta); }

export async function acknowledgeAlert(alertId) {
  try {
    const res = await authFetch(`/api/v1/alerts/${alertId}/acknowledge`, { method: 'POST' });
    if (!res.ok) {
      const data = await res.json();
      toastError(data.detail || '确认失败');
      return;
    }
    await loadAlerts(alertPage);
  } catch (e) {
    toastError('网络错误');
  }
}

export function exportCSV() {
  if (!alertData.length) { toastWarn('请先查询数据'); return; }
  const headers = ['ID','时间','摄像头','人数','消息','级别','已确认'];
  const rows = alertData.map(r => [r.id, r.created_at || r.timestamp, r.camera_id, r.person_count, `"${(r.message||'').replace(/"/g,'""')}"`, r.level, r.acknowledged ? '是' : '否']);
  const csv = [headers.join(','), ...rows.map(r => r.join(','))].join('\n');
  const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url; a.download = `alerts_${new Date().toISOString().slice(0,10)}.csv`;
  a.click(); URL.revokeObjectURL(url);
}

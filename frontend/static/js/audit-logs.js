// ── 审计日志模块 ──
import { authFetch } from './auth.js';

let auditPage = 0;
const PAGE_SIZE = 50;

export async function showAuditLogs() {
  auditPage = 0;
  await loadAuditLogs();
}

async function loadAuditLogs() {
  const wrap = document.getElementById('audit-log-content');
  if (!wrap) return;

  try {
    const params = new URLSearchParams({ limit: PAGE_SIZE, offset: auditPage * PAGE_SIZE });
    const username = document.getElementById('audit-filter-user')?.value;
    const action = document.getElementById('audit-filter-action')?.value;
    if (username) params.set('username', username);
    if (action) params.set('action', action);

    const res = await authFetch(`/api/v1/audit-logs?${params}`);
    const data = await res.json();

    renderAuditTable(data, wrap);
  } catch (e) {
    wrap.innerHTML = '<div class="empty-row">加载失败（需要管理员权限）</div>';
  }
}

function renderAuditTable(data, wrap) {
  const logs = data.logs || [];
  const total = data.total || 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  wrap.innerHTML = `
    <div class="filter-bar">
      <label>用户名</label>
      <input type="text" id="audit-filter-user" placeholder="筛选用户名" class="form-input-sm">
      <label>操作</label>
      <select id="audit-filter-action" class="form-select-sm">
        <option value="">全部</option>
        <option value="login">登录</option>
        <option value="login_failed">登录失败</option>
        <option value="camera_add">添加摄像头</option>
        <option value="camera_remove">移除摄像头</option>
        <option value="camera_edit">编辑摄像头</option>
        <option value="roi_create">创建 ROI</option>
        <option value="user_create">创建用户</option>
        <option value="user_update">更新用户</option>
        <option value="user_delete">删除用户</option>
        <option value="alert_acknowledge">确认告警</option>
        <option value="alert_escalate">升级告警</option>
        <option value="notification_toggle">通知开关</option>
      </select>
      <button class="btn" onclick="window.reloadAuditLogs()">查询</button>
    </div>
    <div class="table-wrap">
      <table class="mgmt-table">
        <thead>
          <tr><th>时间</th><th>用户</th><th>操作</th><th>资源</th><th>详情</th><th>IP</th></tr>
        </thead>
        <tbody>
          ${logs.length ? logs.map(l => `
            <tr>
              <td>${formatTime(l.timestamp)}</td>
              <td>${l.username}</td>
              <td><span class="action-badge">${l.action}</span></td>
              <td>${l.resource || '—'}</td>
              <td class="detail-cell">${l.detail || '—'}</td>
              <td>${l.ip_address || '—'}</td>
            </tr>
          `).join('') : '<tr><td colspan="6" class="empty-row">暂无日志</td></tr>'}
        </tbody>
      </table>
    </div>
    <div class="pagination">
      <span>共 ${total} 条，第 ${auditPage + 1}/${totalPages || 1} 页</span>
      <button class="btn" onclick="window.auditPageChange(-1)" ${auditPage <= 0 ? 'disabled' : ''}>上一页</button>
      <button class="btn" onclick="window.auditPageChange(1)" ${auditPage >= totalPages - 1 ? 'disabled' : ''}>下一页</button>
    </div>
  `;
}

function formatTime(ts) {
  if (!ts) return '—';
  const d = new Date(ts);
  return d.toLocaleString('zh-CN', { hour12: false });
}

// 暴露全局函数
window.reloadAuditLogs = async () => { auditPage = 0; await loadAuditLogs(); };
window.auditPageChange = async (delta) => { auditPage = Math.max(0, auditPage + delta); await loadAuditLogs(); };

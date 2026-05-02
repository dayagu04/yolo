// ── 通知设置模块 ──
import { authFetch } from './auth.js';
import { toastError, toastSuccess } from './toast.js';

export async function showNotificationSettings() {
  const wrap = document.getElementById('notification-content');
  if (!wrap) return;

  try {
    const res = await authFetch('/api/v1/notifications/config');
    const config = await res.json();
    renderNotificationSettings(config, wrap);
  } catch (e) {
    wrap.innerHTML = '<div class="empty-row">加载失败</div>';
  }
}

function renderNotificationSettings(config, wrap) {
  const channels = [
    { key: 'feishu', name: '飞书', icon: ' ' },
    { key: 'wechat_work', name: '企业微信', icon: ' ' },
    { key: 'dingtalk', name: '钉钉', icon: ' ' },
    { key: 'email', name: '邮件', icon: '✉️' },
    { key: 'webhook', name: 'Webhook', icon: ' ' },
  ];

  wrap.innerHTML = `
    <div class="notification-grid">
      ${channels.map(ch => {
        const cfg = config[ch.key] || {};
        return `
          <div class="notification-card ${cfg.enabled ? 'enabled' : 'disabled'}">
            <div class="notif-header">
              <span class="notif-icon">${ch.icon}</span>
              <span class="notif-name">${ch.name}</span>
              <label class="toggle-switch">
                <input type="checkbox" ${cfg.enabled ? 'checked' : ''}
                       onchange="window.toggleNotification('${ch.key}', this.checked)">
                <span class="toggle-slider"></span>
              </label>
            </div>
            <div class="notif-details">
              ${cfg.webhook_url ? `<div class="notif-url">URL: ${cfg.webhook_url}</div>` : ''}
              ${cfg.smtp_host ? `<div class="notif-url">SMTP: ${cfg.smtp_host}</div>` : ''}
              ${cfg.to_addrs_count !== undefined ? `<div class="notif-url">收件人: ${cfg.to_addrs_count} 个</div>` : ''}
              ${!cfg.enabled ? '<div class="notif-disabled-hint">未启用</div>' : ''}
            </div>
          </div>
        `;
      }).join('')}
    </div>
    <div class="notification-note">
      <p>通知渠道开关为运行时生效，无需重启服务。</p>
      <p>如需修改 Webhook URL 或邮件配置，请编辑 config.yaml 后重启。</p>
    </div>
  `;
}

export async function toggleNotification(channel, enabled) {
  try {
    const res = await authFetch(`/api/v1/notifications/${channel}/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled }),
    });
    if (!res.ok) {
      const data = await res.json();
      toastError(data.detail || '操作失败');
      return;
    }
    toastSuccess('通知设置已更新');
    await showNotificationSettings();
  } catch (e) {
    toastError('网络错误');
  }
}

window.toggleNotification = toggleNotification;

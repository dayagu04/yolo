// ── 用户管理模块 ──
import { authFetch } from './auth.js';

export async function showUserManagement() {
  // 用户列表通过审计日志接口间接获取（后端无独立用户列表接口时用此方案）
  // 此处展示当前用户信息和角色管理入口
  try {
    const res = await authFetch('/api/v1/auth/me');
    if (!res.ok) return;
    const user = await res.json();
    renderUserInfo(user);
  } catch (e) {
    console.error('load user info:', e);
  }
}

function renderUserInfo(user) {
  const wrap = document.getElementById('user-mgmt-content');
  if (!wrap) return;

  wrap.innerHTML = `
    <div style="padding:16px;">
      <div class="stat-card" style="max-width:400px;">
        <div class="label">当前登录用户</div>
        <div class="value" style="font-size:20px">${user.username}</div>
        <div class="sub"><span class="role-badge role-${user.role}">${{admin:'管理员',operator:'操作员',viewer:'观察者'}[user.role] || user.role}</span></div>
      </div>
      <div style="margin-top:16px;color:var(--muted);font-size:12px;">
        用户管理功能需要管理员权限，请通过 API 接口操作。
      </div>
    </div>
  `;
}

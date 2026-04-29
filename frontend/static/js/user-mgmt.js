// ── 用户管理模块 ──
import { authFetch } from './auth.js';

let currentUser = null;

export async function showUserManagement() {
  const wrap = document.getElementById('user-mgmt-content');
  if (!wrap) return;

  try {
    const meRes = await authFetch('/api/v1/auth/me');
    currentUser = await meRes.json();
  } catch (e) {
    wrap.innerHTML = '<div class="empty-row">请先登录</div>';
    return;
  }

  wrap.innerHTML = `
    <div class="mgmt-toolbar">
      <span class="stat-card inline">
        当前用户: <strong>${currentUser.username}</strong>
        <span class="role-badge role-${currentUser.role}">${roleLabel(currentUser.role)}</span>
      </span>
      <button class="btn primary" onclick="window.showAddUserModal()">+ 添加用户</button>
    </div>
    <div id="user-table-wrap">
      <div class="empty-row">加载中...</div>
    </div>

    <!-- 添加用户弹窗 -->
    <div class="modal-overlay" id="add-user-modal">
      <div class="modal-box">
        <h3>添加用户</h3>
        <label>用户名</label>
        <input type="text" id="new-username" placeholder="用户名">
        <label>密码</label>
        <input type="password" id="new-password" placeholder="密码（至少 6 位）">
        <label>角色</label>
        <select id="new-role">
          <option value="viewer">观察者</option>
          <option value="operator">操作员</option>
          <option value="admin">管理员</option>
        </select>
        <div class="modal-error" id="add-user-error"></div>
        <div class="modal-actions">
          <button class="btn" onclick="window.hideAddUserModal()">取消</button>
          <button class="btn primary" onclick="window.addUser()">添加</button>
        </div>
      </div>
    </div>

    <!-- 修改密码弹窗 -->
    <div class="modal-overlay" id="change-pwd-modal">
      <div class="modal-box">
        <h3>修改密码</h3>
        <input type="hidden" id="pwd-user-id">
        <label>旧密码</label>
        <input type="password" id="old-password" placeholder="旧密码">
        <label>新密码</label>
        <input type="password" id="new-pwd" placeholder="新密码（至少 6 位）">
        <div class="modal-error" id="change-pwd-error"></div>
        <div class="modal-actions">
          <button class="btn" onclick="document.getElementById('change-pwd-modal').classList.remove('open')">取消</button>
          <button class="btn primary" onclick="window.submitChangePassword()">确认</button>
        </div>
      </div>
    </div>
  `;

  await loadUsers();
}

async function loadUsers() {
  const wrap = document.getElementById('user-table-wrap');
  if (!wrap) return;

  try {
    const res = await authFetch('/api/v1/auth/users');
    const users = await res.json();
    if (!users.length) {
      wrap.innerHTML = '<div class="empty-row">暂无用户</div>';
      return;
    }

    wrap.innerHTML = `
      <table class="mgmt-table">
        <thead>
          <tr><th>ID</th><th>用户名</th><th>角色</th><th>状态</th><th>操作</th></tr>
        </thead>
        <tbody>
          ${users.map(u => `
            <tr>
              <td>${u.id}</td>
              <td>${u.username}</td>
              <td><span class="role-badge role-${u.role}">${roleLabel(u.role)}</span></td>
              <td>${u.is_active ? '<span class="status-badge status-online">启用</span>' : '<span class="status-badge status-offline">禁用</span>'}</td>
              <td class="action-cell">
                <select class="form-select-sm" onchange="window.changeUserRole(${u.id}, this.value)" title="修改角色">
                  <option value="admin" ${u.role==='admin'?'selected':''}>管理员</option>
                  <option value="operator" ${u.role==='operator'?'selected':''}>操作员</option>
                  <option value="viewer" ${u.role==='viewer'?'selected':''}>观察者</option>
                </select>
                <button class="btn btn-sm" onclick="window.toggleUserActive(${u.id}, ${!u.is_active})">
                  ${u.is_active ? '禁用' : '启用'}
                </button>
                <button class="btn btn-sm" onclick="window.showChangePassword(${u.id})">改密</button>
                <button class="btn btn-sm danger" onclick="window.deleteUser(${u.id}, '${u.username}')">删除</button>
              </td>
            </tr>
          `).join('')}
        </tbody>
      </table>
    `;
  } catch (e) {
    wrap.innerHTML = '<div class="empty-row">加载失败</div>';
  }
}

function roleLabel(role) {
  return { admin: '管理员', operator: '操作员', viewer: '观察者' }[role] || role;
}

export function showAddUserModal() {
  document.getElementById('add-user-modal')?.classList.add('open');
}

export function hideAddUserModal() {
  document.getElementById('add-user-modal')?.classList.remove('open');
  document.getElementById('add-user-error').textContent = '';
}

export async function addUser() {
  const username = document.getElementById('new-username')?.value?.trim();
  const password = document.getElementById('new-password')?.value;
  const role = document.getElementById('new-role')?.value;
  const errEl = document.getElementById('add-user-error');

  if (!username || !password) { errEl.textContent = '用户名和密码必填'; return; }
  if (password.length < 6) { errEl.textContent = '密码至少 6 位'; return; }

  try {
    const res = await authFetch('/api/v1/auth/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, role }),
    });
    if (!res.ok) {
      const data = await res.json();
      errEl.textContent = data.detail || '添加失败';
      return;
    }
    hideAddUserModal();
    await loadUsers();
  } catch (e) {
    errEl.textContent = '网络错误';
  }
}

export async function changeUserRole(userId, role) {
  try {
    await authFetch(`/api/v1/auth/users/${userId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role }),
    });
    await loadUsers();
  } catch (e) { console.error(e); }
}

export async function toggleUserActive(userId, active) {
  try {
    await authFetch(`/api/v1/auth/users/${userId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ is_active: active }),
    });
    await loadUsers();
  } catch (e) { console.error(e); }
}

export async function deleteUser(userId, username) {
  if (!confirm(`确认删除用户 "${username}"？`)) return;
  try {
    await authFetch(`/api/v1/auth/users/${userId}`, { method: 'DELETE' });
    await loadUsers();
  } catch (e) { console.error(e); }
}

export function showChangePassword(userId) {
  document.getElementById('pwd-user-id').value = userId;
  document.getElementById('old-password').value = '';
  document.getElementById('new-pwd').value = '';
  document.getElementById('change-pwd-error').textContent = '';
  document.getElementById('change-pwd-modal')?.classList.add('open');
}

export async function submitChangePassword() {
  const userId = document.getElementById('pwd-user-id')?.value;
  const oldPwd = document.getElementById('old-password')?.value;
  const newPwd = document.getElementById('new-pwd')?.value;
  const errEl = document.getElementById('change-pwd-error');

  if (!newPwd || newPwd.length < 6) { errEl.textContent = '新密码至少 6 位'; return; }

  try {
    const res = await authFetch(`/api/v1/auth/users/${userId}/password`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ old_password: oldPwd, new_password: newPwd }),
    });
    if (!res.ok) {
      const data = await res.json();
      errEl.textContent = data.detail || '修改失败';
      return;
    }
    document.getElementById('change-pwd-modal')?.classList.remove('open');
  } catch (e) {
    errEl.textContent = '网络错误';
  }
}

// ── 认证模块 ──
import { toastError } from './toast.js';
let authToken = localStorage.getItem('auth_token') || '';

export function setToken(token) {
  authToken = token || '';
  if (authToken) localStorage.setItem('auth_token', authToken);
  else localStorage.removeItem('auth_token');
}

export function getToken() { return authToken; }

export function showLogin(message = '') {
  document.getElementById('login-overlay').classList.add('open');
  document.getElementById('login-error').textContent = message;
}

export function hideLogin() {
  document.getElementById('login-overlay').classList.remove('open');
  document.getElementById('login-error').textContent = '';
}

export async function authFetch(url, options = {}) {
  const headers = options.headers ? { ...options.headers } : {};
  if (authToken) headers['Authorization'] = `Bearer ${authToken}`;
  const res = await fetch(url, { ...options, headers });
  if (res.status === 401) {
    setToken('');
    showLogin('登录已过期，请重新登录');
    throw new Error('unauthorized');
  }
  if (!res.ok && res.status !== 404) {
    try {
      const data = await res.clone().json();
      toastError(data.detail || `请求失败 (${res.status})`);
    } catch (_) {
      toastError(`请求失败 (${res.status})`);
    }
  }
  return res;
}

export async function doLogin() {
  const username = document.getElementById('login-username').value.trim();
  const password = document.getElementById('login-password').value;
  const btn = document.getElementById('btn-login');
  const err = document.getElementById('login-error');
  err.textContent = '';

  if (!username || !password) {
    err.textContent = '请输入用户名和密码';
    return;
  }

  btn.disabled = true;
  try {
    const res = await fetch('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!res.ok) {
      err.textContent = data.detail || '登录失败';
      return;
    }
    setToken(data.access_token);
    hideLogin();
    return true;
  } catch (_) {
    err.textContent = '网络错误，请稍后重试';
    return false;
  } finally {
    btn.disabled = false;
  }
}

export async function checkAuth() {
  if (!authToken) return false;
  try {
    const res = await fetch('/api/v1/auth/me', {
      headers: { 'Authorization': `Bearer ${authToken}` }
    });
    if (!res.ok) { setToken(''); return false; }
    return true;
  } catch (_) {
    return false;
  }
}

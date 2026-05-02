// ── Toast 通知工具 ──
let container = null;

function ensureContainer() {
  if (container) return container;
  container = document.createElement('div');
  container.id = 'toast-container';
  document.body.appendChild(container);
  return container;
}

function show(type, message, duration = 3000) {
  const wrap = ensureContainer();
  const el = document.createElement('div');
  el.className = `toast toast-${type}`;
  el.textContent = message;
  wrap.appendChild(el);

  // 触发动画
  requestAnimationFrame(() => el.classList.add('show'));

  const timer = setTimeout(() => dismiss(el), duration);
  el.addEventListener('click', () => { clearTimeout(timer); dismiss(el); });
}

function dismiss(el) {
  el.classList.remove('show');
  el.addEventListener('transitionend', () => el.remove(), { once: true });
  // 兜底：如果 transitionend 不触发
  setTimeout(() => { if (el.parentNode) el.remove(); }, 500);
}

export function toastSuccess(msg) { show('success', msg); }
export function toastError(msg)   { show('error', msg, 5000); }
export function toastWarn(msg)    { show('warn', msg, 4000); }
export function toastInfo(msg)    { show('info', msg); }

export function showToast(msg, type = 'info') {
  ({ success: toastSuccess, error: toastError, warn: toastWarn, info: toastInfo }[type] || toastInfo)(msg);
}

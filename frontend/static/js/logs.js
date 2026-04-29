// ── 日志面板模块 ──
const MAX_LOGS = 200;
let logCount = 0;

export function addLog(msg) {
  const list = document.getElementById('log-list');
  if (!list) return;

  const item = document.createElement('div');
  const type = msg.type || 'log';
  const level = msg.level || 'info';
  const ts = (msg.timestamp || '').slice(11, 19);
  const camPart = msg.camera_id !== undefined ? `[CAM${msg.camera_id}]` : '';
  const event = msg.event || type;
  const text = msg.message || '';

  item.className = `log-item ${type === 'alert' ? 'alert' : level}`;
  item.innerHTML = `<span class="log-ts">${ts}</span><span class="log-cam">${camPart}</span><span class="log-event">${event}</span><span class="log-msg">${text}</span>`;

  list.insertBefore(item, list.firstChild);
  logCount++;
  while (list.children.length > MAX_LOGS) list.removeChild(list.lastChild);
  document.getElementById('log-count').textContent = `${logCount} 条`;
}

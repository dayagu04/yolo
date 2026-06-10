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

  // 使用安全的 DOM 操作代替 innerHTML
  const tsSpan = document.createElement('span');
  tsSpan.className = 'log-ts';
  tsSpan.textContent = ts;

  const camSpan = document.createElement('span');
  camSpan.className = 'log-cam';
  camSpan.textContent = camPart;

  const eventSpan = document.createElement('span');
  eventSpan.className = 'log-event';
  eventSpan.textContent = event;

  const msgSpan = document.createElement('span');
  msgSpan.className = 'log-msg';
  msgSpan.textContent = text;

  item.appendChild(tsSpan);
  item.appendChild(camSpan);
  item.appendChild(eventSpan);
  item.appendChild(msgSpan);

  list.insertBefore(item, list.firstChild);
  logCount++;
  while (list.children.length > MAX_LOGS) list.removeChild(list.lastChild);
  document.getElementById('log-count').textContent = `${logCount} 条`;
}

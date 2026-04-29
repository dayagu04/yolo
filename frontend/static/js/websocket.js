// ── WebSocket 模块 ──
import { getToken } from './auth.js';

let ws = null;
let wsRetry = 0;
let _wsPingInterval = null;
let _messageHandler = null;

export function onMessage(handler) { _messageHandler = handler; }

export function connectWS() {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const token = getToken();
  ws = new WebSocket(`${proto}://${location.host}/ws/alert?token=${encodeURIComponent(token)}`);

  ws.onopen = () => {
    wsRetry = 0;
    setWsDot('connected', '已连接');
    if (_wsPingInterval) clearInterval(_wsPingInterval);
    _wsPingInterval = setInterval(() => ws && ws.readyState === 1 && ws.send('ping'), 15000);
  };

  ws.onmessage = e => {
    try {
      const msg = JSON.parse(e.data);
      if (_messageHandler) _messageHandler(msg);
    } catch (_) {}
  };

  ws.onclose = () => {
    setWsDot('error', '已断开');
    const delay = Math.min(30000, 1000 * 2 ** wsRetry++);
    setTimeout(connectWS, delay);
  };

  ws.onerror = () => setWsDot('error', '错误');
}

function setWsDot(cls, label) {
  const dot = document.getElementById('ws-dot');
  if (dot) {
    dot.className = 'ws-dot ' + cls;
    document.getElementById('ws-label').textContent = label;
  }
}

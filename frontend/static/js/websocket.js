// ── WebSocket 模块 ──
import { getToken } from './auth.js';

let ws = null;
let wsRetry = 0;
let _wsPingInterval = null;
let _messageHandler = null;
let _reconnectTimer = null;
let _suppressReconnect = false;

export function onMessage(handler) { _messageHandler = handler; }

export function connectWS() {
  // 进入连接流程，允许重连
  _suppressReconnect = false;
  if (_reconnectTimer) { clearTimeout(_reconnectTimer); _reconnectTimer = null; }
  // 避免重复连接：已有活动连接时先关闭旧的
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
    try { ws.onclose = null; ws.close(); } catch (_) {}
  }

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

  ws.onclose = (event) => {
    if (_wsPingInterval) { clearInterval(_wsPingInterval); _wsPingInterval = null; }
    // 鉴权失败（后端用 4001 关闭）或主动关闭时，不再重连，避免死循环用过期 token 打服务器
    if (_suppressReconnect || event.code === 4001) {
      setWsDot('error', event.code === 4001 ? '认证失效' : '已断开');
      return;
    }
    setWsDot('error', '已断开');
    const delay = Math.min(30000, 1000 * 2 ** wsRetry++);
    _reconnectTimer = setTimeout(connectWS, delay);
  };

  ws.onerror = () => setWsDot('error', '错误');
}

// 主动关闭连接并停止重连（用于登出 / 401）
export function closeWS() {
  _suppressReconnect = true;
  if (_reconnectTimer) { clearTimeout(_reconnectTimer); _reconnectTimer = null; }
  if (_wsPingInterval) { clearInterval(_wsPingInterval); _wsPingInterval = null; }
  if (ws) {
    try { ws.close(); } catch (_) {}
    ws = null;
  }
  wsRetry = 0;
}

function setWsDot(cls, label) {
  const dot = document.getElementById('ws-dot');
  if (dot) {
    dot.className = 'ws-dot ' + cls;
    document.getElementById('ws-label').textContent = label;
  }
}

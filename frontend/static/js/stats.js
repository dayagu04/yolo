// ── 统计面板模块 ──
import { authFetch } from './auth.js';

let chartTrend = null, chartPie = null;
let statsInterval = null;

export function initCharts() {
  const trendEl = document.getElementById('chart-trend');
  const pieEl = document.getElementById('chart-pie');
  if (!trendEl || !pieEl || typeof echarts === 'undefined') return;

  if (!chartTrend) { trendEl.innerHTML = ''; chartTrend = echarts.init(trendEl, 'dark'); }
  if (!chartPie)   { pieEl.innerHTML = '';   chartPie = echarts.init(pieEl, 'dark'); }
}

export function startStatsPolling() {
  initCharts();
  loadStats();
  if (!statsInterval) statsInterval = setInterval(loadStats, 5000);
}

export function stopStatsPolling() {
  if (statsInterval) { clearInterval(statsInterval); statsInterval = null; }
}

export async function loadStats() {
  try {
    const res = await authFetch('/api/v1/stats');
    if (!res.ok) { showStatsDisabled(); return; }
    const data = await res.json();
    if (data.error) { showStatsDisabled(); return; }

    initCharts();
    if (!chartTrend || !chartPie) return;

    document.getElementById('stat-today').textContent = data.today_alerts ?? '—';
    const personsMap = data.current_persons || {};
    const totalPersons = Object.values(personsMap).reduce((s, v) => s + (parseInt(v) || 0), 0);
    document.getElementById('stat-persons').textContent = totalPersons;

    const hourly = data.hourly_alerts || {};
    const hours = Array.from({length: 24}, (_, i) => `${i.toString().padStart(2,'0')}:00`);
    const counts = hours.map((_, i) => hourly[i] || 0);

    chartTrend.setOption({
      backgroundColor: 'transparent',
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: hours, axisLabel: { fontSize: 10, color: '#55556a' } },
      yAxis: { type: 'value', axisLabel: { color: '#55556a' }, splitLine: { lineStyle: { color: '#252535' } } },
      series: [{ name: '告警', type: 'line', data: counts, smooth: true, areaStyle: { opacity: 0.2 }, itemStyle: { color: '#00e5ff' }, lineStyle: { color: '#00e5ff' } }],
      grid: { left: 40, right: 10, top: 10, bottom: 30 },
    });

    const camAlerts = data.camera_alerts || {};
    const pieData = Object.entries(camAlerts).map(([k, v]) => ({ name: 'CAM ' + k, value: v }));

    chartPie.setOption({
      backgroundColor: 'transparent',
      tooltip: { trigger: 'item' },
      legend: { bottom: 0, textStyle: { color: '#55556a', fontSize: 10 } },
      series: [{ name: '告警分布', type: 'pie', radius: ['40%', '70%'], data: pieData.length ? pieData : [{ name: '无数据', value: 1 }], label: { color: '#e2e2f0', fontSize: 11 }, emphasis: { itemStyle: { shadowBlur: 10 } } }],
    });
  } catch (e) {
    showStatsDisabled();
  }
}

function showStatsDisabled() {
  if (chartTrend) { chartTrend.dispose(); chartTrend = null; }
  if (chartPie)   { chartPie.dispose();   chartPie = null; }
  const panel = document.getElementById('stats-panel');
  if (!panel) return;
  panel.querySelectorAll('.chart-box').forEach(b => {
    b.innerHTML = '<div class="stats-disabled">Redis 统计未启用</div>';
  });
}

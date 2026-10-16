// Same theme as the dashboard: light unless dark was chosen there.
try {
  if (localStorage.getItem('sensehive-dark') === '1') document.documentElement.dataset.theme = 'dark';
} catch (e) { /* private mode */ }

function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'})[ch]);
}
function ago(t) {
  if (!t) return '<span class="muted">never</span>';
  const s = Math.max(0, Math.round(Date.now() / 1000 - t));
  const text = s < 60 ? s + ' s ago' : s < 3600 ? Math.round(s / 60) + ' min ago' : Math.round(s / 3600) + ' h ago';
  return `<span title="${esc(new Date(t * 1000).toLocaleString())}">${text}</span>`;
}
async function load() {
  try {
    const r = await fetch('api/heartbeat/nodes', {credentials: 'same-origin'});
    if (r.status === 401) { location.href = 'login'; return; }
    const d = await r.json();
    document.getElementById('conn').textContent = !d.enabled ? 'receiver off (HEARTBEAT_MASTER_KEY not set)'
      : d.connected ? 'connected to the heartbeat broker' : 'not connected to the heartbeat broker';
    const counts = {online: 0, offline: 0, silent: 0};
    d.nodes.forEach(n => counts[n.status] = (counts[n.status] || 0) + 1);
    document.getElementById('summary').innerHTML =
      `<span class="pill">${d.nodes.length} nodes</span>` +
      ['online', 'silent', 'offline'].map(s => `<span class="pill ${s}">${counts[s] || 0} ${s}</span>`).join('');
    document.getElementById('rows').innerHTML = d.nodes.length ? d.nodes.map(n => `<tr>
      <td class="name">${esc(n.name)}</td>
      <td class="st ${esc(n.status)}">${esc(n.status)}</td>
      <td>${ago(n.last_seen)}</td><td>${ago(n.since)}</td><td>${ago(n.lwt_at)}</td>
      <td class="muted">${esc(n.agent_version || '')}</td></tr>`).join('')
      : '<tr><td colspan="6" class="muted">No heartbeats yet.</td></tr>';
  } catch (e) {
    document.getElementById('conn').textContent = 'could not load';
  }
}
load();
setInterval(load, 10000);

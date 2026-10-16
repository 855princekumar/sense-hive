// Heartbeats view of the dashboard: every node seen by the heartbeat receiver,
// its history (1 minute to 30 days) as a chart, breaks, and CSV export for one,
// the selected or all nodes. Loaded before dashboard.js; exposes
// window.SenseHiveHeartbeats. All URLs are relative (ingress, /sensehive/).
(function () {
    const { useState, useEffect, useMemo, useCallback } = React;

    const RANGES = [['1m', '1 min'], ['1h', '1 hour'], ['1d', '1 day'], ['7d', '7 days'], ['30d', '30 days']];
    const SPAN = { '1m': 60, '1h': 3600, '1d': 86400, '7d': 604800, '30d': 2592000 };
    const STATE = {
        online: { label: 'online', dot: 'bg-green-500', text: 'text-green-600', fill: '#059669' },
        offline: { label: 'offline', dot: 'bg-red-500', text: 'text-red-500', fill: '#dc2626' },
        silent: { label: 'silent', dot: 'bg-yellow-500', text: 'text-yellow-600', fill: '#d97706' },
    };

    function ago(t) {
        if (!t) return 'never';
        const s = Math.max(0, Math.round(Date.now() / 1000 - t));
        if (s < 60) return s + ' s ago';
        if (s < 3600) return Math.round(s / 60) + ' min ago';
        if (s < 86400) return Math.round(s / 3600) + ' h ago';
        return Math.round(s / 86400) + ' d ago';
    }
    function duration(sec) {
        if (sec == null) return '-';
        if (sec < 90) return Math.round(sec) + ' s';
        if (sec < 5400) return Math.round(sec / 60) + ' min';
        if (sec < 172800) return (sec / 3600).toFixed(1) + ' h';
        return (sec / 86400).toFixed(1) + ' d';
    }
    function clock(t, span) {
        const d = new Date(t * 1000);
        if (span <= 3600) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: span <= 60 ? '2-digit' : undefined });
        if (span <= 86400) return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
    }
    function exportUrl(names, what, seconds) {
        const now = Math.floor(Date.now() / 1000);
        const nodes = names === 'all' ? 'all' : names.map(encodeURIComponent).join(',');
        return `api/heartbeat/export.csv?nodes=${nodes}&what=${what}&since=${now - seconds}&until=${now}`;
    }
    function download(url) {
        const a = document.createElement('a');
        a.href = url; a.rel = 'noopener'; a.download = '';
        document.body.appendChild(a); a.click(); a.remove();
    }

    // ------------------------------------------------------------- chart
    function Chart({ data, dark }) {
        const W = 760, H = 230, L = 44, R = 12, T = 14, B = 46;
        const iw = W - L - R, ih = H - T - B;
        const span = data.until - data.since;
        const x = (t) => L + ((t - data.since) / span) * iw;
        const grid = dark ? '#374151' : '#e5e7eb', ink = dark ? '#9ca3af' : '#6b7280';
        const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => data.since + f * span);

        // status band from the events (the first may start before the range)
        const band = [];
        const ev = data.events || [];
        for (let i = 0; i < ev.length; i++) {
            const from = Math.max(ev[i].at, data.since), to = i + 1 < ev.length ? ev[i + 1].at : data.until;
            if (to > from && STATE[ev[i].status]) band.push({ from, to, s: ev[i].status });
        }

        let body = null, yTicks = [], yLabel = '';
        if (data.kind === 'beats') {
            const pts = data.points.filter((p) => p[1] !== 2);
            const gaps = pts.slice(1).map((p, i) => [p[0], p[0] - pts[i][0]]);
            const top = Math.max(30, (data.interval || 10) * 3, ...gaps.map((g) => g[1]).filter((g) => g < (data.interval || 10) * 12));
            const y = (v) => T + ih - (Math.min(v, top) / top) * ih;
            yTicks = [0, top / 2, top].map((v) => ({ v, y: y(v), label: Math.round(v) + ' s' }));
            yLabel = 'seconds between heartbeats';
            body = (
                <g>
                    {(data.breaks || []).map((b, i) => (
                        <rect key={'b' + i} x={x(b.from)} y={T} width={Math.max(2, x(b.to || data.until) - x(b.from))} height={ih}
                            fill="#dc2626" opacity="0.12" />
                    ))}
                    {data.interval && <line x1={L} x2={L + iw} y1={y(data.interval)} y2={y(data.interval)} stroke="#1a56db" strokeDasharray="4 4" strokeWidth="1" opacity="0.6" />}
                    {gaps.length > 1 && <polyline fill="none" stroke="#1a56db" strokeWidth="1.5" strokeLinejoin="round"
                        points={gaps.map((g) => `${x(g[0]).toFixed(1)},${y(g[1]).toFixed(1)}`).join(' ')} />}
                    {gaps.length <= 400 && gaps.map((g, i) => (
                        <circle key={i} cx={x(g[0])} cy={y(g[1])} r="2.6"
                            fill={data.interval && g[1] > Math.max(2.5 * data.interval, data.interval + 5) ? '#dc2626' : '#1a56db'} />
                    ))}
                    {data.points.filter((p) => p[1] === 2).map((p, i) => (
                        <line key={'w' + i} x1={x(p[0])} x2={x(p[0])} y1={T} y2={T + ih} stroke="#dc2626" strokeWidth="1.5" />
                    ))}
                </g>
            );
        } else {
            const y = (pct) => T + ih - (pct / 100) * ih;
            yTicks = [0, 50, 100].map((v) => ({ v, y: y(v), label: v + ' %' }));
            yLabel = 'uptime per hour';
            const bw = Math.max(0.6, iw / Math.max(data.points.length, 1) - 0.4);
            body = (
                <g>
                    {data.points.map((p, i) => {
                        const pct = p[2] ? (100 * p[1]) / p[2] : 0;
                        const fill = pct >= 99 ? '#059669' : pct >= 50 ? '#d97706' : '#dc2626';
                        return <rect key={i} x={x(p[0])} y={y(pct)} width={bw} height={Math.max(0, T + ih - y(pct))} fill={fill} opacity={p[2] ? 0.9 : 0.15} />;
                    })}
                </g>
            );
        }
        return (
            <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label={'Heartbeat history, ' + yLabel}>
                {yTicks.map((t, i) => (
                    <g key={'y' + i}>
                        <line x1={L} x2={L + iw} y1={t.y} y2={t.y} stroke={grid} strokeWidth="1" />
                        <text x={L - 6} y={t.y + 4} fontSize="10" textAnchor="end" fill={ink}>{t.label}</text>
                    </g>
                ))}
                {ticks.map((t, i) => (
                    <text key={'x' + i} x={x(t)} y={T + ih + 14} fontSize="10" fill={ink}
                        textAnchor={i === 0 ? 'start' : i === ticks.length - 1 ? 'end' : 'middle'}>{clock(t, span)}</text>
                ))}
                {body}
                {band.map((b, i) => (
                    <rect key={'s' + i} x={x(b.from)} y={T + ih + 22} width={Math.max(1, x(b.to) - x(b.from))} height="8" rx="2" fill={STATE[b.s].fill} />
                ))}
                <text x={L} y={H - 4} fontSize="10" fill={ink}>status (green online, amber silent, red offline)</text>
            </svg>
        );
    }

    // ------------------------------------------------------------- history dialog
    function History({ node, dark, cardBg, borderClass, onClose }) {
        const [range, setRange] = useState('1h');
        const [data, setData] = useState(null);
        const [error, setError] = useState('');
        useEffect(() => {
            let live = true;
            const load = () => fetch(`api/heartbeat/history?node=${encodeURIComponent(node.name)}&range=${range}`)
                .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
                .then((d) => { if (live) { setData(d); setError(''); } })
                .catch(() => live && setError('Could not load the history.'));
            setData(null); load();
            const timer = setInterval(load, range === '1m' ? 5000 : 30000);
            return () => { live = false; clearInterval(timer); };
        }, [node.name, range]);
        useEffect(() => {
            const onKey = (e) => e.key === 'Escape' && onClose();
            window.addEventListener('keydown', onKey);
            return () => window.removeEventListener('keydown', onKey);
        }, [onClose]);
        const st = STATE[node.status] || STATE.silent;
        const stat = (label, value) => (
            <div className={`${dark ? 'bg-gray-900' : 'bg-gray-50'} rounded-lg px-3 py-2 min-w-0`}>
                <div className="text-xs text-gray-500 whitespace-nowrap">{label}</div>
                <div className="font-semibold truncate">{value}</div>
            </div>
        );
        const what = SPAN[range] <= 86400 ? 'beats' : 'minutes';
        // On document.body, outside the animated view, so "fixed" always means the screen.
        return ReactDOM.createPortal(
            <div className="sh-overlay fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-3 sm:p-4" onClick={onClose}>
                <div className={`sh-modal ${cardBg} rounded-xl w-full max-w-3xl min-w-0`} role="dialog" aria-modal="true"
                    aria-label={'Heartbeat history of ' + node.name} onClick={(e) => e.stopPropagation()}>
                    <div className={`flex items-start justify-between gap-3 p-4 sm:p-5 border-b ${borderClass} flex-shrink-0`}>
                        <div className="min-w-0">
                            <h2 className="text-lg sm:text-xl font-bold break-all">{node.name}</h2>
                            <div className="text-sm flex items-center gap-2 mt-1">
                                <span className={`w-2.5 h-2.5 rounded-full ${st.dot}`} />
                                <span className={st.text}>{st.label}</span>
                                <span className="text-gray-500">since {ago(node.since)}</span>
                            </div>
                        </div>
                        <button data-close onClick={onClose} title="Close" className={`p-2 rounded-lg ${dark ? 'hover:bg-gray-700' : 'hover:bg-gray-100'} flex-shrink-0`}>
                            <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6 6 18M6 6l12 12" /></svg>
                        </button>
                    </div>
                    <div className="sh-modal-body p-4 sm:p-5 space-y-4">
                        <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Period">
                            {RANGES.map(([r, label]) => (
                                <button key={r} role="tab" aria-selected={range === r} data-range={r} onClick={() => setRange(r)}
                                    className={`px-3 py-1.5 rounded-lg text-sm font-medium whitespace-nowrap transition-colors ${range === r ? 'bg-blue-600 text-white' : dark ? 'bg-gray-700 hover:bg-gray-600' : 'bg-gray-100 hover:bg-gray-200'}`}>
                                    {label}
                                </button>
                            ))}
                        </div>
                        {error && <div className="text-red-500 text-sm">{error}</div>}
                        {!data && !error && <div className="h-56 flex items-center justify-center text-gray-500 text-sm">Loading...</div>}
                        {data && (
                            <div className="sh-fade-up space-y-4" key={range}>
                                <div className={`rounded-lg border ${borderClass} p-2`}><Chart data={data} dark={dark} /></div>
                                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-sm">
                                    {stat('Uptime', data.uptime + ' %')}
                                    {data.kind === 'beats' && stat('Heartbeats received', data.received)}
                                    {data.kind === 'beats' && stat('Typical interval', data.interval ? data.interval + ' s' : '-')}
                                    {data.kind === 'beats' && stat('Longest break', duration(data.longest_break))}
                                    {data.kind === 'beats' && stat('Breaks', data.breaks.length)}
                                    {data.kind === 'beats' && stat('Delay (median)', data.lag_ms == null ? '-' : data.lag_ms + ' ms')}
                                    {data.kind === 'hours' && stat('Hours with a gap', data.points.filter((p) => p[2] && p[1] < p[2]).length)}
                                </div>
                                {data.kind === 'beats' && data.breaks.length > 0 && (
                                    <div>
                                        <h3 className="font-semibold text-sm mb-1">Breaks</h3>
                                        <ul className="text-sm space-y-1">
                                            {data.breaks.slice(-20).reverse().map((b, i) => (
                                                <li key={i} className="flex flex-wrap gap-x-2">
                                                    <span className="text-red-500 font-medium">{duration(b.seconds)}</span>
                                                    <span className="text-gray-500">{new Date(b.from * 1000).toLocaleString()}{b.to ? '' : ' (still going)'}</span>
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                            </div>
                        )}
                    </div>
                    <div className={`flex flex-wrap justify-end gap-2 p-4 sm:p-5 border-t ${borderClass} flex-shrink-0`}>
                        <button id="hbExportOne" onClick={() => download(exportUrl([node.name], what, SPAN[range]))}
                            className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg text-sm font-medium transition-colors">
                            Export CSV ({what === 'beats' ? 'every heartbeat' : 'online minutes'})
                        </button>
                        <button onClick={onClose} className={`px-4 py-2 rounded-lg text-sm ${dark ? 'bg-gray-700 hover:bg-gray-600' : 'bg-gray-200 hover:bg-gray-300'} transition-colors`}>Close</button>
                    </div>
                </div>
            </div>,
            document.body
        );
    }

    // ------------------------------------------------------------- view
    function HeartbeatsView({ darkMode, cardBg, borderClass }) {
        const [info, setInfo] = useState(null);
        const [selected, setSelected] = useState(new Set());
        const [open, setOpen] = useState(null);
        const [what, setWhat] = useState('beats');
        const [period, setPeriod] = useState('86400');
        const load = useCallback(() => fetch('api/heartbeat/nodes').then((r) => r.json()).then(setInfo).catch(() => {}), []);
        useEffect(() => { load(); const t = setInterval(load, 10000); return () => clearInterval(t); }, [load]);
        const nodes = info ? info.nodes : [];
        const counts = useMemo(() => nodes.reduce((c, n) => (c[n.status] = (c[n.status] || 0) + 1, c), {}), [nodes]);
        const allOn = nodes.length > 0 && nodes.every((n) => selected.has(n.name));
        const toggle = (name) => setSelected((s) => { const n = new Set(s); n.has(name) ? n.delete(name) : n.add(name); return n; });
        const field = `px-2 py-1.5 rounded-lg border ${borderClass} ${darkMode ? 'bg-gray-700 text-white' : 'bg-white text-gray-900'}`;

        if (!info) return <div className="text-center py-16 text-gray-500">Loading heartbeats...</div>;
        return (
            <div className="space-y-4">
                <div className={`sh-bar ${cardBg} border ${borderClass} rounded-xl px-4 py-3 flex flex-wrap items-center gap-3 text-sm`}>
                    <span className="text-gray-500 mr-auto min-w-0">
                        {!info.enabled ? 'Receiver off: set HEARTBEAT_MASTER_KEY' : info.connected ? 'Connected to the heartbeat broker' : 'Not connected to the heartbeat broker'}
                    </span>
                    <label className="flex items-center gap-2 text-gray-500">Export
                        <select id="hbWhat" value={what} onChange={(e) => setWhat(e.target.value)} className={field}>
                            <option value="beats">every heartbeat</option>
                            <option value="minutes">online minutes</option>
                            <option value="events">status changes</option>
                        </select>
                    </label>
                    <select id="hbPeriod" value={period} onChange={(e) => setPeriod(e.target.value)} className={field} aria-label="Period">
                        <option value="3600">last hour</option>
                        <option value="86400">last day</option>
                        <option value="604800">last 7 days</option>
                        <option value="2592000">last 30 days</option>
                    </select>
                    <button id="hbExportSelected" disabled={!selected.size} onClick={() => download(exportUrl([...selected], what, +period))}
                        className="bg-blue-600 hover:bg-blue-700 text-white px-3 py-1.5 rounded-lg font-medium whitespace-nowrap disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
                        Selected ({selected.size})
                    </button>
                    <button id="hbExportAll" disabled={!nodes.length} onClick={() => download(exportUrl('all', what, +period))}
                        className={`px-3 py-1.5 rounded-lg font-medium whitespace-nowrap border ${borderClass} ${darkMode ? 'hover:bg-gray-700' : 'hover:bg-gray-100'} disabled:opacity-50 transition-colors`}>
                        All nodes
                    </button>
                </div>

                {nodes.length === 0 ? (
                    <div className="text-center py-16 text-gray-500">
                        No heartbeats yet. Nodes appear here by themselves on their first heartbeat.
                    </div>
                ) : (
                    <div className={`${cardBg} border ${borderClass} rounded-xl overflow-x-auto`}>
                        <table id="hbTable" className="w-full text-sm">
                            <thead>
                                <tr className={`text-left text-xs uppercase tracking-wide text-gray-500 border-b ${borderClass}`}>
                                    <th className="px-3 py-2.5 w-8">
                                        <input id="hbSelectAll" type="checkbox" aria-label="Select all" checked={allOn}
                                            onChange={() => setSelected(allOn ? new Set() : new Set(nodes.map((n) => n.name)))} />
                                    </th>
                                    <th className="px-3 py-2.5">Node</th>
                                    <th className="px-3 py-2.5">Status</th>
                                    <th className="px-3 py-2.5 whitespace-nowrap">Last heartbeat</th>
                                    <th className="px-3 py-2.5">Since</th>
                                    <th className="px-3 py-2.5 whitespace-nowrap">Last will</th>
                                    <th className="px-3 py-2.5">Agent</th>
                                    <th className="px-3 py-2.5" />
                                </tr>
                            </thead>
                            <tbody>
                                {nodes.map((n) => {
                                    const st = STATE[n.status] || STATE.silent;
                                    return (
                                        <tr key={n.name} className={`border-b last:border-b-0 ${borderClass}`}>
                                            <td className="px-3 py-2.5"><input type="checkbox" aria-label={'Select ' + n.name}
                                                checked={selected.has(n.name)} onChange={() => toggle(n.name)} /></td>
                                            <td className="px-3 py-2.5 font-medium break-all min-w-[9rem]">{n.name}</td>
                                            <td className="px-3 py-2.5 whitespace-nowrap">
                                                <span className={`hb-state inline-flex items-center gap-1.5 font-semibold ${st.text}`} data-state={n.status}>
                                                    <span className={`w-2 h-2 rounded-full ${st.dot}`} />{st.label}
                                                </span>
                                            </td>
                                            <td className="px-3 py-2.5 whitespace-nowrap">{ago(n.last_seen)}</td>
                                            <td className="px-3 py-2.5 whitespace-nowrap">{ago(n.since)}</td>
                                            <td className="px-3 py-2.5 whitespace-nowrap">{n.lwt_at ? ago(n.lwt_at) : 'never'}</td>
                                            <td className="px-3 py-2.5 text-gray-500 whitespace-nowrap">{n.agent_version || ''}</td>
                                            <td className="px-3 py-2.5 text-right">
                                                <button className="hb-history px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white text-xs font-medium whitespace-nowrap transition-colors"
                                                    onClick={() => setOpen(n)}>History</button>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
                <p className="text-xs text-gray-500">
                    {nodes.length} nodes: {counts.online || 0} online, {counts.silent || 0} silent, {counts.offline || 0} offline.
                    Every heartbeat is kept for 48 hours, online minutes and status changes for 30 days.
                </p>
                {open && <History node={open} dark={darkMode} cardBg={cardBg} borderClass={borderClass} onClose={() => setOpen(null)} />}
            </div>
        );
    }

    window.SenseHiveHeartbeats = HeartbeatsView;
})();

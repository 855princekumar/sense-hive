// Secure topics view of the dashboard (ADR 0009): keys issued here, topics found by
// themselves under the secure root, kept apart from open topics. Loaded before
// dashboard.js; exposes window.SenseHiveSecure. All URLs are relative (ingress, /sensehive/).
(function () {
    const { useState, useEffect, useCallback } = React;

    const STATUS = {
        pending: { label: 'pending', cls: 'bg-yellow-100 text-yellow-800' },
        active: { label: 'active', cls: 'bg-green-100 text-green-800' },
        expired: { label: 'expired', cls: 'bg-gray-200 text-gray-700' },
        revoked: { label: 'revoked', cls: 'bg-red-100 text-red-700' },
    };

    function when(t) { return t ? new Date(t * 1000).toLocaleString() : '-'; }
    function left(t) {
        const s = Math.round(t - Date.now() / 1000);
        if (s <= 0) return 'now';
        return s < 3600 ? Math.round(s / 60) + ' min' : (s / 3600).toFixed(1) + ' h';
    }
    function cell(v) {                                  // a CSV cell no spreadsheet runs as a formula
        const s = String(v == null ? '' : v);
        const safe = /^[=+\-@\t\r]/.test(s) ? "'" + s : s;
        return /[",\n]/.test(safe) ? '"' + safe.replace(/"/g, '""') + '"' : safe;
    }
    function saveCsv(keys, root) {
        const rows = [['key_id', 'key', 'label', 'topic', 'publish_under', 'unused_key_expires_utc']]
            .concat(keys.map((k) => [k.kid, k.key, k.label, k.topic, root + '/', new Date(k.expires_at * 1000).toISOString()]));
        const blob = new Blob([rows.map((r) => r.map(cell).join(',')).join('\n') + '\n'], { type: 'text/csv' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'sensehive-secure-keys-' + new Date().toISOString().slice(0, 16).replace(/[:T]/g, '-') + '.csv';
        document.body.appendChild(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(a.href), 4000);
    }
    function copy(text, done) {
        try { navigator.clipboard.writeText(text).then(() => done(true), () => done(false)); } catch (e) { done(false); }
    }
    async function post(url, body) {
        const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body || {}) });
        const d = await r.json().catch(() => ({}));
        if (!r.ok || d.success === false) throw new Error(d.error || ('HTTP ' + r.status));
        return d;
    }

    function Dialog({ title, sub, onClose, children, footer, cardBg, borderClass, id }) {
        return (
            <div className="sh-overlay fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-3 sm:p-4" onClick={onClose}>
                <div id={id} className={`sh-modal ${cardBg} rounded-xl max-w-2xl w-full min-w-0`} role="dialog" aria-modal="true" aria-label={title}
                    onClick={(e) => e.stopPropagation()}>
                    <div className="px-5 sm:px-6 pt-5 sm:pt-6 pb-3 flex-shrink-0">
                        <h2 className="text-xl font-bold">{title}</h2>
                        {sub && <p className="text-sm text-gray-500 mt-1">{sub}</p>}
                    </div>
                    <div className="sh-modal-body px-5 sm:px-6 pb-3 space-y-3 text-sm">{children}</div>
                    <div className={`flex flex-wrap items-center justify-end gap-2 px-5 sm:px-6 py-4 border-t ${borderClass} flex-shrink-0`}>{footer}</div>
                </div>
            </div>
        );
    }

    function SenseHiveSecure({ darkMode, cardBg, borderClass, nodes, onDetails, refresh, formatValue }) {
        const [status, setStatus] = useState(null);
        const [keys, setKeys] = useState([]);
        const [filter, setFilter] = useState('all');
        const [dialog, setDialog] = useState(null);            // {kind: 'generate'|'made'|'reveal'|'revoke', ...}
        const [form, setForm] = useState({ count: 1, label: '', topic: '' });
        const [error, setError] = useState('');
        const [note, setNote] = useState('');
        const field = `px-3 py-2 rounded-lg border ${borderClass} ${darkMode ? 'bg-gray-700 text-white' : 'bg-white text-gray-900'} w-full`;
        const btn = `px-3 py-2 rounded-lg text-sm font-medium border ${borderClass} ${darkMode ? 'hover:bg-gray-700' : 'hover:bg-gray-100'} transition-colors`;
        const pri = 'px-4 py-2 rounded-lg text-sm font-medium bg-blue-600 hover:bg-blue-700 text-white transition-colors';

        const load = useCallback(() => {
            fetch('api/secure/status').then((r) => r.ok ? r.json() : null).then((d) => d && setStatus(d)).catch(() => {});
            fetch('api/secure/keys').then((r) => r.ok ? r.json() : null).then((d) => d && setKeys(d.keys)).catch(() => {});
        }, []);
        useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t); }, [load]);
        useEffect(() => {
            const onKey = (e) => { if (e.key === 'Escape') setDialog(null); };
            window.addEventListener('keydown', onKey);
            return () => window.removeEventListener('keydown', onKey);
        }, []);

        const root = status ? status.root : 'sensehive/secure';
        const shown = keys.filter((k) => filter === 'all' || k.status === filter);
        const open = (kind, extra) => { setError(''); setNote(''); setDialog({ kind, ...extra }); };

        const generate = async () => {
            setError('');
            const count = Math.floor(Number(form.count));
            if (!(count >= 1 && count <= 100)) { setError('Generate between 1 and 100 keys at a time.'); return; }
            try {
                const d = await post('api/secure/keys', { count, label: form.label, topic: count === 1 ? form.topic.trim() : '' });
                setDialog({ kind: 'made', keys: d.keys, root: d.root });
                load();
            } catch (e) { setError(e.message); }
        };
        const reveal = async () => {
            setError('');
            try {
                const d = await post('api/secure/keys/' + dialog.kid + '/reveal', { password: dialog.password || '' });
                setDialog({ ...dialog, key: d.key, password: '' });
            } catch (e) { setError(e.message); }
        };
        const revoke = async () => {
            setError('');
            try { await post('api/secure/keys/' + dialog.kid + '/revoke'); setDialog(null); load(); refresh(); } catch (e) { setError(e.message); }
        };

        const counts = status ? status.keys : { pending: 0, active: 0, expired: 0, revoked: 0 };
        const rejected = status ? Object.values(status.rejected).reduce((a, b) => a + b, 0) : 0;
        return (
            <div id="secureView">
                <div className={`sh-bar ${cardBg} border ${borderClass} rounded-xl px-4 py-3 mb-6 flex flex-wrap items-center gap-3 text-sm`}>
                    <div className="flex flex-wrap items-center gap-3 mr-auto min-w-0">
                        <span className="text-gray-500 min-w-0">Publish under <code className="font-mono break-all">{root}/</code></span>
                        <span className="text-gray-500">Keys: <b>{counts.active}</b> active, <b>{counts.pending}</b> pending</span>
                        {status && <span id="secureRefused" className="text-gray-500" title={'Messages under the root that failed a check' + (rejected ? ': ' + Object.entries(status.rejected).filter((r) => r[1]).map((r) => r[0].replace('_', ' ') + ' ' + r[1]).join(', ') : '')}>Refused: <b>{rejected}</b></span>}
                    </div>
                    <button id="genKeysBtn" type="button" className={pri}
                        onClick={() => { setForm({ count: 1, label: '', topic: root + '/' }); open('generate'); }}>Generate keys</button>
                </div>

                {status && !status.enabled && (
                    <div className="mb-6 rounded-xl border border-yellow-300 bg-yellow-50 text-yellow-900 px-4 py-3 text-sm">
                        Secure topics are turned off on this server (SENSEHIVE_SECURE_TOPICS=false).
                    </div>
                )}

                <h2 className="text-lg font-semibold mb-3">Secure topics <span className="text-gray-500 font-normal text-sm">({nodes.length})</span></h2>
                {nodes.length === 0 ? (
                    <div className={`${cardBg} border ${borderClass} rounded-xl p-6 mb-8 text-sm text-gray-500`}>
                        No secure topics yet. Generate a key, give it to the device, and publish with it under <code className="font-mono">{root}/</code>:
                        the topic appears here by itself with its first valid message.
                    </div>
                ) : (
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6 items-start mb-8">
                        {nodes.map((node) => (
                            <div key={node.id} className={`sh-card sh-secure-card ${cardBg} rounded-xl shadow-sm border ${borderClass} p-5 min-w-0`}>
                                <div className="flex items-start gap-2 mb-2">
                                    <span className="w-7 h-7 rounded-lg bg-blue-600 text-white flex items-center justify-center flex-shrink-0" title="Encrypted and signed">
                                        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" aria-hidden="true">
                                            <rect x="5" y="11" width="14" height="10" rx="2" /><path d="M8 11V8a4 4 0 0 1 8 0v3" /></svg>
                                    </span>
                                    <div className="min-w-0">
                                        <h3 className="font-semibold break-all">{node.topic}</h3>
                                        <p className="text-xs text-gray-500">{node.node_name} · key {node.key_id} · {node.last_updated ? new Date(node.last_updated).toLocaleString() : 'No data'}</p>
                                    </div>
                                </div>
                                <div className={`rounded-lg p-3 mb-3 ${darkMode ? 'bg-gray-900' : 'bg-gray-50'} min-w-0 overflow-hidden`}>
                                    {node.last_value != null ? formatValue(node.last_value) : <span className="text-gray-500 text-sm">No data yet</span>}
                                </div>
                                <div className="flex flex-wrap items-center gap-2 text-xs text-gray-500">
                                    <span className="mr-auto">{(node.entry_count || 0).toLocaleString()} {node.entry_count === 1 ? 'entry' : 'entries'}</span>
                                    <button type="button" className={btn} onClick={() => onDetails(node)}>Details</button>
                                    <a className={btn} href={'api/nodes/' + node.id + '/export'} download>CSV</a>
                                </div>
                            </div>
                        ))}
                    </div>
                )}

                <div className="flex flex-wrap items-center gap-3 mb-3">
                    <h2 className="text-lg font-semibold mr-auto">Keys</h2>
                    <label className="flex items-center gap-2 text-sm text-gray-500">Show
                        <select id="keyFilter" value={filter} onChange={(e) => setFilter(e.target.value)}
                            className={`px-2 py-1 rounded-lg border ${borderClass} ${darkMode ? 'bg-gray-700 text-white' : 'bg-white text-gray-900'}`}>
                            <option value="all">All ({keys.length})</option>
                            <option value="pending">Pending ({counts.pending})</option>
                            <option value="active">Active ({counts.active})</option>
                            <option value="expired">Expired, never used ({counts.expired})</option>
                            <option value="revoked">Revoked ({counts.revoked})</option>
                        </select>
                    </label>
                </div>
                <div className={`${cardBg} border ${borderClass} rounded-xl overflow-x-auto`}>
                    {shown.length === 0 ? <div className="p-6 text-sm text-gray-500">No keys here.</div> : (
                        <table id="keyTable" className="w-full text-sm">
                            <thead><tr className={`text-left text-gray-500 border-b ${borderClass}`}>
                                {['Key ID', 'Label', 'Topic', 'Status', 'When', 'Messages', ''].map((h) => <th key={h} className="px-3 py-2 font-medium whitespace-nowrap">{h}</th>)}
                            </tr></thead>
                            <tbody>
                                {shown.map((k) => (
                                    <tr key={k.kid} className={`border-b ${borderClass} last:border-0`}>
                                        <td className="px-3 py-2 font-mono whitespace-nowrap">{k.kid}</td>
                                        <td className="px-3 py-2 whitespace-nowrap">{k.label || '-'}</td>
                                        <td className="px-3 py-2 font-mono break-all min-w-[10rem]">{k.topic || <span className="text-gray-500">set by its first message</span>}</td>
                                        <td className="px-3 py-2"><span className={`px-2 py-0.5 rounded-full text-xs font-semibold whitespace-nowrap ${STATUS[k.status].cls}`}>{STATUS[k.status].label}</span></td>
                                        <td className="px-3 py-2 whitespace-nowrap text-gray-500">
                                            {k.status === 'pending' ? 'expires in ' + left(k.expires_at)
                                                : k.status === 'active' ? 'last ' + when(k.last_used_at) : 'ended ' + when(k.ended_at)}
                                        </td>
                                        <td className="px-3 py-2 text-right tabular-nums">{k.messages}</td>
                                        <td className="px-3 py-2 whitespace-nowrap text-right">
                                            {(k.status === 'pending' || k.status === 'active') && (<>
                                                <button type="button" className="text-blue-600 hover:underline mr-3" onClick={() => open('reveal', { kid: k.kid, password: '' })}>Show key</button>
                                                <button type="button" className="text-red-600 hover:underline" onClick={() => open('revoke', { kid: k.kid, label: k.label })}>Revoke</button>
                                            </>)}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    )}
                </div>

                {dialog && dialog.kind === 'generate' && (
                    <Dialog id="genDialog" title="Generate keys" sub="One key per topic. A key unused for 24 hours expires; its first message makes it active and binds it to that topic."
                        onClose={() => setDialog(null)} cardBg={cardBg} borderClass={borderClass}
                        footer={<><span className="text-red-500 mr-auto text-sm">{error}</span>
                            <button type="button" className={btn} onClick={() => setDialog(null)}>Cancel</button>
                            <button id="genGo" type="button" className={pri} onClick={generate}>Generate</button></>}>
                        <label className="block"><span className="font-medium">How many keys</span>
                            <input id="genCount" type="number" min="1" max="100" className={field} value={form.count}
                                onChange={(e) => setForm({ ...form, count: e.target.value })} /></label>
                        <label className="block"><span className="font-medium">Label</span> <span className="text-gray-500">(device or site, numbered when several)</span>
                            <input id="genLabel" maxLength="64" className={field} value={form.label} placeholder="e.g. pump-house"
                                onChange={(e) => setForm({ ...form, label: e.target.value })} /></label>
                        {Number(form.count) === 1 && (
                            <label className="block"><span className="font-medium">Topic</span> <span className="text-gray-500">(optional: else the first message sets it)</span>
                                <input id="genTopic" maxLength="512" className={field + ' font-mono'} value={form.topic}
                                    onChange={(e) => setForm({ ...form, topic: e.target.value })} /></label>
                        )}
                    </Dialog>
                )}

                {dialog && dialog.kind === 'made' && (
                    <Dialog id="madeDialog" title={dialog.keys.length === 1 ? 'Your new key' : dialog.keys.length + ' new keys'}
                        sub="Shown only now. Download the CSV and keep it safe; it opens these topics." onClose={() => setDialog(null)}
                        cardBg={cardBg} borderClass={borderClass}
                        footer={<><span className="text-green-600 mr-auto text-sm">{note}</span>
                            <button type="button" className={btn} onClick={() => copy(dialog.keys.map((k) => k.kid + ' ' + k.key).join('\n'), (ok) => setNote(ok ? 'Copied' : 'Copy failed: use the CSV'))}>Copy</button>
                            <button id="madeCsv" type="button" className={btn} onClick={() => saveCsv(dialog.keys, dialog.root)}>Download CSV</button>
                            <button type="button" className={pri} onClick={() => setDialog(null)}>Done</button></>}>
                        <div className="overflow-x-auto">
                            <table className="w-full text-xs font-mono">
                                <thead><tr className="text-left text-gray-500"><th className="pr-3 py-1">Key ID</th><th className="pr-3 py-1">Key</th><th className="py-1">Label</th></tr></thead>
                                <tbody>{dialog.keys.map((k) => (
                                    <tr key={k.kid}><td className="pr-3 py-1 whitespace-nowrap">{k.kid}</td><td className="pr-3 py-1 break-all">{k.key}</td><td className="py-1 whitespace-nowrap">{k.label}</td></tr>
                                ))}</tbody>
                            </table>
                        </div>
                        <p className="text-gray-500">Publish under <code className="font-mono">{dialog.root}/</code> with the key ID and key: see the guide (i) for device code.</p>
                    </Dialog>
                )}

                {dialog && dialog.kind === 'reveal' && (
                    <Dialog id="revealDialog" title={'Show key ' + dialog.kid} sub="Enter your password to show this key again." onClose={() => setDialog(null)}
                        cardBg={cardBg} borderClass={borderClass}
                        footer={<><span className="text-red-500 mr-auto text-sm">{error || note}</span>
                            <button type="button" className={btn} onClick={() => setDialog(null)}>Close</button>
                            {dialog.key ? <button type="button" className={pri} onClick={() => copy(dialog.key, (ok) => setNote(ok ? 'Copied' : 'Copy failed'))}>Copy</button>
                                : <button id="revealGo" type="button" className={pri} onClick={reveal}>Show</button>}</>}>
                        {dialog.key ? <code className="block font-mono break-all text-base">{dialog.key}</code> : (
                            <input id="revealPassword" type="password" autoComplete="current-password" className={field} value={dialog.password}
                                onChange={(e) => setDialog({ ...dialog, password: e.target.value })}
                                onKeyDown={(e) => { if (e.key === 'Enter') reveal(); }} />
                        )}
                    </Dialog>
                )}

                {dialog && dialog.kind === 'revoke' && (
                    <Dialog id="revokeDialog" title={'Revoke key ' + dialog.kid + '?'} sub="Its device can no longer publish. The topic and its history stay. This cannot be undone."
                        onClose={() => setDialog(null)} cardBg={cardBg} borderClass={borderClass}
                        footer={<><span className="text-red-500 mr-auto text-sm">{error}</span>
                            <button type="button" className={btn} onClick={() => setDialog(null)}>Cancel</button>
                            <button id="revokeGo" type="button" className="px-4 py-2 rounded-lg text-sm font-medium bg-red-600 hover:bg-red-700 text-white" onClick={revoke}>Revoke</button></>}>
                        <p>{dialog.label ? 'Label: ' + dialog.label : 'This key has no label.'}</p>
                    </Dialog>
                )}
            </div>
        );
    }

    window.SenseHiveSecure = SenseHiveSecure;
})();

        const { useState, useEffect, useRef } = React;
        
        const Icons = {
            Settings: (props) => (
                <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"/>
                    <circle cx="12" cy="12" r="3"/>
                </svg>
            ),
            Plus: (props) => (
                <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M5 12h14"/><path d="M12 5v14"/>
                </svg>
            ),
            Trash2: (props) => (
                <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M3 6h18"/><path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"/><path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"/><line x1="10" x2="10" y1="11" y2="17"/><line x1="14" x2="14" y1="11" y2="17"/>
                </svg>
            ),
            Download: (props) => (
                <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" x2="12" y1="15" y2="3"/>
                </svg>
            ),
            Activity: (props) => (
                <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M22 12h-4l-3 9L9 3l-3 9H2"/>
                </svg>
            ),
            Moon: (props) => (
                <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>
                </svg>
            ),
            Sun: (props) => (
                <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>
                </svg>
            ),
            AlertCircle: (props) => (
                <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="10"/><line x1="12" x2="12" y1="8" y2="12"/><line x1="12" x2="12.01" y1="16" y2="16"/>
                </svg>
            ),
            CheckCircle: (props) => (
                <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><polyline points="22 4 12 14.01 9 11.01"/>
                </svg>
            ),
            XCircle: (props) => (
                <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/>
                </svg>
            ),
            LogOut: (props) => (
                <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><line x1="21" x2="9" y1="12" y2="12"/>
                </svg>
            ),
            Key: (props) => (
                <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="7.5" cy="15.5" r="5.5"/><path d="m21 2-9.6 9.6"/><path d="m15.5 7.5 3 3L22 7l-3-3"/>
                </svg>
            ),
            Globe: (props) => (
                <svg {...props} xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <circle cx="12" cy="12" r="10"/><line x1="2" x2="22" y1="12" y2="12"/><path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z"/>
                </svg>
            )
        };

        const IoTDashboard = () => {
            // Light by default, like EdgeShell; the choice is remembered in this browser.
            const [darkMode, setDarkMode] = useState(() => {
                try { return localStorage.getItem('sensehive-dark') === '1'; } catch (e) { return false; }
            });
            useEffect(() => {
                try { localStorage.setItem('sensehive-dark', darkMode ? '1' : '0'); } catch (e) { /* private mode */ }
            }, [darkMode]);
            const [nodes, setNodes] = useState([]);
            const [brokerStatus, setBrokerStatus] = useState('disconnected');
            const [showAddNode, setShowAddNode] = useState(false);
            const [showSettings, setShowSettings] = useState(false);
            const [showDetails, setShowDetails] = useState(null);
            const [showPasswordChange, setShowPasswordChange] = useState(false);
            const emptyNodeForm = { topic: '', tag: '', node_name: '', lwt_topic: '', lwt_online: 'online', lwt_offline: 'offline' };
            const [nodeForm, setNodeForm] = useState(emptyNodeForm);
            const [editingNodeId, setEditingNodeId] = useState(null);
            useEffect(() => {
                const onKey = (e) => {
                    if (e.key !== 'Escape') return;
                    setShowAddNode(false); setShowSettings(false); setShowDetails(null); setShowPasswordChange(false);
                };
                window.addEventListener('keydown', onKey);
                return () => window.removeEventListener('keydown', onKey);
            }, []);
            const [formError, setFormError] = useState('');
            const [stats, setStats] = useState(null);
            const [filterTag, setFilterTag] = useState('all');
            const [sortBy, setSortBy] = useState('created');
            const [groupByNode, setGroupByNode] = useState(false);
            const [timezones, setTimezones] = useState([]);
            const [brokerConfig, setBrokerConfig] = useState({
                host: 'localhost',
                port: 1883,
                username: '',
                password: '',
                timezone: 'UTC'
            });
            const [retention, setRetention] = useState({
                retention_days: 0,
                retention_max_entries: 0
            });
            const [passwordData, setPasswordData] = useState({
                current: '',
                new: '',
                confirm: ''
            });
            const eventSourceRef = useRef(null);

            useEffect(() => {
                connectSSE();
                fetchNodes();
                fetchBrokerConfig();
                fetchTimezones();
                fetchRetention();
                fetchStats();
                checkBrokerStatus();

                const statusInterval = setInterval(checkBrokerStatus, 5000);
                const statsInterval = setInterval(fetchStats, 15000);

                return () => {
                    clearInterval(statusInterval);
                    clearInterval(statsInterval);
                    if (eventSourceRef.current) {
                        eventSourceRef.current.close();
                    }
                };
            }, []);

            const connectSSE = () => {
                if (eventSourceRef.current) {
                    eventSourceRef.current.close();
                }

                const evtSource = new EventSource('stream');
                
                evtSource.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        if (data.type === 'lwt') {
                            updateLwtStatus(data.lwt_topic, data.status, data.timestamp);
                        } else if (data.topic && data.payload !== undefined) {
                            updateNodeData(data.topic, data.payload);
                        }
                    } catch (e) {
                        console.error('SSE parse error:', e);
                    }
                };

                evtSource.onerror = () => {
                    console.log('SSE connection lost, reconnecting...');
                    setTimeout(connectSSE, 3000);
                };

                eventSourceRef.current = evtSource;
            };

            const updateNodeData = (topic, payload) => {
                const approxBytes = JSON.stringify(payload).length + 44;
                setNodes(prev => prev.map(node =>
                    node.topic === topic
                        ? {
                            ...node,
                            last_value: payload,
                            last_updated: new Date().toISOString(),
                            entry_count: (node.entry_count || 0) + 1,
                            approx_size_bytes: (node.approx_size_bytes || 0) + approxBytes
                        }
                        : node
                ));
            };

            const updateLwtStatus = (lwtTopic, status, timestamp) => {
                setNodes(prev => prev.map(node =>
                    node.lwt_topic === lwtTopic ? { ...node, status, status_updated: timestamp } : node
                ));
                fetchStats();
            };

            const fetchStats = async () => {
                try {
                    const res = await fetch('api/stats');
                    if (res.ok) {
                        setStats(await res.json());
                    }
                } catch (e) {
                    console.error('Failed to fetch stats:', e);
                }
            };

            const formatBytes = (bytes) => {
                if (!bytes) return '0 B';
                const units = ['B', 'KB', 'MB', 'GB'];
                const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
                return `${(bytes / Math.pow(1024, i)).toFixed(i === 0 ? 0 : 1)} ${units[i]}`;
            };

            const STATUS_STYLES = {
                active: { dot: 'bg-green-500', label: 'Active' },
                inactive: { dot: 'bg-red-500', label: 'Inactive' },
                unknown: { dot: 'bg-yellow-500', label: 'Unknown' },
                untracked: { dot: 'bg-gray-500', label: 'No LWT' }
            };

            const STATUS_ORDER = { active: 0, unknown: 1, untracked: 2, inactive: 3 };

            const visibleNodes = nodes
                .filter(node => filterTag === 'all' || node.tag === filterTag)
                .slice()
                .sort((a, b) => {
                    switch (sortBy) {
                        case 'name': return a.topic.localeCompare(b.topic);
                        case 'updated': return new Date(b.last_updated || 0) - new Date(a.last_updated || 0);
                        case 'entries': return (b.entry_count || 0) - (a.entry_count || 0);
                        case 'size': return (b.approx_size_bytes || 0) - (a.approx_size_bytes || 0);
                        case 'status': return (STATUS_ORDER[a.status] ?? 9) - (STATUS_ORDER[b.status] ?? 9);
                        case 'tag': return (a.tag || '').localeCompare(b.tag || '') || a.topic.localeCompare(b.topic);
                        default: return 0;
                    }
                });

            const allTags = [...new Set(nodes.map(n => n.tag).filter(Boolean))].sort();
            const allNodeNames = [...new Set(nodes.map(n => n.node_name).filter(Boolean))].sort();

            const nodeGroups = groupByNode
                ? Object.entries(visibleNodes.reduce((groups, node) => {
                    (groups[node.node_name] = groups[node.node_name] || []).push(node);
                    return groups;
                }, {})).sort(([a], [b]) => a.localeCompare(b))
                : [[null, visibleNodes]];

            const groupStatus = (name) => (stats?.node_list || []).find(n => n.node_name === name)?.status || 'unknown';

            const fetchNodes = async () => {
                try {
                    const res = await fetch('api/nodes');
                    if (res.status === 401) {
                        window.location.href = 'login';
                        return;
                    }
                    const data = await res.json();
                    setNodes(data);
                    fetchStats();
                } catch (e) {
                    console.error('Failed to fetch nodes:', e);
                }
            };

            const fetchBrokerConfig = async () => {
                try {
                    const res = await fetch('api/broker');
                    if (res.status === 401) {
                        window.location.href = 'login';
                        return;
                    }
                    const data = await res.json();
                    if (data.host) {
                        setBrokerConfig(data);
                    }
                } catch (e) {
                    console.error('Failed to fetch broker config:', e);
                }
            };

            const fetchTimezones = async () => {
                try {
                    const res = await fetch('api/timezones');
                    if (res.status === 401) {
                        window.location.href = 'login';
                        return;
                    }
                    const data = await res.json();
                    setTimezones(data.timezones || []);
                } catch (e) {
                    console.error('Failed to fetch timezones:', e);
                }
            };

            const fetchRetention = async () => {
                try {
                    const res = await fetch('api/settings/retention');
                    if (res.ok) {
                        setRetention(await res.json());
                    }
                } catch (e) {
                    console.error('Failed to fetch retention settings:', e);
                }
            };

            const runRetentionNow = async () => {
                if (!window.confirm('Apply the retention policy now? Old entries will be permanently deleted.')) return;
                try {
                    await saveRetention();
                    const res = await fetch('api/retention/run', { method: 'POST' });
                    const data = await res.json();
                    alert(`Cleanup complete: ${data.deleted || 0} entries removed`);
                    fetchNodes();
                } catch (e) {
                    alert('Cleanup failed');
                }
            };

            const saveRetention = async () => {
                const res = await fetch('api/settings/retention', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(retention)
                });
                const data = await res.json();
                if (!res.ok) throw new Error(data.error || 'Invalid retention settings');
            };

            const checkBrokerStatus = async () => {
                try {
                    const res = await fetch('api/status');
                    if (res.status === 401) {
                        window.location.href = 'login';
                        return;
                    }
                    const data = await res.json();
                    setBrokerStatus(data.connected ? 'connected' : 'disconnected');
                } catch (e) {
                    setBrokerStatus('error');
                }
            };

            const handleLogout = async () => {
                if (window.confirm('Are you sure you want to logout?')) {
                    try {
                        await fetch('api/logout', { method: 'POST' });
                        window.location.href = 'login';
                    } catch (e) {
                        console.error('Logout failed:', e);
                    }
                }
            };

            const openAddNode = () => {
                setEditingNodeId(null);
                setNodeForm(emptyNodeForm);
                setFormError('');
                setShowAddNode(true);
            };

            const openEditNode = (node) => {
                setEditingNodeId(node.id);
                setNodeForm({
                    topic: node.topic,
                    tag: node.tag || '',
                    node_name: node.node_name || '',
                    lwt_topic: node.lwt_topic || '',
                    lwt_online: node.lwt_online || 'online',
                    lwt_offline: node.lwt_offline || 'offline'
                });
                setFormError('');
                setShowAddNode(true);
            };

            const closeNodeForm = () => {
                setShowAddNode(false);
                setEditingNodeId(null);
                setFormError('');
            };

            const saveNode = async () => {
                if (!nodeForm.topic.trim()) return setFormError('Topic is required');
                if (!nodeForm.node_name.trim()) return setFormError('Node ID is required');
                if (!nodeForm.tag.trim()) return setFormError('Tag is required');

                try {
                    const res = await fetch(editingNodeId ? `api/nodes/${editingNodeId}` : 'api/nodes', {
                        method: editingNodeId ? 'PUT' : 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(nodeForm)
                    });

                    if (res.ok) {
                        closeNodeForm();
                        setNodeForm(emptyNodeForm);
                        fetchNodes();
                    } else {
                        const data = await res.json().catch(() => ({}));
                        setFormError(data.error || 'Failed to save node');
                    }
                } catch (e) {
                    console.error('Failed to save node:', e);
                    setFormError('Failed to save node');
                }
            };

            const deleteNode = async (nodeId, topic) => {
                const exportFirst = window.confirm('Do you want to export data before deleting?');
                
                if (exportFirst) {
                    await exportData(nodeId, topic);
                }
                
                const confirmDelete = window.confirm(
                    exportFirst 
                        ? 'Node data exported. Confirm deletion?' 
                        : 'Node will be deleted and data will be lost. Continue?'
                );
                
                if (confirmDelete) {
                    try {
                        await fetch(`api/nodes/${nodeId}`, { method: 'DELETE' });
                        fetchNodes();
                    } catch (e) {
                        console.error('Failed to delete node:', e);
                    }
                }
            };

            const exportData = async (nodeId, topic) => {
                try {
                    const res = await fetch(`api/nodes/${nodeId}/export`);
                    const blob = await res.blob();
                    const url = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    a.download = `${topic.replace(/\//g, '_')}_data.csv`;
                    a.click();
                    window.URL.revokeObjectURL(url);
                } catch (e) {
                    console.error('Failed to export data:', e);
                }
            };

            const saveBrokerConfig = async () => {
                try {
                    await saveRetention();
                    const res = await fetch('api/broker', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(brokerConfig)
                    });
                    
                    if (res.ok) {
                        setShowSettings(false);
                        alert('Settings saved successfully!');
                        setTimeout(checkBrokerStatus, 1000);
                    }
                } catch (e) {
                    console.error('Failed to save settings:', e);
                    alert(`Failed to save settings${e.message ? ': ' + e.message : ''}`);
                }
            };

            const testBroker = async () => {
                try {
                    const res = await fetch('api/broker/test', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(brokerConfig)
                    });
                    
                    const data = await res.json();
                    alert(data.success ? 'Connection successful!' : `Failed: ${data.error}`);
                } catch (e) {
                    alert('Connection test failed');
                }
            };

            const changePassword = async () => {
                if (passwordData.new !== passwordData.confirm) {
                    alert('New passwords do not match!');
                    return;
                }

                if (passwordData.new.length < 6) {
                    alert('Password must be at least 6 characters long');
                    return;
                }

                try {
                    const res = await fetch('api/change-password', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            current_password: passwordData.current,
                            new_password: passwordData.new
                        })
                    });

                    const data = await res.json();

                    if (data.success) {
                        alert('Password changed successfully!');
                        setShowPasswordChange(false);
                        setPasswordData({ current: '', new: '', confirm: '' });
                    } else {
                        alert(data.error || 'Failed to change password');
                    }
                } catch (e) {
                    alert('Failed to change password');
                }
            };

            const showNodeDetails = async (nodeId) => {
                try {
                    const res = await fetch(`api/nodes/${nodeId}/history`);
                    const data = await res.json();
                    setShowDetails(data);
                } catch (e) {
                    console.error('Failed to fetch history:', e);
                }
            };

            const isNested = (v) => typeof v === 'object' && v !== null;

            const formatValue = (value) => {
                // Arrays (incl. top-level arrays of objects) render as wrapped, pretty-printed JSON
                if (Array.isArray(value)) {
                    return <pre className="payload-json">{JSON.stringify(value, null, 2)}</pre>;
                }
                if (isNested(value)) {
                    return Object.entries(value).map(([k, v]) => isNested(v) ? (
                        <div key={k} className={`py-1 border-b ${darkMode ? 'border-gray-700' : 'border-gray-200'} min-w-0`}>
                            <span className="text-gray-400 text-sm payload-key">{k}:</span>
                            <pre className="payload-json mt-1">{JSON.stringify(v, null, 2)}</pre>
                        </div>
                    ) : (
                        <div key={k} className={`payload-row py-1 border-b ${darkMode ? 'border-gray-700' : 'border-gray-200'}`}>
                            <span className="text-gray-400 text-sm payload-key">{k}:</span>
                            <span className="font-medium payload-value">{JSON.stringify(v)}</span>
                        </div>
                    ));
                }
                return <div className="text-lg font-mono payload-value text-left">{JSON.stringify(value)}</div>;
            };

            const bgClass = darkMode ? 'bg-gray-900 text-white' : 'bg-gray-50 text-gray-900';
            const cardBg = darkMode ? 'bg-gray-800' : 'bg-white';
            const borderClass = darkMode ? 'border-gray-700' : 'border-gray-200';

            return (
                <div className={`min-h-screen ${bgClass} transition-colors duration-300`}>
                    <nav className={`sh-nav ${cardBg} border-b ${borderClass} px-4 sm:px-6 py-3 sticky top-0 z-40 backdrop-blur-lg bg-opacity-90`}>
                        <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 max-w-7xl mx-auto">
                            <div className="flex items-center gap-2 min-w-0">
                                <div className="w-9 h-9 rounded-lg bg-blue-600 flex items-center justify-center flex-shrink-0">
                                    <Icons.Activity className="w-5 h-5 text-white" />
                                </div>
                                <h1 className="text-xl font-bold whitespace-nowrap">SenseHive</h1>
                                <div className="flex items-center gap-1.5 ml-2" title="MQTT broker connection">
                                    <div className={`w-2.5 h-2.5 rounded-full flex-shrink-0 ${
                                        brokerStatus === 'connected' ? 'bg-green-500 animate-pulse' :
                                        brokerStatus === 'disconnected' ? 'bg-red-500' : 'bg-yellow-500'
                                    }`} />
                                    <span className="text-sm font-medium capitalize hidden sm:inline">{brokerStatus}</span>
                                </div>
                            </div>

                            <div className="flex flex-wrap items-center gap-2">
                                {stats && (
                                    <div className={`hidden xl:flex items-center gap-3 text-xs border-r ${borderClass} pr-3 mr-1 whitespace-nowrap`} title="Device status from MQTT LWT">
                                        <span className="text-gray-500">Nodes</span>
                                        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500" />{stats.nodes.active}</span>
                                        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500" />{stats.nodes.inactive}</span>
                                        <span className="text-gray-500 ml-2">Topics</span>
                                        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-green-500" />{stats.topics.active}</span>
                                        <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500" />{stats.topics.inactive}</span>
                                    </div>
                                )}

                                <button id="addNodeBtn" onClick={openAddNode} title="Add Node"
                                    className="flex items-center gap-2 bg-blue-600 hover:bg-blue-700 text-white px-3 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition">
                                    <Icons.Plus className="w-4 h-4" />
                                    <span className="hidden sm:inline">Add Node</span>
                                </button>

                                <a id="heartbeatsLink" href="heartbeats" title="Heartbeats"
                                    className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium whitespace-nowrap border ${borderClass} ${darkMode ? 'hover:bg-gray-700' : 'hover:bg-gray-100'} transition`}>
                                    <Icons.CheckCircle className="w-4 h-4" />
                                    <span className="hidden sm:inline">Heartbeats</span>
                                </a>

                                <button onClick={() => setShowSettings(true)} title="Settings"
                                    className={`p-2 rounded-lg ${darkMode ? 'hover:bg-gray-700' : 'hover:bg-gray-100'} transition`}>
                                    <Icons.Settings className="w-5 h-5" />
                                </button>

                                <button onClick={() => setDarkMode(!darkMode)} title="Toggle theme"
                                    className={`p-2 rounded-lg ${darkMode ? 'hover:bg-gray-700' : 'hover:bg-gray-100'} transition`}>
                                    {darkMode ? <Icons.Sun className="w-5 h-5" /> : <Icons.Moon className="w-5 h-5" />}
                                </button>

                                <button id="logoutBtn" onClick={handleLogout} title="Sign out"
                                    className={`flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium whitespace-nowrap text-red-500 border ${borderClass} ${darkMode ? 'hover:bg-gray-700' : 'hover:bg-red-50'} transition`}>
                                    <Icons.LogOut className="w-4 h-4" />
                                    <span className="hidden sm:inline">Sign out</span>
                                </button>
                            </div>
                        </div>
                    </nav>

                    <div className="max-w-7xl mx-auto p-4 sm:p-6">
                        {nodes.length > 0 && (
                            <div className={`sh-bar ${cardBg} border ${borderClass} rounded-xl px-4 py-3 mb-6 flex flex-wrap items-center gap-3 text-sm`}>
                                <div className="flex flex-wrap items-center gap-3 mr-auto">
                                    <span className="text-gray-500">Topics: <b>{nodes.length}</b></span>
                                    <span className="text-gray-500">Nodes: <b>{allNodeNames.length}</b></span>
                                    <span className="text-gray-500">Entries: <b>{nodes.reduce((sum, n) => sum + (n.entry_count || 0), 0).toLocaleString()}</b></span>
                                    <span className="text-gray-500">DB size: <b>{formatBytes(stats?.db_size_bytes)}</b></span>
                                </div>
                                <label className="flex items-center gap-2 text-gray-500">
                                    Tag
                                    <select id="tagFilter"
                                        value={filterTag}
                                        onChange={(e) => setFilterTag(e.target.value)}
                                        className={`px-2 py-1 rounded-lg border ${borderClass} ${darkMode ? 'bg-gray-700 text-white' : 'bg-white text-gray-900'}`}
                                    >
                                        <option value="all">All tags</option>
                                        {allTags.map(tag => <option key={tag} value={tag}>{tag}</option>)}
                                    </select>
                                </label>
                                <label className="flex items-center gap-2 text-gray-500">
                                    Sort
                                    <select id="sortBy"
                                        value={sortBy}
                                        onChange={(e) => setSortBy(e.target.value)}
                                        className={`px-2 py-1 rounded-lg border ${borderClass} ${darkMode ? 'bg-gray-700 text-white' : 'bg-white text-gray-900'}`}
                                    >
                                        <option value="created">Newest first</option>
                                        <option value="name">Topic name</option>
                                        <option value="tag">Tag</option>
                                        <option value="status">Status</option>
                                        <option value="updated">Last updated</option>
                                        <option value="entries">Entry count</option>
                                        <option value="size">DB size</option>
                                    </select>
                                </label>
                                <label className="flex items-center gap-2 text-gray-500 cursor-pointer">
                                    <input id="groupByNode" type="checkbox" checked={groupByNode} onChange={(e) => setGroupByNode(e.target.checked)} />
                                    Group by node
                                </label>
                            </div>
                        )}

                        {nodes.length === 0 ? (
                            <div className="text-center py-20">
                                <Icons.Activity className="w-16 h-16 mx-auto text-gray-500 mb-4" />
                                <h2 className="text-2xl font-semibold mb-2">No Nodes Yet</h2>
                                <p className="text-gray-500 mb-6">Add your first MQTT topic to get started</p>
                                <button
                                    onClick={openAddNode}
                                    className="bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-lg transition"
                                >
                                    Add Node
                                </button>
                            </div>
                        ) : visibleNodes.length === 0 ? (
                            <div className="text-center py-20 text-gray-500">No topics match the selected tag</div>
                        ) : nodeGroups.map(([groupName, groupNodes]) => (
                            <div key={groupName || 'all'} className="mb-8">
                                {groupName !== null && (
                                    <div className="flex items-center gap-3 mb-3">
                                        <div className={`w-3 h-3 rounded-full ${STATUS_STYLES[groupStatus(groupName)].dot}`} />
                                        <h2 className="text-lg font-semibold break-all">{groupName}</h2>
                                        <span className="text-xs text-gray-500">
                                            {STATUS_STYLES[groupStatus(groupName)].label} · {groupNodes.length} {groupNodes.length === 1 ? 'topic' : 'topics'}
                                        </span>
                                    </div>
                                )}
                            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 sm:gap-6 items-start">
                                {groupNodes.map(node => (
                                    <div key={node.id} className={`sh-card ${cardBg} rounded-xl shadow-sm border ${borderClass} p-5 hover:shadow-md transition min-w-0`}>
                                        <div className="flex justify-between items-start mb-3">
                                            <div className="flex-1 min-w-0">
                                                <h3 className="font-semibold text-lg mb-1 break-all">{node.topic}</h3>
                                                <p className="text-xs text-gray-500">
                                                    {node.last_updated ? new Date(node.last_updated).toLocaleString() : 'No data'}
                                                </p>
                                            </div>
                                            <div
                                                className="flex items-center gap-1 text-xs flex-shrink-0 ml-2"
                                                title={node.lwt_topic ? `LWT: ${node.lwt_topic}` : 'No LWT topic configured'}
                                            >
                                                <div className={`w-2.5 h-2.5 rounded-full ${(STATUS_STYLES[node.status] || STATUS_STYLES.untracked).dot}`} />
                                                <span className="text-gray-400">{(STATUS_STYLES[node.status] || STATUS_STYLES.untracked).label}</span>
                                            </div>
                                        </div>

                                        <div className="flex flex-wrap gap-2 mb-3 text-xs">
                                            <span className={`px-2 py-0.5 rounded-full break-all ${darkMode ? 'bg-blue-600 bg-opacity-20 text-blue-400' : 'bg-blue-50 text-blue-700'}`}>#{node.tag}</span>
                                            <span className={`px-2 py-0.5 rounded-full break-all ${darkMode ? 'bg-purple-600 bg-opacity-20 text-purple-400' : 'bg-sky-50 text-sky-700'}`}>node: {node.node_name}</span>
                                        </div>

                                        <div className={`${darkMode ? 'bg-gray-900' : 'bg-gray-50'} rounded-lg p-4 mb-3 min-h-24 payload-box`}>
                                            {node.last_value ? formatValue(node.last_value) : (
                                                <div className="flex items-center justify-center h-full text-gray-500">
                                                    <Icons.AlertCircle className="w-5 h-5 mr-2" />
                                                    Waiting for data...
                                                </div>
                                            )}
                                        </div>

                                        <div className="flex justify-between text-xs text-gray-500 mb-4">
                                            <span>{(node.entry_count || 0).toLocaleString()} entries</span>
                                            <span>~{formatBytes(node.approx_size_bytes)}</span>
                                        </div>

                                        <div className="flex gap-2">
                                            <button
                                                onClick={() => showNodeDetails(node.id)}
                                                className="flex-1 bg-blue-600 hover:bg-blue-700 text-white px-3 py-2 rounded-lg text-sm transition"
                                            >
                                                Details
                                            </button>
                                            <button
                                                onClick={() => openEditNode(node)}
                                                title="Edit tag / node / LWT"
                                                className={`p-2 rounded-lg ${darkMode ? 'bg-gray-700 hover:bg-gray-600' : 'bg-gray-200 hover:bg-gray-300'} transition`}
                                            >
                                                <Icons.Settings className="w-4 h-4" />
                                            </button>
                                            <button
                                                onClick={() => exportData(node.id, node.topic)}
                                                title="Export CSV"
                                                className={`p-2 rounded-lg ${darkMode ? 'bg-gray-700 hover:bg-gray-600' : 'bg-gray-200 hover:bg-gray-300'} transition`}
                                            >
                                                <Icons.Download className="w-4 h-4" />
                                            </button>
                                            <button
                                                onClick={() => deleteNode(node.id, node.topic)}
                                                title="Delete"
                                                className="p-2 bg-red-600 hover:bg-red-700 text-white rounded-lg transition"
                                            >
                                                <Icons.Trash2 className="w-4 h-4" />
                                            </button>
                                        </div>
                                    </div>
                                ))}
                            </div>
                            </div>
                        ))}
                    </div>

                    {showAddNode && (
                        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4 overflow-y-auto">
                            <div className={`sh-modal ${cardBg} rounded-xl p-5 sm:p-6 max-w-md w-full my-8 min-w-0`} role="dialog" aria-modal="true">
                                <h2 className="text-2xl font-bold mb-4">{editingNodeId ? 'Edit Node' : 'Add New Node'}</h2>
                                <div className="space-y-3">
                                    <label className="block text-xs text-gray-500">
                                        MQTT Topic *
                                        <input
                                            type="text"
                                            value={nodeForm.topic}
                                            disabled={!!editingNodeId}
                                            onChange={(e) => setNodeForm({...nodeForm, topic: e.target.value})}
                                            placeholder="e.g., sensors/temperature"
                                            className={`w-full mt-1 px-4 py-2 rounded-lg border ${borderClass} ${darkMode ? 'bg-gray-700 text-white' : 'bg-white text-gray-900'} ${editingNodeId ? 'opacity-60' : ''}`}
                                        />
                                    </label>
                                    <label className="block text-xs text-gray-500">
                                        Node ID * (groups topics of the same device)
                                        <input
                                            type="text"
                                            list="node-name-options"
                                            value={nodeForm.node_name}
                                            onChange={(e) => setNodeForm({...nodeForm, node_name: e.target.value})}
                                            placeholder="e.g., greenhouse-esp32"
                                            className={`w-full mt-1 px-4 py-2 rounded-lg border ${borderClass} ${darkMode ? 'bg-gray-700 text-white' : 'bg-white text-gray-900'}`}
                                        />
                                        <datalist id="node-name-options">
                                            {allNodeNames.map(name => <option key={name} value={name} />)}
                                        </datalist>
                                    </label>
                                    <label className="block text-xs text-gray-500">
                                        Tag *
                                        <input
                                            type="text"
                                            list="tag-options"
                                            value={nodeForm.tag}
                                            onChange={(e) => setNodeForm({...nodeForm, tag: e.target.value})}
                                            placeholder="e.g., environment"
                                            className={`w-full mt-1 px-4 py-2 rounded-lg border ${borderClass} ${darkMode ? 'bg-gray-700 text-white' : 'bg-white text-gray-900'}`}
                                        />
                                        <datalist id="tag-options">
                                            {allTags.map(tag => <option key={tag} value={tag} />)}
                                        </datalist>
                                    </label>
                                    <label className="block text-xs text-gray-500">
                                        LWT / status topic (optional)
                                        <input
                                            type="text"
                                            value={nodeForm.lwt_topic}
                                            onChange={(e) => setNodeForm({...nodeForm, lwt_topic: e.target.value})}
                                            placeholder="e.g., greenhouse-esp32/status"
                                            className={`w-full mt-1 px-4 py-2 rounded-lg border ${borderClass} ${darkMode ? 'bg-gray-700 text-white' : 'bg-white text-gray-900'}`}
                                        />
                                    </label>
                                    {nodeForm.lwt_topic.trim() && (
                                        <div className="grid grid-cols-2 gap-3">
                                            <label className="block text-xs text-gray-500">
                                                Online payload
                                                <input
                                                    type="text"
                                                    value={nodeForm.lwt_online}
                                                    onChange={(e) => setNodeForm({...nodeForm, lwt_online: e.target.value})}
                                                    className={`w-full mt-1 px-4 py-2 rounded-lg border ${borderClass} ${darkMode ? 'bg-gray-700 text-white' : 'bg-white text-gray-900'}`}
                                                />
                                            </label>
                                            <label className="block text-xs text-gray-500">
                                                Offline payload
                                                <input
                                                    type="text"
                                                    value={nodeForm.lwt_offline}
                                                    onChange={(e) => setNodeForm({...nodeForm, lwt_offline: e.target.value})}
                                                    className={`w-full mt-1 px-4 py-2 rounded-lg border ${borderClass} ${darkMode ? 'bg-gray-700 text-white' : 'bg-white text-gray-900'}`}
                                                />
                                            </label>
                                        </div>
                                    )}
                                    {formError && <p className="text-sm text-red-400">{formError}</p>}
                                </div>
                                <div className="flex gap-3 mt-6">
                                    <button
                                        onClick={saveNode}
                                        className="flex-1 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition"
                                    >
                                        {editingNodeId ? 'Save Changes' : 'Add Node'}
                                    </button>
                                    <button
                                        onClick={closeNodeForm}
                                        className={`px-4 py-2 rounded-lg ${darkMode ? 'bg-gray-700 hover:bg-gray-600' : 'bg-gray-200 hover:bg-gray-300'} transition`}
                                    >
                                        Cancel
                                    </button>
                                </div>
                            </div>
                        </div>
                    )}

                    {showSettings && (
                        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4 overflow-y-auto">
                            <div className={`sh-modal ${cardBg} rounded-xl p-5 sm:p-6 max-w-md w-full my-8 min-w-0`} role="dialog" aria-modal="true">
                                <h2 className="text-2xl font-bold mb-6">Settings</h2>
                                
                                <div className="space-y-6">
                                    <div>
                                        <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
                                            <Icons.Activity className="w-5 h-5" />
                                            MQTT Broker
                                        </h3>
                                        <div className="space-y-3">
                                            <input
                                                type="text"
                                                value={brokerConfig.host}
                                                onChange={(e) => setBrokerConfig({...brokerConfig, host: e.target.value})}
                                                placeholder="Broker Host"
                                                className={`w-full px-4 py-2 rounded-lg border ${borderClass} ${darkMode ? 'bg-gray-700' : 'bg-white'}`}
                                            />
                                            <input
                                                type="number"
                                                value={brokerConfig.port}
                                                onChange={(e) => setBrokerConfig({...brokerConfig, port: parseInt(e.target.value)})}
                                                placeholder="Port"
                                                className={`w-full px-4 py-2 rounded-lg border ${borderClass} ${darkMode ? 'bg-gray-700' : 'bg-white'}`}
                                            />
                                            <input
                                                type="text"
                                                value={brokerConfig.username}
                                                onChange={(e) => setBrokerConfig({...brokerConfig, username: e.target.value})}
                                                placeholder="Username (optional)"
                                                className={`w-full px-4 py-2 rounded-lg border ${borderClass} ${darkMode ? 'bg-gray-700' : 'bg-white'}`}
                                            />
                                            <input
                                                type="password"
                                                value={brokerConfig.password}
                                                onChange={(e) => setBrokerConfig({...brokerConfig, password: e.target.value})}
                                                placeholder="Password (optional)"
                                                className={`w-full px-4 py-2 rounded-lg border ${borderClass} ${darkMode ? 'bg-gray-700' : 'bg-white'}`}
                                            />
                                        </div>
                                        {/* Public Broker Defaults Info */}
<div className={`${darkMode ? 'bg-gray-900 border-gray-700' : 'bg-gray-50 border-gray-200'} border rounded-lg p-4`}>
  <p className="text-sm font-semibold mb-2 text-blue-400">
    Default Public Broker (HiveMQ) - Quick Switch Info
  </p>

  <div className="text-xs space-y-1 text-gray-400">
    <div className="flex justify-between">
      <span>Host:</span>
      <span className="font-mono text-gray-200">broker.hivemq.com</span>
    </div>
    <div className="flex justify-between">
      <span>TCP Port:</span>
      <span className="font-mono text-gray-200">1883</span>
    </div>
    <div className="flex justify-between">
      <span>TLS TCP Port:</span>
      <span className="font-mono text-gray-200">8883</span>
    </div>
  </div>

  <p className="text-[11px] text-gray-500 mt-2">
    Note: Internet connection is required to use this free public broker Leave username & password empty.
  </p>
</div>

                                    </div>

                                    <div>
                                        <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
                                            <Icons.Globe className="w-5 h-5" />
                                            Timezone
                                        </h3>
                                        <select
                                            value={brokerConfig.timezone}
                                            onChange={(e) => setBrokerConfig({...brokerConfig, timezone: e.target.value})}
                                            className={`w-full px-4 py-2 rounded-lg border ${borderClass} ${darkMode ? 'bg-gray-700' : 'bg-white'}`}
                                        >
                                            {timezones.map(tz => (
                                                <option key={tz} value={tz}>{tz}</option>
                                            ))}
                                        </select>
                                        <p className="text-xs text-gray-500 mt-1">All timestamps will be stored in this timezone</p>
                                    </div>

                                    <div>
                                        <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
                                            <Icons.Trash2 className="w-5 h-5" />
                                            Data Retention
                                        </h3>
                                        <div className="grid grid-cols-2 gap-3">
                                            <label className="text-xs text-gray-500">
                                                Keep days
                                                <input
                                                    type="number"
                                                    min="0"
                                                    value={retention.retention_days}
                                                    onChange={(e) => setRetention({...retention, retention_days: Math.max(0, parseInt(e.target.value) || 0)})}
                                                    className={`w-full mt-1 px-4 py-2 rounded-lg border ${borderClass} ${darkMode ? 'bg-gray-700 text-white' : 'bg-white text-gray-900'}`}
                                                />
                                            </label>
                                            <label className="text-xs text-gray-500">
                                                Max entries / topic
                                                <input
                                                    type="number"
                                                    min="0"
                                                    value={retention.retention_max_entries}
                                                    onChange={(e) => setRetention({...retention, retention_max_entries: Math.max(0, parseInt(e.target.value) || 0)})}
                                                    className={`w-full mt-1 px-4 py-2 rounded-lg border ${borderClass} ${darkMode ? 'bg-gray-700 text-white' : 'bg-white text-gray-900'}`}
                                                />
                                            </label>
                                        </div>
                                        <p className="text-xs text-gray-500 mt-1">0 = keep forever. Cleanup runs automatically every hour.</p>
                                        <button
                                            onClick={runRetentionNow}
                                            className={`w-full mt-3 px-4 py-2 rounded-lg ${darkMode ? 'bg-gray-700 hover:bg-gray-600' : 'bg-gray-200 hover:bg-gray-300'} transition text-sm`}
                                        >
                                            Run Cleanup Now
                                        </button>
                                    </div>

                                    <div>
                                        <h3 className="text-lg font-semibold mb-3 flex items-center gap-2">
                                            <Icons.Key className="w-5 h-5" />
                                            Account
                                        </h3>
                                        <button
                                            onClick={() => setShowPasswordChange(true)}
                                            className="w-full bg-purple-600 hover:bg-purple-700 px-4 py-2 rounded-lg transition"
                                        >
                                            Change Password
                                        </button>
                                    </div>
                                </div>

                                <div className={`flex gap-3 mt-6 pt-6 border-t ${borderClass}`}>
                                    <button
                                        onClick={testBroker}
                                        className="flex-1 bg-green-600 hover:bg-green-700 px-4 py-2 rounded-lg transition"
                                    >
                                        Test Connection
                                    </button>
                                    <button
                                        onClick={saveBrokerConfig}
                                        className="flex-1 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition"
                                    >
                                        Save All
                                    </button>
                                    <button
                                        onClick={() => setShowSettings(false)}
                                        className={`px-4 py-2 rounded-lg ${darkMode ? 'bg-gray-700 hover:bg-gray-600' : 'bg-gray-200 hover:bg-gray-300'} transition`}
                                    >
                                        Cancel
                                    </button>
                                </div>
                            </div>
                        </div>
                    )}

                    {showPasswordChange && (
                        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
                            <div className={`sh-modal ${cardBg} rounded-xl p-5 sm:p-6 max-w-md w-full min-w-0`} role="dialog" aria-modal="true">
                                <h2 className="text-2xl font-bold mb-4">Change Password</h2>
                                <div className="space-y-4">
                                    <input
                                        type="password"
                                        value={passwordData.current}
                                        onChange={(e) => setPasswordData({...passwordData, current: e.target.value})}
                                        placeholder="Current Password"
                                        className={`w-full px-4 py-2 rounded-lg border ${borderClass} ${darkMode ? 'bg-gray-700' : 'bg-white'}`}
                                    />
                                    <input
                                        type="password"
                                        value={passwordData.new}
                                        onChange={(e) => setPasswordData({...passwordData, new: e.target.value})}
                                        placeholder="New Password (min 6 characters)"
                                        className={`w-full px-4 py-2 rounded-lg border ${borderClass} ${darkMode ? 'bg-gray-700' : 'bg-white'}`}
                                    />
                                    <input
                                        type="password"
                                        value={passwordData.confirm}
                                        onChange={(e) => setPasswordData({...passwordData, confirm: e.target.value})}
                                        placeholder="Confirm New Password"
                                        className={`w-full px-4 py-2 rounded-lg border ${borderClass} ${darkMode ? 'bg-gray-700' : 'bg-white'}`}
                                    />
                                </div>
                                <div className="flex gap-3 mt-6">
                                    <button
                                        onClick={changePassword}
                                        className="flex-1 bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-lg transition"
                                    >
                                        Update Password
                                    </button>
                                    <button
                                        onClick={() => {
                                            setShowPasswordChange(false);
                                            setPasswordData({ current: '', new: '', confirm: '' });
                                        }}
                                        className={`px-4 py-2 rounded-lg ${darkMode ? 'bg-gray-700 hover:bg-gray-600' : 'bg-gray-200 hover:bg-gray-300'} transition`}
                                    >
                                        Cancel
                                    </button>
                                </div>
                            </div>
                        </div>
                    )}

                    {showDetails && (
                        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
                            <div className={`sh-modal ${cardBg} rounded-xl p-5 sm:p-6 max-w-4xl w-full max-h-[85vh] overflow-y-auto min-w-0`} role="dialog" aria-modal="true">
                                <div className="flex justify-between items-center mb-4">
                                    <h2 className="text-2xl font-bold">History - Last 50 Values</h2>
                                    <button
                                        onClick={() => setShowDetails(null)}
                                        className={`p-2 rounded-lg ${darkMode ? 'hover:bg-gray-700' : 'hover:bg-gray-100'} transition`}
                                    >
                                        <Icons.XCircle className="w-6 h-6" />
                                    </button>
                                </div>
                                <div className="space-y-3">
                                    {showDetails.history?.map((entry, idx) => (
                                        <div key={idx} className={`${darkMode ? 'bg-gray-900' : 'bg-gray-50'} rounded-lg p-4 payload-box`}>
                                            <div className="text-xs text-gray-500 mb-2">{new Date(entry.timestamp).toLocaleString()}</div>
                                            {formatValue(entry.payload)}
                                        </div>
                                    ))}
                                    {(!showDetails.history || showDetails.history.length === 0) && (
                                        <div className="text-center py-8 text-gray-500">No data available</div>
                                    )}
                                </div>
                            </div>
                        </div>
                    )}
                </div>
            );
        };

        ReactDOM.createRoot(document.getElementById('root')).render(<IoTDashboard />);

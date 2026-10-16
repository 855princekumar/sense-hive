        const { useState } = React;

        const LoginPage = () => {
            const [username, setUsername] = useState('');
            const [password, setPassword] = useState('');
            const [error, setError] = useState('');
            const [loading, setLoading] = useState(false);

            const handleLogin = async (e) => {
                e.preventDefault();
                setError('');
                setLoading(true);

                try {
                    const response = await fetch('api/login', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ username, password })
                    });

                    const data = await response.json();

                    if (data.success) {
                        window.location.href = './';
                    } else {
                        setError(data.error || 'Login failed');
                    }
                } catch (err) {
                    setError('Connection error. Please try again.');
                } finally {
                    setLoading(false);
                }
            };

            // Same sign-in card as EdgeShell: light page, white card, primary blue.
            return (
                <div className="min-h-screen bg-slate-100 flex items-center justify-center p-4">
                    <div className="bg-white rounded-2xl shadow-xl w-full max-w-md px-6 py-10 sm:px-10">
                        <div className="flex items-center gap-3 mb-8">
                            <div className="w-10 h-10 rounded-lg bg-blue-600 flex items-center justify-center flex-shrink-0">
                                <svg className="w-5 h-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M22 12h-4l-3 9L9 3l-3 9H2" />
                                </svg>
                            </div>
                            <div className="min-w-0">
                                <div className="text-xl font-bold text-gray-900">SenseHive</div>
                                <div className="text-xs text-gray-400">MQTT data logger</div>
                            </div>
                        </div>
                        <h1 className="text-2xl font-bold text-gray-900 mb-1">Sign in</h1>
                        <p className="text-sm text-gray-400 mb-7">Sign in to see your nodes and their data.</p>

                        <form onSubmit={handleLogin} className="space-y-4">
                            {error && (
                                <div id="loginError" role="alert" className="bg-red-50 border border-red-300 text-red-500 px-3 py-2.5 rounded-lg text-sm">
                                    {error}
                                </div>
                            )}
                            <div>
                                <label htmlFor="username" className="block text-sm font-medium text-gray-700 mb-1">Username</label>
                                <input id="username" type="text" value={username} autoComplete="username"
                                    onChange={(e) => setUsername(e.target.value)}
                                    className="w-full px-3 py-2.5 rounded-lg border-2 border-gray-300 bg-gray-50 text-gray-900 text-sm focus:outline-none focus:border-blue-600 focus:bg-white focus:ring-4 focus:ring-blue-100 transition"
                                    required autoFocus />
                            </div>
                            <div>
                                <label htmlFor="password" className="block text-sm font-medium text-gray-700 mb-1">Password</label>
                                <input id="password" type="password" value={password} autoComplete="current-password"
                                    onChange={(e) => setPassword(e.target.value)}
                                    className="w-full px-3 py-2.5 rounded-lg border-2 border-gray-300 bg-gray-50 text-gray-900 text-sm focus:outline-none focus:border-blue-600 focus:bg-white focus:ring-4 focus:ring-blue-100 transition"
                                    required />
                            </div>
                            <button id="submitBtn" type="submit" disabled={loading}
                                className="w-full mt-2 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-700 text-white font-semibold transition disabled:opacity-60 disabled:cursor-not-allowed">
                                {loading ? 'Signing in...' : 'Sign in'}
                            </button>
                        </form>
                        <p className="text-center mt-6 text-xs text-gray-300">SenseHive</p>
                    </div>
                </div>
            );
        };

        ReactDOM.createRoot(document.getElementById('root')).render(<LoginPage />);

"""Tiny cookie-aware JSON HTTP client (stdlib only, so tests need no extra dependencies)."""
import http.cookiejar
import json
import urllib.error
import urllib.request


class Session:
    def __init__(self, base_url):
        self.base_url = base_url
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def _request(self, method, path, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base_url + path, data=data, method=method,
                                     headers={'Content-Type': 'application/json'})
        try:
            with self.opener.open(req, timeout=10) as res:
                return json.loads(res.read().decode() or 'null')
        except urllib.error.HTTPError as e:
            return json.loads(e.read().decode() or 'null')

    def get(self, path):
        return self._request('GET', path)

    def post(self, path, body):
        return self._request('POST', path, body)

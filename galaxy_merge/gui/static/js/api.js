const API = {
  async get(path) {
    const r = await fetch(path);
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  },
  async post(path, data) {
    const r = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    const body = await r.json();
    if (!r.ok) throw new Error(body.error || `${r.status} ${r.statusText}`);
    return body;
  },
  async patch(path, data) {
    const r = await fetch(path, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
    const body = await r.json();
    if (!r.ok) throw new Error(body.error || `${r.status} ${r.statusText}`);
    return body;
  },
  getSession() { return this.get('/api/session'); },
  getSessions() { return this.get('/api/sessions'); },
  getProject() { return this.get('/api/project'); },
  getTools() { return this.get('/api/tools'); },
  getTree() { return this.get('/api/tree'); },
  postGoal(goal) { return this.post('/api/goal', { goal }); },
  getEvents() { return this.get('/api/events'); },
  getSafety() { return this.get('/api/safety'); },
  getNotes() { return this.get('/api/notes'); },
  getNotesUsage() { return this.get('/api/notes/usage'); },
  getNotesTrashed() { return this.get('/api/notes/trash'); },
  getNotesInjected() { return this.get('/api/notes/injected'); },
  getCouncil() { return this.get('/api/council'); },
  getMemory(kind = 'all') { return this.get(`/api/memory?kind=${encodeURIComponent(kind)}`); },
  getSkills() { return this.get('/api/skills'); },
  postSecretScan() { return this.post('/api/secret-scan', {}); },
  getBrowserSessions() { return this.get('/api/browser/sessions'); },
  getBrowserConsole() { return this.get('/api/browser/console'); },
  getBrowserNetwork() { return this.get('/api/browser/network'); },
  getBrowserErrors() { return this.get('/api/browser/errors'); },
  getBrowserScreenshot(sessionId = 'gui') { return this.get(`/api/browser/screenshot?session_id=${encodeURIComponent(sessionId)}`); },
  postBrowserOpen(url) { return this.post('/api/browser/open', { url }); },
  getWebSearch(q, source = 'duckduckgo') { return this.get(`/api/web/search?q=${encodeURIComponent(q)}&source=${encodeURIComponent(source)}`); },
  postWebFetch(url, source = 'duckduckgo') { return this.post('/api/web/fetch', { url, source }); },
  getWebSource(url) { return this.post('/api/web/fetch', { url }); },
  getGithubScan(url) { return this.get(`/api/github/scan?url=${encodeURIComponent(url)}`); },
  getLocations() { return this.get('/api/locations'); },
};

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
  getProject() { return this.get('/api/project'); },
  getTree() { return this.get('/api/tree'); },
  postGoal(goal) { return this.post('/api/goal', { goal }); },
  getEvents() { return this.get('/api/events'); },
  getSafety() { return this.get('/api/safety'); },
  getNotes() { return this.get('/api/notes'); },
  getCouncil() { return this.get('/api/council'); },
};

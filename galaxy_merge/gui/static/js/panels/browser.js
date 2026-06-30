(function() {
  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
  }

  window.BrowserPanel = {
    async refresh() {
      await this.refreshSessions();
      await this.refreshConsole();
      await this.refreshNetwork();
      await this.refreshErrors();
    },

    async refreshSessions() {
      try {
        const data = await API.get('/api/browser/sessions');
        const container = document.getElementById('browser-sessions');
        if (!container) return;
        const sessions = data.sessions || [];
        if (sessions.length === 0) {
          container.innerHTML = '<div style="color:var(--fg2);padding:4px">No browser sessions</div>';
          return;
        }
        let html = '';
        for (const s of sessions) {
          const status = s.running ? '<span style="color:var(--accent2)">running</span>' : '<span style="color:var(--red)">stopped</span>';
          html += `<div class="provider-card">
            <div class="provider-name">${escapeHtml(s.session_id)}</div>
            <div class="provider-status">${escapeHtml(s.url)} ${status}</div>
          </div>`;
        }
        container.innerHTML = html;
      } catch (e) {
        console.error('browser sessions refresh failed', e);
      }
    },

    async refreshConsole() {
      try {
        const data = await API.getBrowserConsole();
        const container = document.getElementById('browser-console');
        if (!container) return;
        const logs = data.logs || [];
        if (logs.length === 0) {
          container.innerHTML = '<div style="color:var(--fg2);padding:4px">No console logs</div>';
          return;
        }
        let html = '';
        for (const log of logs.slice(-50)) {
          const level = (log.level || '').toLowerCase();
          const color = level === 'error' ? 'var(--red)' : level === 'warn' ? 'var(--yellow)' : 'var(--fg)';
          html += `<div class="log-line" style="color:${color}">[${escapeHtml(log.level || 'log')}] ${escapeHtml(log.text || log.message || '')}</div>`;
        }
        container.innerHTML = html;
        container.scrollTop = container.scrollHeight;
      } catch (e) {
        console.error('browser console refresh failed', e);
      }
    },

    async refreshNetwork() {
      try {
        const data = await API.getBrowserNetwork();
        const container = document.getElementById('browser-network');
        if (!container) return;
        const logs = data.logs || [];
        if (logs.length === 0) {
          container.innerHTML = '<div style="color:var(--fg2);padding:4px">No network logs</div>';
          return;
        }
        let html = '';
        for (const log of logs.slice(-30)) {
          const failed = log.failed || (log.status >= 400);
          const color = failed ? 'var(--red)' : 'var(--fg2)';
          html += `<div class="log-line" style="color:${color}">${escapeHtml(log.method || 'GET')} ${escapeHtml(log.url || '')} ${log.status || ''}</div>`;
        }
        container.innerHTML = html;
      } catch (e) {
        console.error('browser network refresh failed', e);
      }
    },

    async refreshErrors() {
      try {
        const container = document.getElementById('browser-errors');
        if (!container) return;
        container.innerHTML = '<div style="color:var(--fg2);padding:4px">Page errors captured via CDP</div>';
      } catch (e) {
        console.error('browser errors refresh failed', e);
      }
    }
  };
})();

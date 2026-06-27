(function() {
  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
  }

  window.BrowserPanel = {
    async refresh() {
      try {
        const r = await fetch('/api/browser/sessions');
        const data = await r.json();
        const container = document.getElementById('browser-panel');
        const sessions = data.sessions || [];
        if (sessions.length === 0) {
          container.innerHTML = '<div style="color:var(--fg2);padding:4px">No browser sessions</div>';
          return;
        }
        let html = '';
        for (const s of sessions) {
          html += `<div class="tree-item" style="padding:2px 0">${escapeHtml(s.session_id)}: ${escapeHtml(s.url)} ${s.running ? 'running' : 'stopped'}</div>`;
        }
        container.innerHTML = html;
      } catch (e) {
        console.error('browser refresh failed', e);
      }
    }
  };
})();

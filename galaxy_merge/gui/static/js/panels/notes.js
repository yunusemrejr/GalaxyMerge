(function() {
  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
  }

  window.NotesPanel = {
    async refresh() {
      try {
        const payload = await API.getNotes();
        const container = document.getElementById('notes-panel');
        const entries = payload.notes || Object.entries(payload || {})
          .filter(([name, value]) => typeof value === 'string' && name !== 'index')
          .map(([name, content]) => ({name, content}));
        container.innerHTML = '';
        if (entries.length === 0) {
          container.innerHTML = '<div style="color:var(--fg2);padding:4px">No notes. Click + to create.</div>';
          return;
        }
        if (payload.truncated) {
          const notice = document.createElement('div');
          notice.className = 'tree-item';
          notice.style.color = 'var(--yellow)';
          notice.textContent = `Showing ${entries.length} of ${payload.total} notes`;
          container.appendChild(notice);
        }
        for (const note of entries) {
          const name = note.name;
          const content = note.content || '';
          const preview = content.slice(0, 60).replace(/\n/g, ' ');
          const div = document.createElement('div');
          div.className = 'tree-item';
          div.innerHTML = `<span style="color:var(--accent)">${escapeHtml(name)}.md</span> ${escapeHtml(preview)}${content.length > 60 ? '...' : ''}`;
          div.style.cursor = 'pointer';
          div.onclick = () => {
            const newContent = prompt(`Edit ${name}.md:`, content);
            if (newContent !== null) {
              API.patch(`/api/notes/${encodeURIComponent(name)}`, {content: newContent}).then(() => this.refresh());
            }
          };
          container.appendChild(div);
        }
      } catch (e) {
        console.error('notes refresh failed', e);
      }
    }
  };

  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('btn-new-note').addEventListener('click', () => {
      const name = prompt('Note name:');
      if (!name) return;
      fetch('/api/notes', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name, content: ''}),
      }).then(() => window.NotesPanel.refresh());
    });
  });
})();

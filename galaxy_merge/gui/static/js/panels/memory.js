(function() {
  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
  }

  window.MemoryPanel = {
    async refresh() {
      try {
        const payload = await API.getNotes();
        const container = document.getElementById('memory-panel');
        const entries = payload.notes || [];
        if (entries.length === 0) {
          container.innerHTML = '<div style="color:var(--fg2);padding:4px">No memory entries</div>';
          return;
        }
        container.innerHTML = entries.slice(0, 10).map(note => {
          const content = note.content || '';
          const preview = content.slice(0, 80).replace(/\n/g, ' ');
          return `<div class="tree-item">${escapeHtml(note.name)}.md: ${escapeHtml(preview)}${content.length > 80 ? '...' : ''}</div>`;
        }).join('');
      } catch (e) {
        console.error('memory refresh failed', e);
      }
    }
  };
})();

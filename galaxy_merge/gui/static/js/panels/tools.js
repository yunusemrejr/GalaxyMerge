(function() {
  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
  }

  window.ToolsPanel = {
    render(tools) {
      const container = document.getElementById('tools-panel');
      if (!tools || tools.length === 0) {
        container.innerHTML = '<div style="color:var(--fg2);padding:4px">No tools registered</div>';
        return;
      }
      let html = '';
      for (const t of tools) {
        html += `<div class="tree-item" style="padding:2px 4px;border-bottom:1px solid var(--border)">`;
        html += `<span style="color:var(--accent)">${escapeHtml(t.name)}</span>`;
        if (t.mutates) html += ' <span style="color:var(--yellow)">[mutates]</span>';
        html += `<div style="color:var(--fg2);font-size:10px">${escapeHtml(t.description)}</div>`;
        html += `</div>`;
      }
      container.innerHTML = html;
    }
  };
})();

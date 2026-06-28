(function() {
  function escapeHtml(value) {
    return String(value || '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  window.CouncilPanel = {
    render(data) {
      const container = document.getElementById('council-panel');
      if (!data || data.length === 0) {
        container.innerHTML = '<div style="color:var(--fg2);padding:4px">No council data</div>';
        return;
      }
      let html = '<table style="width:100%;border-collapse:collapse;font-size:11px">';
      html += '<tr style="color:var(--fg2)"><th>Role</th><th>Provider</th><th>Model</th><th>Status</th><th>Error</th></tr>';
      for (const entry of data) {
        const rawStatus = String(entry.status || (entry.error ? 'degraded' : 'ok')).toUpperCase();
        const failed = rawStatus === 'DEGRADED' || rawStatus === 'FAILED';
        const color = failed ? 'var(--red)' : rawStatus === 'FALLBACK' ? 'var(--yellow)' : 'var(--accent2)';
        html += `<tr style="border-bottom:1px solid var(--border)">
          <td>${escapeHtml(entry.role)}</td>
          <td>${escapeHtml(entry.provider || entry.provider_id)}</td>
          <td>${escapeHtml(entry.model)}</td>
          <td style="color:${color};font-weight:600">${escapeHtml(rawStatus)}</td>
          <td style="color:${color};max-width:320px;white-space:normal">${escapeHtml(entry.error)}</td>
        </tr>`;
      }
      html += '</table>';
      container.innerHTML = html;
    }
  };
})();

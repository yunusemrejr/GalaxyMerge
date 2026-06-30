(function() {
  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
  }

  const toolCalls = [];

  window.ToolsPanel = {
    render(tools) {
      const container = document.getElementById('tools-panel');
      if (!container) return;
      let html = '<div class="memory-section">';
      html += '<div class="memory-section-header">Registered Tools</div>';
      if (!tools || tools.length === 0) {
        html += '<div style="color:var(--fg2);padding:4px">No tools registered</div>';
      } else {
        for (const t of tools) {
          html += `<div class="tree-item" style="padding:2px 4px;border-bottom:1px solid var(--border)">`;
          html += `<span style="color:var(--accent)">${escapeHtml(t.name)}</span>`;
          if (t.mutates) html += ' <span style="color:var(--yellow)">[mutates]</span>';
          html += `<div style="color:var(--fg2);font-size:10px">${escapeHtml(t.description)}</div>`;
          html += `</div>`;
        }
      }
      html += '</div>';

      html += '<div class="memory-section">';
      html += '<div class="memory-section-header">Recent Tool Calls</div>';
      if (toolCalls.length === 0) {
        html += '<div style="color:var(--fg2);padding:4px">No recent tool calls</div>';
      } else {
        for (const call of toolCalls.slice(-20).reverse()) {
          const statusColor = call.status === 'blocked' ? 'var(--red)' : call.status === 'completed' ? 'var(--accent2)' : 'var(--accent)';
          html += `<div class="failure-entry">
            <span style="color:${statusColor}">${escapeHtml(call.tool)}</span>
            <span style="color:var(--fg2);font-size:9px"> ${escapeHtml(call.status || 'started')}</span>
            ${call.duration_ms ? `<span style="color:var(--fg2);font-size:9px"> ${call.duration_ms}ms</span>` : ''}
          </div>`;
        }
      }
      html += '</div>';

      container.innerHTML = html;
    },

    addToolCall(data) {
      toolCalls.push({
        tool: data.tool || 'unknown',
        status: data.status || 'started',
        duration_ms: data.duration_ms,
        time: data.time || Date.now()
      });
      if (toolCalls.length > 100) {
        toolCalls.splice(0, toolCalls.length - 100);
      }
    }
  };
})();

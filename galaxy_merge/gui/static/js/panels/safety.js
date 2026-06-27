(function() {
  window.SafetyPanel = {
    async refresh() {
      try {
        const safety = await API.getSafety();
        const container = document.getElementById('safety-panel');
        if (!safety) return;
        let html = `<div class="safety-entry">Policy: ${safety.active_policy || 'default'}`;
        if (safety.readonly_mode) html += ' <span style="color:var(--yellow)">[READ-ONLY]</span>';
        html += '</div>';
        html += `<div class="safety-entry">Blocked commands: ${(safety.blocked_commands||[]).length}</div>`;
        container.innerHTML = html;
      } catch (e) {
        console.error('safety refresh failed', e);
      }
    }
  };
})();

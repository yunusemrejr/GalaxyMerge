(function() {
  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
  }

  window.LocationsPanel = {
    async refresh() {
      try {
        const r = await fetch('/api/locations');
        const data = await r.json();
        const container = document.getElementById('locations-panel');
        
        let html = '';
        
        if (data.workroot) {
          html += `<div class="location-card">
            <div class="loc-target">WorkRoot</div>
            <div style="font-size:10px;color:var(--fg2)">${escapeHtml(data.workroot)}</div>
          </div>`;
        }
        
        if (data.taskscope) {
          const ts = Array.isArray(data.taskscope) ? data.taskscope.join(', ') : data.taskscope;
          html += `<div class="location-card">
            <div class="loc-target">TaskScope</div>
            <div style="font-size:10px;color:var(--fg2)">${escapeHtml(ts)}</div>
          </div>`;
        }
        
        const classified = data.classified_locations || [];
        if (classified.length > 0) {
          html += '<div style="font-size:10px;color:var(--fg2);padding:4px;border-bottom:1px solid var(--border)">Classified Locations</div>';
          for (const loc of classified) {
            const riskClass = loc.risk === 'high' ? 'loc-risk-high' : loc.risk === 'medium' ? 'loc-risk-medium' : 'loc-risk-low';
            html += `<div class="location-card">
              <div class="loc-target">${escapeHtml(loc.target || '')}</div>
              <div class="loc-class">
                <span style="color:var(--accent)">${escapeHtml(loc.classification || 'unknown')}</span>
                <span class="${riskClass}">[${escapeHtml(loc.risk || 'low')}]</span>
              </div>
              ${loc.host ? `<div style="font-size:10px;color:var(--fg2)">Host: ${escapeHtml(loc.host)}</div>` : ''}
              ${loc.policy_decision ? `<div class="loc-policy">Policy: ${escapeHtml(loc.policy_decision)}</div>` : ''}
            </div>`;
          }
        }
        
        const remoteTargets = data.remote_targets || [];
        if (remoteTargets.length > 0) {
          html += '<div style="font-size:10px;color:var(--fg2);padding:4px;border-bottom:1px solid var(--border)">Remote Targets</div>';
          for (const remote of remoteTargets) {
            html += `<div class="location-card">
              <div class="loc-target">${escapeHtml(remote.id || remote.repo || '')}</div>
              <div style="font-size:10px;color:var(--fg2)">${escapeHtml(remote.host || '')} ${escapeHtml(remote.path || '')}</div>
            </div>`;
          }
        }
        
        if (!html) {
          html = '<div style="color:var(--fg2);padding:4px">No location data</div>';
        }
        
        container.innerHTML = html;
      } catch (e) {
        console.error('locations refresh failed', e);
      }
    }
  };
})();

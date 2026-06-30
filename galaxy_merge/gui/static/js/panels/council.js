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
    async refresh() {
      try {
        const data = await API.getCouncil();
        this.renderRoles(data.roles || []);
        this.renderProviders(data.providers || []);
        this.renderFailures(data.provider_failures || [], data.fallback_events || []);
      } catch (e) {
        console.error('council refresh failed', e);
      }
    },

    renderRoles(roles) {
      const container = document.getElementById('council-roles');
      if (!container) return;
      if (!roles || roles.length === 0) {
        container.innerHTML = '<div style="color:var(--fg2);padding:4px">No council roles</div>';
        return;
      }
      let html = '';
      for (const entry of roles) {
        const rawStatus = String(entry.status || (entry.error ? 'degraded' : 'ok')).toUpperCase();
        const failed = rawStatus === 'DEGRADED' || rawStatus === 'FAILED';
        const color = failed ? 'var(--red)' : rawStatus === 'FALLBACK' ? 'var(--yellow)' : 'var(--accent2)';
        html += `<div class="provider-card">
          <div>
            <span class="provider-name">${escapeHtml(entry.role)}</span>
            <span style="color:${color};font-weight:600;font-size:10px"> ${escapeHtml(rawStatus)}</span>
          </div>
          <div style="font-size:10px;color:var(--fg2)">
            ${escapeHtml(entry.provider || entry.provider_id)} / ${escapeHtml(entry.model)}
          </div>
          ${entry.error ? `<div class="provider-error">${escapeHtml(entry.error)}</div>` : ''}
        </div>`;
      }
      container.innerHTML = html;
    },

    renderProviders(providers) {
      const container = document.getElementById('council-providers');
      if (!container) return;
      if (!providers || providers.length === 0) {
        container.innerHTML = '<div style="color:var(--fg2);padding:4px">No providers configured</div>';
        return;
      }
      let html = '';
      for (const p of providers) {
        const statusColor = p.available ? 'var(--accent2)' : 'var(--red)';
        html += `<div class="provider-card">
          <div>
            <span class="provider-name">${escapeHtml(p.provider_id || p.id || '')}</span>
            <span style="color:${statusColor};font-size:10px"> ${p.available ? 'available' : 'unavailable'}</span>
          </div>
          ${p.warning ? `<div class="provider-warning">${escapeHtml(p.warning)}</div>` : ''}
          ${p.error ? `<div class="provider-error">${escapeHtml(p.error)}</div>` : ''}
        </div>`;
      }
      container.innerHTML = html;
    },

    renderFailures(failures, fallbacks) {
      const container = document.getElementById('council-failures');
      if (!container) return;
      if ((!failures || failures.length === 0) && (!fallbacks || fallbacks.length === 0)) {
        container.innerHTML = '<div style="color:var(--fg2);padding:4px">No failures or fallbacks</div>';
        return;
      }
      let html = '';
      for (const f of failures || []) {
        html += `<div class="failure-entry">
          <span class="failure-role">${escapeHtml(f.role)}</span>
          <span style="color:var(--fg2)"> ${escapeHtml(f.provider || f.provider_id)}</span>
          <div class="failure-error">${escapeHtml(f.error || '')}</div>
          <div class="failure-time">${escapeHtml(f.time || '')}</div>
        </div>`;
      }
      for (const fb of fallbacks || []) {
        html += `<div class="failure-entry">
          <span class="failure-role">${escapeHtml(fb.role)}</span>
          <span style="color:var(--yellow)"> ${escapeHtml(fb.from_provider)} → ${escapeHtml(fb.to_provider)}</span>
          <div class="failure-time">${escapeHtml(fb.time || '')}</div>
        </div>`;
      }
      container.innerHTML = html;
    }
  };
})();

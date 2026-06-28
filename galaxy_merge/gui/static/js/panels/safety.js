(function() {
  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
  }

  window.SafetyPanel = {
    async refresh() {
      await this.refreshStatus();
      await this.refreshBlocked();
      await this.refreshAudit();
    },

    async refreshStatus() {
      try {
        const safety = await API.getSafety();
        const container = document.getElementById('safety-status');
        if (!safety) return;
        
        let html = `<div class="safety-entry">
          <span style="color:var(--fg2)">Policy:</span> ${escapeHtml(safety.active_policy || 'default')}
        </div>`;
        
        if (safety.readonly_mode) {
          html += `<div class="safety-entry" style="color:var(--yellow)">READ-ONLY MODE</div>`;
        }
        
        html += `<div class="safety-entry">
          <span style="color:var(--fg2)">Blocked commands:</span> ${(safety.blocked_commands||[]).length}
        </div>`;
        
        html += `<div class="safety-entry" style="margin-top:6px">
          <button id="btn-secret-scan" class="pane-btn" style="border:1px solid var(--border);padding:2px 8px;color:var(--fg);background:var(--bg3);cursor:pointer;font-size:11px;border-radius:3px">Run Secret Scan</button>
          <span id="secret-scan-result" style="margin-left:8px;font-size:10px;color:var(--fg2)"></span>
        </div>`;
        
        container.innerHTML = html;
        
        document.getElementById('btn-secret-scan').addEventListener('click', async () => {
          const resultEl = document.getElementById('secret-scan-result');
          resultEl.textContent = 'Scanning...';
          resultEl.style.color = 'var(--fg2)';
          try {
            const r = await fetch('/api/secret-scan', { method: 'POST', headers: {'Content-Type':'application/json'}, body: '{}' });
            const data = await r.json();
            if (data.success) {
              resultEl.textContent = 'Clean';
              resultEl.style.color = 'var(--accent2)';
            } else {
              resultEl.textContent = data.error || 'Issues found';
              resultEl.style.color = 'var(--red)';
            }
          } catch (e) {
            resultEl.textContent = 'Scan failed';
            resultEl.style.color = 'var(--red)';
          }
        });
      } catch (e) {
        console.error('safety status refresh failed', e);
      }
    },

    async refreshBlocked() {
      try {
        const safety = await API.getSafety();
        const container = document.getElementById('safety-blocked');
        const blocked = safety.blocked_commands || [];
        
        if (blocked.length === 0) {
          container.innerHTML = '<div style="color:var(--fg2);padding:4px">No blocked commands</div>';
          return;
        }
        
        let html = '';
        for (const cmd of blocked) {
          html += `<div class="failure-entry">
            <span style="color:var(--red)">${escapeHtml(cmd)}</span>
          </div>`;
        }
        container.innerHTML = html;
      } catch (e) {
        console.error('safety blocked refresh failed', e);
      }
    },

    async refreshAudit() {
      try {
        const events = await API.getEvents();
        const container = document.getElementById('safety-audit');
        const safetyEvents = events.filter(e => 
          e.event === 'tool_call_blocked' || 
          e.event === 'safety_event'
        );
        
        if (safetyEvents.length === 0) {
          container.innerHTML = '<div style="color:var(--fg2);padding:4px">No safety events</div>';
          return;
        }
        
        let html = '';
        for (const evt of safetyEvents.slice(-20)) {
          html += `<div class="failure-entry">
            <span style="color:var(--red)">${escapeHtml(evt.event)}</span>
            <span style="color:var(--fg2);font-size:9px"> ${escapeHtml(evt.tool || evt.target || '')}</span>
            <div style="color:var(--fg2);font-size:9px">${escapeHtml(evt.reason || '')}</div>
          </div>`;
        }
        container.innerHTML = html;
      } catch (e) {
        console.error('safety audit refresh failed', e);
      }
    }
  };
})();

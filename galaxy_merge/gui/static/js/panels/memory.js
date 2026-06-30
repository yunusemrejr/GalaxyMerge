(function() {
  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
  }

  window.MemoryPanel = {
    async refresh() {
      await this.refreshSessionMemory();
      await this.refreshProjectMemory();
      await this.refreshMachineMemory();
      await this.refreshSkills();
    },

    async refreshSessionMemory() {
      try {
        const events = await API.getEvents();
        const container = document.getElementById('memory-panel');
        if (!container) return;
        
        const sessionEvents = events.filter(e => 
          e.event === 'session_started' || 
          e.event === 'goal_received' ||
          e.event === 'note_loaded'
        );
        
        let html = '<div class="memory-section">';
        html += '<div class="memory-section-header">Session Context</div>';
        
        if (sessionEvents.length === 0) {
          html += '<div class="memory-entry">No session context</div>';
        } else {
          for (const evt of sessionEvents.slice(-5)) {
            if (evt.event === 'goal_received' && evt.goal) {
              html += `<div class="memory-entry">Goal: ${escapeHtml(evt.goal.slice(0, 80))}</div>`;
            }
            if (evt.event === 'note_loaded' && evt.notes_count) {
              html += `<div class="memory-entry">Notes loaded: ${evt.notes_count}</div>`;
            }
          }
        }
        
        html += '</div>';
        container.innerHTML = html;
      } catch (e) {
        console.error('session memory refresh failed', e);
      }
    },

    async refreshProjectMemory() {
      try {
        const payload = await API.getNotes();
        const container = document.getElementById('memory-panel');
        if (!container) return;
        const entries = payload.notes || [];
        
        let html = '<div class="memory-section">';
        html += '<div class="memory-section-header">Project Notes</div>';
        
        if (entries.length === 0) {
          html += '<div class="memory-entry">No project notes</div>';
        } else {
          for (const note of entries.slice(0, 5)) {
            const content = note.content || '';
            const preview = content.slice(0, 60).replace(/\n/g, ' ');
            html += `<div class="memory-entry">${escapeHtml(note.name)}: ${escapeHtml(preview)}${content.length > 60 ? '...' : ''}</div>`;
          }
        }
        
        html += '</div>';
        container.innerHTML += html;
      } catch (e) {
        console.error('project memory refresh failed', e);
      }
    },

    async refreshMachineMemory() {
      try {
        const data = await API.getMemory('all');
        const container = document.getElementById('memory-panel');
        if (!container) return;
        const memory = data.memory || {};
        
        let html = '<div class="memory-section">';
        html += '<div class="memory-section-header">Machine Memory</div>';
        
        const kinds = ['facts', 'failures', 'fixes', 'lessons'];
        for (const kind of kinds) {
          const records = memory[kind] || [];
          if (records.length > 0) {
            html += `<div style="font-size:10px;color:var(--accent);margin-top:4px">${escapeHtml(kind)}</div>`;
            for (const record of records.slice(-3)) {
              const content = typeof record === 'string' ? record : JSON.stringify(record);
              const preview = content.slice(0, 60).replace(/\n/g, ' ');
              html += `<div class="memory-entry">${escapeHtml(preview)}${content.length > 60 ? '...' : ''}</div>`;
            }
          }
        }
        
        html += '</div>';
        container.innerHTML += html;
      } catch (e) {
        console.error('machine memory refresh failed', e);
      }
    },

    async refreshSkills() {
      try {
        const data = await API.getSkills();
        const container = document.getElementById('memory-panel');
        if (!container) return;
        const skills = data.skills || [];
        
        let html = '<div class="memory-section">';
        html += '<div class="memory-section-header">Skills</div>';
        
        if (skills.length === 0) {
          html += '<div class="memory-entry">No skills loaded</div>';
        } else {
          for (const skill of skills.slice(0, 5)) {
            html += `<div class="memory-entry">
              <span style="color:var(--accent)">${escapeHtml(skill.name || skill.id || '')}</span>
              ${skill.summary ? `<span style="color:var(--fg2)"> - ${escapeHtml(skill.summary.slice(0, 40))}</span>` : ''}
            </div>`;
          }
        }
        
        html += '</div>';
        container.innerHTML += html;
      } catch (e) {
        console.error('skills refresh failed', e);
      }
    }
  };
})();

(function() {
  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;',
    }[ch]));
  }

  window.SkillsPanel = {
    async refresh() {
      try {
        const skillsPayload = await API.getSkills();
        const events = await API.getEvents();
        const selectedEvents = Array.isArray(events)
          ? events.filter((evt) => evt.event === 'skill_selected')
          : [];

        const selectedSkills = [];
        const recent = selectedEvents.slice(-8).reverse();
        for (const evt of recent) {
          const candidates = evt.skills || [];
          if (Array.isArray(candidates)) {
            selectedSkills.push(...candidates);
          }
        }
        const selectedSet = new Set(selectedSkills);

        const container = document.getElementById('skills-panel');
        if (!container) return;
        const skills = skillsPayload.skills || [];

        let html = '<div class="memory-section">';
        html += '<div class="memory-section-header">Available Skills</div>';
        if (skills.length === 0) {
          html += '<div class="memory-entry">No skills loaded</div>';
        } else {
          for (const skill of skills) {
            const name = escapeHtml(skill.name || skill.id || '');
            const summary = escapeHtml((skill.summary || '').slice(0, 90));
            const selectedBadge = selectedSet.has(name) ? ' <span style="color:var(--yellow);">[selected]</span>' : '';
            html += `<div class="memory-entry"><span class="goal-state-label">${name}</span> ${summary}${selectedBadge}</div>`;
          }
        }
        html += '</div>';

        html += '<div class="memory-section">';
        html += '<div class="memory-section-header">Selected by Council</div>';
        if (!recent.length || !selectedSkills.length) {
          html += '<div class="memory-entry">No skill selection events yet</div>';
        } else {
          for (const skillName of selectedSet) {
            html += `<div class="memory-entry">${escapeHtml(skillName)}</div>`;
          }
        }
        html += '</div>';

        container.innerHTML = html;
      } catch (e) {
        console.error('skills refresh failed', e);
      }
    },
  };
})();

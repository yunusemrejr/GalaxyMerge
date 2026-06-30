(function() {
  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
  }

  const goalState = {
    phase: 'idle',
    goal: '',
    blocked: false,
    degraded: false,
    error: null,
    complete: false,
    verificationPassed: null,
    reviewIssues: [],
    compactionCount: 0,
    toolCallCount: 0,
    lastUpdate: null
  };

  window.GoalPanel = {
    render(goal, phase, detail) {
      const phaseEl = document.getElementById('goal-phase');
      if (phaseEl) phaseEl.textContent = phase || 'idle';
      const detailEl = document.getElementById('goal-phase-detail');
      if (detailEl && detail) {
        detailEl.textContent = detail;
      }
    },
    updateFromResult(result) {
      if (!result) return;
      const phase = result.complete ? 'complete' : (result.error ? 'error' : 'running');
      const detail = result.summary || result.error || '';
      this.render(null, phase, detail);

      goalState.phase = phase;
      goalState.complete = result.complete || false;
      goalState.error = result.error || null;
      goalState.lastUpdate = Date.now();

      if (result.review && result.review.issues) {
        goalState.reviewIssues = result.review.issues;
      }

      if (result.plan) {
        PlanPanel.render(result.plan);
      }
      if (result.diff) {
        DiffPanel.render(result.diff);
      }
      if (result.output) {
        OutputPanel.render(result.output);
      }
    },
    getState() {
      return { ...goalState };
    },
    setBlocked(blocked, reason) {
      goalState.blocked = blocked;
      if (blocked) {
        goalState.phase = 'blocked';
        this.render(null, 'blocked', reason || 'blocked by safety');
      }
    },
    setDegraded(degraded, reason) {
      goalState.degraded = degraded;
      if (degraded) {
        this.render(null, 'degraded', reason || 'degraded');
      }
    },
    addToolCall() {
      goalState.toolCallCount++;
      goalState.lastUpdate = Date.now();
    },
    addCompaction() {
      goalState.compactionCount++;
      goalState.lastUpdate = Date.now();
    },
    setVerification(passed) {
      goalState.verificationPassed = passed;
      goalState.lastUpdate = Date.now();
    }
  };

  window.PlanPanel = {
    render(plan) {
      const container = document.getElementById('plan-panel');
      if (!container) return;
      if (!plan) {
        container.innerHTML = '<div style="color:var(--fg2);padding:4px">No plan yet</div>';
        return;
      }
      let html = '';
      if (plan.steps && Array.isArray(plan.steps)) {
        html += '<div style="font-size:11px;margin-bottom:4px;color:var(--fg2)">Plan Steps:</div>';
        for (let i = 0; i < plan.steps.length; i++) {
          const step = plan.steps[i];
          const status = step.status || 'pending';
          const statusColor = status === 'complete' ? 'var(--accent2)' : status === 'active' ? 'var(--accent)' : 'var(--fg2)';
          html += `<div class="verify-entry">
            <span style="color:${statusColor}">${i + 1}.</span>
            <span>${escapeHtml(step.description || step.action || JSON.stringify(step))}</span>
          </div>`;
        }
      } else if (typeof plan === 'string') {
        html = `<div style="font-size:11px;white-space:pre-wrap">${escapeHtml(plan)}</div>`;
      } else {
        html = `<pre style="font-size:10px;white-space:pre-wrap">${escapeHtml(JSON.stringify(plan, null, 2))}</pre>`;
      }
      container.innerHTML = html;
    }
  };

  window.DiffPanel = {
    render(diff) {
      const container = document.getElementById('diff-panel');
      if (!container) return;
      if (!diff) {
        container.innerHTML = '<div style="color:var(--fg2);padding:4px">No diff available</div>';
        return;
      }
      container.innerHTML = `<pre style="font-size:10px;white-space:pre-wrap">${escapeHtml(diff)}</pre>`;
    }
  };

  window.OutputPanel = {
    render(output) {
      const container = document.getElementById('output-panel');
      if (!container) return;
      if (!output) {
        container.innerHTML = '<div style="color:var(--fg2);padding:4px">No output yet</div>';
        return;
      }
      container.innerHTML = `<pre style="font-size:10px;white-space:pre-wrap">${escapeHtml(output)}</pre>`;
    }
  };

  window.VerifyPanel = {
    async refresh() {
      try {
        const events = await API.getEvents();
        const container = document.getElementById('verify-panel');
        if (!container) return;

        const state = GoalPanel.getState();
        let html = '';

        html += '<div class="goal-state">';
        html += `<div><span class="goal-state-label">Goal State: </span><span class="goal-state-value goal-state-${state.phase}">${escapeHtml(state.phase.toUpperCase())}</span></div>`;
        if (state.goal) {
          html += `<div><span class="goal-state-label">Goal: </span><span class="goal-state-value">${escapeHtml(state.goal.slice(0, 60))}${state.goal.length > 60 ? '...' : ''}</span></div>`;
        }
        if (state.blocked) {
          html += `<div><span class="goal-state-label goal-state-blocked">BLOCKED</span></div>`;
        }
        if (state.degraded) {
          html += `<div><span class="goal-state-label goal-state-degraded">DEGRADED</span></div>`;
        }
        if (state.error) {
          html += `<div><span class="goal-state-label">Error: </span><span class="goal-state-value" style="color:var(--red)">${escapeHtml(state.error)}</span></div>`;
        }
        html += `<div><span class="goal-state-label">Tool Calls: </span><span class="goal-state-value">${state.toolCallCount}</span></div>`;
        html += `<div><span class="goal-state-label">Compactions: </span><span class="goal-state-value">${state.compactionCount}</span></div>`;
        html += '</div>';

        if (state.verificationPassed !== null) {
          html += '<div class="goal-state">';
          html += `<div><span class="goal-state-label">Verification: </span><span class="goal-state-value ${state.verificationPassed ? 'goal-state-complete' : 'goal-state-blocked'}">${state.verificationPassed ? 'PASSED' : 'FAILED'}</span></div>`;
          html += '</div>';
        }

        if (state.reviewIssues.length > 0) {
          html += '<div class="goal-state">';
          html += `<div class="goal-state-label">Review Issues:</div>`;
          for (const issue of state.reviewIssues) {
            html += `<div style="color:var(--red);font-size:10px;padding-left:8px">- ${escapeHtml(issue)}</div>`;
          }
          html += '</div>';
        }

        const verifyEvents = events.filter(e =>
          e.event === 'verification_completed' ||
          e.event === 'completion_accepted' ||
          e.event === 'completion_rejected' ||
          e.event === 'completion_review_started'
        );

        if (verifyEvents.length > 0) {
          html += '<div style="font-size:10px;color:var(--fg2);padding:4px;border-bottom:1px solid var(--border)">Verification History</div>';
          for (const evt of verifyEvents.slice(-10)) {
            const passed = evt.event === 'completion_accepted' || evt.passed;
            const statusClass = passed ? 'verify-pass' : evt.event === 'completion_rejected' ? 'verify-fail' : '';
            const statusText = evt.event === 'completion_accepted' ? 'ACCEPTED' :
                              evt.event === 'completion_rejected' ? 'REJECTED' :
                              evt.event === 'verification_completed' ? (evt.passed ? 'PASSED' : 'FAILED') :
                              'REVIEWING';
            html += `<div class="verify-entry">
              <span class="${statusClass}" style="font-weight:600">${statusText}</span>
              <span style="color:var(--fg2);font-size:10px"> ${escapeHtml(evt.time || '')}</span>
            </div>`;
          }
        }

        if (!html) {
          html = '<div style="color:var(--fg2);padding:4px">No verification data</div>';
        }

        container.innerHTML = html;
      } catch (e) {
        console.error('verify refresh failed', e);
      }
    }
  };
})();

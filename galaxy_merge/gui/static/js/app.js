(function() {
  async function init() {
    try {
      GM.session = await API.getSession();
      GM.project = await API.getProject();
    } catch (e) {
      addChat('system', 'Failed to connect to backend. Is the server running?');
      return;
    }

    await updateTopBar();
    FilesPanel.refresh();
    NotesPanel.refresh();
    MemoryPanel.refresh();
    SafetyPanel.refresh();
    BrowserPanel.refresh();
    LocationsPanel.refresh();
    refreshCouncilStatus();
    LogsPanel.refreshFromServer();
    VerifyPanel.refresh();

    if (GM.project && GM.project.readonly_mode) {
      addChat('system', 'READ-ONLY MODE: Operating inside Galaxy Merge codebase. Mutations disabled.');
      const safetyBar = document.getElementById('bar-safety');
      if (safetyBar) safetyBar.textContent = 'Safety: read-only';
    }

    const wsUrl = `ws://${location.host}/ws/session/${GM.session.session_id}`;
    connectWebSocket(wsUrl);

    const goalSubmit = document.getElementById('goal-submit');
    if (goalSubmit) goalSubmit.addEventListener('click', submitGoal);
    const goalInput = document.getElementById('goal-input');
    if (goalInput) goalInput.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        submitGoal();
      }
    });
    const btnRefresh = document.getElementById('btn-refresh-tree');
    if (btnRefresh) btnRefresh.addEventListener('click', () => FilesPanel.refresh());

    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    document.querySelectorAll('.center-tab-btn').forEach(btn => {
      btn.addEventListener('click', () => switchCenterTab(btn.dataset.centerTab));
    });

    document.querySelectorAll('.sub-tab-btn').forEach(btn => {
      btn.addEventListener('click', () => switchSubTab(btn.closest('.tab-content'), btn.dataset.subTab));
    });

    refreshAll();
  }

  async function updateTopBar() {
    const project = GM.project || {};
    const session = GM.session || {};
    const projectEl = document.getElementById('bar-project');
    if (projectEl) {
      projectEl.textContent = `Project: ${project.name || project.workroot || '--'}`;
    }
    const workrootEl = document.getElementById('bar-workroot');
    if (workrootEl) {
      const wr = project.workroot || session.workroot || '';
      workrootEl.textContent = `WorkRoot: ${wr ? wr.split('/').pop() : '--'}`;
      if (wr) workrootEl.title = wr;
    }
    const taskscopeEl = document.getElementById('bar-taskscope');
    if (taskscopeEl) {
      try {
        const locs = await API.getLocations();
        const raw = locs.taskscope;
        const ts = Array.isArray(raw) ? (raw[0] || '') : (raw || '');
        taskscopeEl.textContent = `TaskScope: ${ts ? ts.split('/').pop() : '--'}`;
        if (ts) taskscopeEl.title = ts;
      } catch (e) {
        taskscopeEl.textContent = 'TaskScope: --';
      }
    }
    const goalEl = document.getElementById('bar-goal');
    if (goalEl) {
      const goal = session.goal || '';
      const phase = session.status || session.goal_state || 'idle';
      goalEl.textContent = `Goal: ${goal ? (goal.slice(0, 24) + (goal.length > 24 ? '...' : '')) : phase}`;
      if (goal) goalEl.title = goal;
    }
    await populateSessionPicker();
  }

  async function populateSessionPicker() {
    const picker = document.getElementById('session-picker');
    if (!picker) return;
    try {
      const data = await API.getSessions();
      const sessions = data.sessions || [];
      const current = data.current_session_id || (GM.session && GM.session.session_id);
      picker.innerHTML = '';
      if (!sessions.length) {
        const opt = document.createElement('option');
        opt.value = current || '';
        opt.textContent = current ? current.slice(0, 12) : '--';
        opt.disabled = true;
        picker.appendChild(opt);
        return;
      }
      for (const s of sessions) {
        const opt = document.createElement('option');
        opt.value = s.session_id;
        const label = `${s.session_id.slice(0, 12)}${s.active ? '' : ' (inactive)'}`;
        opt.textContent = label;
        if (s.session_id === current) opt.selected = true;
        picker.appendChild(opt);
      }
    } catch (e) {
      console.error('session picker failed', e);
    }
  }

  let wsReconnectDelay = 1000;
  const wsMaxReconnectDelay = 30000;

  function connectWebSocket(url) {
    try {
      GM.ws = new WebSocket(url);
      setConnectionState('connecting');
      GM.ws.onopen = () => {
        wsReconnectDelay = 1000;
        setConnectionState('connected');
      };
      GM.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          handleWSEvent(data);
        } catch (e) {
          console.error('ws parse error', e);
        }
      };
      GM.ws.onclose = () => {
        setConnectionState('reconnecting');
        setTimeout(() => connectWebSocket(url), wsReconnectDelay);
        wsReconnectDelay = Math.min(wsReconnectDelay * 2, wsMaxReconnectDelay);
      };
      GM.ws.onerror = () => {
        setConnectionState('degraded');
      };
    } catch (e) {
      console.error('ws connection failed', e);
    }
  }

  function handleWSEvent(data) {
    const type = data.type || data.event || '';

    if (type === 'goal_set' || type === 'goal_received') {
      GoalPanel.render(null, data.status || 'understanding', '');
      const state = GoalPanel.getState();
      state.goal = data.goal || '';
      addChat('system', `Goal accepted: ${data.goal}`);
    }
    if (type === 'goal_result') {
      const result = data.result;
      if (result) {
        GoalPanel.updateFromResult(result);
        if (result.complete) {
          addChat('system', `✓ Goal complete`);
        } else if (result.error) {
          addChat('error', `Goal failed: ${result.error}`);
        } else if (result.review && result.review.issues && result.review.issues.length) {
          addChat('error', `Incomplete: ${result.review.issues.join('; ')}`);
        }
        if (result.fusion && result.fusion.summary) {
          addChat('system', result.fusion.summary);
        }
        if (result.plan) {
          PlanPanel.render(result.plan);
        }
        VerifyPanel.refresh();
      }
    }
    if (type === 'log') {
      LogsPanel.add(data.message, data.level);
    }
    if (type === 'tool_event' || type === 'tool_call_started' || type === 'tool_call_completed') {
      LogsPanel.add(`[tool] ${data.tool} — ${data.status || 'started'}`, data.status === 'blocked' ? 'error' : '');
      ToolsPanel.addToolCall(data);
      GoalPanel.addToolCall();
    }
    if (type === 'tool_call_blocked') {
      LogsPanel.add(`[safety] blocked: ${data.tool} — ${data.reason || ''}`, 'error');
      GoalPanel.setBlocked(true, data.reason || 'blocked by safety');
      SafetyPanel.refresh();
    }
    if (type === 'council_event' || type === 'council_completed') {
      const roles = data.roles || [];
      LogsPanel.add(`[council] completed: ${roles.length ? roles.join(', ') : 'no roles completed'}`, roles.length ? '' : 'warn');
      CouncilPanel.refresh();
    }
    if (type === 'provider_called') {
      LogsPanel.add(`[provider] ${data.provider_id} called for ${data.role}`, '');
    }
    if (type === 'provider_failed') {
      LogsPanel.add(`[provider] ${data.provider_id} failed: ${data.error}`, 'error');
      GoalPanel.setDegraded(true, `provider ${data.provider_id} failed`);
      CouncilPanel.refresh();
    }
    if (type === 'role_fallback') {
      LogsPanel.add(`[council] fallback: ${data.role} ${data.from_provider} → ${data.to_provider}`, 'warn');
      GoalPanel.setDegraded(true, `fallback: ${data.role}`);
      CouncilPanel.refresh();
    }
    if (type === 'compaction_started') {
      LogsPanel.add(`[compaction] started: ${data.reason || 'context limit'}`, 'warn');
      GoalPanel.addCompaction();
    }
    if (type === 'compaction_completed') {
      LogsPanel.add(`[compaction] completed: ${data.context_before_tokens} → ${data.context_after_tokens} tokens`, '');
    }
    if (type === 'verification_started') {
      addChat('system', 'Verification started...');
    }
    if (type === 'verification_completed') {
      GoalPanel.setVerification(data.passed);
      if (data.passed) {
        addChat('system', '✓ Verification passed');
      } else {
        addChat('error', '✗ Verification failed');
      }
      VerifyPanel.refresh();
    }
    if (type === 'completion_accepted') {
      addChat('system', '✓ Task verified and accepted');
      GoalPanel.setVerification(true);
      VerifyPanel.refresh();
    }
    if (type === 'completion_rejected') {
      addChat('system', '✗ Task rejected by reviewer');
      GoalPanel.setVerification(false);
      VerifyPanel.refresh();
    }
    if (type === 'session_stopped') {
      addChat('system', 'Session stopped');
    }
  }

  async function submitGoal() {
    const input = document.getElementById('goal-input');
    const goal = input.value.trim();
    if (!goal) return;

    addChat('user', goal);
    input.value = '';

    try {
      const result = await API.postGoal(goal);
      if (result.status === 'accepted') {
        GoalPanel.render(null, 'understanding', '');
      }
    } catch (e) {
      addChat('error', `Failed to submit goal: ${e.message}`);
    }
  }

  function addChat(type, text) {
    const container = document.getElementById('stream-panel');
    const entry = document.createElement('div');
    entry.className = `chat-entry ${type}`;
    const prefix = type === 'user' ? '>' : type === 'error' ? '!' : '#';
    entry.innerHTML = `<span class="prefix">${prefix}</span> ${escapeHtml(text)}`;
    container.appendChild(entry);
    container.scrollTop = container.scrollHeight;
  }

  async function refreshCouncilStatus() {
    try {
      const data = await API.getCouncil();
      const providers = data.providers || [];
      const unavailable = providers.filter(p => !p.available);
      const providerBar = document.getElementById('bar-providers');
      if (providerBar) {
        if (providers.length === 0) {
          providerBar.textContent = 'Providers: not configured';
          providerBar.style.color = 'var(--yellow)';
        } else {
          providerBar.textContent = `Providers: ${providers.length - unavailable.length}/${providers.length} available`;
          if (unavailable.length) {
            providerBar.style.color = 'var(--yellow)';
          }
        }
      }
      if (unavailable.length) {
        unavailable.slice(0, 3).forEach(p => addChat('error', `${p.provider_id}: ${p.warning || 'unavailable'}`));
      }
      ToolsPanel.render(data.tools || []);
      if (window.CouncilPanel) {
        CouncilPanel.refresh();
      }
    } catch (e) {
      const barEl = document.getElementById('bar-providers');
      if (barEl) barEl.textContent = 'Providers: unavailable';
    }
  }

  function switchTab(tabId) {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
    const btn = document.querySelector(`.tab-btn[data-tab="${tabId}"]`);
    if (btn) btn.classList.add('active');
    const panel = document.getElementById(`${tabId}-panel`);
    if (panel) panel.classList.add('active');
  }

  function switchCenterTab(tabId) {
    document.querySelectorAll('.center-tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.center-tab-content').forEach(c => c.classList.remove('active'));
    const btn = document.querySelector(`.center-tab-btn[data-center-tab="${tabId}"]`);
    if (btn) btn.classList.add('active');
    const panel = document.getElementById(`${tabId}-panel`);
    if (panel) panel.classList.add('active');
  }

  function switchSubTab(parent, subTabId) {
    if (!parent) return;
    parent.querySelectorAll('.sub-tab-btn').forEach(b => b.classList.remove('active'));
    parent.querySelectorAll('.sub-tab-content').forEach(c => c.classList.remove('active'));
    const btn = parent.querySelector(`.sub-tab-btn[data-sub-tab="${subTabId}"]`);
    if (btn) btn.classList.add('active');
    const panel = document.getElementById(subTabId);
    if (panel) panel.classList.add('active');
  }

  function setConnectionState(state) {
    const el = document.getElementById('bar-connection');
    if (!el) return;
    const labels = {
      connecting: 'Backend: connecting',
      connected: 'Backend: online',
      reconnecting: 'Backend: reconnecting',
      degraded: 'Backend: degraded',
    };
    el.textContent = labels[state] || `Backend: ${state}`;
    el.style.color = state === 'connected' ? 'var(--accent2)' : state === 'degraded' || state === 'reconnecting' ? 'var(--yellow)' : 'var(--fg2)';
  }

  function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
  }

  let _refreshInterval = null;

  function refreshAll() {
    if (_refreshInterval !== null) {
      clearInterval(_refreshInterval);
    }
    _refreshInterval = window.setInterval(() => {
      FilesPanel.refresh();
      SafetyPanel.refresh();
      refreshCouncilStatus();
      LogsPanel.refreshFromServer();
    }, 10000);
  }

  document.addEventListener('DOMContentLoaded', init);
})();

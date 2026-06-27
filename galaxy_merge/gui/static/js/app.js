(function() {
  async function init() {
    try {
      GM.session = await API.getSession();
      GM.project = await API.getProject();
    } catch (e) {
      addChat('system', 'Failed to connect to backend. Is the server running?');
      return;
    }

    updateTopBar();
    FilesPanel.refresh();
    NotesPanel.refresh();
    MemoryPanel.refresh();
    SafetyPanel.refresh();
    BrowserPanel.refresh();
    LocationsPanel.refresh();
    refreshCouncilStatus();

    if (GM.project && GM.project.readonly_mode) {
      addChat('system', 'READ-ONLY MODE: Operating inside Galaxy Merge codebase. Mutations disabled.');
      document.getElementById('bar-safety').textContent = 'Safety: read-only';
    }

    const wsUrl = `ws://${location.host}/ws/session/${GM.session.session_id}`;
    connectWebSocket(wsUrl);

    document.getElementById('goal-submit').addEventListener('click', submitGoal);
    document.getElementById('goal-input').addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        submitGoal();
      }
    });
    document.getElementById('btn-refresh-tree').addEventListener('click', () => FilesPanel.refresh());

    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => switchTab(btn.dataset.tab));
    });

    refreshAll();
  }

  function updateTopBar() {
    if (GM.session) {
      document.getElementById('bar-session').textContent = `Session: ${GM.session.session_id.slice(0, 20)}...`;
    }
    if (GM.project) {
      document.getElementById('bar-project').textContent = `Project: ${GM.project.name || GM.project.workroot || '--'}`;
    }
  }

  function connectWebSocket(url) {
    try {
      GM.ws = new WebSocket(url);
      document.getElementById('bar-safety').textContent = 'Backend: connecting';
      GM.ws.onopen = () => {
        document.getElementById('bar-safety').textContent = GM.project && GM.project.readonly_mode ? 'Safety: read-only' : 'Safety: enabled';
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
        document.getElementById('bar-safety').textContent = 'Backend: reconnecting';
        setTimeout(() => connectWebSocket(url), 3000);
      };
      GM.ws.onerror = () => {
        document.getElementById('bar-safety').textContent = 'Backend: degraded';
      };
    } catch (e) {
      console.error('ws connection failed', e);
    }
  }

  function handleWSEvent(data) {
    const type = data.type || data.event || '';

    if (type === 'goal_set' || type === 'goal_received') {
      GoalPanel.render(null, data.status || 'understanding', '');
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
      }
    }
    if (type === 'log') {
      LogsPanel.add(data.message, data.level);
    }
    if (type === 'tool_event' || type === 'tool_call_started' || type === 'tool_call_completed') {
      LogsPanel.add(`[tool] ${data.tool} — ${data.status || 'started'}`, data.status === 'blocked' ? 'error' : '');
    }
    if (type === 'council_event' || type === 'council_completed') {
      const roles = data.roles || [];
      LogsPanel.add(`[council] completed: ${roles.length ? roles.join(', ') : 'no roles completed'}`, roles.length ? '' : 'warn');
    }
    if (type === 'safety_event' || data.event === 'tool_call_blocked') {
      LogsPanel.add(`[safety] blocked: ${data.tool || data.target} — ${data.reason || ''}`, 'error');
      SafetyPanel.refresh();
    }
    if (type === 'completion_accepted') {
      addChat('system', '✓ Task verified and accepted');
    }
    if (type === 'completion_rejected') {
      addChat('system', '✗ Task rejected by reviewer');
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
    const container = document.getElementById('chat-stream');
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
      providerBar.textContent = `Providers: ${providers.length - unavailable.length}/${providers.length} available`;
      if (unavailable.length) {
        providerBar.style.color = 'var(--yellow)';
        unavailable.slice(0, 3).forEach(p => addChat('error', `${p.provider_id}: ${p.warning || 'unavailable'}`));
      }
      ToolsPanel.render(data.tools || []);
    } catch (e) {
      document.getElementById('bar-providers').textContent = 'Providers: unavailable';
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

  function escapeHtml(text) {
    const d = document.createElement('div');
    d.textContent = text;
    return d.innerHTML;
  }

  function refreshAll() {
    const interval = setInterval(() => {
      FilesPanel.refresh();
      SafetyPanel.refresh();
      refreshCouncilStatus();
    }, 10000);
  }

  document.addEventListener('DOMContentLoaded', init);
})();

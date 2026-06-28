(function() {
  let logPage = 0;
  const logPageSize = 100;
  let logTotal = 0;

  window.LogsPanel = {
    add(message, level) {
      const container = document.getElementById('logs-container');
      if (!container) return;
      const line = document.createElement('div');
      line.className = `log-line ${level || ''}`;
      line.textContent = message;
      container.appendChild(line);
      container.scrollTop = container.scrollHeight;
    },

    async refreshFromServer() {
      try {
        const data = await API.get(`/api/logs?limit=${logPageSize}&offset=${logPage * logPageSize}`);
        const container = document.getElementById('logs-container');
        if (!container) return;
        
        logTotal = data.total || 0;
        const lines = data.lines || [];
        
        container.innerHTML = '';
        for (const line of lines) {
          const div = document.createElement('div');
          div.className = 'log-line';
          div.textContent = line;
          container.appendChild(div);
        }
        container.scrollTop = container.scrollHeight;

        const countEl = document.getElementById('logs-count');
        if (countEl) {
          countEl.textContent = `${logPage * logPageSize + 1}-${Math.min((logPage + 1) * logPageSize, logTotal)} of ${logTotal}`;
        }

        const prevBtn = document.getElementById('logs-prev');
        const nextBtn = document.getElementById('logs-next');
        const pageEl = document.getElementById('logs-page');
        
        if (prevBtn) prevBtn.disabled = logPage === 0;
        if (nextBtn) nextBtn.disabled = (logPage + 1) * logPageSize >= logTotal;
        if (pageEl) pageEl.textContent = logPage + 1;
      } catch (e) {
        console.error('logs refresh failed', e);
      }
    },

    clear() {
      const container = document.getElementById('logs-container');
      if (container) container.innerHTML = '';
    }
  };

  document.addEventListener('DOMContentLoaded', () => {
    const clearBtn = document.getElementById('logs-clear');
    const prevBtn = document.getElementById('logs-prev');
    const nextBtn = document.getElementById('logs-next');

    if (clearBtn) {
      clearBtn.addEventListener('click', () => window.LogsPanel.clear());
    }
    if (prevBtn) {
      prevBtn.addEventListener('click', () => {
        if (logPage > 0) {
          logPage--;
          window.LogsPanel.refreshFromServer();
        }
      });
    }
    if (nextBtn) {
      nextBtn.addEventListener('click', () => {
        if ((logPage + 1) * logPageSize < logTotal) {
          logPage++;
          window.LogsPanel.refreshFromServer();
        }
      });
    }
  });
})();

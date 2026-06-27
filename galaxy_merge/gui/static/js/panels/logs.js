(function() {
  window.LogsPanel = {
    add(message, level) {
      const container = document.getElementById('logs-panel');
      const line = document.createElement('div');
      line.className = `log-line ${level || ''}`;
      line.textContent = message;
      container.appendChild(line);
      container.scrollTop = container.scrollHeight;
    },
    clear() {
      document.getElementById('logs-panel').innerHTML = '';
    }
  };
})();

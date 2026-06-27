(function() {
  window.LocationsPanel = {
    async refresh() {
      try {
        const r = await fetch('/api/locations');
        const data = await r.json();
        const container = document.getElementById('locations-panel');
        container.innerHTML = '';
        const pre = document.createElement('pre');
        pre.style.fontSize = '10px';
        pre.style.whiteSpace = 'pre-wrap';
        pre.textContent = JSON.stringify(data, null, 2);
        container.appendChild(pre);
      } catch (e) {
        console.error('locations refresh failed', e);
      }
    }
  };
})();

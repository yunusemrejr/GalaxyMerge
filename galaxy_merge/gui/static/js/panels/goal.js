(function() {
  window.GoalPanel = {
    render(goal, phase, detail) {
      document.getElementById('goal-phase').textContent = phase || 'idle';
      const detailEl = document.getElementById('goal-phase-detail');
      if (detail) {
        detailEl.textContent = detail;
      }
    },
    updateFromResult(result) {
      if (!result) return;
      const phase = result.complete ? 'complete' : (result.error ? 'error' : 'running');
      const detail = result.summary || result.error || '';
      this.render(null, phase, detail);
    }
  };
})();

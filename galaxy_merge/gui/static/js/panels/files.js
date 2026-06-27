(function() {
  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
  }

  window.FilesPanel = {
    async refresh() {
      try {
        const tree = await API.getTree();
        const container = document.getElementById('file-tree');
        const notice = tree.truncated ? `<div class="tree-item" style="color:var(--yellow)">Tree truncated at ${tree.entry_count} entries</div>` : '';
        container.innerHTML = notice + this._renderTree(tree);
      } catch (e) {
        console.error('tree refresh failed', e);
      }
    },
    _renderTree(node, depth) {
      if (!node) return '';
      const indent = (depth || 0) * 16;
      let html = '';
      if (node.type === 'directory') {
        html += `<div class="tree-item dir" style="padding-left:${indent}px">${escapeHtml(node.name)}/</div>`;
        if (node.children) {
          for (const child of node.children) {
            html += this._renderTree(child, (depth || 0) + 1);
          }
        }
      } else {
        const size = node.size ? ` (${this._fmtSize(node.size)})` : '';
        html += `<div class="tree-item file" style="padding-left:${indent}px">${escapeHtml(node.name)}${size}</div>`;
      }
      return html;
    },
    _fmtSize(bytes) {
      if (bytes < 1024) return `${bytes}B`;
      if (bytes < 1024*1024) return `${(bytes/1024).toFixed(1)}K`;
      return `${(bytes/(1024*1024)).toFixed(1)}M`;
    }
  };
})();

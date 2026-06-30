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

  function formatUsage(value) {
    if (!Array.isArray(value) || value.length === 0) return '';
    return value.map((role) => escapeHtml(role)).join(', ');
  }

  let searchQuery = '';

  window.NotesPanel = {
    async refresh() {
      try {
        const payload = await API.getNotes();
        const [trending, usage, injected] = await Promise.all([
          Promise.resolve(payload),
          API.getNotesUsage().catch(() => ({ usage: {} })),
          API.getNotesInjected().catch(() => ({ injected: [] })),
        ]);

        const container = document.getElementById('notes-panel');
        if (!container) return;
        const entries = trending.notes || [];

        let html = `<div class="note-search">
          <input type="text" id="note-search-input" placeholder="Search notes..." value="${escapeHtml(searchQuery)}">
          <button id="note-search-btn">Search</button>
          <button id="note-clear-btn">Clear</button>
        </div>`;

        const usageMap = usage.usage || {};
        const injectedSet = new Set((injected.injected || []).map((name) => String(name)));

        if (searchQuery) {
          const searchResults = await API.get(`/api/notes/search?q=${encodeURIComponent(searchQuery)}`);
          const results = searchResults.results || [];
          html += `<div style="font-size:10px;color:var(--fg2);padding:2px 4px">${results.length} result(s) for "${escapeHtml(searchQuery)}"</div>`;
          if (results.length === 0) {
            html += '<div style="color:var(--fg2);padding:4px">No notes match this query.</div>';
          }
          for (const result of results) {
            const usedBy = Array.isArray(usageMap[result.name]) ? usageMap[result.name] : [];
            const note = {
              name: result.name,
              content: result.preview,
              tags: result.tags || [],
              pinned: result.pinned,
              path: `${result.name}.md`,
              injected: injectedSet.has(result.name),
            };
            html += this._renderNoteItem(note, false, usedBy);
          }
        } else {
          if (entries.length === 0) {
            html += '<div style="color:var(--fg2);padding:4px">No notes. Click + to create.</div>';
          } else {
            if (payload.truncated) {
              html += `<div class="tree-item" style="color:var(--yellow)">Showing ${entries.length} of ${payload.total} notes</div>`;
            }
            for (const note of entries) {
              const usedBy = Array.isArray(usageMap[note.name]) ? usageMap[note.name] : [];
              note.injected = injectedSet.has(note.name);
              html += this._renderNoteItem(note, true, usedBy);
            }
          }
        }

        container.innerHTML = html;

        const searchInput = document.getElementById('note-search-input');
        const searchBtn = document.getElementById('note-search-btn');
        const clearBtn = document.getElementById('note-clear-btn');

        if (searchInput) {
          searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
              searchQuery = searchInput.value.trim();
              this.refresh();
            }
          });
        }
        if (searchBtn) {
          searchBtn.addEventListener('click', () => {
            searchQuery = (searchInput && searchInput.value || '').trim();
            this.refresh();
          });
        }
        if (clearBtn) {
          clearBtn.addEventListener('click', () => {
            searchQuery = '';
            this.refresh();
          });
        }

        container.querySelectorAll('.note-edit-btn').forEach((btn) => {
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const name = btn.dataset.name;
            const content = btn.dataset.content || '';
            this.editNote(name, content);
          });
        });

        container.querySelectorAll('.note-rename-btn').forEach((btn) => {
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const name = btn.dataset.name;
            this.renameNote(name);
          });
        });

        container.querySelectorAll('.note-delete-btn').forEach((btn) => {
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const name = btn.dataset.name;
            this.deleteNote(name);
          });
        });

        container.querySelectorAll('.note-inject-btn').forEach((btn) => {
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const name = btn.dataset.name;
            this.injectNote(name);
          });
        });

        container.querySelectorAll('.note-pin-btn').forEach((btn) => {
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const name = btn.dataset.name;
            const pinned = btn.dataset.pinned === 'true';
            this.pinNote(name, !pinned);
          });
        });

        container.querySelectorAll('.note-tag-btn').forEach((btn) => {
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const name = btn.dataset.name;
            this.tagNote(name);
          });
        });

        container.querySelectorAll('.note-restore-btn').forEach((btn) => {
          btn.addEventListener('click', async (e) => {
            e.stopPropagation();
            const name = btn.dataset.name;
            try {
              await fetch(`/api/notes/${encodeURIComponent(name)}/restore`, { method: 'POST' });
              this.refresh();
            } catch (e) {
              console.error('note restore failed', e);
            }
          });
        });

        await this.refreshTrashed();
      } catch (e) {
        console.error('notes refresh failed', e);
      }
    },

    _renderNoteItem(note, showActions, usedBy = []) {
      const name = note.name || 'untitled';
      const content = note.content || '';
      const preview = content.slice(0, 120).replace(/\n/g, ' ');
      const tags = note.tags || [];
      const pinned = Boolean(note.pinned);

      let html = `<div class="note-item">
        <div class="note-name">${escapeHtml(name)}.md ${pinned ? '<span class="note-pinned">[pinned]</span>' : ''} ${note.injected ? '<span class="note-pinned">[injected]</span>' : ''}</div>
        <div class="note-preview">${escapeHtml(preview)}${content.length > 120 ? '...' : ''}</div>`;

      if (tags.length > 0) {
        html += `<div class="note-tags">${tags.map((t) => escapeHtml(t)).join(', ')}</div>`;
      }

      if (usedBy.length) {
        html += `<div class="memory-entry" style="font-size:9px;color:var(--yellow)">used by: ${formatUsage(usedBy)}</div>`;
      }

      if (showActions) {
        html += `<div class="note-actions">
          <button class="note-edit-btn" data-name="${escapeHtml(name)}" data-content="${escapeHtml(content)}">Edit</button>
          <button class="note-rename-btn" data-name="${escapeHtml(name)}">Rename</button>
          <button class="note-pin-btn" data-name="${escapeHtml(name)}" data-pinned="${pinned}">${pinned ? 'Unpin' : 'Pin'}</button>
          <button class="note-tag-btn" data-name="${escapeHtml(name)}">Tag</button>
          <button class="note-inject-btn" data-name="${escapeHtml(name)}">Inject</button>
          <button class="note-delete-btn" data-name="${escapeHtml(name)}">Delete</button>
        </div>`;
      }

      html += '</div>';
      return html;
    },

    editNote(name, content) {
      const newContent = prompt(`Edit ${name}.md:`, content);
      if (newContent === null) return;
      API.patch(`/api/notes/${encodeURIComponent(name)}`, { content: newContent })
        .then(() => this.refresh());
    },

    async renameNote(name) {
      const newName = prompt(`Rename ${name}.md to:`, name);
      if (!newName) return;
      try {
        await API.patch(`/api/notes/${encodeURIComponent(name)}/rename`, { new_name: newName.trim() });
        this.refresh();
      } catch (e) {
        console.error('note rename failed', e);
      }
    },

    async tagNote(name) {
      const tagValue = prompt('Comma-separated tags:', '');
      if (tagValue === null) return;
      const tags = tagValue
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean);
      try {
        await API.patch(`/api/notes/${encodeURIComponent(name)}/tag`, { tags });
        this.refresh();
      } catch (e) {
        console.error('note tag failed', e);
      }
    },

    async pinNote(name, pinned = true) {
      try {
        await API.patch(`/api/notes/${encodeURIComponent(name)}/pin`, { pinned });
        this.refresh();
      } catch (e) {
        console.error('note pin failed', e);
      }
    },

    async deleteNote(name) {
      if (!confirm(`Delete ${name}.md?`)) return;
      try {
        await fetch(`/api/notes/${encodeURIComponent(name)}`, { method: 'DELETE' });
        this.refresh();
      } catch (e) {
        console.error('note delete failed', e);
      }
    },

    async injectNote(name) {
      try {
        await fetch(`/api/notes/${encodeURIComponent(name)}/inject`, { method: 'POST' });
        this.refresh();
      } catch (e) {
        console.error('note inject failed', e);
      }
    },

    async refreshTrashed() {
      try {
        const r = await fetch('/api/notes/trash');
        if (!r.ok) return;
        const data = await r.json();
        const container = document.getElementById('notes-panel');
        if (!container) return;
        const trashed = data.notes || [];

        if (trashed.length > 0) {
          let html = '<div class="trash-header">Trashed Notes</div>';
          for (const note of trashed) {
            html += `<div class="note-item">
              <div class="note-name" style="color:var(--fg2)">${escapeHtml(note.name)}.md</div>
              <div class="note-actions">
                <button class="note-restore-btn" data-name="${escapeHtml(note.name)}">Restore</button>
              </div>
            </div>`;
          }
          container.innerHTML += html;
        }
      } catch (e) {
        console.error('trashed notes refresh failed', e);
      }
    }
  };

  document.addEventListener('DOMContentLoaded', () => {
    const createBtn = document.getElementById('btn-new-note');
    if (!createBtn) return;
    createBtn.addEventListener('click', async () => {
      const name = prompt('Note name:');
      const title = prompt('Optional title:');
      if (!name) return;
      try {
        const payload = { name: name.trim(), content: '' };
        if (title) payload.title = title;
        const response = await fetch('/api/notes', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          const err = await response.json();
          throw new Error(err.error || 'failed to create note');
        }
        window.NotesPanel.refresh();
      } catch (e) {
        console.error('create note failed', e);
      }
    });
  });
})();

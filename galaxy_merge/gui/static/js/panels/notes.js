(function() {
  function escapeHtml(value) {
    return String(value || '').replace(/[&<>"']/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
    }[ch]));
  }

  let searchQuery = '';

  window.NotesPanel = {
    async refresh() {
      await this.refreshNotes();
      await this.refreshTrashed();
    },

    async refreshNotes() {
      try {
        const payload = await API.getNotes();
        const container = document.getElementById('notes-panel');
        const entries = payload.notes || [];
        
        let html = `<div class="note-search">
          <input type="text" id="note-search-input" placeholder="Search notes..." value="${escapeHtml(searchQuery)}">
          <button id="note-search-btn">Search</button>
        </div>`;

        if (searchQuery) {
          const searchResults = await API.get(`/api/notes/search?q=${encodeURIComponent(searchQuery)}`);
          const results = searchResults.results || [];
          html += `<div style="font-size:10px;color:var(--fg2);padding:2px 4px">${results.length} results for "${escapeHtml(searchQuery)}"</div>`;
          for (const result of results) {
            html += this._renderNoteItem(result.name, result.preview, {}, false);
          }
        } else {
          if (entries.length === 0) {
            html += '<div style="color:var(--fg2);padding:4px">No notes. Click + to create.</div>';
          } else {
            if (payload.truncated) {
              html += `<div class="tree-item" style="color:var(--yellow)">Showing ${entries.length} of ${payload.total} notes</div>`;
            }
            for (const note of entries) {
              html += this._renderNoteItem(note.name, note.content, note, true);
            }
          }
        }

        container.innerHTML = html;

        const searchInput = document.getElementById('note-search-input');
        const searchBtn = document.getElementById('note-search-btn');
        if (searchInput) {
          searchInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
              searchQuery = searchInput.value.trim();
              this.refreshNotes();
            }
          });
        }
        if (searchBtn) {
          searchBtn.addEventListener('click', () => {
            searchQuery = searchInput.value.trim();
            this.refreshNotes();
          });
        }

        container.querySelectorAll('.note-edit-btn').forEach(btn => {
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const name = btn.dataset.name;
            const content = btn.dataset.content;
            this.editNote(name, content);
          });
        });

        container.querySelectorAll('.note-delete-btn').forEach(btn => {
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const name = btn.dataset.name;
            this.deleteNote(name);
          });
        });

        container.querySelectorAll('.note-inject-btn').forEach(btn => {
          btn.addEventListener('click', (e) => {
            e.stopPropagation();
            const name = btn.dataset.name;
            this.injectNote(name);
          });
        });

      } catch (e) {
        console.error('notes refresh failed', e);
      }
    },

    _renderNoteItem(name, content, noteData, showActions) {
      const preview = (content || '').slice(0, 60).replace(/\n/g, ' ');
      const tags = noteData.tags || [];
      const pinned = noteData.pinned || false;
      
      let html = `<div class="note-item">
        <div class="note-name">${escapeHtml(name)}.md ${pinned ? '<span class="note-pinned">[pinned]</span>' : ''}</div>
        <div class="note-preview">${escapeHtml(preview)}${(content || '').length > 60 ? '...' : ''}</div>`;
      
      if (tags.length > 0) {
        html += `<div class="note-tags">${tags.map(t => escapeHtml(t)).join(', ')}</div>`;
      }
      
      if (showActions) {
        html += `<div class="note-actions">
          <button class="note-edit-btn" data-name="${escapeHtml(name)}" data-content="${escapeHtml(content || '')}">Edit</button>
          <button class="note-inject-btn" data-name="${escapeHtml(name)}">Inject</button>
          <button class="note-delete-btn" data-name="${escapeHtml(name)}">Delete</button>
        </div>`;
      }
      
      html += '</div>';
      return html;
    },

    editNote(name, content) {
      const newContent = prompt(`Edit ${name}.md:`, content);
      if (newContent !== null) {
        API.patch(`/api/notes/${encodeURIComponent(name)}`, {content: newContent}).then(() => this.refresh());
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
        alert(`Note "${name}" injected into goal context`);
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

          container.querySelectorAll('.note-restore-btn').forEach(btn => {
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
        }
      } catch (e) {
        // Trash endpoint may not exist, ignore
      }
    }
  };

  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('btn-new-note').addEventListener('click', () => {
      const name = prompt('Note name:');
      if (!name) return;
      fetch('/api/notes', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({name, content: ''}),
      }).then(() => window.NotesPanel.refresh());
    });
  });
})();

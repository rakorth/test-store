const list = document.querySelector('#todos');
const error = document.querySelector('#error');
const form = document.querySelector('#add-form');
const input = document.querySelector('#title');
const rows = new Map();
let refreshVersion = 0;
async function request(path, method = 'GET', data) {
  const response = await fetch(path, {
    method,
    headers: data === undefined ? {} : {'Content-Type': 'application/json'},
    body: data === undefined ? undefined : JSON.stringify(data)
  });
  if (!response.ok) {
    const result = await response.json();
    throw new Error(result.error || 'Request failed');
  }
  return response.status === 204 ? null : response.json();
}
function createRow(initial) {
  let todo = initial;
  let editing = false;
  let busy = false;
  const row = document.createElement('li');
  const checkbox = document.createElement('input');
  checkbox.type = 'checkbox';
  const title = document.createElement('span');
  const edit = document.createElement('button');
  edit.textContent = 'Edit';
  const remove = document.createElement('button');
  remove.textContent = 'Delete';
  const editor = document.createElement('form');
  editor.className = 'editor';
  editor.noValidate = true;
  const draft = document.createElement('input');
  draft.type = 'text';
  draft.autocomplete = 'off';
  const save = document.createElement('button');
  save.type = 'submit';
  save.textContent = 'Save';
  const cancel = document.createElement('button');
  cancel.type = 'button';
  cancel.textContent = 'Cancel';
  const message = document.createElement('span');
  message.className = 'row-error';
  message.id = `edit-error-${todo.id}`;
  message.setAttribute('role', 'alert');
  draft.setAttribute('aria-describedby', message.id);
  editor.append(draft, save, cancel);
  row.append(checkbox, title, edit, editor, remove, message);
  function render() {
    checkbox.checked = todo.completed;
    checkbox.setAttribute('aria-label', `Complete ${todo.title}`);
    title.className = todo.completed ? 'title done' : 'title';
    title.textContent = todo.title;
    edit.setAttribute('aria-label', `Edit ${todo.title}`);
    remove.setAttribute('aria-label', `Delete ${todo.title}`);
    draft.setAttribute('aria-label', `Title for ${todo.title}`);
    save.setAttribute('aria-label', `Save ${todo.title}`);
    cancel.setAttribute('aria-label', `Cancel editing ${todo.title}`);
    title.hidden = editing;
    edit.hidden = editing;
    editor.hidden = !editing;
    checkbox.disabled = busy || editing;
    remove.disabled = busy || editing;
    edit.disabled = busy;
    draft.disabled = busy;
    save.disabled = busy;
    cancel.disabled = busy;
    row.setAttribute('aria-busy', String(busy));
  }
  function finish() {
    editing = false;
    message.textContent = '';
    draft.removeAttribute('aria-invalid');
    render();
    edit.focus();
  }
  edit.addEventListener('click', () => {
    if (busy) return;
    editing = true;
    draft.value = todo.title;
    message.textContent = '';
    render();
    draft.focus();
    draft.select();
  });
  cancel.addEventListener('click', () => { if (!busy) finish(); });
  draft.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      event.preventDefault();
      if (!busy) finish();
    }
  });
  editor.addEventListener('submit', async event => {
    event.preventDefault();
    if (busy) return;
    const normalized = draft.value.trim();
    if ([...normalized].length < 1 || [...normalized].length > 200) {
      message.textContent = 'Title must contain 1–200 characters after trimming.';
      draft.setAttribute('aria-invalid', 'true');
      draft.focus();
      return;
    }
    busy = true;
    render();
    try {
      const result = await request(`/api/todos/${todo.id}`, 'PATCH', {title: draft.value});
      // Invalidate older GET responses so they cannot overwrite this save.
      refreshVersion++;
      todo = result.todo;
      busy = false;
      finish();
    } catch (failure) {
      busy = false;
      message.textContent = failure.message;
      render();
      draft.focus();
    }
  });
  checkbox.addEventListener('change', async () => {
    if (busy || editing) return;
    const completed = checkbox.checked;
    busy = true;
    render();
    try {
      const result = await request(`/api/todos/${todo.id}`, 'PATCH', {completed});
      refreshVersion++;
      todo = result.todo;
      message.textContent = '';
    } catch (failure) {
      message.textContent = failure.message;
    } finally {
      busy = false;
      render();
      checkbox.focus();
    }
  });
  remove.addEventListener('click', async () => {
    if (busy || editing) return;
    busy = true;
    render();
    try {
      await request(`/api/todos/${todo.id}`, 'DELETE');
      refreshVersion++;
      rows.delete(todo.id);
      row.remove();
      document.querySelector('#empty').hidden = rows.size !== 0;
      input.focus();
    } catch (failure) {
      message.textContent = failure.message;
      busy = false;
      render();
      remove.focus();
    }
  });
  render();
  return {
    row,
    protected: () => editing || busy,
    update(next) { if (!busy) { todo = next; render(); } }
  };
}
async function refresh() {
  const version = ++refreshVersion;
  const {todos} = await request('/api/todos');
  if (version !== refreshVersion) return;
  const ids = new Set(todos.map(todo => todo.id));
  for (const [id, state] of rows) {
    if (!ids.has(id) && !state.protected()) {
      state.row.remove();
      rows.delete(id);
    }
  }
  for (const todo of todos) {
    let state = rows.get(todo.id);
    if (!state) {
      state = createRow(todo);
      rows.set(todo.id, state);
      list.append(state.row);
    } else {
      state.update(todo);
    }
  }
  document.querySelector('#empty').hidden = rows.size !== 0;
}
async function act(operation) {
  error.textContent = '';
  try {
    await operation();
    await refresh();
  } catch (failure) {
    error.textContent = failure.message;
  }
}
form.addEventListener('submit', event => {
  event.preventDefault();
  act(async () => {
    await request('/api/todos', 'POST', {title: input.value});
    input.value = '';
    input.focus();
  });
});
act(async () => {});

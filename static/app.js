const list = document.querySelector('#todos');
const error = document.querySelector('#error');
const form = document.querySelector('#add-form');
const input = document.querySelector('#title');
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
async function refresh() {
  const {todos} = await request('/api/todos');
  list.replaceChildren();
  document.querySelector('#empty').hidden = todos.length !== 0;
  for (const todo of todos) {
    const row = document.createElement('li');
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    checkbox.checked = todo.completed;
    checkbox.setAttribute('aria-label', `Complete ${todo.title}`);
    const title = document.createElement('span');
    title.className = todo.completed ? 'title done' : 'title';
    title.textContent = todo.title;
    const remove = document.createElement('button');
    remove.textContent = 'Delete';
    remove.setAttribute('aria-label', `Delete ${todo.title}`);
    checkbox.addEventListener('change', () => act(async () => {
      await request(`/api/todos/${todo.id}`, 'PATCH', {completed: checkbox.checked});
    }));
    remove.addEventListener('click', () => act(() => request(`/api/todos/${todo.id}`, 'DELETE')));
    row.append(checkbox, title, remove);
    list.append(row);
  }
}
async function act(operation) {
  error.textContent = '';
  try {
    await operation();
    await refresh();
  } catch (failure) {
    error.textContent = failure.message;
    try { await refresh(); } catch (_) { /* Keep original error visible. */ }
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

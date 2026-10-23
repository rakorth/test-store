# Python todo app — milestone 1

Requires Python 3.11 or newer. Uses only the standard library; no installation or package downloads are needed.

From the repository root, run:

```sh
python3 app.py
```

Open http://127.0.0.1:8080 in a browser. Add, complete/uncomplete, and delete todos. Stop with Ctrl+C. Storage is in memory only: restarting the process clears all todos.

To configure the listener:

```sh
python3 app.py --host 127.0.0.1 --port 9000
```

Run the test suite from the repository root:

```sh
python3 -m unittest discover -s tests -v
```

HTTP tests use independent stores and ephemeral loopback ports, never workspace runtime data.

## API

- `GET /api/todos` → `200 {"todos": [...]}`
- `POST /api/todos` with `{"title":"Buy milk"}` → `201 {"todo": {...}}`
- `PATCH /api/todos/1` with `{"completed":true}` → `200 {"todo": {...}}`
- `DELETE /api/todos/1` → `204` with no body

Send JSON with `Content-Type: application/json`. Each todo has `id`, `title`, and `completed`. IDs are positive integers and are never reused within a store instance. Titles are trimmed and must contain 1–200 characters after trimming. Completion must be a JSON boolean. Invalid input returns `400 {"error":"..."}`; unknown routes or todo IDs return `404 {"error":"..."}`. Request bodies are limited to 16 KiB. Browser titles are assigned through `textContent`.

`create_server(host, port, store)` accepts an injected `TodoStore` implementation with `list`, `create`, `set_completed`, and `delete` operations (missing IDs raise `KeyError`). The default `MemoryTodoStore` uses a lock and returns copies so callers cannot mutate stored records. A future milestone can replace that implementation; this milestone contains no disk persistence.

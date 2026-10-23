# Python todo app

Requires Python 3.11 or newer. Uses only the standard library; no installation or package downloads are needed.

From the repository root, run:

```sh
python3 app.py
```

Open http://127.0.0.1:8080 in a browser. Add, complete/uncomplete, and delete todos. Stop with Ctrl+C. Todos persist across restarts in `todos.sqlite3` in the current working directory. The schema is created automatically.

To configure the listener:

```sh
python3 app.py --host 127.0.0.1 --port 9000
```

Run the test suite from the repository root:

```sh
python3 -m unittest discover -s tests -v
```

Tests use isolated in-memory stores or temporary SQLite databases and ephemeral loopback ports, never workspace runtime data.

## API

- `GET /api/todos` → `200 {"todos": [...]}`
- `POST /api/todos` with `{"title":"Buy milk"}` → `201 {"todo": {...}}`
- `PATCH /api/todos/1` with `{"completed":true}` → `200 {"todo": {...}}`
- `DELETE /api/todos/1` → `204` with no body

Send JSON with `Content-Type: application/json`. Each todo has `id`, `title`, and `completed`. IDs are positive integers and are never reused in the same database. Titles are trimmed and must contain 1–200 characters after trimming. Completion must be a JSON boolean. Invalid input returns `400 {"error":"..."}`; unknown routes or todo IDs return `404 {"error":"..."}`. Request bodies are limited to 16 KiB. Browser titles are assigned through `textContent`.

## Storage configuration and backups

Set `TODO_DB_PATH` to choose a database file (its parent directory must exist):

```sh
TODO_DB_PATH=/path/to/todos.sqlite3 python3 app.py
```

The default is `todos.sqlite3` relative to the working directory. Use a file path, not `:memory:`: each store operation opens and closes its own SQLite connection so HTTP threads never share connections. Writes use parameterized queries and committed transactions. Generated SQLite databases, journals, and Python caches are ignored by Git; never commit a database.

For a simple safe backup, stop the app with Ctrl+C, copy the database to a safe location, then restart the app. Stop all processes using that database before copying or restoring it; do not copy a live database file by itself. To back up while running, use Python's `sqlite3.Connection.backup()` API to create a consistent snapshot instead. Restore with the app stopped, keeping a copy of the current database first. Backups contain todo titles and should be stored privately.

`create_server(host, port, store)` accepts an injected `TodoStore` with `list`, `create`, `set_completed`, and `delete` operations (missing IDs raise `KeyError`). Without an injected store it uses `SQLiteTodoStore` and reads `TODO_DB_PATH`. `MemoryTodoStore` remains available for isolated tests.

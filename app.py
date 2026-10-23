"""Standard-library todo server. Todos persist in SQLite by default."""
import argparse
from contextlib import closing
import os
import sqlite3
import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Lock
from typing import Protocol
from urllib.parse import urlsplit


class TodoStore(Protocol):
    def list(self) -> list[dict]: ...
    def create(self, title: str) -> dict: ...
    def set_completed(self, todo_id: int, completed: bool) -> dict: ...
    def delete(self, todo_id: int) -> None: ...


class MemoryTodoStore:
    def __init__(self):
        self._todos = {}
        self._next_id = 1
        self._lock = Lock()

    def list(self):
        with self._lock:
            return [todo.copy() for todo in self._todos.values()]

    def create(self, title):
        with self._lock:
            todo = dict(id=self._next_id, title=title, completed=False)
            self._todos[self._next_id] = todo
            self._next_id += 1
            return todo.copy()

    def set_completed(self, todo_id, completed):
        with self._lock:
            todo = self._todos[todo_id]
            todo['completed'] = completed
            return todo.copy()

    def delete(self, todo_id):
        with self._lock:
            del self._todos[todo_id]


class SQLiteTodoStore:
    """File-backed store; each operation owns its connection and transaction."""

    def __init__(self, path):
        self.path = str(path)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            connection.execute("""
                CREATE TABLE IF NOT EXISTS todos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    completed INTEGER NOT NULL DEFAULT 0 CHECK (completed IN (0, 1))
                )
            """)

    @staticmethod
    def _todo(row):
        return dict(id=row[0], title=row[1], completed=bool(row[2]))

    def list(self):
        with closing(sqlite3.connect(self.path)) as connection:
            return [self._todo(row) for row in connection.execute(
                'SELECT id, title, completed FROM todos ORDER BY id')]

    def create(self, title):
        with closing(sqlite3.connect(self.path)) as connection, connection:
            cursor = connection.execute('INSERT INTO todos (title) VALUES (?)', (title,))
            return dict(id=cursor.lastrowid, title=title, completed=False)

    def set_completed(self, todo_id, completed):
        if not 1 <= todo_id <= 9223372036854775807:
            raise KeyError(todo_id)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            cursor = connection.execute(
                'UPDATE todos SET completed = ? WHERE id = ?', (completed, todo_id))
            if not cursor.rowcount:
                raise KeyError(todo_id)
            row = connection.execute(
                'SELECT id, title, completed FROM todos WHERE id = ?', (todo_id,)).fetchone()
            return self._todo(row)

    def delete(self, todo_id):
        if not 1 <= todo_id <= 9223372036854775807:
            raise KeyError(todo_id)
        with closing(sqlite3.connect(self.path)) as connection, connection:
            cursor = connection.execute('DELETE FROM todos WHERE id = ?', (todo_id,))
            if not cursor.rowcount:
                raise KeyError(todo_id)


STATIC = Path(__file__).parent / 'static'
MAX_BODY = 16384


def create_server(host='127.0.0.1', port=8080, store: TodoStore | None = None):
    """Return an unstarted server; caller owns serve_forever/server_close."""
    todo_store = SQLiteTodoStore(os.environ.get('TODO_DB_PATH', 'todos.sqlite3')) if store is None else store

    class Handler(BaseHTTPRequestHandler):
        def send_body(self, status, body=b'', content_type='application/json; charset=utf-8'):
            self.send_response(status)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def json_response(self, status, value):
            self.send_body(status, json.dumps(value).encode('utf-8'))

        def read_json(self):
            if self.headers.get('Transfer-Encoding'):
                raise ValueError('Transfer-Encoding is not supported')
            if self.headers.get_content_type() != 'application/json':
                raise ValueError('Content-Type must be application/json')
            try:
                length = int(self.headers.get('Content-Length', '0'))
            except ValueError:
                raise ValueError('Invalid Content-Length') from None
            if not 0 < length <= MAX_BODY:
                raise ValueError('JSON body must be between 1 and 16384 bytes')
            try:
                value = json.loads(self.rfile.read(length))
            except (ValueError, UnicodeDecodeError):
                raise ValueError('Malformed JSON body') from None
            if not isinstance(value, dict):
                raise ValueError('JSON body must be an object')
            return value

        def dispatch(self):
            path = urlsplit(self.path).path
            method = self.command
            if method == 'GET' and path in ('/', '/app.js'):
                name, mime = ('index.html', 'text/html') if path == '/' else ('app.js', 'text/javascript')
                self.send_body(200, (STATIC / name).read_bytes(), mime + '; charset=utf-8')
                return
            if path == '/api/todos' and method == 'GET':
                self.json_response(200, {'todos': todo_store.list()})
                return
            if path == '/api/todos' and method == 'POST':
                data = self.read_json()
                title = data.get('title')
                if not isinstance(title, str) or not 1 <= len(title.strip()) <= 200:
                    raise ValueError('title must be a string of 1–200 characters after trimming')
                self.json_response(201, {'todo': todo_store.create(title.strip())})
                return
            match = re.fullmatch(r'/api/todos/([1-9][0-9]*)', path)
            if match and method in ('PATCH', 'DELETE'):
                todo_id = int(match[1])
                if method == 'PATCH':
                    data = self.read_json()
                    if type(data.get('completed')) is not bool:
                        raise ValueError('completed must be a boolean')
                    self.json_response(200, {'todo': todo_store.set_completed(todo_id, data['completed'])})
                else:
                    todo_store.delete(todo_id)
                    self.send_body(204)
                return
            self.json_response(404, {'error': 'Route not found'})

        def handle_request(self):
            try:
                self.dispatch()
            except ValueError as error:
                self.json_response(400, {'error': str(error)})
            except KeyError:
                self.json_response(404, {'error': 'Todo not found'})

        do_GET = handle_request
        do_POST = handle_request
        do_PATCH = handle_request
        do_DELETE = handle_request

    return ThreadingHTTPServer((host, port), Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', default='127.0.0.1')
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    with create_server(args.host, args.port) as server:
        print(f'Todo app: http://{args.host}:{server.server_port}', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()

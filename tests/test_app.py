from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
from unittest.mock import patch
import os

import http.client
import json
import threading
import unittest

from app import MemoryTodoStore, SQLiteTodoStore, create_server


class StoreTests(unittest.TestCase):
    def test_isolated_stores_stable_ids_and_defensive_copies(self):
        store = MemoryTodoStore()
        first = store.create('first')
        first['title'] = 'changed'
        self.assertEqual(store.list()[0]['title'], 'first')
        listing = store.list()
        listing[0]['completed'] = True
        self.assertFalse(store.list()[0]['completed'])
        store.delete(first['id'])
        self.assertEqual(store.create('second')['id'], 2)
        self.assertEqual(MemoryTodoStore().list(), [])
        with self.assertRaises(KeyError):
            store.set_completed(1, True)

    def test_concurrent_creation_has_unique_ids(self):
        store = MemoryTodoStore()
        threads = [threading.Thread(target=store.create, args=('todo',)) for _ in range(30)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(sorted(t['id'] for t in store.list()), list(range(1, 31)))


class SQLiteStoreTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'test.sqlite3'

    def test_restart_persists_create_update_delete_and_ids(self):
        store = SQLiteTodoStore(self.path)
        title = "Robert'); DROP TABLE todos; --"
        first = store.create(title)
        deleted = store.create('delete me')
        fresh = SQLiteTodoStore(self.path)
        self.assertEqual(fresh.list(), [first, deleted])
        updated = fresh.set_completed(first['id'], True)
        fresh.delete(deleted['id'])
        restarted = SQLiteTodoStore(self.path)
        self.assertEqual(restarted.list(), [updated])
        self.assertEqual(updated, dict(id=first['id'], title=title, completed=True))
        self.assertGreater(restarted.create('next')['id'], deleted['id'])
        restarted.set_completed(first['id'], False)
        self.assertIs(SQLiteTodoStore(self.path).list()[0]['completed'], False)
        for operation in (restarted.delete, lambda key: restarted.set_completed(key, True)):
            for key in (deleted['id'], 10 ** 100):
                with self.assertRaises(KeyError):
                    operation(key)

    def test_concurrent_connections_commit_unique_records(self):
        store = SQLiteTodoStore(self.path)
        with ThreadPoolExecutor(max_workers=8) as executor:
            todos = list(executor.map(store.create, [f'todo {i}' for i in range(30)]))
        self.assertEqual(len({todo['id'] for todo in todos}), 30)
        self.assertEqual(SQLiteTodoStore(self.path).list(), sorted(todos, key=lambda t: t['id']))


class HTTPTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.store = SQLiteTodoStore(Path(directory.name) / "test.sqlite3")
        self.server = create_server('127.0.0.1', 0, self.store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method, path='/api/todos', data=None, raw=None, headers=None):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        try:
            body = json.dumps(data) if raw is None and data is not None else raw
            connection.request(method, path, body, headers or {'Content-Type': 'application/json'})
            response = connection.getresponse()
            payload = response.read()
            content_type = response.getheader('Content-Type')
            result = json.loads(payload) if payload and content_type.startswith('application/json') else payload
            return response.status, result
        finally:
            connection.close()

    def test_create_list_toggle_delete(self):
        self.assertEqual(self.request('GET'), (200, {'todos': []}))
        status, result = self.request('POST', data={'title': '  buy milk  '})
        self.assertEqual(status, 201)
        todo = result['todo']
        self.assertEqual(todo, {'id': 1, 'title': 'buy milk', 'completed': False})
        self.assertEqual(self.store.list(), [todo])  # injected store is actually used
        self.assertEqual(self.request('GET'), (200, {'todos': [todo]}))
        for completed in (True, False):
            status, result = self.request('PATCH', '/api/todos/1', {'completed': completed})
            self.assertEqual(status, 200)
            self.assertIs(result['todo']['completed'], completed)
            self.assertIs(self.request('GET')[1]['todos'][0]['completed'], completed)
        self.assertEqual(self.request('DELETE', '/api/todos/1'), (204, b''))
        self.assertEqual(self.request('GET'), (200, {'todos': []}))
        self.assertEqual(self.request('POST', data={'title': 'next'})[1]['todo']['id'], 2)

    def test_title_boundaries_and_types(self):
        for title in ('x', 'x' * 200, '  ' + 'x' * 200 + '\n'):
            with self.subTest(title_length=len(title)):
                status, result = self.request('POST', data={'title': title})
                self.assertEqual(status, 201)
                self.assertEqual(result['todo']['title'], title.strip())
        before = self.store.list()
        for title in ('', ' \t\n', 'x' * 201, None, True, 7, [], {}):
            with self.subTest(title=title):
                status, result = self.request('POST', data={'title': title})
                self.assertEqual(status, 400)
                self.assertTrue(result['error'])
        self.assertEqual(self.store.list(), before)

    def test_strict_boolean_completion(self):
        self.store.create('task')
        for value in (0, 1, 'true', None, [], {}):
            with self.subTest(value=value):
                status, result = self.request('PATCH', '/api/todos/1', {'completed': value})
                self.assertEqual(status, 400)
                self.assertIn('boolean', result['error'])
        self.assertEqual(self.request('PATCH', '/api/todos/1', {})[0], 400)
        self.assertFalse(self.store.list()[0]['completed'])

    def test_malformed_bodies(self):
        for raw in ('{', '[]', 'null', '1', '"text"', '', '\ud800'.encode('utf-8', errors='surrogatepass')):
            with self.subTest(raw=raw):
                status, result = self.request('POST', raw=raw)
                self.assertEqual(status, 400)
                self.assertTrue(result['error'])
        self.assertEqual(self.request('POST', data={})[0], 400)
        self.assertEqual(self.request('POST', raw='{}', headers={'Content-Type': 'text/plain'})[0], 400)
        self.assertEqual(self.request('POST', raw='x' * 16385)[0], 400)
        self.assertEqual(self.store.list(), [])

    def test_missing_ids_and_routes(self):
        for method in ('PATCH', 'DELETE'):
            status, result = self.request(method, '/api/todos/999', {'completed': True})
            self.assertEqual(status, 404)
            self.assertEqual(result, {'error': 'Todo not found'})
        for path in ('/missing', '/api/todos/0', '/api/todos/-1', '/api/todos/nope', '/api/todos/1/extra'):
            with self.subTest(path=path):
                self.assertEqual(self.request('GET', path)[0], 404)
        self.assertEqual(self.request('POST', '/missing', {'title': 'x'})[0], 404)

    def test_ui_and_untrusted_title(self):
        title = '<img src=x onerror=alert(1)>'
        self.assertEqual(self.request('POST', data={'title': title})[1]['todo']['title'], title)
        status, html = self.request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn(b'<script src="/app.js" defer>', html)
        self.assertNotIn(title.encode(), html)
        status, script = self.request('GET', '/app.js')
        self.assertEqual(status, 200)
        self.assertIn(b'title.textContent = todo.title', script)
        self.assertNotIn(b'innerHTML', script)
        self.assertNotIn(b'insertAdjacentHTML', script)
        self.assertEqual(self.request('GET')[1]['todos'][0]['title'], title)


class RestartHTTPTests(unittest.TestCase):
    request = HTTPTests.request
    close_server = HTTPTests.close_server
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'http.sqlite3'
        self.start_server()

    def start_server(self):
        with patch.dict(os.environ, TODO_DB_PATH=str(self.path)):
            self.server = create_server('127.0.0.1', 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        server, thread = self.server, self.thread
        def cleanup():
            server.shutdown()
            server.server_close()
            thread.join()
        self.addCleanup(cleanup)

    def test_restart_default_app(self):
        first = self.request('POST', data={'title': '  persistent  '})[1]['todo']
        deleted = self.request('POST', data={'title': 'delete'})[1]['todo']
        self.close_server()
        self.start_server()
        self.assertEqual(self.request('GET'), (200, {'todos': [first, deleted]}))
        updated = self.request('PATCH', f"/api/todos/{first['id']}", {'completed': True})[1]['todo']
        self.assertEqual(self.request('DELETE', f"/api/todos/{deleted['id']}")[0], 204)
        self.close_server()
        self.start_server()
        self.assertEqual(self.request('GET'), (200, {'todos': [updated]}))
        self.assertEqual(updated, dict(id=first['id'], title='persistent', completed=True))
        self.assertGreater(self.request('POST', data={'title': 'next'})[1]['todo']['id'], deleted['id'])


if __name__ == '__main__':
    unittest.main()

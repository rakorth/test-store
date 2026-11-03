"""Title editing regressions; no external packages or workspace data."""
from pathlib import Path
import tempfile
import threading
import unittest

from app import MemoryTodoStore, SQLiteTodoStore, create_server
import test_app


class TitleStoreTests(unittest.TestCase):
    def test_both_stores_validate_atomically_and_preserve_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            for store in (MemoryTodoStore(), SQLiteTodoStore(Path(directory) / 'todos.db')):
                with self.subTest(store=type(store).__name__):
                    original = store.create('original')
                    key = original['id']
                    self.assertEqual(store.update(key, title=' renamed '),
                                     dict(id=key, title='renamed', completed=False))
                    combined = store.update(key, title=' combined ', completed=True)
                    self.assertEqual(combined, dict(id=key, title='combined', completed=True))
                    self.assertEqual(store.update(key, title='finished')['completed'], True)
                    for title in ('x', 'x' * 200, '  ' + 'x' * 200 + '\n'):
                        self.assertEqual(store.update(key, title=title)['title'], title.strip())
                    before = store.list()
                    invalid = [{}, {'other': 1}]
                    invalid += [{'title': title, 'completed': False}
                                for title in ('', ' \t\n', 'x' * 201, None, True, 7, [], {})]
                    invalid += [{'title': 'must not persist', 'completed': value}
                                for value in (0, 1, 'true', None, [], {})]
                    for changes in invalid:
                        with self.subTest(changes=changes):
                            with self.assertRaises(ValueError):
                                store.update(key, **changes)
                            self.assertEqual(store.list(), before)
                    with self.assertRaises(KeyError):
                        store.update(999, title='missing')
                    returned = store.set_completed(key, False)
                    returned['title'] = 'mutated copy'
                    self.assertEqual(store.list()[0]['title'], before[0]['title'])
                    self.assertFalse(store.list()[0]['completed'])

    def test_sqlite_rename_survives_new_store(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'todos.db'
            store = SQLiteTodoStore(path)
            todo = store.create('old')
            title = "Robert'); DROP TABLE todos; --"
            expected = store.update(todo['id'], title=title, completed=True)
            self.assertEqual(SQLiteTodoStore(path).list(), [expected])


class TitleHTTPTests(unittest.TestCase):
    setUp = test_app.HTTPTests.setUp
    close_server = test_app.HTTPTests.close_server
    request = test_app.HTTPTests.request

    def test_patch_title_and_combined_validation(self):
        todo = self.request('POST', data={'title': 'old'})[1]['todo']
        path = f"/api/todos/{todo['id']}"
        for title in ('x', 'x' * 200, '  ' + 'x' * 200 + '\n'):
            status, body = self.request('PATCH', path, {'title': title})
            self.assertEqual(status, 200)
            self.assertEqual(body['todo'], dict(id=todo['id'], title=title.strip(), completed=False))
        status, body = self.request('PATCH', path, {'title': ' combined ', 'completed': True})
        self.assertEqual((status, body['todo']),
                         (200, dict(id=todo['id'], title='combined', completed=True)))
        status, body = self.request('PATCH', path, {'title': ' renamed completed '})
        self.assertEqual((status, body['todo']),
                         (200, dict(id=todo['id'], title='renamed completed', completed=True)))
        before = self.request('GET')
        invalid = [{}, {'unknown': True}]
        invalid += [{'title': title, 'completed': False}
                    for title in ('', ' \t\n', 'x' * 201, None, True, 7, [], {})]
        invalid += [{'title': 'must not persist', 'completed': value}
                    for value in (0, 1, 'true', None, [], {})]
        for changes in invalid:
            with self.subTest(changes=changes):
                status, body = self.request('PATCH', path, changes)
                self.assertEqual(status, 400)
                self.assertTrue(body['error'])
                self.assertEqual(self.request('GET'), before)
        for key in (999, 10 ** 100):
            for changes in ({'title': 'missing'}, {'title': 'missing', 'completed': True}):
                self.assertEqual(self.request('PATCH', f'/api/todos/{key}', changes)[0], 404)


class LegacyCompletionTests(unittest.TestCase):
    request = test_app.HTTPTests.request
    close_server = test_app.HTTPTests.close_server

    def test_completion_only_injected_store_does_not_need_update(self):
        class LegacyStore:
            def __init__(self):
                self.called = None

            def set_completed(self, key, completed):
                self.called = (key, completed)
                return dict(id=key, title='legacy', completed=completed)

        store = LegacyStore()
        self.server = create_server('127.0.0.1', 0, store)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.assertEqual(self.request('PATCH', '/api/todos/1', {'completed': True}),
                         (200, {'todo': dict(id=1, title='legacy', completed=True)}))
        self.assertEqual(store.called, (1, True))
        self.assertEqual(self.request('PATCH', '/api/todos/1', {'completed': 1})[0], 400)
        self.assertEqual(store.called, (1, True))


class TitleRestartTests(unittest.TestCase):
    setUp = test_app.RestartHTTPTests.setUp
    start_server = test_app.RestartHTTPTests.start_server
    close_server = test_app.HTTPTests.close_server
    request = test_app.HTTPTests.request

    def test_renamed_title_survives_server_restart(self):
        todo = self.request('POST', data={'title': 'old'})[1]['todo']
        path = f"/api/todos/{todo['id']}"
        expected = dict(id=todo['id'], title='persisted rename', completed=True)
        self.assertEqual(self.request('PATCH', path, {'title': ' persisted rename ', 'completed': True}),
                         (200, {'todo': expected}))
        self.close_server()
        self.start_server()
        self.assertEqual(self.request('GET'), (200, {'todos': [expected]}))
        expected['title'] = 'second rename'
        self.assertEqual(self.request('PATCH', path, {'title': expected['title']}),
                         (200, {'todo': expected}))
        self.close_server()
        self.start_server()
        self.assertEqual(self.request('GET'), (200, {'todos': [expected]}))


class UISourceSafeguards(unittest.TestCase):
    def test_safe_editor_values_and_persistent_rows(self):
        script = (Path(__file__).resolve().parents[1] / 'static' / 'app.js').read_text()
        self.assertNotIn('innerHTML', script)
        self.assertNotIn('insertAdjacentHTML', script)
        self.assertIn('title.textContent = todo.title', script)
        self.assertIn('draft.value = todo.title', script)
        self.assertIn("draft.setAttribute('aria-label'", script)
        self.assertIn("message.setAttribute('role', 'alert')", script)
        # Rebuilding the list on refresh used to destroy unrelated drafts and errors.
        self.assertNotIn('list.replaceChildren', script)
        self.assertIn('rows.get(todo.id)', script)
        self.assertIn("editor.addEventListener('submit'", script)
        self.assertIn("event.key === 'Escape'", script)
        self.assertIn('save.disabled = busy', script)
        self.assertIn('cancel.disabled = busy', script)


if __name__ == '__main__':
    unittest.main()

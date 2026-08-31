import sqlite3
import json

class Database:
    def __init__(self, db_path="forwarder.db"):
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self._init()

    def _init(self):
        c = self.conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_channel TEXT NOT NULL,
            target_channel TEXT NOT NULL,
            interval_minutes INTEGER DEFAULT 60,
            last_forwarded_id INTEGER DEFAULT 0,
            is_active INTEGER DEFAULT 1,
            content_types TEXT DEFAULT '["all"]',
            batch_size INTEGER DEFAULT 50,
            custom_name TEXT DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        c.execute('''CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER,
            action TEXT,
            details TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )''')
        self.conn.commit()

    def add_task(self, source, target, interval, content_types, batch_size, name):
        c = self.conn.cursor()
        c.execute('''INSERT INTO tasks 
            (source_channel, target_channel, interval_minutes, content_types, batch_size, custom_name)
            VALUES (?,?,?,?,?,?)''',
            (source, target, interval, json.dumps(content_types), batch_size, name))
        self.conn.commit()
        return c.lastrowid

    def get_active_tasks(self):
        c = self.conn.cursor()
        c.execute('SELECT * FROM tasks WHERE is_active=1')
        return [self._row_to_dict(r) for r in c.fetchall()]

    def get_all_tasks(self):
        c = self.conn.cursor()
        c.execute('SELECT * FROM tasks')
        return [self._row_to_dict(r) for r in c.fetchall()]

    def update_last_id(self, tid, mid):
        c = self.conn.cursor()
        c.execute('UPDATE tasks SET last_forwarded_id=? WHERE id=?', (mid, tid))
        self.conn.commit()

    def toggle_task(self, tid, active):
        c = self.conn.cursor()
        c.execute('UPDATE tasks SET is_active=? WHERE id=?', (1 if active else 0, tid))
        self.conn.commit()

    def delete_task(self, tid):
        c = self.conn.cursor()
        c.execute('DELETE FROM tasks WHERE id=?', (tid,))
        self.conn.commit()

    def log(self, tid, action, details=""):
        c = self.conn.cursor()
        c.execute('INSERT INTO logs (task_id,action,details) VALUES (?,?,?)',
                  (tid, action, details))
        self.conn.commit()

    def get_logs(self, tid=None, limit=50):
        c = self.conn.cursor()
        if tid:
            c.execute('SELECT * FROM logs WHERE task_id=? ORDER BY id DESC LIMIT ?',
                      (tid, limit))
        else:
            c.execute('SELECT * FROM logs ORDER BY id DESC LIMIT ?', (limit,))
        return c.fetchall()

    def _row_to_dict(self, r):
        return {
            "id": r[0], "source_channel": r[1], "target_channel": r[2],
            "interval_minutes": r[3], "last_forwarded_id": r[4],
            "is_active": bool(r[5]), "content_types": json.loads(r[6]),
            "batch_size": r[7], "custom_name": r[8], "created_at": r[9]
        }

-- 1. Publisher
CREATE TABLE publisher (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  notes TEXT
);

-- 2. Narrator
CREATE TABLE narrator (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  calendar_alias TEXT UNIQUE,
  notes TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- 3. Book
CREATE TABLE book (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  slug TEXT UNIQUE NOT NULL,
  title TEXT NOT NULL,
  publisher_id INTEGER,
  source_path TEXT NOT NULL,
  view_path TEXT NOT NULL,
  format TEXT NOT NULL,
  genre TEXT,
  publisher_notes TEXT,
  body_chars INTEGER DEFAULT 0,
  raw_chars INTEGER DEFAULT 0,
  chars_per_page INTEGER DEFAULT 0,
  pages INTEGER DEFAULT 0,
  images INTEGER DEFAULT 0,
  charts_tables INTEGER DEFAULT 0,
  audio_folder TEXT,
  drive_sync_path TEXT,
  narrator_id INTEGER,
  planned_end DATE,
  current_page INTEGER DEFAULT 1,
  status TEXT CHECK(status IN ('planned','in_progress','done','archived')) DEFAULT 'planned',
  is_draft INTEGER DEFAULT 0,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (publisher_id) REFERENCES publisher(id),
  FOREIGN KEY (narrator_id)  REFERENCES narrator(id)
);

CREATE TRIGGER book_touch AFTER UPDATE ON book BEGIN
  UPDATE book SET updated_at = CURRENT_TIMESTAMP WHERE id = NEW.id;
END;

-- 4. Narrator-book assignment history
CREATE TABLE narrator_book (
  narrator_id INTEGER,
  book_id     INTEGER,
  assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  finished_at DATETIME,
  PRIMARY KEY (narrator_id, book_id),
  FOREIGN KEY (narrator_id) REFERENCES narrator(id),
  FOREIGN KEY (book_id)     REFERENCES book(id)
);

-- 5. Schedule items (declared before reading_session so FK target exists)
CREATE TABLE schedule_item (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source TEXT CHECK(source IN ('studio_1','studio_2','manual')) NOT NULL,
  google_event_id TEXT UNIQUE,
  start_time DATETIME NOT NULL,
  end_time   DATETIME NOT NULL,
  raw_title TEXT NOT NULL,
  notes     TEXT,
  resolved_narrator_id INTEGER,
  resolved_book_id     INTEGER,
  resolved_at DATETIME,
  action_status TEXT CHECK(action_status IN
    ('pending','started','completed','skipped','cancelled')
  ) DEFAULT 'pending',
  kind TEXT CHECK(kind IN ('recording','editing','deadline')),
  last_synced_at DATETIME,
  FOREIGN KEY (resolved_narrator_id) REFERENCES narrator(id),
  FOREIGN KEY (resolved_book_id)     REFERENCES book(id)
);

-- 6. Reading session
CREATE TABLE reading_session (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id     INTEGER NOT NULL,
  narrator_id INTEGER,
  started_at DATETIME NOT NULL,
  ended_at   DATETIME,
  start_page INTEGER NOT NULL,
  end_page   INTEGER,
  tracked_progress_page INTEGER,
  active_seconds INTEGER DEFAULT 0,
  last_heartbeat_at DATETIME,
  auto_closed INTEGER DEFAULT 0,
  schedule_item_id INTEGER,
  FOREIGN KEY (book_id)          REFERENCES book(id),
  FOREIGN KEY (narrator_id)      REFERENCES narrator(id),
  FOREIGN KEY (schedule_item_id) REFERENCES schedule_item(id)
);

-- 7. Work session
CREATE TABLE work_session (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id     INTEGER NOT NULL,
  narrator_id INTEGER,
  kind TEXT CHECK(kind IN ('recording','editing')) NOT NULL,
  started_at DATETIME NOT NULL,
  ended_at   DATETIME,
  start_page INTEGER,
  end_page   INTEGER,
  notes TEXT,
  FOREIGN KEY (book_id)     REFERENCES book(id),
  FOREIGN KEY (narrator_id) REFERENCES narrator(id)
);

-- 8. Audio file
CREATE TABLE audio_file (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id         INTEGER NOT NULL,
  work_session_id INTEGER,
  path     TEXT NOT NULL,
  filename TEXT NOT NULL,
  duration_seconds REAL DEFAULT 0,
  size_bytes INTEGER DEFAULT 0,
  mtime DATETIME,
  scanned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (book_id)         REFERENCES book(id),
  FOREIGN KEY (work_session_id) REFERENCES work_session(id)
);

-- 9. Marks
CREATE TABLE mark (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  book_id INTEGER NOT NULL,
  page INTEGER NOT NULL,
  x_pct REAL NOT NULL,
  y_pct REAL NOT NULL,
  w_pct REAL NOT NULL,
  h_pct REAL NOT NULL,
  color TEXT DEFAULT '#FFFF00',
  comment TEXT,
  created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (book_id) REFERENCES book(id)
);

-- 10. Derived stats
CREATE TABLE book_stats (
  book_id INTEGER PRIMARY KEY,
  total_audio_seconds REAL DEFAULT 0,
  chars_per_hour REAL DEFAULT 0,
  pages_per_hour REAL DEFAULT 0,
  progress_pct REAL DEFAULT 0,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (book_id) REFERENCES book(id)
);

CREATE TABLE narrator_stats (
  narrator_id INTEGER PRIMARY KEY,
  books_assigned INTEGER DEFAULT 0,
  books_done INTEGER DEFAULT 0,
  total_audio_seconds REAL DEFAULT 0,
  avg_chars_per_hour REAL DEFAULT 0,
  avg_pages_per_hour REAL DEFAULT 0,
  updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (narrator_id) REFERENCES narrator(id)
);

-- 11. App settings
CREATE TABLE app_setting (
  key TEXT PRIMARY KEY,
  value TEXT
);

-- Indexes
CREATE INDEX idx_book_status     ON book(status);
CREATE INDEX idx_book_narrator   ON book(narrator_id);
CREATE INDEX idx_sched_time      ON schedule_item(start_time);
CREATE INDEX idx_sched_status    ON schedule_item(action_status, start_time);
CREATE INDEX idx_rsess_book      ON reading_session(book_id, started_at);
CREATE INDEX idx_rsess_open      ON reading_session(ended_at) WHERE ended_at IS NULL;
CREATE INDEX idx_wsess_book      ON work_session(book_id, started_at);
CREATE INDEX idx_audio_book      ON audio_file(book_id);
CREATE INDEX idx_mark_book_page  ON mark(book_id, page);

-- Schema version marker
INSERT INTO app_setting (key, value) VALUES ('schema_version', '1');

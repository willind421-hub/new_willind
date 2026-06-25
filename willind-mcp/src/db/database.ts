import Database from 'better-sqlite3'

let db: Database.Database

export function initDb(path: string = process.env.DB_PATH ?? './willind.db'): void {
  db = new Database(path)
  db.pragma('journal_mode = WAL')

  // 빈 스키마 — 자신의 MCP 도구가 쓸 테이블을 여기에 정의한다.
  //
  // 예시:
  //   db.exec(`
  //     CREATE TABLE IF NOT EXISTS my_table (
  //       id INTEGER PRIMARY KEY AUTOINCREMENT,
  //       value TEXT NOT NULL,
  //       created_at DATETIME DEFAULT CURRENT_TIMESTAMP
  //     );
  //   `)
}

export function getDb(): Database.Database {
  if (!db) throw new Error('DB가 초기화되지 않았습니다')
  return db
}

export function closeDb(): void { db?.close() }

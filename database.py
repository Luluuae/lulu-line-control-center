import re
import sqlite3


def _qmark_to_pyformat(sql):
    return sql.replace("?", "%s")


def _postgres_sql(sql):
    stripped = sql.strip()
    upper = stripped.upper()
    if upper.startswith("SELECT LAST_INSERT_ROWID()"):
        return "SELECT LASTVAL() AS id"
    if upper.startswith("INSERT OR IGNORE INTO"):
        sql = re.sub(r"(?i)^\s*INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", sql)
        sql = sql.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
    sql = re.sub(r"(?i)\bBLOB\b", "BYTEA", sql)
    sql = re.sub(r"(?i)\bREAL\b", "DOUBLE PRECISION", sql)
    return _qmark_to_pyformat(sql)


class EmptyCursor:
    description = []

    def fetchone(self):
        return None

    def fetchall(self):
        return []


class PostgresCursor:
    def __init__(self, cursor):
        self._cursor = cursor

    def execute(self, sql, params=None):
        self._cursor.execute(_postgres_sql(sql), params or ())
        return self

    def executemany(self, sql, params_seq):
        self._cursor.executemany(_postgres_sql(sql), params_seq)
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    def close(self):
        self._cursor.close()

    def __iter__(self):
        return iter(self._cursor)

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class PostgresConnection:
    def __init__(self, connection):
        self._connection = connection

    def cursor(self):
        return PostgresCursor(self._connection.cursor())

    def execute(self, sql, params=None):
        stripped = sql.strip()
        upper = stripped.upper()
        if upper.startswith("PRAGMA WAL_CHECKPOINT") or upper.startswith("PRAGMA JOURNAL_MODE"):
            return EmptyCursor()
        match = re.match(r"(?i)^PRAGMA\s+table_info\(([^)]+)\)", stripped)
        if match:
            table = match.group(1).strip().strip('"')
            return self.cursor().execute(
                "SELECT column_name AS name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name=? ORDER BY ordinal_position",
                (table,),
            )
        if "FROM SQLITE_MASTER" in upper:
            return self.cursor().execute(
                "SELECT tablename AS name FROM pg_catalog.pg_tables "
                "WHERE schemaname='public' ORDER BY tablename"
            )
        return self.cursor().execute(sql, params)

    def executemany(self, sql, params_seq):
        return self.cursor().executemany(sql, params_seq)

    def executescript(self, script):
        script = re.sub(r"(?im)^\s*PRAGMA\s+[^;]+;", "", script)
        script = re.sub(r"(?i)\bid\s+INTEGER\s+PRIMARY\s+KEY\b", "id BIGSERIAL PRIMARY KEY", script)
        script = re.sub(r"(?i)\bBLOB\b", "BYTEA", script)
        script = re.sub(r"(?i)\bREAL\b", "DOUBLE PRECISION", script)
        for statement in script.split(";"):
            if statement.strip():
                self.execute(statement)
        return self

    def commit(self):
        self._connection.commit()

    def rollback(self):
        self._connection.rollback()

    def close(self):
        self._connection.close()

    def __getattr__(self, name):
        return getattr(self._connection, name)


def connect(database_url, sqlite_path):
    if database_url:
        import psycopg
        from psycopg.rows import dict_row

        connection = psycopg.connect(database_url, row_factory=dict_row, connect_timeout=15)
        return PostgresConnection(connection)
    connection = sqlite3.connect(sqlite_path, check_same_thread=False)
    connection.row_factory = sqlite3.Row
    return connection


def is_postgres(database_url):
    return bool(database_url and database_url.startswith(("postgresql://", "postgres://")))

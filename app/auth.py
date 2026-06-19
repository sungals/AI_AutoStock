"""사용자 인증 헬퍼.

Werkzeug password hash를 사용하고, DB connection은 호출자가 주입한다.
"""
from typing import Optional

from werkzeug.security import check_password_hash, generate_password_hash


def create_user(conn, username: str, password: str, is_admin: bool = False) -> int:
    if not username or not password:
        raise ValueError('username and password are required')
    conn.execute(
        "INSERT INTO users (username, password_hash, is_admin) VALUES (?,?,?)",
        (username, generate_password_hash(password, method='pbkdf2:sha256'),
         1 if is_admin else 0))
    return int(conn.execute("SELECT last_insert_rowid() AS id").fetchone()['id'])


def get_user(conn, user_id: int) -> Optional[dict]:
    row = conn.execute(
        "SELECT id, username, is_admin FROM users WHERE id=?", (user_id,)).fetchone()
    if not row:
        return None
    return {'id': row['id'], 'username': row['username'], 'is_admin': bool(row['is_admin'])}


def verify_user(conn, username: str, password: str) -> Optional[dict]:
    row = conn.execute(
        "SELECT id, username, password_hash, is_admin FROM users WHERE username=?",
        (username,)).fetchone()
    if row and check_password_hash(row['password_hash'], password):
        return {'id': row['id'], 'username': row['username'], 'is_admin': bool(row['is_admin'])}
    return None


def change_password(conn, username: str, current_password: str,
                    new_password: str) -> bool:
    if not new_password:
        raise ValueError('new_password is required')
    user = verify_user(conn, username, current_password)
    if not user:
        return False
    conn.execute(
        "UPDATE users SET password_hash=? WHERE username=?",
        (generate_password_hash(new_password, method='pbkdf2:sha256'), username))
    return True

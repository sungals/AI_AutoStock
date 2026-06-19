"""사용자 비밀번호 변경 CLI.

사용:
    venv/bin/python change_password.py admin
"""
from getpass import getpass
import argparse
import sys

import auth
import db_core


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='사용자 비밀번호 변경')
    parser.add_argument('username')
    parser.add_argument('--db', default=None)
    args = parser.parse_args(argv)

    current = getpass('Current password: ')
    new_password = getpass('New password: ')
    confirm = getpass('Confirm new password: ')
    if new_password != confirm:
        print('password mismatch')
        return 1
    if len(new_password) < 8:
        print('new password must be at least 8 characters')
        return 1
    db_core.init_db(args.db)
    with db_core.get_connection(args.db) as conn:
        changed = auth.change_password(conn, args.username, current, new_password)
    if not changed:
        print('invalid current password')
        return 1
    print('password changed: %s' % args.username)
    return 0


if __name__ == '__main__':
    sys.exit(main())

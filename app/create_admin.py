"""초기 관리자 계정 생성 CLI.

사용:
    venv/bin/python create_admin.py admin
    # 비밀번호는 프롬프트 입력
"""
from getpass import getpass
import argparse
import sys

import auth
import db_core


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='관리자 계정 생성')
    parser.add_argument('username')
    parser.add_argument('--db', default=None)
    args = parser.parse_args(argv)

    password = getpass('Password: ')
    confirm = getpass('Confirm: ')
    if password != confirm:
        print('password mismatch')
        return 1
    db_core.init_db(args.db)
    with db_core.get_connection(args.db) as conn:
        auth.create_user(conn, args.username, password, is_admin=True)
    print('created admin: %s' % args.username)
    return 0


if __name__ == '__main__':
    sys.exit(main())

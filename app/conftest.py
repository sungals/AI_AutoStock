"""pytest 설정 — app 디렉토리(BASE_DIR)를 import 경로에 추가.

이 파일이 app/ 루트에 있으므로, 테스트에서 `import config`, `import execution_model`
등 앱 모듈을 디렉토리 구조 없이 바로 import 할 수 있다.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

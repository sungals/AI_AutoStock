# Codex Handoff

## 현재 확인 명령

```bash
cd app
venv/bin/python -m pytest tests/ -q
PORT=5001 venv/bin/python web_app.py
```

## 다음 후보 작업

- 웹 UI 화면 추가 개선: 필터, 정렬, 상세 모달.
- 운영 배포: Gunicorn/launchd, 로그 로테이션, DB 백업.
- 데이터 확장: 투자자별 수급/공시 수집기 실제 연결.

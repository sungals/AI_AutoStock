"""Phase 5: 네이버 뉴스 수집기."""
import db_core
import news_crawler


def test_parse_naver_article_strips_html_and_dates():
    item = {
        'title': '<b>삼성전자</b> 호실적 급등',
        'description': '수주 확대 &amp; 성장 기대',
        'originallink': 'https://example.com/original',
        'link': 'https://example.com/news',
        'pubDate': 'Tue, 02 Jan 2024 09:30:00 +0900',
    }
    parsed = news_crawler.parse_naver_article(item)

    assert parsed['title'] == '삼성전자 호실적 급등'
    assert parsed['summary'] == '수주 확대 & 성장 기대'
    assert parsed['url'] == 'https://example.com/original'
    assert parsed['published_at'] == '2024-01-02 09:30:00'


def test_fetch_news_without_keys_skips(tmp_path, monkeypatch):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    monkeypatch.setattr(news_crawler.config, 'NAVER_CLIENT_ID', '')
    monkeypatch.setattr(news_crawler.config, 'NAVER_CLIENT_SECRET', '')

    with db_core.get_connection(dbp) as conn:
        res = news_crawler.fetch_news_for_stock(conn, '000001', '삼성전자')

    assert res['skipped'] is True
    assert res['rows'] == 0


def test_fetch_news_upserts_articles_with_sentiment(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)

    def fake_fetch(query, display, sort):
        return [{
            'title': '수주 확대 호실적',
            'description': '성장 기대',
            'originallink': 'https://example.com/a',
            'pubDate': 'Tue, 02 Jan 2024 09:30:00 +0900',
        }]

    with db_core.get_connection(dbp) as conn:
        res = news_crawler.fetch_news_for_stock(
            conn, '000001', '테스트회사', client_id='id', client_secret='secret',
            fetch_fn=fake_fetch)
        row = conn.execute(
            "SELECT title, sentiment FROM news_articles WHERE stock_code='000001'"
        ).fetchone()

    assert res['rows'] == 1
    assert row['title'] == '수주 확대 호실적'
    assert row['sentiment'] == 'positive'


def test_fetch_all_news_stops_gracefully_on_provider_error(tmp_path, monkeypatch):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    monkeypatch.setattr(news_crawler.config, 'NAVER_CLIENT_ID', 'id')
    monkeypatch.setattr(news_crawler.config, 'NAVER_CLIENT_SECRET', 'secret')
    monkeypatch.setattr(news_crawler.config, 'NAVER_DELAY', 0)

    with db_core.get_connection(dbp) as conn:
        for code in ('000001', '000002'):
            conn.execute(
                "INSERT INTO companies (corp_code, stock_code, corp_name) VALUES (?,?,?)",
                ('C' + code, code, 'CO' + code))

        def fake_fetch(query, display, sort):
            if query == 'CO000002':
                raise RuntimeError('429 Too Many Requests')
            return [{
                'title': '호실적',
                'description': '성장',
                'originallink': 'https://example.com/%s' % query,
                'pubDate': 'Tue, 02 Jan 2024 09:30:00 +0900',
            }]

        res = news_crawler.fetch_all_news(conn, fetch_fn=fake_fetch)

    assert res['companies'] == 1
    assert res['rows'] == 1
    assert res['errors'] == 1
    assert '429' in res['error']

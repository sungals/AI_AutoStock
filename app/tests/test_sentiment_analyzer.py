"""Phase 5: 키워드 기반 뉴스/토론 감성 분석."""
import db_core
import sentiment_analyzer as sa


def test_analyze_sentiment_keyword_dictionary():
    assert sa.analyze_sentiment('호실적 성장 수주 계약 급등')[0] == 'positive'
    assert sa.analyze_sentiment('실적악화 적자 소송 급락 우려')[0] == 'negative'
    assert sa.analyze_sentiment('정기 주주총회 개최 안내')[0] == 'neutral'


def test_aggregate_and_save_sentiment_scores(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        conn.execute(
            """INSERT INTO news_articles
               (stock_code, title, published_at, sentiment, sentiment_score)
               VALUES ('000001', '호실적 급등', '2024-01-02 09:00:00', 'positive', 1.0)""")
        conn.execute(
            """INSERT INTO news_articles
               (stock_code, title, published_at, sentiment, sentiment_score)
               VALUES ('000001', '실적악화 우려', '2024-01-02 10:00:00', 'negative', -1.0)""")
        conn.execute(
            """INSERT INTO stock_discussions
               (stock_code, title, published_at, sentiment, sentiment_score)
               VALUES ('000001', '성장 기대', '2024-01-02 11:00:00', 'positive', 1.0)""")
        score = sa.aggregate_for_stock(conn, '000001', '2024-01-02')

    with db_core.get_connection(dbp) as conn:
        row = conn.execute(
            "SELECT * FROM sentiment_scores WHERE stock_code='000001' AND score_date='2024-01-02'"
        ).fetchone()

    assert score['news_pos'] == 1
    assert score['news_neg'] == 1
    assert score['disc_pos'] == 1
    assert row['news_pos'] == 1
    assert row['disc_pos'] == 1
    assert round(row['composite_score'], 4) == 0.3333


def test_analyze_and_upsert_news_article(tmp_path):
    dbp = str(tmp_path / 'q.db')
    db_core.init_db(dbp)
    with db_core.get_connection(dbp) as conn:
        sa.upsert_news_article(
            conn, '000001', '수주 확대 호실적', 'https://example.com/a',
            '2024-01-02 09:00:00', source='테스트', summary='성장 기대')
        row = conn.execute(
            "SELECT sentiment, sentiment_score FROM news_articles WHERE stock_code='000001'"
        ).fetchone()

    assert row['sentiment'] == 'positive'
    assert row['sentiment_score'] > 0

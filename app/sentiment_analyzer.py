"""키워드 기반 한국어 감성 분석 + 종목별 감성 점수 집계.

05-구현-가이드 Phase 5. ML 모델 없이 운영 가능한 사전 기반 분류를 제공한다.
Python 3.9 호환.
"""
from typing import Dict, Tuple


POSITIVE_KEYWORDS = [
    '급등', '상승', '호실적', '흑자', '성장', '최고', '돌파', '신고가',
    '매수', '긍정', '개선', '확대', '증가', '호조', '선방', '수주',
    '계약', '특허', '혁신', '흑자전환', '실적개선', '기대',
]

NEGATIVE_KEYWORDS = [
    '급락', '하락', '부진', '적자', '감소', '최저', '이탈', '신저가',
    '매도', '부정', '악화', '축소', '우려', '손실', '소송', '벌금',
    '횡령', '수사', '적자전환', '실적악화', '리콜',
]


def analyze_sentiment(text: str) -> Tuple[str, float]:
    """텍스트 감성 분류. 반환: (positive|negative|neutral, -1.0~1.0)."""
    body = text or ''
    pos_count = sum(1 for kw in POSITIVE_KEYWORDS if kw in body)
    neg_count = sum(1 for kw in NEGATIVE_KEYWORDS if kw in body)
    total = pos_count + neg_count
    if total == 0:
        return 'neutral', 0.0
    score = round(float(pos_count - neg_count) / float(total), 4)
    if score > 0.1:
        return 'positive', score
    if score < -0.1:
        return 'negative', score
    return 'neutral', score


def upsert_news_article(conn, stock_code: str, title: str, url: str,
                        published_at: str, source: str = '',
                        summary: str = '') -> None:
    """뉴스 기사 저장 시 제목+요약으로 감성까지 계산한다."""
    sentiment, score = analyze_sentiment('%s %s' % (title or '', summary or ''))
    conn.execute(
        """INSERT OR REPLACE INTO news_articles
           (stock_code, title, url, published_at, source, summary, sentiment, sentiment_score)
           VALUES (?,?,?,?,?,?,?,?)""",
        (stock_code, title, url, published_at, source, summary, sentiment, score))


def upsert_discussion(conn, stock_code: str, title: str, published_at: str,
                      views: int = 0, likes: int = 0) -> None:
    """종목 토론 게시글 저장 시 제목으로 감성까지 계산한다."""
    sentiment, score = analyze_sentiment(title or '')
    conn.execute(
        """INSERT OR REPLACE INTO stock_discussions
           (stock_code, title, views, likes, published_at, sentiment, sentiment_score)
           VALUES (?,?,?,?,?,?,?)""",
        (stock_code, title, views, likes, published_at, sentiment, score))


def _counts(rows) -> Dict[str, int]:
    out = {'positive': 0, 'negative': 0, 'neutral': 0}
    for r in rows:
        s = r['sentiment'] or 'neutral'
        if s not in out:
            s = 'neutral'
        out[s] += 1
    return out


def aggregate_for_stock(conn, stock_code: str, score_date: str) -> Dict:
    """해당 일자의 뉴스+토론 감성을 집계해 sentiment_scores에 저장한다."""
    news = conn.execute(
        """SELECT sentiment, sentiment_score FROM news_articles
           WHERE stock_code=? AND substr(published_at, 1, 10)=?""",
        (stock_code, score_date)).fetchall()
    disc = conn.execute(
        """SELECT sentiment, sentiment_score FROM stock_discussions
           WHERE stock_code=? AND substr(published_at, 1, 10)=?""",
        (stock_code, score_date)).fetchall()
    news_counts = _counts(news)
    disc_counts = _counts(disc)
    scores = [r['sentiment_score'] for r in list(news) + list(disc)
              if r['sentiment_score'] is not None]
    composite = round(sum(scores) / len(scores), 4) if scores else 0.0
    result = {
        'stock_code': stock_code,
        'score_date': score_date,
        'news_pos': news_counts['positive'],
        'news_neg': news_counts['negative'],
        'news_neu': news_counts['neutral'],
        'disc_pos': disc_counts['positive'],
        'disc_neg': disc_counts['negative'],
        'disc_neu': disc_counts['neutral'],
        'composite_score': composite,
    }
    conn.execute(
        """INSERT OR REPLACE INTO sentiment_scores
           (stock_code, score_date, news_pos, news_neg, news_neu,
            disc_pos, disc_neg, disc_neu, composite_score)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (stock_code, score_date, result['news_pos'], result['news_neg'], result['news_neu'],
         result['disc_pos'], result['disc_neg'], result['disc_neu'], composite))
    return result


def aggregate_all(conn, score_date: str) -> Dict[str, Dict]:
    """companies 전체 종목의 일자별 감성 집계."""
    rows = conn.execute("SELECT stock_code FROM companies ORDER BY stock_code").fetchall()
    return {r['stock_code']: aggregate_for_stock(conn, r['stock_code'], score_date)
            for r in rows}

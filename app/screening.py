"""일일 스크리닝 — 전략별 점수를 screening_results에 저장.

value/turnaround는 PIT 펀더멘털 점수(backtester 채점 재사용), momentum은 추세 수익률.
모두 screen_date 시점 기준(미래참조 없음).
03-시스템-아키텍처.md §8, 05-구현-가이드.md Phase 4. Python 3.9 호환.
"""
from typing import Dict, List, Optional
import json
import point_in_time
import backtester as bt


def _trailing_return(conn, stock_code: str, as_of: str,
                     lookback_days: int = 20) -> Optional[float]:
    rows = conn.execute(
        """SELECT close FROM price_data
           WHERE stock_code = ? AND trade_date <= ?
           ORDER BY trade_date DESC LIMIT ?""",
        (stock_code, as_of, lookback_days + 1)).fetchall()
    if len(rows) < 2:
        return None
    now = rows[0]['close']
    past = rows[-1]['close']
    if not now or not past or past <= 0:
        return None
    return (now - past) / past


def _save(conn, corp_code: str, stock_code: str, strategy: str,
          score: float, signals: List[str], screen_date: str) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO screening_results
           (corp_code, stock_code, strategy, score, signals, screen_date)
           VALUES (?,?,?,?,?,?)""",
        (corp_code, stock_code, strategy, score,
         json.dumps(signals, ensure_ascii=False), screen_date))


def _value_signals(m: Dict) -> List[str]:
    s = []
    if m.get('per') is not None and 0 < m['per'] < 10:
        s.append('저PER %.1f' % m['per'])
    if m.get('pbr') is not None and 0 < m['pbr'] < 1.5:
        s.append('저PBR %.2f' % m['pbr'])
    if m.get('roe') is not None and m['roe'] > 10:
        s.append('고ROE %.1f%%' % m['roe'])
    return s


def _turnaround_signals(m: Dict) -> List[str]:
    s = []
    if m.get('opincome_turnaround') == 1:
        s.append('영업이익 흑자전환')
    if m.get('revenue_growth_yoy') is not None and m['revenue_growth_yoy'] > 20:
        s.append('매출 +%.0f%%' % m['revenue_growth_yoy'])
    return s


def _technical_signals(conn, stock_code: str, screen_date: str) -> Dict:
    rows = conn.execute(
        """SELECT signal_name, signal_value, signal_label
           FROM technical_signals
           WHERE stock_code = ? AND calc_date <= ?
           ORDER BY calc_date DESC""",
        (stock_code, screen_date)).fetchall()
    out = {}
    for r in rows:
        if r['signal_name'] not in out:
            out[r['signal_name']] = {
                'value': r['signal_value'],
                'label': r['signal_label'] or '',
            }
    return out


def _score_trend(t: Dict) -> Optional[float]:
    score = 0.0
    if t.get('ma_cross', {}).get('value') == 1:
        score += 20
    if '골든' in t.get('macd', {}).get('label', ''):
        score += 20
    ma5 = t.get('ma_5', {}).get('value')
    ma20 = t.get('ma_20', {}).get('value')
    ma60 = t.get('ma_60', {}).get('value')
    if ma5 is not None and ma20 is not None and ma5 > ma20:
        score += 15
    if ma20 is not None and ma60 is not None and ma20 > ma60:
        score += 15
    return score if score >= 30 else None


def _trend_signals(t: Dict) -> List[str]:
    s = []
    for name in ('ma_cross', 'macd'):
        label = t.get(name, {}).get('label')
        if label:
            s.append(label)
    ma5 = t.get('ma_5', {}).get('value')
    ma20 = t.get('ma_20', {}).get('value')
    ma60 = t.get('ma_60', {}).get('value')
    if ma5 is not None and ma20 is not None and ma5 > ma20:
        s.append('MA5 > MA20')
    if ma20 is not None and ma60 is not None and ma20 > ma60:
        s.append('MA20 > MA60')
    return s


def _score_mean_revert(t: Dict) -> Optional[float]:
    score = 0.0
    rsi = t.get('rsi_14', {}).get('value')
    if rsi is not None and rsi <= 30:
        score += 20
    if '하단 이탈' in t.get('bollinger', {}).get('label', ''):
        score += 20
    if t.get('hammer') or t.get('bullish_engulfing') or t.get('doji'):
        score += 10
    return score if score >= 30 else None


def _mean_revert_signals(t: Dict) -> List[str]:
    s = []
    for name in ('rsi_14', 'bollinger', 'hammer', 'bullish_engulfing', 'doji'):
        label = t.get(name, {}).get('label')
        if label:
            s.append(label)
    return s


def _volatility_score(conn, stock_code: str, screen_date: str) -> Optional[float]:
    rows = conn.execute(
        """SELECT high, low FROM price_data
           WHERE stock_code = ? AND trade_date <= ?
           ORDER BY trade_date DESC LIMIT 21""",
        (stock_code, screen_date)).fetchall()
    if len(rows) < 6:
        return None
    ranges = [abs((r['high'] or 0) - (r['low'] or 0)) for r in rows]
    current = float(ranges[0])
    prev = [float(x) for x in ranges[1:] if x is not None]
    avg = sum(prev) / len(prev) if prev else 0.0
    if avg <= 0:
        return None
    ratio = current / avg
    if ratio >= 1.5:
        return min(100.0, ratio * 30.0)
    return None


def _sector_score(conn, stock_code: str, sector: Optional[str], screen_date: str) -> Optional[float]:
    if not sector:
        return None
    peers = conn.execute(
        "SELECT stock_code FROM companies WHERE sector=?",
        (sector,)).fetchall()
    winners = 0
    for p in peers:
        ret = _trailing_return(conn, p['stock_code'], screen_date, 20)
        if ret is not None and ret > 0.05:
            winners += 1
    own_ret = _trailing_return(conn, stock_code, screen_date, 20)
    if winners >= 2 and own_ret is not None and own_ret > 0:
        return min(100.0, 20.0 + winners * 10.0 + own_ret * 100.0)
    return None


def _event_score(conn, stock_code: str, screen_date: str) -> Optional[float]:
    from datetime import date, timedelta
    start = (date.fromisoformat(screen_date) - timedelta(days=7)).strftime('%Y%m%d')
    end = screen_date.replace('-', '')
    disc = conn.execute(
        """SELECT report_nm, disclosure_type FROM dart_disclosures
           WHERE stock_code=? AND rcept_dt BETWEEN ? AND ?
           ORDER BY rcept_dt DESC LIMIT 1""",
        (stock_code, start, end)).fetchone()
    if not disc:
        return None
    sent = conn.execute(
        """SELECT composite_score FROM sentiment_scores
           WHERE stock_code=? AND score_date<=?
           ORDER BY score_date DESC LIMIT 1""",
        (stock_code, screen_date)).fetchone()
    sentiment_score = sent['composite_score'] if sent and sent['composite_score'] is not None else 0.0
    positive_text = '%s %s' % (disc['report_nm'] or '', disc['disclosure_type'] or '')
    if sentiment_score > 0 or any(k in positive_text for k in ('계약', '수주', '공급', 'positive')):
        return min(100.0, 30.0 + max(0.0, float(sentiment_score)) * 40.0)
    return None


def _flow_score(conn, stock_code: str, screen_date: str) -> Optional[float]:
    rows = conn.execute(
        """SELECT inst_net_buy, foreign_net_buy FROM investor_trading
           WHERE stock_code=? AND trade_date<=?
           ORDER BY trade_date DESC LIMIT 3""",
        (stock_code, screen_date)).fetchall()
    if len(rows) < 3:
        return None
    combined = [(r['inst_net_buy'] or 0) + (r['foreign_net_buy'] or 0) for r in rows]
    if all(v > 0 for v in combined):
        avg = sum(combined) / len(combined)
        return min(100.0, 30.0 + avg / 1_000_000.0)
    return None


def _quality_lowvol_score(conn, stock_code: str, metrics: Dict, screen_date: str) -> Optional[float]:
    roe = metrics.get('roe')
    if roe is None or roe <= 10:
        return None
    rows = conn.execute(
        """SELECT close FROM price_data
           WHERE stock_code=? AND trade_date<=?
           ORDER BY trade_date DESC LIMIT 21""",
        (stock_code, screen_date)).fetchall()
    if len(rows) < 10:
        return None
    closes = [float(r['close']) for r in rows if r['close']]
    rets = []
    for i in range(1, len(closes)):
        if closes[i] > 0:
            rets.append(abs(closes[i - 1] / closes[i] - 1.0))
    avg_abs_ret = sum(rets) / len(rets) if rets else 1.0
    if avg_abs_ret < 0.03:
        return min(100.0, 40.0 + float(roe))
    return None


def _guru_score(conn, corp_code: str, stock_code: str, metrics: Dict, screen_date: str) -> Optional[float]:
    row = conn.execute(
        """SELECT metric_value FROM calculated_metrics
           WHERE stock_code=? AND metric_name='guru_score' AND calc_date<=?
           ORDER BY calc_date DESC LIMIT 1""",
        (stock_code, screen_date)).fetchone()
    if row and row['metric_value'] is not None and row['metric_value'] >= 60:
        return float(row['metric_value'])
    per = metrics.get('per')
    pbr = metrics.get('pbr')
    roe = metrics.get('roe')
    debt = metrics.get('debt_ratio')
    score = 0.0
    if per is not None and 0 < per < 15:
        score += 25
    if pbr is not None and 0 < pbr < 2:
        score += 20
    if roe is not None and roe > 12:
        score += 25
    if debt is not None and debt < 100:
        score += 20
    return score if score >= 60 else None


def run_all_screens(conn, screen_date: str, lookback_days: int = 20) -> Dict[str, int]:
    """모든 전략 스크리닝 실행 및 저장. 반환: 전략별 선정 종목 수."""
    conn.execute("DELETE FROM screening_results WHERE screen_date = ?", (screen_date,))
    companies = conn.execute(
        "SELECT corp_code, stock_code, sector FROM companies").fetchall()
    counts = {
        'value': 0, 'turnaround': 0, 'momentum': 0,
        'trend': 0, 'mean_revert': 0, 'volatility': 0,
        'sector': 0, 'event': 0, 'flow': 0, 'quality_lowvol': 0, 'guru': 0,
    }

    for c in companies:
        corp, code = c['corp_code'], c['stock_code']
        m = point_in_time.get_metrics_asof(conn, corp, screen_date, stock_code=code)

        sv = bt._score_value(m)
        if sv is not None:
            _save(conn, corp, code, 'value', sv, _value_signals(m), screen_date)
            counts['value'] += 1

        st = bt._score_turnaround(m)
        if st is not None:
            _save(conn, corp, code, 'turnaround', st, _turnaround_signals(m), screen_date)
            counts['turnaround'] += 1

        ret = _trailing_return(conn, code, screen_date, lookback_days)
        if ret is not None and ret > 0:
            score = min(100.0, ret * 200.0)
            _save(conn, corp, code, 'momentum', round(score, 2),
                  ['모멘텀 %.1f%%' % (ret * 100)], screen_date)
            counts['momentum'] += 1

        tech = _technical_signals(conn, code, screen_date)
        trend_score = _score_trend(tech)
        if trend_score is not None:
            _save(conn, corp, code, 'trend', round(trend_score, 2),
                  _trend_signals(tech), screen_date)
            counts['trend'] += 1

        mean_score = _score_mean_revert(tech)
        if mean_score is not None:
            _save(conn, corp, code, 'mean_revert', round(mean_score, 2),
                  _mean_revert_signals(tech), screen_date)
            counts['mean_revert'] += 1

        vol_score = _volatility_score(conn, code, screen_date)
        if vol_score is not None:
            _save(conn, corp, code, 'volatility', round(vol_score, 2),
                  ['ATR 급증 %.1fx' % (vol_score / 30.0)], screen_date)
            counts['volatility'] += 1

        sector_score = _sector_score(conn, code, c['sector'], screen_date)
        if sector_score is not None:
            _save(conn, corp, code, 'sector', round(sector_score, 2),
                  ['%s 업종 동반 상승' % c['sector']], screen_date)
            counts['sector'] += 1

        event_score = _event_score(conn, code, screen_date)
        if event_score is not None:
            _save(conn, corp, code, 'event', round(event_score, 2),
                  ['최근 긍정 공시/뉴스'], screen_date)
            counts['event'] += 1

        flow_score = _flow_score(conn, code, screen_date)
        if flow_score is not None:
            _save(conn, corp, code, 'flow', round(flow_score, 2),
                  ['기관+외국인 3일 연속 순매수'], screen_date)
            counts['flow'] += 1

        quality_score = _quality_lowvol_score(conn, code, m, screen_date)
        if quality_score is not None:
            _save(conn, corp, code, 'quality_lowvol', round(quality_score, 2),
                  ['고ROE 저변동성'], screen_date)
            counts['quality_lowvol'] += 1

        guru_score = _guru_score(conn, corp, code, m, screen_date)
        if guru_score is not None:
            _save(conn, corp, code, 'guru', round(guru_score, 2),
                  ['Guru score %.0f' % guru_score], screen_date)
            counts['guru'] += 1

    return counts

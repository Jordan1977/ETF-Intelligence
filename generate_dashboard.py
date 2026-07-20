from __future__ import annotations

import html, math, time, os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import yfinance as yf

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'data'
CACHE = DATA / 'cache'
OUTPUT = ROOT / 'docs' / 'index.html'
TRADING_DAYS = 252

THRESHOLDS = {
    'max_ter': 0.0040,
    'min_aum_eur': 100_000_000,
    'max_tracking_error': 0.0100,
    'max_negative_tracking_difference': -0.0100,
    'min_history_days': 126,
    'max_metadata_age_days': 180,
}

MARKETS = {
    'MSCI World proxy': 'URTH',
    'S&P 500': '^GSPC',
    'Nasdaq-100': '^NDX',
    'Euro Stoxx 50': '^STOXX50E',
    'EUR/USD': 'EURUSD=X',
    'Gold': 'GC=F',
}


def log(msg):
    print(f'[ETF Intelligence] {msg}', flush=True)


def load_csv(name):
    return pd.read_csv(DATA / name)


def clean_download(raw, ticker):
    if raw is None or raw.empty:
        return pd.Series(dtype=float, name=ticker)
    if isinstance(raw.columns, pd.MultiIndex):
        for field in ('Adj Close', 'Close'):
            cols = [c for c in raw.columns if c[0] == field]
            if cols:
                s = raw[cols[0]].dropna().astype(float)
                s.name = ticker
                return s
    for field in ('Adj Close', 'Close'):
        if field in raw.columns:
            s = raw[field].dropna().astype(float)
            s.name = ticker
            return s
    return pd.Series(dtype=float, name=ticker)


def get_price(ticker, retries=1):
    CACHE.mkdir(exist_ok=True)
    if os.getenv('ETF_OFFLINE') == '1':
        log(f'{ticker}: offline test mode')
        return pd.Series(dtype=float, name=ticker)
    safe = ticker.replace('^', '_').replace('=', '_').replace('/', '_')
    cache = CACHE / f'{safe}.csv'
    for attempt in range(retries):
        try:
            raw = yf.download(ticker, period='3y', interval='1d', auto_adjust=False,
                              progress=False, threads=False, timeout=15)
            s = clean_download(raw, ticker)
            if not s.empty:
                pd.DataFrame({'date': s.index, 'price': s.values}).to_csv(cache, index=False)
                log(f'{ticker}: {len(s)} observations downloaded')
                return s
        except Exception as exc:
            log(f'{ticker}: download attempt {attempt + 1} failed: {exc}')
        time.sleep(1)
    if cache.exists():
        try:
            df = pd.read_csv(cache, parse_dates=['date'])
            s = df.set_index('date')['price'].dropna().astype(float)
            s.name = ticker
            log(f'{ticker}: using cached data')
            return s
        except Exception as exc:
            log(f'{ticker}: cache error: {exc}')
    log(f'{ticker}: unavailable; continuing without market metrics')
    return pd.Series(dtype=float, name=ticker)


def total_return(s):
    s = s.dropna()
    return np.nan if len(s) < 2 else s.iloc[-1] / s.iloc[0] - 1


def period_return(s, days):
    s = s.dropna()
    if len(s) < 2:
        return np.nan
    cut = s.index[-1] - pd.Timedelta(days=days)
    return total_return(s[s.index >= cut])


def ytd_return(s):
    s = s.dropna()
    if len(s) < 2:
        return np.nan
    return total_return(s[s.index.year == s.index[-1].year])


def annual_return(s):
    s = s.dropna()
    if len(s) < 2:
        return np.nan
    years = (s.index[-1] - s.index[0]).days / 365.25
    return np.nan if years <= 0 else (s.iloc[-1] / s.iloc[0]) ** (1 / years) - 1


def volatility(s):
    r = s.pct_change().dropna()
    return np.nan if len(r) < 2 else r.std(ddof=1) * math.sqrt(TRADING_DAYS)


def max_drawdown(s):
    s = s.dropna()
    return np.nan if len(s) < 2 else (s / s.cummax() - 1).min()


def tracking(etf, benchmark):
    j = pd.concat([etf.rename('etf'), benchmark.rename('bench')], axis=1).dropna()
    if len(j) < THRESHOLDS['min_history_days']:
        return np.nan, np.nan
    active = j.etf.pct_change() - j.bench.pct_change()
    te = active.dropna().std(ddof=1) * math.sqrt(TRADING_DAYS)
    td = annual_return(j.etf) - annual_return(j.bench)
    return te, td


def build_metrics(meta, prices):
    rows = []
    for _, r in meta.iterrows():
        s = prices.get(str(r.ticker), pd.Series(dtype=float))
        b = prices.get(str(r.benchmark_ticker), pd.Series(dtype=float))
        te, td = tracking(s, b) if not s.empty and not b.empty else (np.nan, np.nan)
        rows.append({**r.to_dict(), 'return_1m': period_return(s, 31),
                     'return_ytd': ytd_return(s), 'return_1y': period_return(s, 365),
                     'volatility': volatility(s), 'max_drawdown': max_drawdown(s),
                     'tracking_error': te, 'tracking_difference': td,
                     'history_days': len(s)})
    return pd.DataFrame(rows)


def pct(x):
    return 'N/A' if pd.isna(x) else f'{x * 100:.2f}%'


def eur(x):
    if pd.isna(x): return 'N/A'
    if x >= 1e9: return f'€{x / 1e9:.2f}bn'
    if x >= 1e6: return f'€{x / 1e6:.0f}m'
    return f'€{x:,.0f}'


def score_metrics(df):
    df = df.copy()
    scores, strengths, watch = [], [], []
    for _, r in df.iterrows():
        peers = df[df.category == r.category]
        parts = []
        if pd.notna(r.ter) and peers.ter.notna().any():
            parts.append((1 - (peers.ter.dropna() <= r.ter).mean(), 25))
        if pd.notna(r.tracking_error) and peers.tracking_error.notna().any():
            parts.append((1 - (peers.tracking_error.dropna() <= r.tracking_error).mean(), 25))
        if pd.notna(r.tracking_difference) and peers.tracking_difference.notna().any():
            vals = peers.tracking_difference.abs().dropna()
            parts.append((1 - (vals <= abs(r.tracking_difference)).mean(), 20))
        if pd.notna(r.aum_eur) and peers.aum_eur.notna().any():
            parts.append(((peers.aum_eur.dropna() <= r.aum_eur).mean(), 20))
        parts.append((min(r.history_days / 756, 1), 10))
        score = sum(v*w for v,w in parts) / sum(w for _,w in parts) * 100 if parts else np.nan
        scores.append(score)
        s, w = [], []
        if pd.notna(r.ter) and r.ter <= peers.ter.median(skipna=True): s.append('Competitive TER in peer group')
        if r.history_days >= 504: s.append('Sufficient monitoring history')
        if pd.notna(r.tracking_error) and r.tracking_error <= THRESHOLDS['max_tracking_error']: s.append('Contained tracking error')
        if pd.isna(r.aum_eur): w.append('AUM requires manual verification')
        if pd.isna(r.tracking_error): w.append('Tracking error unavailable')
        strengths.append('; '.join(s) or 'No material strength identified from available data')
        watch.append('; '.join(w) or 'No major issue under illustrative rules')
    df['selection_score'] = scores
    df['strengths'] = strengths
    df['watchpoints'] = watch
    return df


def alerts(df):
    out = []
    def add(r, indicator, value, threshold, status, comment):
        out.append({'ETF': r.ticker, 'Category': r.category, 'Indicator': indicator,
                    'Observed': value, 'Threshold': threshold, 'Status': status, 'Comment': comment})
    today = datetime.now(timezone.utc).date()
    for _, r in df.iterrows():
        add(r, 'TER', r.ter, THRESHOLDS['max_ter'], 'Alert' if pd.notna(r.ter) and r.ter > THRESHOLDS['max_ter'] else ('Watch' if pd.isna(r.ter) else 'Compliant'), 'Illustrative TER ceiling')
        add(r, 'AUM', r.aum_eur, THRESHOLDS['min_aum_eur'], 'Alert' if pd.notna(r.aum_eur) and r.aum_eur < THRESHOLDS['min_aum_eur'] else ('Watch' if pd.isna(r.aum_eur) else 'Compliant'), 'Illustrative minimum fund size')
        add(r, 'Tracking error', r.tracking_error, THRESHOLDS['max_tracking_error'], 'Alert' if pd.notna(r.tracking_error) and r.tracking_error > THRESHOLDS['max_tracking_error'] else ('Watch' if pd.isna(r.tracking_error) else 'Compliant'), 'Annualised active-return volatility')
        add(r, 'Tracking difference', r.tracking_difference, THRESHOLDS['max_negative_tracking_difference'], 'Alert' if pd.notna(r.tracking_difference) and r.tracking_difference < THRESHOLDS['max_negative_tracking_difference'] else ('Watch' if pd.isna(r.tracking_difference) else 'Compliant'), 'ETF annual return minus benchmark')
        try:
            age = (today - pd.to_datetime(r.last_verified).date()).days
            add(r, 'Metadata age', age, THRESHOLDS['max_metadata_age_days'], 'Alert' if age > THRESHOLDS['max_metadata_age_days'] else 'Compliant', 'Manual data freshness')
        except Exception:
            add(r, 'Metadata age', np.nan, THRESHOLDS['max_metadata_age_days'], 'Watch', 'Missing verification date')
    return pd.DataFrame(out)


def make_chart(df, prices, drawdown=False):
    fig = go.Figure()
    for _, r in df.iterrows():
        s = prices.get(str(r.ticker), pd.Series(dtype=float)).dropna()
        if len(s) < 2: continue
        y = (s / s.cummax() - 1) * 100 if drawdown else s / s.iloc[0] * 100
        fig.add_trace(go.Scatter(x=y.index, y=y, mode='lines', name=r.ticker))
    if not fig.data:
        return '<div class="empty">Market data unavailable during this generation.</div>'
    fig.update_layout(template='plotly_white', height=420, margin=dict(l=35,r=20,t=40,b=35),
                      title='Drawdown (%)' if drawdown else 'ETF performance — base 100',
                      hovermode='x unified', legend=dict(orientation='h', y=-0.2))
    return fig.to_html(full_html=False, include_plotlyjs='cdn' if not drawdown else False)


def table(df, columns, fmts=None, table_id=''):
    fmts = fmts or {}
    h = ''.join(f'<th>{html.escape(c)}</th>' for c in columns)
    rows = []
    for _, r in df.iterrows():
        cells = []
        for c in columns:
            v = r.get(c, '')
            if c in fmts: v = fmts[c](v)
            elif not isinstance(v, str) and pd.isna(v): v = 'N/A'
            cells.append(f'<td>{html.escape(str(v))}</td>')
        rows.append('<tr>' + ''.join(cells) + '</tr>')
    return f'<div class="table-wrap"><table id="{table_id}"><thead><tr>{h}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def generate(meta, metrics, alert_df, competitors, prices):
    now = datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')
    alert_count = int((alert_df.Status == 'Alert').sum())
    watch_count = int((alert_df.Status == 'Watch').sum())
    best = metrics.sort_values('selection_score', ascending=False).iloc[0] if metrics.selection_score.notna().any() else None

    cards = [('ETFs monitored', len(metrics)), ('Alerts', alert_count), ('Watch items', watch_count),
             ('Best illustrative score', f'{best.ticker} — {best.selection_score:.0f}/100' if best is not None else 'N/A')]
    cards_html = ''.join(f'<div class="card"><span>{k}</span><strong>{v}</strong></div>' for k,v in cards)

    comp = metrics.rename(columns={'ter':'TER','aum_eur':'AUM','return_1y':'1Y performance','max_drawdown':'Max drawdown','tracking_error':'Tracking error','tracking_difference':'Tracking difference','selection_score':'Score'})
    comp_cols = ['ticker','name','category','benchmark_name','TER','AUM','replication','sfdr','1Y performance','volatility','Max drawdown','Tracking error','Tracking difference','Score']
    comp_table = table(comp, comp_cols, {'TER':pct,'AUM':eur,'1Y performance':pct,'volatility':pct,'Max drawdown':pct,'Tracking error':pct,'Tracking difference':pct,'Score':lambda x:'N/A' if pd.isna(x) else f'{x:.0f}/100'})
    score_table = table(metrics.sort_values(['category','selection_score'], ascending=[True,False]), ['ticker','category','selection_score','strengths','watchpoints'], {'selection_score':lambda x:'N/A' if pd.isna(x) else f'{x:.0f}/100'})
    alert_order = {'Alert':0,'Watch':1,'Compliant':2}
    ad = alert_df.assign(_o=alert_df.Status.map(alert_order)).sort_values(['_o','ETF']).drop(columns='_o')
    alert_table = table(ad, ['ETF','Category','Indicator','Observed','Threshold','Status','Comment'], {'Observed':lambda x:'N/A' if pd.isna(x) else f'{x:,.4f}','Threshold':lambda x:f'{x:,.4f}'})

    market_rows = []
    for name,ticker in MARKETS.items():
        s = prices.get(ticker, pd.Series(dtype=float))
        market_rows.append({'Market':name,'Ticker':ticker,'1M':period_return(s,31),'YTD':ytd_return(s),'Volatility':volatility(s),'Last date':s.index[-1].date().isoformat() if not s.empty else ''})
    market_table = table(pd.DataFrame(market_rows), ['Market','Ticker','1M','YTD','Volatility','Last date'], {'1M':pct,'YTD':pct,'Volatility':pct})

    competitor_cols = ['company','product','wrapper','maximum_total_fees','minimum_investment','management_type','investment_universe','etf_based','esg_positioning','private_assets','key_strength','key_watchpoint','last_verified']
    competitor_table = table(competitors, competitor_cols)

    source_items = ''.join(f'<li><a href="{html.escape(str(r.source_url))}" target="_blank">{html.escape(str(r.name))}</a> — verified {html.escape(str(r.last_verified))}</li>' for _,r in meta.iterrows())
    competitor_sources = ''.join(f'<li><a href="{html.escape(str(r.source_url))}" target="_blank">{html.escape(str(r.company))}</a> — verified {html.escape(str(r.last_verified))}</li>' for _,r in competitors.iterrows())

    css = '''
    :root{--ink:#172235;--muted:#6d7788;--line:#e3e8ef;--bg:#f4f6f9;--panel:#fff;--accent:#244f78;--soft:#edf3f8}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;font-family:Inter,system-ui,-apple-system,Segoe UI,Arial;background:var(--bg);color:var(--ink);line-height:1.5}nav{position:sticky;top:0;z-index:5;background:#fffffff2;border-bottom:1px solid var(--line);padding:12px 5%;display:flex;gap:22px;overflow:auto}nav a{text-decoration:none;color:var(--ink);font-size:14px;white-space:nowrap}header{padding:60px 6% 44px;background:linear-gradient(135deg,#17283d,#2b5277);color:white}header h1{font-size:clamp(36px,5vw,64px);letter-spacing:-.04em;margin:0}header p{font-size:18px;color:#dce7f0;max-width:800px}main{max-width:1450px;margin:auto;padding:28px 4% 80px}section{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:26px;margin:22px 0;box-shadow:0 8px 28px #18283a0a}h2{font-size:28px;margin:0 0 6px}.sub{color:var(--muted)}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:14px}.card{background:var(--soft);border-radius:12px;padding:18px}.card span{display:block;color:var(--muted);font-size:13px}.card strong{font-size:21px;display:block;margin-top:5px}.notice{background:#edf4fa;border-left:4px solid var(--accent);padding:15px;border-radius:7px;margin:18px 0}.table-wrap{overflow:auto;border:1px solid var(--line);border-radius:10px;margin:16px 0}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:11px 12px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}th{background:#edf2f6}.two{display:grid;grid-template-columns:1fr 1fr;gap:18px}.empty{padding:40px;text-align:center;color:var(--muted);border:1px dashed var(--line);border-radius:10px}a{color:var(--accent)}footer{text-align:center;color:var(--muted);padding:35px}@media(max-width:900px){.two{grid-template-columns:1fr}main{padding:16px 3% 60px}section{padding:18px}}
    '''

    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>ETF Intelligence Platform</title><style>{css}</style></head><body>
<nav><a href="#overview">Overview</a><a href="#comparator">ETF Comparator</a><a href="#score">Selection Score</a><a href="#alerts">Alerts</a><a href="#markets">Markets</a><a href="#competitors">Competitors</a><a href="#methodology">Methodology</a></nav>
<header><h1>ETF Intelligence Platform</h1><p>ETF Selection, Monitoring & Competitor Intelligence — a public-data prototype by Jordan Scouarnec.</p></header><main>
<section id="overview"><h2>Executive Overview</h2><p class="sub">Last generated: {now}</p><div class="notice"><strong>Why this project?</strong><br>This prototype explores how public data can support ETF selection committees, ongoing monitoring and competitor intelligence. It does not reproduce Yomoni's internal tools, allocations or criteria.</div><div class="cards">{cards_html}</div></section>
<section id="comparator"><h2>ETF Comparator</h2><p class="sub">Compare ETFs inside coherent peer groups. Missing public data remain explicitly unavailable.</p>{comp_table}<div class="two"><div>{make_chart(metrics,prices)}</div><div>{make_chart(metrics,prices,True)}</div></div></section>
<section id="score"><h2>ETF Selection Score</h2><p class="sub">Transparent illustrative scoring, normalised within category.</p>{score_table}</section>
<section id="alerts"><h2>ETF Monitoring & Alerts</h2><p class="sub">Thresholds are pedagogical and editable in the Python script.</p>{alert_table}</section>
<section id="markets"><h2>Market Environment</h2><p class="sub">Concise context rather than a trading terminal.</p>{market_table}</section>
<section id="competitors"><h2>Competitor Monitor</h2><p class="sub">Public, dated product information. Non-comparable performance is deliberately excluded.</p>{competitor_table}<h3>What should an asset manager monitor?</h3><p>Fee changes · product launches · new wrappers · investment-universe changes · ESG positioning · published performance methodology · partnerships · public AUM.</p></section>
<section id="methodology"><h2>Methodology & Limitations</h2><ul><li>Volatility: daily standard deviation × √252.</li><li>Maximum drawdown: worst decline from a previous peak.</li><li>Tracking error: annualised standard deviation of ETF minus benchmark daily returns.</li><li>Tracking difference: ETF annualised return minus benchmark annualised return.</li><li>Yahoo Finance is not an institutional data source and may be delayed or unavailable.</li><li>TER, AUM, replication, SFDR and competitor information require manual verification.</li><li>No investment recommendation is provided.</li></ul><h3>ETF sources</h3><ul>{source_items}</ul><h3>Competitor sources</h3><ul>{competitor_sources}</ul></section>
</main><footer>Prototype for educational and interview purposes — public data only.</footer></body></html>'''


def main():
    meta = load_csv('etf_metadata.csv')
    meta['ter'] = pd.to_numeric(meta.ter, errors='coerce')
    meta['aum_eur'] = pd.to_numeric(meta.aum_eur, errors='coerce')
    competitors = load_csv('competitors.csv')
    tickers = set(meta.ticker.dropna().astype(str)) | set(meta.benchmark_ticker.dropna().astype(str)) | set(MARKETS.values())
    prices = {t:get_price(t) for t in sorted(tickers)}
    metrics = score_metrics(build_metrics(meta, prices))
    alert_df = alerts(metrics)
    page = generate(meta, metrics, alert_df, competitors, prices)
    OUTPUT.parent.mkdir(exist_ok=True)
    temp = OUTPUT.with_suffix('.tmp')
    temp.write_text(page, encoding='utf-8')
    if temp.stat().st_size < 10000:
        raise RuntimeError('Generated dashboard is unexpectedly small; previous HTML preserved.')
    temp.replace(OUTPUT)
    log(f'Generated {OUTPUT} ({OUTPUT.stat().st_size:,} bytes)')


if __name__ == '__main__':
    main()

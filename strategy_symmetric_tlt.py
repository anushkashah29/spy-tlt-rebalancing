import pandas as pd
import numpy as np
import yfinance as yf
from scipy import stats

# =============================================================================
# STRATEGY: SYMMETRIC TLT-DOMINANT MEAN REVERSION
# =============================================================================
# Mirror of spy_tlt_rebalancing.py but with the roles reversed.
#
# Hypothesis: When TLT outperforms SPY by more than 5% during the main window
# (first to second-to-last trading day), pension/insurance rebalancing pressure
# pushes SPY back up (and TLT down) on the final trading day of the month.
#
# Signal:  TLT beat SPY by >5% in the main window
# Trade:   Long $2M SPY / Short $1M TLT on the last trading day
# Entry:   Close of second-to-last trading day
# Exit:    Close of last trading day
# Holding: 1 day
#
# Data source: spy_tlt_closes.csv (produced by spy_tlt_rebalancing.py).
#              If the file is missing, data is re-fetched via yfinance.
# =============================================================================

LONG_SIZE        = 2_000_000   # $2M long SPY
SHORT_SIZE       = 1_000_000   # $1M short TLT
START_DATE       = "2016-04-01"
END_DATE         = "2026-04-01"
SPREAD_THRESHOLD = 0.05        # TLT must beat SPY by >5% in the main window

# =============================================================================
# SECTION 1: LOAD DATA
# =============================================================================
try:
    df = pd.read_csv('spy_tlt_closes.csv')
    if df.columns[0] != 'Date':
        df = pd.read_csv('spy_tlt_closes.csv', header=[0, 1])
        df.columns = ['Date', 'SPY', 'TLT']
    print("Loaded data from spy_tlt_closes.csv")
except FileNotFoundError:
    print(f"spy_tlt_closes.csv not found — fetching from yfinance ({START_DATE} to {END_DATE})...")
    data = yf.download(["SPY", "TLT"], start=START_DATE, end=END_DATE, auto_adjust=True)
    df = data["Close"][["SPY", "TLT"]].copy()
    df.index.name = "Date"
    df = df.reset_index()
    df.to_csv("spy_tlt_closes.csv", index=False)
    print(f"Saved {len(df)} rows to spy_tlt_closes.csv")

df['Date'] = pd.to_datetime(df['Date'])
df['SPY']  = pd.to_numeric(df['SPY'], errors='coerce')
df['TLT']  = pd.to_numeric(df['TLT'], errors='coerce')
df = df.dropna().sort_values('Date').reset_index(drop=True)

print(f"Total trading days: {len(df)}")
print(f"Date range:         {df['Date'].min().date()} to {df['Date'].max().date()}")
print()

# =============================================================================
# SECTION 2: CALCULATE MONTHLY RETURNS
# =============================================================================
# Same three key dates as the original strategy:
#   d1     = first business day
#   d2last = second-to-last business day  (end of main window)
#   dlast  = last business day            (trade day)

results = []

for (year, month), group in df.groupby([df['Date'].dt.year, df['Date'].dt.month]):
    group = group.sort_values('Date')
    days  = group['Date'].tolist()

    if len(days) < 3:
        continue

    d1, d2last, dlast = days[0], days[-2], days[-1]

    spy1 = group.loc[group['Date'] == d1,     'SPY'].values[0]
    spy2 = group.loc[group['Date'] == d2last, 'SPY'].values[0]
    spy3 = group.loc[group['Date'] == dlast,  'SPY'].values[0]
    tlt1 = group.loc[group['Date'] == d1,     'TLT'].values[0]
    tlt2 = group.loc[group['Date'] == d2last, 'TLT'].values[0]
    tlt3 = group.loc[group['Date'] == dlast,  'TLT'].values[0]

    spy_main  = spy2 / spy1 - 1
    tlt_main  = tlt2 / tlt1 - 1
    spy_final = spy3 / spy2 - 1
    tlt_final = tlt3 / tlt2 - 1

    results.append({
        'Month':                           f'{year}-{month:02d}',
        'First Bus Day':                   d1.date(),
        '2nd-to-Last':                     d2last.date(),
        'Last Bus Day':                    dlast.date(),
        'SPY Main (%)':                    round(spy_main * 100, 4),
        'TLT Main (%)':                    round(tlt_main * 100, 4),
        'Main Spread (TLT-SPY %)':         round((tlt_main - spy_main) * 100, 4),
        'SPY Final (%)':                   round(spy_final * 100, 4),
        'TLT Final (%)':                   round(tlt_final * 100, 4),
        'Final Spread (SPY-TLT %)':        round((spy_final - tlt_final) * 100, 4),
        'spy_main_raw':                    spy_main,
        'tlt_main_raw':                    tlt_main,
        'spy_final_raw':                   spy_final,
        'tlt_final_raw':                   tlt_final,
        'Qualifies (TLT beat SPY by >5%)': (tlt_main - spy_main) > SPREAD_THRESHOLD,
    })

df_res = pd.DataFrame(results)
print(f"Complete months calculated: {len(df_res)}")
print()

# =============================================================================
# SECTION 3: FILTER QUALIFYING MONTHS
# =============================================================================
qualified = df_res[df_res['Qualifies (TLT beat SPY by >5%)']].copy()

print(f"Total complete months:                     {len(df_res)}")
print(f"Qualifying months (TLT beat SPY by >5%):  {len(qualified)}")
print()
print(qualified[['Month', 'First Bus Day', '2nd-to-Last', 'Last Bus Day',
                 'SPY Main (%)', 'TLT Main (%)', 'Main Spread (TLT-SPY %)',
                 'SPY Final (%)', 'TLT Final (%)', 'Final Spread (SPY-TLT %)']].to_string(index=False))
print()

# =============================================================================
# SECTION 4: STATISTICAL ANALYSIS
# =============================================================================
# A positive final-day spread (SPY minus TLT) confirms the hypothesis:
# SPY mean-reverts up while TLT pulls back on the rebalancing day.

spread = qualified['spy_final_raw'] - qualified['tlt_final_raw']
t, p   = stats.ttest_1samp(spread, 0)

print('=== STATISTICAL ANALYSIS: TLT-Dominant Rebalancing Effect ===')
print(f'  Complete months tested:                    {len(df_res)}')
print(f'  Months where TLT beat SPY by >5%:         {len(qualified)}')
print(f'  Avg final-day SPY return:                  {qualified["spy_final_raw"].mean()*100:.4f}%')
print(f'  Avg final-day TLT return:                  {qualified["tlt_final_raw"].mean()*100:.4f}%')
print(f'  Avg final-day SPY minus TLT:               {spread.mean()*100:.4f}%')
print(f'  Median final-day SPY minus TLT:            {spread.median()*100:.4f}%')
print(f'  SPY outperformed TLT on final day:         {(spread>0).sum()} / {len(spread)} ({(spread>0).mean()*100:.1f}%)')
print(f'  t-stat on final-day spread:                {t:.4f}')
print(f'  p-value:                                   {p:.6f}')
print()

# =============================================================================
# SECTION 5: TRADE P&L
# =============================================================================
# P&L = $2M * SPY_1day_return - $1M * TLT_1day_return

qualified['P&L ($)'] = (
    LONG_SIZE  * qualified['spy_final_raw'] -
    SHORT_SIZE * qualified['tlt_final_raw']
).round(2)

trade_table = qualified[['Month', '2nd-to-Last', 'Last Bus Day',
                          'SPY Final (%)', 'TLT Final (%)', 'P&L ($)']].copy()
trade_table['Trade Window'] = (trade_table['2nd-to-Last'].astype(str)
                               + ' -> ' + trade_table['Last Bus Day'].astype(str))
trade_table['Win'] = trade_table['P&L ($)'] > 0
trade_table = trade_table[['Month', 'Trade Window', 'SPY Final (%)', 'TLT Final (%)', 'P&L ($)', 'Win']]

print('=== TRADE P&L TABLE ===')
print(trade_table.to_string(index=False))
print()

pnl = qualified['P&L ($)']
print('=== TRADE SUMMARY ===')
print(f'  Long ${LONG_SIZE/1e6:.0f}M SPY / Short ${SHORT_SIZE/1e6:.0f}M TLT')
print(f'  Total P&L:             ${pnl.sum():,.2f}')
print(f'  Average P&L per trade: ${pnl.mean():,.2f}')
print(f'  Median P&L:            ${pnl.median():,.2f}')
print(f'  Winning trades:        {(pnl>0).sum()} / {len(pnl)} ({(pnl>0).mean()*100:.1f}%)')
print(f'  Losing trades:         {(pnl<0).sum()} / {len(pnl)} ({(pnl<0).mean()*100:.1f}%)')
print(f'  Best trade:            {qualified.loc[pnl.idxmax(), "Month"]} (${pnl.max():,.2f})')
print(f'  Worst trade:           {qualified.loc[pnl.idxmin(), "Month"]} (${pnl.min():,.2f})')
print()

# =============================================================================
# SECTION 6: SHARPE RATIO
# =============================================================================
n      = len(pnl)
mean   = pnl.mean()
std    = pnl.std(ddof=1)
sharpe = (mean / std) * np.sqrt(n)

print('=== SHARPE RATIO ===')
print(f'  N (number of trades): {n}')
print(f'  Mean P&L:             ${mean:,.2f}')
print(f'  Std Dev:              ${std:,.2f}')
print(f'  Sharpe Ratio:         {sharpe:.4f}')
print()

# =============================================================================
# SECTION 7: COMPARISON — SYMMETRIC vs ORIGINAL STRATEGY
# =============================================================================
# Side-by-side summary of the two strategies across the same 10-year period.

print('=== STRATEGY COMPARISON ===')
print(f'  {"Metric":<35} {"Original (SPY dominant)":>24} {"Symmetric (TLT dominant)":>24}')
print(f'  {"-"*83}')

orig_qual  = 24
orig_wins  = 18
orig_total = 202_585.31
orig_avg   = 8_441.05
orig_wr    = 75.0
orig_sh    = 2.0843

rows = [
    ('Qualifying months',          f'{orig_qual} / 120',    f'{len(qualified)} / 120'),
    ('Winning trades',             f'{orig_wins} / {orig_qual} ({orig_wr:.1f}%)',
                                   f'{(pnl>0).sum()} / {len(pnl)} ({(pnl>0).mean()*100:.1f}%)'),
    ('Total P&L',                  f'${orig_total:,.2f}',   f'${pnl.sum():,.2f}'),
    ('Avg P&L per trade',          f'${orig_avg:,.2f}',     f'${mean:,.2f}'),
    ('Sharpe Ratio',               f'{orig_sh:.4f}',        f'{sharpe:.4f}'),
    ('t-stat (final-day spread)',   '-2.4500',               f'{t:.4f}'),
    ('p-value',                    '0.0223',                 f'{p:.6f}'),
]

for label, orig, sym in rows:
    print(f'  {label:<35} {orig:>24} {sym:>24}')

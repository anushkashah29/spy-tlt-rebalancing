import pandas as pd
import numpy as np
import yfinance as yf
from scipy import stats

# =============================================================================
# STRATEGY: SPY NEXT-DAY BOUNCE
# =============================================================================
# After a qualifying month (SPY beat TLT by >5% in main window) where SPY
# ALSO had a negative return on the final trading day, SPY tends to bounce
# back on the first trading day of the next month.
#
# Trade:    Long $1M SPY
# Entry:    Close of the last trading day of the qualifying month
# Exit:     Close of the first trading day of the next month
# Holding:  1 day
#
# Data source: spy_tlt_closes.csv (produced by spy_tlt_rebalancing.py).
#              If the file is missing, data is re-fetched via yfinance.
# =============================================================================

POSITION_SIZE = 1_000_000   # $1M long SPY
START_DATE    = "2016-04-01"
END_DATE      = "2026-04-01"
SPREAD_THRESHOLD = 0.05     # SPY must beat TLT by >5% in the main window

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
# SECTION 2: IDENTIFY QUALIFYING MONTHS
# =============================================================================
# Replicates the same monthly key-date logic from spy_tlt_rebalancing.py:
#   d1     = first business day
#   d2last = second-to-last business day  (end of main window)
#   dlast  = last business day            (end of final day / bounce entry)

monthly = []

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

    monthly.append({
        'Month':            f'{year}-{month:02d}',
        'Last Bus Day':     dlast.date(),
        'spy_main_raw':     spy_main,
        'tlt_main_raw':     tlt_main,
        'spy_final_raw':    spy_final,
        'tlt_final_raw':    tlt_final,
        'spy_last_price':   spy3,
        'tlt_last_price':   tlt3,
        'Qualifies':        (spy_main - tlt_main) > SPREAD_THRESHOLD,
        'SPY Final Neg':    spy_final < 0,
    })

df_monthly = pd.DataFrame(monthly)

qualified        = df_monthly[df_monthly['Qualifies']].copy()
bounce_eligible  = qualified[qualified['SPY Final Neg']].copy()

print(f"Total complete months:                     {len(df_monthly)}")
print(f"Qualifying months (SPY beat TLT by >5%):  {len(qualified)}")
print(f"Bounce eligible (+ negative SPY final day):{len(bounce_eligible)}")
print()

# =============================================================================
# SECTION 3: COMPUTE NEXT-DAY BOUNCE TRADES
# =============================================================================

trades = []

for _, row in bounce_eligible.iterrows():
    last_day         = pd.Timestamp(row['Last Bus Day'])
    spy_entry_price  = row['spy_last_price']

    next_row = df[df['Date'] > last_day].head(1)
    if next_row.empty:
        continue

    spy_exit_price = next_row['SPY'].values[0]
    exit_date      = pd.Timestamp(next_row['Date'].values[0]).date()
    spy_next_ret   = spy_exit_price / spy_entry_price - 1

    trades.append({
        'Month':          row['Month'],
        'Entry Date':     row['Last Bus Day'],
        'Exit Date':      exit_date,
        'Entry Price ($)':round(spy_entry_price, 2),
        'Exit Price ($)': round(spy_exit_price, 2),
        'SPY Return (%)': round(spy_next_ret * 100, 4),
        'spy_next_raw':   spy_next_ret,
        'spy_final_raw':  row['spy_final_raw'],
        'tlt_final_raw':  row['tlt_final_raw'],
    })

df_trades = pd.DataFrame(trades)
df_trades['P&L ($)'] = (POSITION_SIZE * df_trades['spy_next_raw']).round(2)
df_trades['Win']     = df_trades['P&L ($)'] > 0

# =============================================================================
# SECTION 4: TRADE TABLE & SUMMARY
# =============================================================================
print('=== BOUNCE TRADE TABLE ===')
print(df_trades[['Month', 'Entry Date', 'Exit Date',
                 'SPY Return (%)', 'P&L ($)', 'Win']].to_string(index=False))
print()

pnl = df_trades['P&L ($)']
print('=== BOUNCE TRADE SUMMARY ===')
print(f'  Position size:         ${POSITION_SIZE:,.0f} long SPY')
print(f'  Total trades:          {len(df_trades)}')
print(f'  Total P&L:             ${pnl.sum():,.2f}')
print(f'  Average P&L per trade: ${pnl.mean():,.2f}')
print(f'  Median P&L:            ${pnl.median():,.2f}')
print(f'  Winning trades:        {(pnl>0).sum()} / {len(pnl)} ({(pnl>0).mean()*100:.1f}%)')
print(f'  Losing trades:         {(pnl<0).sum()} / {len(pnl)} ({(pnl<0).mean()*100:.1f}%)')
print(f'  Best trade:            {df_trades.loc[pnl.idxmax(), "Month"]} (${pnl.max():,.2f})')
print(f'  Worst trade:           {df_trades.loc[pnl.idxmin(), "Month"]} (${pnl.min():,.2f})')
print()

# =============================================================================
# SECTION 5: STATISTICAL ANALYSIS
# =============================================================================
returns = df_trades['spy_next_raw']
t, p    = stats.ttest_1samp(returns, 0)

print('=== STATISTICAL ANALYSIS ===')
print(f'  Avg next-day SPY return:    {returns.mean()*100:.4f}%')
print(f'  Median next-day SPY return: {returns.median()*100:.4f}%')
print(f'  Positive returns:           {(returns>0).sum()} / {len(returns)} ({(returns>0).mean()*100:.0f}%)')
print(f'  t-stat:                     {t:.4f}')
print(f'  p-value:                    {p:.6f}')
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
# SECTION 7: COMBINED P&L — ORIGINAL STRATEGY + BOUNCE LEG
# =============================================================================
# For the subset of months that trigger BOTH the original trade AND the bounce,
# shows whether stacking the two legs improves overall results.
#
# Original leg: Long $2M TLT / Short $1M SPY on the final day
# Bounce leg:   Long $1M SPY on the first day of the next month

df_trades['Original P&L ($)'] = (
    2_000_000 * df_trades['tlt_final_raw'] -
    1_000_000 * df_trades['spy_final_raw']
).round(2)
df_trades['Combined P&L ($)'] = (df_trades['Original P&L ($)'] + df_trades['P&L ($)']).round(2)

orig_pnl  = df_trades['Original P&L ($)']
combo_pnl = df_trades['Combined P&L ($)']

print('=== COMBINED STRATEGY (original + bounce, same qualifying months) ===')
print(df_trades[['Month', 'Original P&L ($)', 'P&L ($)', 'Combined P&L ($)']].rename(
    columns={'P&L ($)': 'Bounce P&L ($)'}
).to_string(index=False))
print()
print(f'  Original leg total P&L: ${orig_pnl.sum():,.2f}')
print(f'  Bounce leg total P&L:   ${pnl.sum():,.2f}')
print(f'  Combined total P&L:     ${combo_pnl.sum():,.2f}')
print()
n_c      = len(combo_pnl)
sharpe_c = (combo_pnl.mean() / combo_pnl.std(ddof=1)) * np.sqrt(n_c)
print(f'  Combined Sharpe Ratio:  {sharpe_c:.4f}')

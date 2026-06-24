import pandas as pd
import numpy as np
import yfinance as yf
from scipy import stats

# =============================================================================
# SECTION 1: LOAD & MERGE DATA
# =============================================================================
# Load the combined CSV produced by yfinance
start_date = "2016-04-01"
end_date = "2026-04-01"

print(f"Fetching SPY and TLT daily closing prices from {start_date} to {end_date}...")

data = yf.download(["SPY", "TLT"], start=start_date, end=end_date, auto_adjust=True)

close = data["Close"][["SPY", "TLT"]].copy()
close.index.name = "Date"
close.to_csv("spy_tlt_closes.csv")
print(f"Saved {len(close)} rows to spy_tlt_closes.csv")

df = pd.read_csv('spy_tlt_closes.csv')

if df.columns[0] != 'Date':
    df = pd.read_csv('spy_tlt_closes.csv', header=[0,1])
    df.columns = ['Date', 'SPY', 'TLT']

# Parse Date and convert prices to numeric
df['Date'] = pd.to_datetime(df['Date'])
df['SPY']  = pd.to_numeric(df['SPY'], errors='coerce')
df['TLT']  = pd.to_numeric(df['TLT'], errors='coerce')

# Drop any rows with missing data, sort oldest to newest
df = df.dropna().sort_values('Date').reset_index(drop=True)

print(f'Total trading days: {len(df)}')
print(f'Date range: {df["Date"].min().date()} to {df["Date"].max().date()}')
print()

# =============================================================================
# SECTION 2: CALCULATE MONTHLY RETURNS
# =============================================================================
# For each month we identify 3 key dates:
#   d1     = first business day (start of month)
#   d2last = second-to-last business day (end of main window)
#   dlast  = last business day (rebalancing day)
#
# Main window return: d1 -> d2last  (was it a strong month?)
# Final day return:   d2last -> dlast  (what happened on rebalancing day?)

results = []

for (year, month), group in df.groupby([df['Date'].dt.year, df['Date'].dt.month]):
    group = group.sort_values('Date')
    days = group['Date'].tolist()

    # Need at least 3 trading days to have d1, d2last, dlast
    if len(days) < 3:
        continue

    d1, d2last, dlast = days[0], days[-2], days[-1]

    # Pull prices for each key date
    spy1 = group.loc[group['Date']==d1,     'SPY'].values[0]
    spy2 = group.loc[group['Date']==d2last, 'SPY'].values[0]
    spy3 = group.loc[group['Date']==dlast,  'SPY'].values[0]
    tlt1 = group.loc[group['Date']==d1,     'TLT'].values[0]
    tlt2 = group.loc[group['Date']==d2last, 'TLT'].values[0]
    tlt3 = group.loc[group['Date']==dlast,  'TLT'].values[0]

    # Calculate returns: (end price / start price) - 1
    spy_main  = spy2/spy1 - 1
    tlt_main  = tlt2/tlt1 - 1
    spy_final = spy3/spy2 - 1
    tlt_final = tlt3/tlt2 - 1

    results.append({
        'Month':                          f'{year}-{month:02d}',
        'First Bus Day':                  d1.date(),
        '2nd-to-Last':                    d2last.date(),
        'Last Bus Day':                   dlast.date(),
        'SPY Main (%)':                   round(spy_main*100, 4),
        'TLT Main (%)':                   round(tlt_main*100, 4),
        'Main Spread (SPY-TLT %)':        round((spy_main-tlt_main)*100, 4),
        'SPY Final (%)':                  round(spy_final*100, 4),
        'TLT Final (%)':                  round(tlt_final*100, 4),
        'Final Spread (SPY-TLT %)':       round((spy_final-tlt_final)*100, 4),
        'spy_main_raw':                   spy_main,
        'tlt_main_raw':                   tlt_main,
        'spy_final_raw':                  spy_final,
        'tlt_final_raw':                  tlt_final,
        'Qualifies (SPY beat TLT by >5%)': (spy_main - tlt_main) > 0.05
    })

df_res = pd.DataFrame(results)
print(f'Complete months calculated: {len(df_res)}')
print()

# =============================================================================
# SECTION 3: FILTER QUALIFYING MONTHS
# =============================================================================
# Keep only months where SPY beat TLT by more than 5% in the main window.
# These are the months where pension/insurance rebalancing pressure is highest.

qualified = df_res[df_res['Qualifies (SPY beat TLT by >5%)']].copy()

print(f'Total complete months:                    {len(df_res)}')
print(f'Qualifying months (SPY beat TLT by >5%): {len(qualified)}')
print()
print(qualified[['Month','First Bus Day','2nd-to-Last','Last Bus Day',
                 'SPY Main (%)','TLT Main (%)','Main Spread (SPY-TLT %)',
                 'SPY Final (%)','TLT Final (%)','Final Spread (SPY-TLT %)']].to_string(index=False))
print()

# =============================================================================
# SECTION 4: STATISTICAL ANALYSIS
# =============================================================================
# Test whether TLT consistently beats SPY on the final rebalancing day.
# A negative spread (SPY minus TLT) means TLT won — what the hypothesis predicts.

spread = qualified['spy_final_raw'] - qualified['tlt_final_raw']
t, p = stats.ttest_1samp(spread, 0)

print('=== ANALYSIS 1: Month-End Rebalancing Effect ===')
print(f'  Complete months tested:                    {len(df_res)}')
print(f'  Months where SPY beat TLT by >5%:         {len(qualified)}')
print(f'  Avg final-day SPY return:                  {qualified["spy_final_raw"].mean()*100:.4f}%')
print(f'  Avg final-day TLT return:                  {qualified["tlt_final_raw"].mean()*100:.4f}%')
print(f'  Avg final-day SPY minus TLT:               {spread.mean()*100:.4f}%')
print(f'  Median final-day SPY minus TLT:            {spread.median()*100:.4f}%')
print(f'  SPY underperformed TLT:                    {(spread<0).sum()} / {len(spread)} = {(spread<0).mean()*100:.1f}%')
print(f'  t-stat on final-day spread:                {t:.4f}')
print(f'  p-value:                                   {p:.6f}')
print()

# =============================================================================
# SECTION 5: TRADE P&L
# =============================================================================
# For each qualifying month, simulate: Long $2M TLT / Short $1M SPY
# P&L formula: 2,000,000 x TLT_1day_return - 1,000,000 x SPY_1day_return

qualified['P&L ($)'] = (
    2_000_000 * qualified['tlt_final_raw'] -
    1_000_000 * qualified['spy_final_raw']
).round(2)

# Full trade table
trade_table = qualified[['Month','2nd-to-Last','Last Bus Day',
                          'SPY Final (%)','TLT Final (%)','P&L ($)']].copy()
trade_table['Trade Window'] = (trade_table['2nd-to-Last'].astype(str)
                                + ' -> ' + trade_table['Last Bus Day'].astype(str))
trade_table['Win'] = trade_table['P&L ($)'] > 0
trade_table = trade_table[['Month','Trade Window','SPY Final (%)','TLT Final (%)','P&L ($)','Win']]

print('=== TRADE P&L TABLE ===')
print(trade_table.to_string(index=False))
print()

pnl = qualified['P&L ($)']
print('=== TRADE SUMMARY ===')
print(f'  Total P&L:             ${pnl.sum():,.2f}')
print(f'  Average P&L per trade: ${pnl.mean():,.2f}')
print(f'  Median P&L:            ${pnl.median():,.2f}')
print(f'  Winning trades:        {(pnl>0).sum()} / {len(pnl)} = {(pnl>0).mean()*100:.1f}%')
print(f'  Losing trades:         {(pnl<0).sum()} / {len(pnl)} = {(pnl<0).mean()*100:.1f}%')
print(f'  Best trade:            {qualified.loc[pnl.idxmax(), "Month"]} (${pnl.max():,.2f})')
print(f'  Worst trade:           {qualified.loc[pnl.idxmin(), "Month"]} (${pnl.min():,.2f})')
print()

# =============================================================================
# SECTION 6: NEXT-DAY BOUNCE ANALYSIS
# =============================================================================
# After a strong month + month-end selloff, does SPY bounce the very next day?
#
# Filter:
#   1. SPY beat TLT by >= 5% in the main window
#   2. SPY return on final day was negative (confirmed selloff happened)
#   3. Measure: next trading day return (last bus day -> first bus day next month)

next_day_results = []

for _, row in qualified.iterrows():
    # Find the first trading day after the last business day of this month
    next_day_data = df[df['Date'] > pd.Timestamp(row['Last Bus Day'])].head(1)
    if len(next_day_data) == 0:
        continue

    next_day       = next_day_data['Date'].values[0]
    spy_next_price = next_day_data['SPY'].values[0]
    tlt_next_price = next_day_data['TLT'].values[0]
    spy_last_price = df.loc[df['Date']==pd.Timestamp(row['Last Bus Day']), 'SPY'].values[0]
    tlt_last_price = df.loc[df['Date']==pd.Timestamp(row['Last Bus Day']), 'TLT'].values[0]

    spy_next_ret = spy_next_price/spy_last_price - 1
    tlt_next_ret = tlt_next_price/tlt_last_price - 1

    next_day_results.append({
        'Month':             row['Month'],
        'Last Bus Day':      row['Last Bus Day'],
        'Next Trading Day':  pd.Timestamp(next_day).date(),
        'SPY Final Day (%)': round(row['spy_final_raw']*100, 4),
        'SPY Next Day (%)':  round(spy_next_ret*100, 4),
        'TLT Next Day (%)':  round(tlt_next_ret*100, 4),
        'spy_final_raw':     row['spy_final_raw'],
        'spy_next_raw':      spy_next_ret,
    })

df_next = pd.DataFrame(next_day_results)

# Tighter filter: also had a negative final day (confirmed selloff happened)
df_bounce = df_next[df_next['spy_final_raw'] < 0].copy()

print('=== NEXT-DAY BOUNCE TABLE (strong month + negative final day) ===')
print(df_bounce[['Month','Last Bus Day','Next Trading Day',
                 'SPY Final Day (%)','SPY Next Day (%)','TLT Next Day (%)']].to_string(index=False))
print()

print('=== NEXT-DAY BOUNCE SUMMARY ===')
print(f'  Number of cases:           {len(df_bounce)}')
print(f'  Avg next-day SPY return:   {df_bounce["spy_next_raw"].mean()*100:.4f}%')
print(f'  Median next-day SPY return:{df_bounce["spy_next_raw"].median()*100:.4f}%')
print(f'  Positive next-day returns: {(df_bounce["spy_next_raw"]>0).sum()} / {len(df_bounce)} ({(df_bounce["spy_next_raw"]>0).mean()*100:.0f}%)')
print(f'  Negative next-day returns: {(df_bounce["spy_next_raw"]<0).sum()} / {len(df_bounce)} ({(df_bounce["spy_next_raw"]<0).mean()*100:.0f}%)')

# =============================================================================
# SECTION 7: SHARPE RATIO
# =============================================================================
pnl    = qualified['P&L ($)']
n      = len(pnl)
mean   = pnl.mean()
std    = pnl.std(ddof=1)
sharpe = (mean / std) * np.sqrt(n)

print('=== SECTION 7: SHARPE RATIO ===')
print(f'  N (number of trades): {n}')
print(f'  Sum of all P&Ls:      ${pnl.sum():,.2f}')
print(f'  Mean P&L:             ${mean:,.2f}')
print(f'  Variance:             ${pnl.var(ddof=1):,.2f}')
print(f'  Std Dev:              ${std:,.2f}')
print(f'  √N:                   {np.sqrt(n):.4f}')
print(f'  Sharpe Ratio:         {sharpe:.4f}')
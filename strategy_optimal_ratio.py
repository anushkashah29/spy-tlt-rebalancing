import pandas as pd
import numpy as np
import yfinance as yf
from scipy import stats
from scipy.optimize import minimize_scalar

# =============================================================================
# OPTIMAL TLT:SPY RATIO ANALYSIS
# =============================================================================
# The original strategy uses Long $2M TLT / Short $1M SPY — a vol-parity
# construction (SPY ~2x daily vol of TLT, so 2x notional equalises dollar risk).
#
# This script asks: is 2:1 actually optimal? We fix SPY short at $1M, vary the
# TLT long notional from $0 to $5M, and find the ratio that maximises Sharpe.
#
# Trade P&L formula:
#   P&L = (ratio * 1M) * TLT_final_return  -  1M * SPY_final_return
# =============================================================================

SPY_NOTIONAL = 1_000_000
START_DATE   = "2016-04-01"
END_DATE     = "2026-04-01"

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
    print(f"Fetching from yfinance ({START_DATE} to {END_DATE})...")
    data = yf.download(["SPY", "TLT"], start=START_DATE, end=END_DATE, auto_adjust=True)
    df = data["Close"][["SPY", "TLT"]].copy()
    df.index.name = "Date"
    df = df.reset_index()
    df.to_csv("spy_tlt_closes.csv", index=False)

df['Date'] = pd.to_datetime(df['Date'])
df['SPY']  = pd.to_numeric(df['SPY'], errors='coerce')
df['TLT']  = pd.to_numeric(df['TLT'], errors='coerce')
df = df.dropna().sort_values('Date').reset_index(drop=True)

# =============================================================================
# SECTION 2: BUILD QUALIFYING MONTH RETURNS
# =============================================================================
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
        'Month':        f'{year}-{month:02d}',
        'spy_final':    spy_final,
        'tlt_final':    tlt_final,
        'Qualifies':    (spy_main - tlt_main) > 0.05,
    })

df_res   = pd.DataFrame(results)
qual     = df_res[df_res['Qualifies']].copy().reset_index(drop=True)
spy_r    = qual['spy_final'].values
tlt_r    = qual['tlt_final'].values
n_trades = len(qual)

print(f"Qualifying months: {n_trades}")
print()

# =============================================================================
# SECTION 3: VOLATILITY ANALYSIS — WHY 2:1?
# =============================================================================
spy_vol = spy_r.std()
tlt_vol = tlt_r.std()
corr    = np.corrcoef(spy_r, tlt_r)[0, 1]
cov     = np.cov(spy_r, tlt_r, ddof=1)[0, 1]

vol_parity_ratio = spy_vol / tlt_vol   # TLT notional multiplier for equal dollar-vol

print('=== VOLATILITY ANALYSIS (qualifying final days) ===')
print(f'  SPY daily vol (final days):  {spy_vol*100:.4f}%')
print(f'  TLT daily vol (final days):  {tlt_vol*100:.4f}%')
print(f'  SPY/TLT vol ratio:           {vol_parity_ratio:.4f}x')
print(f'  Implied vol-parity ratio:    Long ${vol_parity_ratio:.2f}M TLT / Short $1M SPY')
print(f'  Correlation (SPY vs TLT):    {corr:.4f}')
print(f'  Current ratio used (2:1):    {"matches vol-parity" if abs(vol_parity_ratio - 2.0) < 0.3 else "differs from vol-parity"}')
print()

# =============================================================================
# SECTION 4: CLOSED-FORM SHARPE-OPTIMAL RATIO
# =============================================================================
# Fix SPY short at $1M. TLT long = ratio * $1M.
# P&L_i = ratio * tlt_i - spy_i   (in units of $1M)
#
# Sharpe = E[P&L] / std[P&L]
#        = (ratio*mu_tlt - mu_spy) / sqrt(ratio^2*var_tlt + var_spy - 2*ratio*cov)
#
# Setting d(Sharpe)/d(ratio) = 0 gives:
#   ratio* = (mu_tlt * var_spy - (-mu_spy) * cov) / ((-mu_spy) * var_tlt - mu_tlt * cov)
# or equivalently (with a = mu_tlt, b = -mu_spy):
#   ratio* = (a * var_spy + b * cov) / (a * cov + b * var_tlt)

mu_tlt  = tlt_r.mean()
mu_spy  = spy_r.mean()          # negative on qualifying days
a       = mu_tlt
b       = -mu_spy               # positive (SPY avg is negative, so -avg is positive)
var_tlt = tlt_r.var(ddof=1)
var_spy = spy_r.var(ddof=1)

ratio_cf = (a * var_spy + b * cov) / (a * cov + b * var_tlt)

print('=== CLOSED-FORM SHARPE-OPTIMAL RATIO ===')
print(f'  mu_SPY  (avg final day):     {mu_spy*100:.4f}%')
print(f'  mu_TLT  (avg final day):     {mu_tlt*100:.4f}%')
print(f'  Covariance (SPY, TLT):       {cov:.8f}')
print(f'  Sharpe-optimal ratio:        {ratio_cf:.4f}x')
print(f'  Optimal TLT notional:        ${ratio_cf * SPY_NOTIONAL:,.0f}')
print()

# =============================================================================
# SECTION 5: GRID SCAN — P&L AND SHARPE AT EACH RATIO
# =============================================================================
ratios = np.arange(0.0, 5.1, 0.25)
scan   = []

for r in ratios:
    pnl   = SPY_NOTIONAL * (r * tlt_r - spy_r)
    mean  = pnl.mean()
    std   = pnl.std(ddof=1)
    sh    = (mean / std) * np.sqrt(n_trades) if std > 0 else 0
    wins  = (pnl > 0).sum()
    scan.append({
        'Ratio (TLT:SPY)': f'{r:.2f}',
        'TLT Notional ($)': f'${r * SPY_NOTIONAL:,.0f}',
        'Total P&L ($)':   round(pnl.sum(), 2),
        'Avg P&L ($)':     round(mean, 2),
        'Std Dev ($)':     round(std, 2),
        'Win Rate (%)':    round((pnl > 0).mean() * 100, 1),
        'Sharpe':          round(sh, 4),
        'sharpe_raw':      sh,
    })

df_scan = pd.DataFrame(scan)

best_idx    = df_scan['sharpe_raw'].idxmax()
best_ratio  = float(df_scan.loc[best_idx, 'Ratio (TLT:SPY)'])
best_sharpe = df_scan.loc[best_idx, 'Sharpe']

print('=== GRID SCAN: SHARPE AND P&L BY TLT:SPY RATIO ===')
print(f'  {"Ratio":<12} {"TLT Notional":>15} {"Total P&L":>14} {"Avg P&L":>12} {"Win Rate":>10} {"Sharpe":>8}')
print(f'  {"-"*75}')
for _, row in df_scan.iterrows():
    marker = ' <-- current' if row['Ratio (TLT:SPY)'] == '2.00' else ''
    marker = ' <-- optimal (grid)' if row['Ratio (TLT:SPY)'] == f'{best_ratio:.2f}' and marker == '' else marker
    print(f'  {row["Ratio (TLT:SPY)"]:<12} {row["TLT Notional ($)"]:>15} '
          f'{row["Total P&L ($)"]:>14,.2f} {row["Avg P&L ($)"]:>12,.2f} '
          f'{row["Win Rate (%)"]:>9.1f}% {row["Sharpe"]:>8.4f}{marker}')
print()

# =============================================================================
# SECTION 6: PRECISE OPTIMAL VIA SCIPY
# =============================================================================
def neg_sharpe(r):
    pnl  = SPY_NOTIONAL * (r * tlt_r - spy_r)
    mean = pnl.mean()
    std  = pnl.std(ddof=1)
    return -(mean / std) * np.sqrt(n_trades) if std > 0 else 0

result       = minimize_scalar(neg_sharpe, bounds=(0.01, 10.0), method='bounded')
ratio_opt    = result.x
sharpe_opt   = -result.fun
pnl_opt      = SPY_NOTIONAL * (ratio_opt * tlt_r - spy_r)

print('=== PRECISE OPTIMAL RATIO (scipy minimizer) ===')
print(f'  Optimal TLT:SPY ratio:       {ratio_opt:.4f}x')
print(f'  Optimal TLT notional:        ${ratio_opt * SPY_NOTIONAL:,.0f}')
print(f'  Optimal Sharpe:              {sharpe_opt:.4f}')
print(f'  Closed-form ratio:           {ratio_cf:.4f}x  (should match)')
print()

# =============================================================================
# SECTION 7: SIDE-BY-SIDE — CURRENT 2:1 vs OPTIMAL
# =============================================================================
pnl_current = SPY_NOTIONAL * (2.0 * tlt_r - spy_r)
pnl_optimal = SPY_NOTIONAL * (ratio_opt * tlt_r - spy_r)

def summary(pnl, label):
    n   = len(pnl)
    mu  = pnl.mean()
    sd  = pnl.std(ddof=1)
    sh  = (mu / sd) * np.sqrt(n)
    t, p = stats.ttest_1samp(pnl, 0)
    print(f'  {label}')
    print(f'    TLT notional:          ${SPY_NOTIONAL * (2.0 if "Current" in label else ratio_opt):,.0f}')
    print(f'    Total P&L:             ${pnl.sum():,.2f}')
    print(f'    Avg P&L per trade:     ${mu:,.2f}')
    print(f'    Std Dev:               ${sd:,.2f}')
    print(f'    Win rate:              {(pnl>0).sum()} / {n} ({(pnl>0).mean()*100:.1f}%)')
    print(f'    Best trade:            ${pnl.max():,.2f}  ({qual.loc[pnl.argmax(), "Month"]})')
    print(f'    Worst trade:           ${pnl.min():,.2f}  ({qual.loc[pnl.argmin(), "Month"]})')
    print(f'    Sharpe:                {sh:.4f}')
    print(f'    p-value:               {p:.6f}')
    print()

print('=== CURRENT 2:1 vs SHARPE-OPTIMAL RATIO ===')
summary(pnl_current, f'Current  (2.00:1 -> Long $2M TLT / Short $1M SPY)')
summary(pnl_optimal, f'Optimal  ({ratio_opt:.2f}:1 -> Long ${ratio_opt*SPY_NOTIONAL/1e6:.2f}M TLT / Short $1M SPY)')

# Trade-by-trade comparison
df_compare = qual[['Month']].copy()
df_compare['SPY Final (%)']   = (spy_r * 100).round(4)
df_compare['TLT Final (%)']   = (tlt_r * 100).round(4)
df_compare['P&L Current ($)'] = pnl_current.round(2)
df_compare['P&L Optimal ($)'] = pnl_optimal.round(2)
df_compare['Diff ($)']        = (pnl_optimal - pnl_current).round(2)

print('=== TRADE-BY-TRADE: CURRENT vs OPTIMAL ===')
print(df_compare.to_string(index=False))
print()
print(f'  Total gain from switching to optimal ratio: ${(pnl_optimal - pnl_current).sum():,.2f}')

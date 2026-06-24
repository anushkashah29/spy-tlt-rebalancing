import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from scipy import stats

# =============================================================================
# LOAD DATA & BUILD QUALIFYING MONTHS
# =============================================================================
df = pd.read_csv('spy_tlt_closes.csv')
df['Date'] = pd.to_datetime(df['Date'])
df['SPY']  = pd.to_numeric(df['SPY'], errors='coerce')
df['TLT']  = pd.to_numeric(df['TLT'], errors='coerce')
df = df.dropna().sort_values('Date').reset_index(drop=True)

results = []
for (year, month), group in df.groupby([df['Date'].dt.year, df['Date'].dt.month]):
    group = group.sort_values('Date')
    days  = group['Date'].tolist()
    if len(days) < 3:
        continue
    d1, d2last, dlast = days[0], days[-2], days[-1]
    spy1 = group.loc[group['Date']==d1,     'SPY'].values[0]
    spy2 = group.loc[group['Date']==d2last, 'SPY'].values[0]
    spy3 = group.loc[group['Date']==dlast,  'SPY'].values[0]
    tlt1 = group.loc[group['Date']==d1,     'TLT'].values[0]
    tlt2 = group.loc[group['Date']==d2last, 'TLT'].values[0]
    tlt3 = group.loc[group['Date']==dlast,  'TLT'].values[0]
    spy_main  = spy2/spy1 - 1;  tlt_main  = tlt2/tlt1 - 1
    spy_final = spy3/spy2 - 1;  tlt_final = tlt3/tlt2 - 1
    results.append({
        'Month':      f'{year}-{month:02d}',
        'spy_final':  spy_final * 100,
        'tlt_final':  tlt_final * 100,
        'spread':     (tlt_final - spy_final) * 100,   # TLT minus SPY
        'Qualifies':  (spy_main - tlt_main) > 0.05,
    })

qual   = pd.DataFrame(results)
qual   = qual[qual['Qualifies']].reset_index(drop=True)
spread = qual['spread'].values        # TLT final − SPY final (%)
n      = len(spread)
mu     = spread.mean()
sigma  = spread.std(ddof=1)
t_stat, p_val = stats.ttest_1samp(spread, 0)
wins   = (spread > 0).sum()

# =============================================================================
# PLOT
# =============================================================================
fig, ax = plt.subplots(figsize=(11, 6))
fig.patch.set_facecolor('#0f1117')
ax.set_facecolor('#0f1117')

# --- histogram ---
bins      = np.linspace(spread.min() - 0.5, spread.max() + 0.5, 14)
bin_width = bins[1] - bins[0]
counts, edges, patches = ax.hist(
    spread, bins=bins, density=True,
    color='#2a9d8f', edgecolor='#0f1117', linewidth=1.2, alpha=0.85, zorder=3
)

# colour bars: red for negative spread (SPY wins), green for positive (TLT wins)
for patch, left in zip(patches, edges[:-1]):
    patch.set_facecolor('#e76f51' if left + bin_width / 2 < 0 else '#2a9d8f')

# --- fitted normal curve ---
x_curve = np.linspace(spread.min() - 1.5, spread.max() + 1.5, 400)
y_curve = stats.norm.pdf(x_curve, mu, sigma)
ax.plot(x_curve, y_curve, color='#e9c46a', linewidth=2.5, zorder=5, label='Fitted normal')

# --- fill under curve: negative (red) and positive (green) regions ---
ax.fill_between(x_curve, y_curve, where=(x_curve < 0),
                color='#e76f51', alpha=0.15, zorder=2)
ax.fill_between(x_curve, y_curve, where=(x_curve >= 0),
                color='#2a9d8f', alpha=0.15, zorder=2)

# --- reference lines ---
ax.axvline(0,  color='white',   linewidth=1.2, linestyle='--', alpha=0.6, zorder=4, label='Break-even (0%)')
ax.axvline(mu, color='#e9c46a', linewidth=2.0, linestyle='-',  alpha=0.9, zorder=4, label=f'Mean = {mu:+.4f}%')

# std-dev bands
for i, (alpha, lw) in enumerate([(0.45, 1.0), (0.25, 0.7)], start=1):
    ax.axvline(mu + i*sigma, color='#e9c46a', linewidth=lw, linestyle=':', alpha=alpha, zorder=3)
    ax.axvline(mu - i*sigma, color='#e9c46a', linewidth=lw, linestyle=':', alpha=alpha, zorder=3)

# --- annotations ---
stats_text = (
    f"n = {n} trades\n"
    f"Mean  = {mu:+.4f}%\n"
    f"Std   = {sigma:.4f}%\n"
    f"TLT wins: {wins}/{n} ({wins/n*100:.1f}%)\n"
    f"t-stat = {t_stat:.4f}\n"
    f"p-value = {p_val:.4f}"
)
ax.text(0.974, 0.97, stats_text,
        transform=ax.transAxes, fontsize=9.5,
        verticalalignment='top', horizontalalignment='right',
        color='#e9c46a',
        bbox=dict(facecolor='#1a1d27', edgecolor='#e9c46a', alpha=0.85,
                  boxstyle='round,pad=0.5'))

# label individual months above bars
for i, row in qual.iterrows():
    y_pos = stats.norm.pdf(row['spread'], mu, sigma) + 0.005
    ax.text(row['spread'], y_pos, row['Month'],
            ha='center', va='bottom', fontsize=6.5,
            color='white', rotation=70, alpha=0.75)

# --- legend & labels ---
win_patch  = mpatches.Patch(color='#2a9d8f', alpha=0.85, label=f'TLT outperforms SPY ({wins} trades)')
loss_patch = mpatches.Patch(color='#e76f51', alpha=0.85, label=f'SPY outperforms TLT ({n-wins} trades)')
ax.legend(handles=[win_patch, loss_patch,
                   plt.Line2D([0],[0], color='#e9c46a', linewidth=2.5, label='Fitted normal'),
                   plt.Line2D([0],[0], color='white',   linewidth=1.2, linestyle='--', label='Break-even (0%)')],
          facecolor='#1a1d27', edgecolor='#444', labelcolor='white', fontsize=9, loc='upper left')

ax.set_xlabel('Final-Day Spread: TLT Return − SPY Return (%)', color='white', fontsize=11)
ax.set_ylabel('Probability Density', color='white', fontsize=11)
ax.set_title(
    'Distribution of Final-Day TLT vs SPY Returns\n'
    'Qualifying Months: SPY beat TLT by >5% in Main Window  |  Apr 2016 – Mar 2026',
    color='white', fontsize=13, pad=14
)

ax.tick_params(colors='white')
for spine in ax.spines.values():
    spine.set_edgecolor('#444')

ax.xaxis.label.set_color('white')
ax.yaxis.label.set_color('white')

plt.tight_layout()
plt.savefig('final_day_distribution.png', dpi=150, bbox_inches='tight',
            facecolor=fig.get_facecolor())
plt.close()
print("Saved final_day_distribution.png")

# =============================================================================
# PLOT 2: P&L DISTRIBUTION  (Long $2M TLT / Short $1M SPY, 2:1 ratio)
# =============================================================================
pnl    = (2_000_000 * qual['tlt_final'] / 100 - 1_000_000 * qual['spy_final'] / 100)
mu_p   = pnl.mean()
sig_p  = pnl.std(ddof=1)
wins_p = (pnl > 0).sum()
n_p    = len(pnl)
sharpe = (mu_p / sig_p) * np.sqrt(n_p)
t_p, p_p = stats.ttest_1samp(pnl, 0)

fig2, ax2 = plt.subplots(figsize=(11, 6))
fig2.patch.set_facecolor('#0f1117')
ax2.set_facecolor('#0f1117')

# --- histogram ---
bins_p    = np.linspace(pnl.min() - 3000, pnl.max() + 3000, 14)
bw_p      = bins_p[1] - bins_p[0]
counts_p, edges_p, patches_p = ax2.hist(
    pnl, bins=bins_p, density=True,
    color='#2a9d8f', edgecolor='#0f1117', linewidth=1.2, alpha=0.85, zorder=3
)
for patch, left in zip(patches_p, edges_p[:-1]):
    patch.set_facecolor('#e76f51' if left + bw_p / 2 < 0 else '#2a9d8f')

# --- fitted normal curve ---
x_p = np.linspace(pnl.min() - 15000, pnl.max() + 15000, 500)
y_p = stats.norm.pdf(x_p, mu_p, sig_p)
ax2.plot(x_p, y_p, color='#e9c46a', linewidth=2.5, zorder=5)
ax2.fill_between(x_p, y_p, where=(x_p < 0),  color='#e76f51', alpha=0.15, zorder=2)
ax2.fill_between(x_p, y_p, where=(x_p >= 0), color='#2a9d8f', alpha=0.15, zorder=2)

# --- reference lines ---
ax2.axvline(0,    color='white',   linewidth=1.2, linestyle='--', alpha=0.6, zorder=4)
ax2.axvline(mu_p, color='#e9c46a', linewidth=2.0, linestyle='-',  alpha=0.9, zorder=4)
for i, (alpha, lw) in enumerate([(0.45, 1.0), (0.25, 0.7)], start=1):
    ax2.axvline(mu_p + i*sig_p, color='#e9c46a', linewidth=lw, linestyle=':', alpha=alpha, zorder=3)
    ax2.axvline(mu_p - i*sig_p, color='#e9c46a', linewidth=lw, linestyle=':', alpha=alpha, zorder=3)

# --- stats box ---
stats_text2 = (
    f"n = {n_p} trades  |  Ratio: 2:1\n"
    f"Mean P&L  = ${mu_p:>10,.2f}\n"
    f"Std Dev   = ${sig_p:>10,.2f}\n"
    f"Win rate  = {wins_p}/{n_p} ({wins_p/n_p*100:.1f}%)\n"
    f"Sharpe    = {sharpe:.4f}\n"
    f"t-stat    = {t_p:.4f}\n"
    f"p-value   = {p_p:.4f}"
)
ax2.text(0.974, 0.97, stats_text2,
         transform=ax2.transAxes, fontsize=9.5,
         verticalalignment='top', horizontalalignment='right',
         color='#e9c46a',
         bbox=dict(facecolor='#1a1d27', edgecolor='#e9c46a', alpha=0.85,
                   boxstyle='round,pad=0.5'))

# --- month labels ---
for i, (month, p_val_trade) in enumerate(zip(qual['Month'], pnl)):
    y_pos = stats.norm.pdf(p_val_trade, mu_p, sig_p) + 0.000001
    ax2.text(p_val_trade, y_pos, month,
             ha='center', va='bottom', fontsize=6.5,
             color='white', rotation=70, alpha=0.75)

# --- legend ---
win_p  = mpatches.Patch(color='#2a9d8f', alpha=0.85, label=f'Winning trades ({wins_p})')
loss_p = mpatches.Patch(color='#e76f51', alpha=0.85, label=f'Losing trades ({n_p - wins_p})')
ax2.legend(handles=[win_p, loss_p,
                    plt.Line2D([0],[0], color='#e9c46a', linewidth=2.5, label='Fitted normal'),
                    plt.Line2D([0],[0], color='white',   linewidth=1.2, linestyle='--', label='Break-even ($0)')],
           facecolor='#1a1d27', edgecolor='#444', labelcolor='white', fontsize=9, loc='upper left')

# format x-axis in $K
ax2.xaxis.set_major_formatter(
    plt.FuncFormatter(lambda x, _: f'${x/1000:,.0f}K')
)

ax2.set_xlabel('Trade P&L  (Long $2M TLT / Short $1M SPY)', color='white', fontsize=11)
ax2.set_ylabel('Probability Density', color='white', fontsize=11)
ax2.set_title(
    'P&L Distribution — 2:1 Ratio  (Long $2M TLT / Short $1M SPY)\n'
    '24 Qualifying Months: SPY beat TLT by >5% in Main Window  |  Apr 2016 – Mar 2026',
    color='white', fontsize=13, pad=14
)
ax2.tick_params(colors='white')
for spine in ax2.spines.values():
    spine.set_edgecolor('#444')

plt.tight_layout()
plt.savefig('pnl_distribution.png', dpi=150, bbox_inches='tight',
            facecolor=fig2.get_facecolor())
plt.close()
print("Saved pnl_distribution.png")

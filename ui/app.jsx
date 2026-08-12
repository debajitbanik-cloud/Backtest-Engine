const { useState, useEffect, useRef, useMemo } = React;
const API = 'http://127.0.0.1:8080';

const COLORS = {
  bgRoot: '#0a0b0f',
  bgSurface: '#111318',
  bgElevated: '#161820',
  bgHover: '#1c1e26',
  border: '#22242c',
  borderActive: '#333540',
  text: '#e4e6ef',
  textSecondary: '#8b8fa3',
  textTertiary: '#5a5e6f',
  blue: '#4e8cff',
  green: '#2ecc71',
  red: '#e74c3c',
  amber: '#f0a500',
  purple: '#9b59b6',
  cyan: '#00c8e8',
};

const fmtNum = (n, dec=2) => n != null && !isNaN(n) ? Number(n).toFixed(dec) : '--';
const fmtPct = (n) => n != null && !isNaN(n) ? (Number(n) > 0 ? '+' : '') + Number(n).toFixed(2) + '%' : '--';
const fmtCur = (n) => n != null && !isNaN(n) ? '$' + Number(n).toLocaleString(undefined, {minimumFractionDigits:2, maximumFractionDigits:2}) : '--';
const ts = () => new Date().toLocaleTimeString();

function StatusDot({ on }) {
  return React.createElement('span', {
    style: {
      display: 'inline-block', width: 8, height: 8, borderRadius: '50%',
      background: on ? COLORS.green : COLORS.red,
      boxShadow: on ? `0 0 6px ${COLORS.green}` : `0 0 6px ${COLORS.red}`,
      marginRight: 6
    }
  });
}

function MetricCard({ label, value, sub, icon, color, trend }) {
  const trendArrow = trend === 'up' ? '↑' : trend === 'down' ? '↓' : '';
  const trendColor = trend === 'up' ? COLORS.green : trend === 'down' ? COLORS.red : COLORS.textSecondary;
  return React.createElement('div', {
    style: {
      background: COLORS.bgElevated, border: `1px solid ${COLORS.border}`,
      borderRadius: 8, padding: '16px', minWidth: 0
    }
  },
    React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 } },
      React.createElement('span', { style: { fontSize: 12, color: COLORS.textTertiary, textTransform: 'uppercase', letterSpacing: '0.05em' } }, label),
      icon && React.createElement('i', { 'data-lucide': icon, style: { width: 16, height: 16, color: COLORS.textTertiary } })
    ),
    React.createElement('div', { style: { fontSize: 24, fontWeight: 700, color: color || COLORS.text, lineHeight: 1.2 } }, value),
    sub && React.createElement('div', { style: { fontSize: 12, color: COLORS.textSecondary, marginTop: 4 } }, sub),
    trend && React.createElement('div', { style: { fontSize: 11, color: trendColor, marginTop: 2 } }, trendArrow + ' ' + trend)
  );
}

function Section({ title, children, style }) {
  return React.createElement('div', {
    style: {
      background: COLORS.bgSurface, border: `1px solid ${COLORS.border}`,
      borderRadius: 10, padding: 20, marginBottom: 16, ...style
    }
  },
    React.createElement('h2', {
      style: { fontSize: 14, color: COLORS.textSecondary, textTransform: 'uppercase', letterSpacing: '0.06em', fontWeight: 600, marginBottom: 16 }
    }, title),
    children
  );
}

function ProgressBar({ pct, color, height=4 }) {
  return React.createElement('div', { style: { background: COLORS.bgHover, borderRadius: height/2, height, overflow: 'hidden' } },
    React.createElement('div', {
      style: {
        width: Math.min(100, Math.max(0, pct)) + '%',
        height: '100%', background: color || COLORS.blue,
        borderRadius: height/2, transition: 'width 0.5s ease'
      }
    })
  );
}

function CorrelationMatrix({ data }) {
  if (!data) return React.createElement('div', { style: { color: COLORS.textTertiary, fontSize: 13 } }, 'Loading correlation data...');
  const abs = Math.abs(data.current || 0);
  const corrColor = abs > 0.7 ? COLORS.red : abs > 0.4 ? COLORS.amber : COLORS.green;
  const label = abs > 0.7 ? 'High correlation — poor diversification' : abs > 0.4 ? 'Moderate correlation' : 'Low correlation — good diversification';
  const timeframes = [
    { key: 'correlation_1h', label: '1h' },
    { key: 'correlation_4h', label: '4h' },
    { key: 'correlation_1d', label: '1d' },
    { key: 'correlation_7d', label: '7d' },
  ];
  return React.createElement('div', null,
    React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 } },
      React.createElement('span', { style: { fontSize: 13, color: COLORS.textSecondary } }, data.symbol_a),
      React.createElement('span', { style: { color: COLORS.textTertiary } }, '↔'),
      React.createElement('span', { style: { fontSize: 13, color: COLORS.textSecondary } }, data.symbol_b)
    ),
    React.createElement('div', { style: { display: 'flex', alignItems: 'baseline', gap: 8, marginBottom: 12 } },
      React.createElement('span', { style: { fontSize: 36, fontWeight: 700, color: corrColor, fontVariantNumeric: 'tabular-nums' } }, abs.toFixed(2)),
      React.createElement('span', { style: { fontSize: 13, color: COLORS.textSecondary } }, label)
    ),
    React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8 } },
      timeframes.map(tf => React.createElement('div', { key: tf.key, style: { background: COLORS.bgHover, borderRadius: 6, padding: '8px 12px', textAlign: 'center' } },
        React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 4 } }, tf.label),
        React.createElement('div', { style: { fontSize: 16, fontWeight: 600, color: Math.abs(data[tf.key]||0) > 0.7 ? COLORS.red : Math.abs(data[tf.key]||0) > 0.4 ? COLORS.amber : COLORS.green, fontVariantNumeric: 'tabular-nums' } }, (data[tf.key]||0).toFixed(2))
      ))
    ),
    data.trend && React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginTop: 8 } },
      'Trend: ', React.createElement('span', { style: { color: data.trend === 'rising' ? COLORS.red : data.trend === 'falling' ? COLORS.green : COLORS.textSecondary } }, data.trend.toUpperCase())
    )
  );
}

function ExposureGauge({ data }) {
  if (!data) return React.createElement('div', { style: { color: COLORS.textTertiary, fontSize: 13 } }, 'Loading exposure data...');
  const cryptoPct = data.crypto_allocation_pct || 0;
  const rwaPct = data.rwa_allocation_pct || 0;
  return React.createElement('div', null,
    React.createElement('div', { style: { display: 'flex', marginBottom: 16 } },
      React.createElement('div', { style: { flex: 1 } },
        React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 4 } }, 'Crypto'),
        React.createElement('div', { style: { fontSize: 22, fontWeight: 700, color: COLORS.blue, fontVariantNumeric: 'tabular-nums' } }, cryptoPct.toFixed(1) + '%'),
        React.createElement('div', { style: { fontSize: 11, color: COLORS.textSecondary, marginTop: 2 } }, fmtCur(data.total_crypto_exposure))
      ),
      React.createElement('div', { style: { width: 1, background: COLORS.border, margin: '0 20px' } }),
      React.createElement('div', { style: { flex: 1 } },
        React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 4 } }, 'Gold (XAUT)'),
        React.createElement('div', { style: { fontSize: 22, fontWeight: 700, color: COLORS.amber, fontVariantNumeric: 'tabular-nums' } }, rwaPct.toFixed(1) + '%'),
        React.createElement('div', { style: { fontSize: 11, color: COLORS.textSecondary, marginTop: 2 } }, fmtCur(data.total_rwa_exposure))
      )
    ),
    React.createElement('div', { style: { height: 24, borderRadius: 12, overflow: 'hidden', display: 'flex', marginBottom: 12 } },
      React.createElement('div', { style: { width: cryptoPct + '%', background: COLORS.blue, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 600, transition: 'width 0.5s' } }, cryptoPct > 15 ? 'Crypto' : ''),
      React.createElement('div', { style: { flex: 1, background: COLORS.amber, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 600 } }, rwaPct > 15 ? 'Gold' : '')
    ),
    React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 } },
      React.createElement('div', { style: { fontSize: 12, color: COLORS.textSecondary } },
        'Net Exposure: ', React.createElement('span', { style: { color: COLORS.text } }, fmtCur(data.net_exposure))
      ),
      React.createElement('div', { style: { fontSize: 12, color: COLORS.textSecondary } },
        'Concentration: ', React.createElement('span', { style: { color: (data.concentration_risk || 0) > 0.7 ? COLORS.red : COLORS.green } }, ((data.concentration_risk || 0) * 100).toFixed(0) + '%')
      )
    )
  );
}

function HedgePanel({ data }) {
  if (!data) return React.createElement('div', { style: { color: COLORS.textTertiary, fontSize: 13 } }, 'Loading hedge metrics...');
  const eff = data.hedge_effectiveness || 0;
  const effColor = eff > 0.7 ? COLORS.green : eff > 0.4 ? COLORS.amber : COLORS.red;
  const effLabel = eff > 0.7 ? 'Effective' : eff > 0.4 ? 'Partial' : 'Weak';
  return React.createElement('div', null,
    React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 } },
      React.createElement('div', null,
        React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 4 } }, 'Hedge Effectiveness (R²)'),
        React.createElement('div', { style: { fontSize: 28, fontWeight: 700, color: effColor, fontVariantNumeric: 'tabular-nums' } }, (eff*100).toFixed(1) + '%'),
        React.createElement('div', { style: { fontSize: 11, color: COLORS.textSecondary, marginTop: 2 } }, effLabel)
      ),
      React.createElement('div', null,
        React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 4 } }, 'Hedge Ratio (β)'),
        React.createElement('div', { style: { fontSize: 28, fontWeight: 700, color: COLORS.cyan, fontVariantNumeric: 'tabular-nums' } }, (data.beta||0).toFixed(3)),
        React.createElement('div', { style: { fontSize: 11, color: COLORS.textSecondary, marginTop: 2 } }, 'Optimal: ' + (data.optimal_hedge_ratio||0).toFixed(3))
      )
    ),
    React.createElement('div', { style: { background: COLORS.bgHover, borderRadius: 6, padding: 12, marginBottom: 12 } },
      React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', fontSize: 12 } },
        React.createElement('span', { style: { color: COLORS.textSecondary } }, 'Net Delta Exposure'),
        React.createElement('span', { style: { color: COLORS.text, fontFamily: 'monospace' } }, fmtCur(data.net_delta_exposure))
      ),
      React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', fontSize: 12, marginTop: 6 } },
        React.createElement('span', { style: { color: COLORS.textSecondary } }, 'Alpha'),
        React.createElement('span', { style: { color: COLORS.text, fontFamily: 'monospace' } }, (data.alpha||0).toFixed(4))
      ),
      React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', fontSize: 12, marginTop: 6 } },
        React.createElement('span', { style: { color: COLORS.textSecondary } }, 'Confidence'),
        React.createElement('span', { style: { color: COLORS.text, fontFamily: 'monospace' } }, ((data.confidence||0)*100).toFixed(0) + '%')
      )
    ),
    data.rebalance_signal && React.createElement('div', {
      style: { background: COLORS.red + '15', border: `1px solid ${COLORS.red}40`, borderRadius: 6, padding: '10px 14px', fontSize: 13, color: COLORS.red }
    }, '⚠ Rebalance needed — current ratio deviates >20% from optimal'),
    !data.rebalance_signal && React.createElement('div', {
      style: { background: COLORS.green + '15', border: `1px solid ${COLORS.green}40`, borderRadius: 6, padding: '10px 14px', fontSize: 13, color: COLORS.green }
    }, '✓ Hedge ratio within optimal range')
  );
}

function PerformancePanel({ data, symbol }) {
  if (!data) return React.createElement('div', { style: { color: COLORS.textTertiary, fontSize: 13 } }, 'Loading performance data...');
  const retColor = (data.total_return_pct||0) >= 0 ? COLORS.green : COLORS.red;
  return React.createElement('div', null,
    React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 16 } },
      React.createElement('div', null,
        React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'Total Return'),
        React.createElement('div', { style: { fontSize: 22, fontWeight: 700, color: retColor, fontVariantNumeric: 'tabular-nums' } }, fmtPct(data.total_return_pct))
      ),
      React.createElement('div', null,
        React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'Sharpe / Sortino'),
        React.createElement('div', { style: { fontSize: 22, fontWeight: 700, color: COLORS.text, fontVariantNumeric: 'tabular-nums' } }, fmtNum(data.sharpe_ratio, 2)),
        React.createElement('div', { style: { fontSize: 11, color: COLORS.textSecondary } }, 'Sortino: ' + fmtNum(data.sortino_ratio, 2))
      ),
      React.createElement('div', null,
        React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'Max Drawdown'),
        React.createElement('div', { style: { fontSize: 22, fontWeight: 700, color: COLORS.red, fontVariantNumeric: 'tabular-nums' } }, fmtPct(data.max_drawdown_pct))
      )
    ),
    React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 12, marginBottom: 16 } },
      [
        { label: 'Win Rate', value: fmtNum(data.win_rate,1)+'%', color: (data.win_rate||0) > 50 ? COLORS.green : COLORS.amber },
        { label: 'Profit Factor', value: fmtNum(data.profit_factor,2), color: (data.profit_factor||0) > 1.5 ? COLORS.green : COLORS.red },
        { label: 'Avg W/L Ratio', value: fmtNum(data.avg_win_loss_ratio,2), color: (data.avg_win_loss_ratio||0) > 1.5 ? COLORS.green : COLORS.amber },
        { label: 'Consec Wins', value: data.consecutive_wins||0, color: COLORS.blue },
      ].map((m,i) => React.createElement('div', { key: i, style: { background: COLORS.bgHover, borderRadius: 6, padding: '10px 12px', textAlign: 'center' } },
        React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 4 } }, m.label),
        React.createElement('div', { style: { fontSize: 18, fontWeight: 600, color: m.color, fontVariantNumeric: 'tabular-nums' } }, m.value)
      ))
    ),
    React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 6 } }, 'Weekly PnL'),
    React.createElement('div', { style: { display: 'flex', gap: 4, alignItems: 'flex-end', height: 48 } },
      (data.weekly_pnl || []).map((w, i) => {
        const h = Math.max(4, Math.min(44, Math.abs(w) * 400));
        return React.createElement('div', { key: i,
          style: { flex: 1, borderRadius: '3px 3px 0 0', background: w >= 0 ? COLORS.green : COLORS.red, height: h + 'px', opacity: 0.8 }
        });
      })
    )
  );
}

function DeltaStatusPanel({ health, onSwitchMode }) {
  if (!health) return React.createElement('div', { style: { color: COLORS.textTertiary, fontSize: 13 } }, 'Loading Delta connection...');
  const isReadOnly = health.mode === 'read_only';
  const modeColor = isReadOnly ? COLORS.amber : COLORS.green;
  return React.createElement('div', null,
    React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 } },
      React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 8 } },
        React.createElement(StatusDot, { on: health.connected }),
        React.createElement('span', { style: { fontSize: 14, fontWeight: 600, color: health.connected ? COLORS.green : COLORS.red } },
          health.connected ? 'Delta Exchange Connected' : 'Delta Exchange Offline')
      ),
      React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 8 } },
        React.createElement('span', { style: { fontSize: 11, color: COLORS.textTertiary } }, 'Environment: ' + (health.environment || 'production')),
        React.createElement('span', { style: { fontSize: 11, color: modeColor, textTransform: 'uppercase', fontWeight: 600, padding: '4px 10px', background: modeColor + '20', borderRadius: 4, border: `1px solid ${modeColor}40` } },
          isReadOnly ? 'Read Only' : 'Trading')
      )
    ),
    React.createElement('div', { style: { display: 'flex', gap: 8, marginBottom: 16 } },
      React.createElement('button', {
        onClick: () => onSwitchMode('read_only'),
        disabled: isReadOnly,
        style: {
          flex: 1, padding: '10px 16px', borderRadius: 6, cursor: isReadOnly ? 'default' : 'pointer',
          background: isReadOnly ? COLORS.amber + '30' : 'transparent',
          border: `1px solid ${COLORS.amber}50`, color: COLORS.amber,
          fontSize: 13, fontWeight: 600, opacity: isReadOnly ? 1 : 0.7
        }
      }, 'Read Only'),
      React.createElement('button', {
        onClick: () => onSwitchMode('trading'),
        disabled: !isReadOnly,
        style: {
          flex: 1, padding: '10px 16px', borderRadius: 6, cursor: !isReadOnly ? 'default' : 'pointer',
          background: !isReadOnly ? COLORS.green + '30' : 'transparent',
          border: `1px solid ${COLORS.green}50`, color: COLORS.green,
          fontSize: 13, fontWeight: 600, opacity: !isReadOnly ? 1 : 0.7
        }
      }, 'Trading')
    ),
    React.createElement('div', { style: { fontSize: 12, color: COLORS.textTertiary, lineHeight: 1.6 } },
      React.createElement('div', null, 'Provider: ', React.createElement('span', { style: { color: COLORS.cyan, fontWeight: 600 } }, 'CCXT → Delta Exchange')),
      React.createElement('div', null, 'API Key: ', React.createElement('span', { style: { color: health.has_auth ? COLORS.green : COLORS.red } }, health.has_auth ? 'Configured' : 'Not Configured')),
      health.error && React.createElement('div', { style: { color: COLORS.red, marginTop: 4 } }, 'Error: ' + health.error),
      React.createElement('div', { style: { marginTop: 4 } }, isReadOnly ? 'Read-only mode provides market data, tickers, and analytics.' : 'Trading mode enables balance, positions, and order management.')
    )
  );
}

function DeltaBalancePanel({ balance, mode }) {
  if (!balance) return React.createElement('div', { style: { color: COLORS.textTertiary, fontSize: 13 } }, 'No balance data available (requires trading mode)');
  if (balance.error) return React.createElement('div', { style: { color: COLORS.red, fontSize: 13 } }, balance.error);
  const marginPct = balance.margin_ratio || 0;
  const marginColor = marginPct > 85 ? COLORS.red : marginPct > 70 ? COLORS.amber : COLORS.green;
  return React.createElement('div', null,
    React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 16 } },
      React.createElement('div', null,
        React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 4 } }, 'Total Equity'),
        React.createElement('div', { style: { fontSize: 28, fontWeight: 700, color: COLORS.blue, fontVariantNumeric: 'tabular-nums' } }, fmtCur(balance.total_equity))
      ),
      React.createElement('div', null,
        React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 4 } }, 'Available Margin'),
        React.createElement('div', { style: { fontSize: 28, fontWeight: 700, color: COLORS.green, fontVariantNumeric: 'tabular-nums' } }, fmtCur(balance.available_margin))
      )
    ),
    React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12, marginBottom: 16 } },
      React.createElement('div', { style: { background: COLORS.bgHover, borderRadius: 6, padding: '10px 12px', textAlign: 'center' } },
        React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 4 } }, 'Used Margin'),
        React.createElement('div', { style: { fontSize: 16, fontWeight: 600, fontVariantNumeric: 'tabular-nums' } }, fmtCur(balance.used_margin))
      ),
      React.createElement('div', { style: { background: COLORS.bgHover, borderRadius: 6, padding: '10px 12px', textAlign: 'center' } },
        React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 4 } }, 'Unrealized PnL'),
        React.createElement('div', { style: { fontSize: 16, fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: (balance.unrealized_pnl||0) >= 0 ? COLORS.green : COLORS.red } }, fmtCur(balance.unrealized_pnl))
      ),
      React.createElement('div', { style: { background: COLORS.bgHover, borderRadius: 6, padding: '10px 12px', textAlign: 'center' } },
        React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 4 } }, 'Margin Ratio'),
        React.createElement('div', { style: { fontSize: 16, fontWeight: 600, fontVariantNumeric: 'tabular-nums', color: marginColor } }, marginPct.toFixed(1) + '%')
      )
    ),
    React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 6 } }, 'Margin Utilization'),
    React.createElement(ProgressBar, { pct: marginPct, color: marginColor, height: 6 })
  );
}

function DeltaPositionsPanel({ positions }) {
  if (!positions || positions.length === 0) return React.createElement('div', { style: { color: COLORS.textTertiary, fontSize: 13 } }, 'No open positions');
  return React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 8 } },
    positions.map((p, i) => React.createElement('div', { key: i, style: { background: COLORS.bgHover, borderRadius: 6, padding: '12px 16px' } },
      React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 } },
        React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 8 } },
          React.createElement('span', { style: { fontSize: 14, fontWeight: 700 } }, p.symbol),
          React.createElement('span', { style: { fontSize: 11, padding: '2px 8px', borderRadius: 4, background: p.side === 'long' ? COLORS.green + '20' : COLORS.red + '20', color: p.side === 'long' ? COLORS.green : COLORS.red } }, p.side.toUpperCase()),
          React.createElement('span', { style: { fontSize: 11, color: COLORS.textTertiary } }, p.leverage + 'x')
        ),
        React.createElement('span', { style: { fontSize: 14, fontWeight: 700, color: (p.unrealized_pnl||0) >= 0 ? COLORS.green : COLORS.red, fontVariantNumeric: 'tabular-nums' } }, fmtCur(p.unrealized_pnl))
      ),
      React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, fontSize: 11 } },
        React.createElement('div', null, 'Entry: ', React.createElement('span', { style: { color: COLORS.text } }, fmtNum(p.entry_price, 4))),
        React.createElement('div', null, 'Mark: ', React.createElement('span', { style: { color: COLORS.text } }, fmtNum(p.mark_price, 4))),
        React.createElement('div', null, 'Liq: ', React.createElement('span', { style: { color: COLORS.red } }, fmtNum(p.liquidation_price, 4))),
        React.createElement('div', null, 'Size: ', React.createElement('span', { style: { color: COLORS.text } }, fmtNum(p.size, 4)))
      )
    ))
  );
}

function TopGainersPanel({ gainers }) {
  if (!gainers || gainers.length === 0) return React.createElement('div', { style: { color: COLORS.textTertiary, fontSize: 13 } }, 'No gainers data (requires Delta connection)');
  return React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 4 } },
    React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 80px 100px 80px', fontSize: 10, color: COLORS.textTertiary, padding: '0 8px', marginBottom: 4 } },
      React.createElement('span', null, 'Symbol'),
      React.createElement('span', { style: { textAlign: 'right' } }, '24h %'),
      React.createElement('span', { style: { textAlign: 'right' } }, 'Volume'),
      React.createElement('span', { style: { textAlign: 'right' } }, 'Mark Price')
    ),
    gainers.map((g, i) => React.createElement('div', { key: i, style: { display: 'grid', gridTemplateColumns: '1fr 80px 100px 80px', padding: '8px', background: COLORS.bgHover, borderRadius: 4, fontSize: 12 } },
      React.createElement('span', { style: { fontWeight: 600, color: COLORS.text } }, g.symbol),
      React.createElement('span', { style: { textAlign: 'right', color: g.change_24h > 0 ? COLORS.green : COLORS.red, fontWeight: 600 } }, fmtPct(g.change_24h)),
      React.createElement('span', { style: { textAlign: 'right', color: COLORS.textSecondary } }, fmtNum(g.volume_24h, 0)),
      React.createElement('span', { style: { textAlign: 'right', color: COLORS.text } }, fmtNum(g.mark_price, 2))
    ))
  );
}

function StrategyPanel({ strategy }) {
  if (!strategy) return React.createElement('div', { style: { color: COLORS.textTertiary, fontSize: 13 } }, 'No optimized strategy available');
  const retColor = (strategy.total_return_pct||0) >= 0 ? COLORS.green : COLORS.red;
  return React.createElement('div', null,
    React.createElement('div', { style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 } },
      React.createElement('div', null,
        React.createElement('div', { style: { fontSize: 16, fontWeight: 700, color: COLORS.text } }, strategy.strategy_name || 'Optimized Strategy'),
        React.createElement('div', { style: { fontSize: 12, color: COLORS.textSecondary, marginTop: 4 } },
          'Symbol: ', React.createElement('span', { style: { color: COLORS.blue, fontWeight: 600 } }, strategy.symbol),
          ' • Timeframe: ', React.createElement('span', { style: { color: COLORS.cyan, fontWeight: 600 } }, strategy.timeframe)
        )
      ),
      React.createElement('div', { style: { textAlign: 'right' } },
        React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 4 } }, 'Confidence'),
        React.createElement('div', { style: { fontSize: 18, fontWeight: 700, color: (strategy.confidence||0) > 0.7 ? COLORS.green : COLORS.amber, fontVariantNumeric: 'tabular-nums' } }, ((strategy.confidence||0)*100).toFixed(0) + '%')
      )
    ),
    React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 16 } },
      React.createElement('div', { style: { background: COLORS.bgHover, borderRadius: 6, padding: '10px 12px', textAlign: 'center' } },
        React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 4 } }, 'Backtest Return'),
        React.createElement('div', { style: { fontSize: 18, fontWeight: 700, color: retColor, fontVariantNumeric: 'tabular-nums' } }, fmtPct(strategy.total_return_pct))
      ),
      React.createElement('div', { style: { background: COLORS.bgHover, borderRadius: 6, padding: '10px 12px', textAlign: 'center' } },
        React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 4 } }, 'Win Rate'),
        React.createElement('div', { style: { fontSize: 18, fontWeight: 700, color: COLORS.text, fontVariantNumeric: 'tabular-nums' } }, fmtNum(strategy.win_rate, 1) + '%')
      ),
      React.createElement('div', { style: { background: COLORS.bgHover, borderRadius: 6, padding: '10px 12px', textAlign: 'center' } },
        React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 4 } }, 'Trades'),
        React.createElement('div', { style: { fontSize: 18, fontWeight: 700, color: COLORS.text, fontVariantNumeric: 'tabular-nums' } }, strategy.trades || 0)
      )
    ),
    React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 8 } }, 'Indicator Configuration'),
    React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 4 } },
      Object.entries(strategy.indicators || {}).map(([k, v]) => React.createElement('div', { key: k, style: { display: 'flex', justifyContent: 'space-between', padding: '4px 8px', background: COLORS.bgHover, borderRadius: 4, fontSize: 11 } },
        React.createElement('span', { style: { color: COLORS.textSecondary } }, k.replace(/_/g, ' ')),
        React.createElement('span', { style: { color: COLORS.text, fontFamily: 'monospace', fontWeight: 600 } }, typeof v === 'number' ? v.toFixed(3) : String(v))
      ))
    )
  );
}

function AgentList({ agents }) {
  const names = Object.keys(agents || {});
  if (names.length === 0) return React.createElement('div', { style: { color: COLORS.textTertiary, fontSize: 13 } }, 'No agents connected');
  return React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 6 } },
    names.map(name => React.createElement('div', { key: name, style: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '10px 14px', background: COLORS.bgHover, borderRadius: 6 } },
      React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 8 } },
        React.createElement('span', { style: { width: 6, height: 6, borderRadius: '50%', background: COLORS.green, boxShadow: `0 0 4px ${COLORS.green}` } }),
        React.createElement('span', { style: { fontSize: 13, fontWeight: 500 } }, name)
      ),
      React.createElement('span', { style: { fontSize: 11, color: COLORS.textTertiary } },
        agents[name]?.timestamp ? new Date(agents[name].timestamp).toLocaleTimeString() : ''
      )
    ))
  );
}

function Controls({ sendCommand }) {
  const modes = [
    { label: 'Defensive', color: COLORS.blue, cmd: () => sendCommand('tune_agent', { target_agent: 'RiskCheckingAgent', parameters: { max_portfolio_drawdown: 0.05 } }) },
    { label: 'Aggressive', color: COLORS.red, cmd: () => sendCommand('tune_agent', { target_agent: 'RiskCheckingAgent', parameters: { max_portfolio_drawdown: 0.15 } }) },
    { label: 'Normal', color: COLORS.green, cmd: () => sendCommand('tune_agent', { target_agent: 'RiskCheckingAgent', parameters: { max_portfolio_drawdown: 0.10 } }) },
    { label: 'Reduce Risk', color: COLORS.amber, cmd: () => sendCommand('tune_agent', { target_agent: 'PositionSizingAgent', parameters: { max_risk_per_trade: 0.01 } }) },
    { label: 'Halt', color: COLORS.textTertiary, cmd: () => sendCommand('halt', {}) },
  ];
  return React.createElement('div', { style: { display: 'flex', flexWrap: 'wrap', gap: 8 } },
    modes.map(m => React.createElement('button', {
      key: m.label,
      onClick: m.cmd,
      style: {
        background: m.color + '20', border: `1px solid ${m.color}40`,
        color: m.color, borderRadius: 6, padding: '10px 18px',
        fontSize: 13, fontWeight: 600, cursor: 'pointer',
        transition: 'all 0.15s'
      },
      onMouseEnter: e => { e.target.style.background = m.color + '30'; e.target.style.borderColor = m.color + '60'; },
      onMouseLeave: e => { e.target.style.background = m.color + '20'; e.target.style.borderColor = m.color + '40'; },
    }, m.label))
  );
}

function MarketSummaryPanel({ summary }) {
  if (!summary) return React.createElement('div', { style: { color: COLORS.textTertiary, fontSize: 13 } }, 'Loading market summary...');
  return React.createElement('div', null,
    React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 16 } },
      React.createElement('div', { style: { background: COLORS.bgHover, borderRadius: 6, padding: '10px 12px', textAlign: 'center' } },
        React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 4 } }, 'Total Symbols'),
        React.createElement('div', { style: { fontSize: 18, fontWeight: 700, color: COLORS.text } }, summary.total_symbols)
      ),
      React.createElement('div', { style: { background: COLORS.bgHover, borderRadius: 6, padding: '10px 12px', textAlign: 'center' } },
        React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 4 } }, 'Gainers / Losers'),
        React.createElement('div', { style: { fontSize: 18, fontWeight: 700 } },
          React.createElement('span', { style: { color: COLORS.green } }, summary.gainers),
          React.createElement('span', { style: { color: COLORS.textTertiary, margin: '0 4px' } }, '/'),
          React.createElement('span', { style: { color: COLORS.red } }, summary.losers)
        )
      ),
      React.createElement('div', { style: { background: COLORS.bgHover, borderRadius: 6, padding: '10px 12px', textAlign: 'center' } },
        React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 4 } }, 'Avg 24h Change'),
        React.createElement('div', { style: { fontSize: 18, fontWeight: 700, color: summary.avg_change >= 0 ? COLORS.green : COLORS.red } }, fmtPct(summary.avg_change))
      )
    ),
    React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', fontSize: 12, color: COLORS.textSecondary, padding: '8px 12px', background: COLORS.bgHover, borderRadius: 6 } },
      React.createElement('span', null, 'Total Volume (24h)'),
      React.createElement('span', { style: { color: COLORS.cyan, fontWeight: 600, fontVariantNumeric: 'tabular-nums' } }, '$' + (summary.total_volume || 0).toLocaleString(undefined, {maximumFractionDigits: 0}))
    )
  );
}

function SpotDerivativesPanel({ data }) {
  if (!data) return React.createElement('div', { style: { color: COLORS.textTertiary, fontSize: 13 } }, 'Loading market breakdown...');
  const items = [
    { label: 'Spot', value: data.spot || 0, color: COLORS.blue },
    { label: 'Perpetual Swaps', value: data.swap || 0, color: COLORS.green },
    { label: 'Options', value: data.option || 0, color: COLORS.purple },
    { label: 'Futures', value: data.future || 0, color: COLORS.amber },
  ];
  const maxVal = Math.max(...items.map(i => i.value), 1);
  return React.createElement('div', null,
    React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 8 } },
      items.map((item, i) => React.createElement('div', { key: i },
        React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', fontSize: 12, marginBottom: 4 } },
          React.createElement('span', { style: { color: COLORS.textSecondary } }, item.label),
          React.createElement('span', { style: { color: COLORS.text, fontWeight: 600 } }, item.value)
        ),
        React.createElement(ProgressBar, { pct: (item.value / maxVal) * 100, color: item.color, height: 4 })
      ))
    ),
    React.createElement('div', { style: { marginTop: 12, fontSize: 11, color: COLORS.textTertiary, textAlign: 'center' } },
      'Total: ' + (data.total || 0) + ' markets via CCXT'
    )
  );
}

function XAUStatusPanel({ status, smc, kelly, risk }) {
  if (!status) return React.createElement('div', { style: { color: COLORS.textTertiary, fontSize: 13 } }, 'Loading XAU AI status...');
  const available = status.available;
  const modules = status.modules || {};
  return React.createElement('div', null,
    React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 } },
      React.createElement(StatusDot, { on: available }),
      React.createElement('span', { style: { fontSize: 14, fontWeight: 600, color: available ? COLORS.green : COLORS.amber } },
        available ? 'XAU AI Strategy Modules Active' : 'XAU AI Repo Not Detected')
    ),
    React.createElement('div', { style: { fontSize: 12, color: COLORS.textTertiary, marginBottom: 12 } },
      status.error ? status.error : 'Optional integration with xau-ai-trading-bot'
    ),
    React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8, marginBottom: 16 } },
      [
        { label: 'SMC', on: modules.smc, icon: 'git-branch' },
        { label: 'HMM Regime', on: modules.regime, icon: 'activity' },
        { label: 'Kelly', on: modules.kelly, icon: 'percent' },
        { label: 'Risk Analytics', on: modules.risk_analytics, icon: 'shield' },
        { label: 'Feature Eng', on: modules.feature_eng, icon: 'cpu' },
        { label: 'Risk Engine', on: modules.risk_engine, icon: 'alert-triangle' },
      ].map((m, i) => React.createElement('div', { key: i, style: { background: COLORS.bgHover, borderRadius: 6, padding: '10px 12px', textAlign: 'center' } },
        React.createElement('i', { 'data-lucide': m.icon, style: { width: 14, height: 14, color: m.on ? COLORS.green : COLORS.textTertiary, marginBottom: 6 } }),
        React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 4 } }, m.label),
        React.createElement('div', { style: { fontSize: 12, fontWeight: 600, color: m.on ? COLORS.green : COLORS.red } }, m.on ? 'Active' : 'Missing')
      ))
    ),
    smc && smc.current_price && React.createElement('div', { style: { background: COLORS.bgHover, borderRadius: 6, padding: 12, marginBottom: 12 } },
      React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 6 } }, 'SMC Swing Levels'),
      React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', fontSize: 12 } },
        React.createElement('span', { style: { color: COLORS.textSecondary } }, 'Current Price'),
        React.createElement('span', { style: { color: COLORS.text, fontWeight: 600 } }, '$' + (smc.current_price || 0).toFixed(2))
      ),
      React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', fontSize: 12, marginTop: 6 } },
        React.createElement('span', { style: { color: COLORS.textSecondary } }, 'Swing High'),
        React.createElement('span', { style: { color: COLORS.red } }, smc.swing_highs && smc.swing_highs.length > 0 ? '$' + smc.swing_highs[smc.swing_highs.length-1].price.toFixed(2) : '--')
      ),
      React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', fontSize: 12, marginTop: 6 } },
        React.createElement('span', { style: { color: COLORS.textSecondary } }, 'Swing Low'),
        React.createElement('span', { style: { color: COLORS.green } }, smc.swing_lows && smc.swing_lows.length > 0 ? '$' + smc.swing_lows[smc.swing_lows.length-1].price.toFixed(2) : '--')
      )
    ),
    kelly && React.createElement('div', { style: { background: COLORS.bgHover, borderRadius: 6, padding: 12, marginBottom: 12 } },
      React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 6 } }, 'Kelly Position Scaling'),
      React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', fontSize: 12 } },
        React.createElement('span', { style: { color: COLORS.textSecondary } }, 'Kelly Fraction'),
        React.createElement('span', { style: { color: COLORS.cyan, fontWeight: 600 } }, (kelly.kelly_fraction || 0).toFixed(4))
      ),
      React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', fontSize: 12, marginTop: 6 } },
        React.createElement('span', { style: { color: COLORS.textSecondary } }, 'Recommendation'),
        React.createElement('span', { style: { color: kelly.recommendation === 'INCREASE' ? COLORS.green : COLORS.amber, fontWeight: 600 } }, kelly.recommendation)
      )
    ),
    risk && risk.sharpe_ratio !== undefined && React.createElement('div', { style: { background: COLORS.bgHover, borderRadius: 6, padding: 12 } },
      React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 6 } }, 'Risk Analytics (XAU AI)'),
      React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 } },
        [
          { label: 'Sharpe', value: (risk.sharpe_ratio||0).toFixed(2) },
          { label: 'Sortino', value: (risk.sortino_ratio||0).toFixed(2) },
          { label: 'Max DD', value: ((risk.max_drawdown||0)*100).toFixed(2) + '%' },
          { label: 'Win Rate', value: ((risk.win_rate||0)*100).toFixed(1) + '%' },
        ].map((m, i) => React.createElement('div', { key: i, style: { display: 'flex', justifyContent: 'space-between', fontSize: 12, padding: '4px 0' } },
          React.createElement('span', { style: { color: COLORS.textSecondary } }, m.label),
          React.createElement('span', { style: { color: COLORS.text } }, m.value)
        ))
      )
    )
  );
}

function RecommendationPanel({ recommendations }) {
  if (!recommendations || Object.keys(recommendations).length === 0) {
    return React.createElement('div', { style: { color: COLORS.textTertiary, fontSize: 13 } }, 'Waiting for agent signals...');
  }
  
  return React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 12 } },
    Object.entries(recommendations).map(([symbol, rec]) => {
      if (!rec) return null;
      const dirColor = rec.direction === 'long' ? COLORS.green : rec.direction === 'short' ? COLORS.red : COLORS.amber;
      const dirLabel = rec.direction === 'long' ? 'LONG' : rec.direction === 'short' ? 'SHORT' : 'FLAT';
      const confPct = ((rec.confidence || 0) * 100).toFixed(0);
      
      return React.createElement('div', { key: symbol, style: { background: COLORS.bgHover, borderRadius: 8, padding: '16px' } },
        React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 } },
          React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 10 } },
            React.createElement('span', { style: { fontSize: 16, fontWeight: 700, color: COLORS.text } }, symbol),
            React.createElement('span', { style: { fontSize: 11, padding: '3px 10px', borderRadius: 4, background: dirColor + '20', color: dirColor, fontWeight: 700, border: `1px solid ${dirColor}40` } }, dirLabel)
          ),
          React.createElement('div', { style: { textAlign: 'right' } },
            React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 2 } }, 'Confidence'),
            React.createElement('div', { style: { fontSize: 20, fontWeight: 700, color: confPct > 70 ? COLORS.green : confPct > 50 ? COLORS.amber : COLORS.red, fontVariantNumeric: 'tabular-nums' } }, confPct + '%')
          )
        ),
        React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 12 } },
          React.createElement('div', { style: { background: COLORS.bgSurface, borderRadius: 6, padding: '10px 12px', textAlign: 'center' } },
            React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 4 } }, 'Timeframe'),
            React.createElement('div', { style: { fontSize: 18, fontWeight: 700, color: COLORS.cyan } }, rec.recommended_timeframe || '--')
          ),
          React.createElement('div', { style: { background: COLORS.bgSurface, borderRadius: 6, padding: '10px 12px', textAlign: 'center' } },
            React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 4 } }, 'Confluence'),
            React.createElement('div', { style: { fontSize: 18, fontWeight: 700, color: COLORS.blue } }, ((rec.confluence_score || 0) * 100).toFixed(0) + '%')
          ),
          React.createElement('div', { style: { background: COLORS.bgSurface, borderRadius: 6, padding: '10px 12px', textAlign: 'center' } },
            React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 4 } }, 'Risk'),
            React.createElement('div', { style: { fontSize: 18, fontWeight: 700, color: COLORS.green } }, ((rec.risk_score || 0) * 100).toFixed(0) + '%')
          )
        ),
        rec.alignment && React.createElement('div', { style: { marginBottom: 12 } },
          React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 6 } }, 'Agent Alignment'),
          React.createElement('div', { style: { display: 'flex', flexWrap: 'wrap', gap: 6 } },
            Object.entries(rec.alignment).map(([agent, signal]) => {
              const sColor = signal === 'bullish' || signal === 'strong_bullish' || signal === 'long' ? COLORS.green : signal === 'bearish' || signal === 'strong_bearish' || signal === 'short' ? COLORS.red : COLORS.amber;
              return React.createElement('span', { key: agent, style: { fontSize: 11, padding: '3px 10px', borderRadius: 4, background: sColor + '15', color: sColor, border: `1px solid ${sColor}30` } },
                agent.replace(/_agent/g, '').replace(/_/g, ' ') + ': ' + signal
              );
            })
          )
        ),
        rec.reasoning && rec.reasoning.length > 0 && React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, lineHeight: 1.5 } },
          rec.reasoning.map((r, i) => React.createElement('div', { key: i }, '• ' + r))
        )
      );
    })
  );
}

function TopGainerChart({ chart }) {
  if (!chart) return React.createElement('div', { style: { color: COLORS.textTertiary, fontSize: 13 } }, 'Loading top gainer chart...');
  if (chart.error) return React.createElement('div', { style: { color: COLORS.red, fontSize: 13 } }, chart.error);
  
  const candles = chart.candles || [];
  const symbol = chart.symbol || '--';
  const change = chart.change_24h || 0;
  const changeColor = change >= 0 ? COLORS.green : COLORS.red;
  
  // Build a simple SVG candlestick chart
  const width = 800;
  const height = 300;
  const padding = 40;
  
  let chartContent;
  if (candles.length === 0) {
    chartContent = React.createElement('div', { style: { padding: 40, textAlign: 'center', color: COLORS.textTertiary } }, 'No OHLCV data available for this symbol');
  } else {
    const prices = candles.flatMap(c => [c[2], c[3]]); // high, low
    const minPrice = Math.min(...prices);
    const maxPrice = Math.max(...prices);
    const priceRange = maxPrice - minPrice || 1;
    const candleWidth = (width - padding * 2) / candles.length;
    
    chartContent = React.createElement('svg', { width: '100%', height: height, viewBox: `0 0 ${width} ${height}` },
      React.createElement('line', { x1: padding, y1: 10, x2: padding, y2: height - padding, stroke: COLORS.border, strokeWidth: 1 }),
      React.createElement('line', { x1: padding, y1: height - padding, x2: width - padding, y2: height - padding, stroke: COLORS.border, strokeWidth: 1 }),
      candles.map((c, i) => {
        const [timestamp, open, high, low, close, volume] = c;
        const x = padding + i * candleWidth + candleWidth / 2;
        const yOpen = height - padding - ((open - minPrice) / priceRange) * (height - padding * 2);
        const yClose = height - padding - ((close - minPrice) / priceRange) * (height - padding * 2);
        const yHigh = height - padding - ((high - minPrice) / priceRange) * (height - padding * 2);
        const yLow = height - padding - ((low - minPrice) / priceRange) * (height - padding * 2);
        const color = close >= open ? COLORS.green : COLORS.red;
        const bodyTop = Math.min(yOpen, yClose);
        const bodyHeight = Math.max(Math.abs(yClose - yOpen), 1);
        
        return React.createElement('g', { key: i },
          React.createElement('line', { x1: x, y1: yHigh, x2: x, y2: yLow, stroke: color, strokeWidth: 1 }),
          React.createElement('rect', { x: x - candleWidth * 0.35, y: bodyTop, width: candleWidth * 0.7, height: bodyHeight, fill: color, rx: 1 })
        );
      })
    );
  }
  
  return React.createElement('div', null,
    React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 } },
      React.createElement('div', null,
        React.createElement('div', { style: { fontSize: 18, fontWeight: 700, color: COLORS.text } }, symbol),
        React.createElement('div', { style: { fontSize: 12, color: COLORS.textSecondary, marginTop: 4 } }, 'Highest 24h gainer')
      ),
      React.createElement('div', { style: { fontSize: 24, fontWeight: 700, color: changeColor, fontVariantNumeric: 'tabular-nums' } }, fmtPct(change))
    ),
    chartContent,
    React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginTop: 8, textAlign: 'center' } },
      candles.length > 0 ? `${candles.length} candles • 15m timeframe` : 'Fetching OHLCV...'
    )
  );
}

function TradingSuggestionsPanel({ suggestions, openPositions }) {
  if (!suggestions || suggestions.length === 0) {
    return React.createElement('div', { style: { color: COLORS.textTertiary, fontSize: 13 } }, 'Generating real-time suggestions...');
  }
  
  return React.createElement('div', null,
    React.createElement('div', { style: { fontSize: 12, color: COLORS.textTertiary, marginBottom: 16 } },
      'Real-time recommendations combined with open positions and market momentum'
    ),
    React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 10 } },
      suggestions.map((s, i) => {
        const dirColor = s.direction === 'long' ? COLORS.green : s.direction === 'short' ? COLORS.red : COLORS.amber;
        const dirLabel = s.direction === 'long' ? 'LONG' : s.direction === 'short' ? 'SHORT' : 'FLAT';
        const confPct = ((s.confidence || 0) * 100).toFixed(0);
        const hasPosition = s.has_position;
        
        return React.createElement('div', { key: i, style: {
          background: COLORS.bgHover, borderRadius: 8, padding: '16px',
          border: hasPosition ? `1px solid ${COLORS.green}50` : `1px solid ${COLORS.border}`,
        } },
          React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 } },
            React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 10 } },
              React.createElement('span', { style: { fontSize: 16, fontWeight: 700, color: COLORS.text } }, s.symbol),
              React.createElement('span', { style: { fontSize: 11, padding: '3px 10px', borderRadius: 4, background: dirColor + '20', color: dirColor, fontWeight: 700, border: `1px solid ${dirColor}40` } }, dirLabel),
              hasPosition && React.createElement('span', { style: { fontSize: 10, padding: '2px 8px', borderRadius: 4, background: COLORS.green + '20', color: COLORS.green, fontWeight: 600 } }, 'OPEN POSITION'),
              s.source && React.createElement('span', { style: { fontSize: 10, padding: '2px 8px', borderRadius: 4, background: COLORS.cyan + '20', color: COLORS.cyan } }, 'MOMENTUM')
            ),
            React.createElement('div', { style: { textAlign: 'right' } },
              React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 2 } }, 'Confidence'),
              React.createElement('div', { style: { fontSize: 18, fontWeight: 700, color: confPct > 70 ? COLORS.green : confPct > 50 ? COLORS.amber : COLORS.red } }, confPct + '%')
            )
          ),
          React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 12 } },
            React.createElement('div', { style: { background: COLORS.bgSurface, borderRadius: 6, padding: '8px 10px', textAlign: 'center' } },
              React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 3 } }, 'Timeframe'),
              React.createElement('div', { style: { fontSize: 15, fontWeight: 700, color: COLORS.cyan } }, s.recommended_timeframe || '15m')
            ),
            React.createElement('div', { style: { background: COLORS.bgSurface, borderRadius: 6, padding: '8px 10px', textAlign: 'center' } },
              React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 3 } }, '24h Change'),
              React.createElement('div', { style: { fontSize: 15, fontWeight: 700, color: (s.change_24h || 0) >= 0 ? COLORS.green : COLORS.red } }, fmtPct(s.change_24h))
            ),
            React.createElement('div', { style: { background: COLORS.bgSurface, borderRadius: 6, padding: '8px 10px', textAlign: 'center' } },
              React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 3 } }, 'Mark Price'),
              React.createElement('div', { style: { fontSize: 15, fontWeight: 700, color: COLORS.text } }, s.mark_price ? '$' + Number(s.mark_price).toFixed(2) : '--')
            )
          ),
          hasPosition && s.position && React.createElement('div', { style: { background: COLORS.green + '10', borderRadius: 6, padding: '10px 12px', marginBottom: 12, fontSize: 12 } },
            React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', marginBottom: 4 } },
              React.createElement('span', { style: { color: COLORS.textSecondary } }, 'Position: ' + s.position.side.toUpperCase() + ' ' + s.position.size),
              React.createElement('span', { style: { color: (s.position.unrealized_pnl || 0) >= 0 ? COLORS.green : COLORS.red, fontWeight: 600 } }, fmtCur(s.position.unrealized_pnl))
            ),
            React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between' } },
              React.createElement('span', { style: { color: COLORS.textSecondary } }, 'Entry: ' + fmtNum(s.position.entry_price, 4)),
              React.createElement('span', { style: { color: COLORS.textSecondary } }, 'Mark: ' + fmtNum(s.position.mark_price, 4))
            )
          )
        );
      })
    )
  );
}

function MarginAllocationPanel({ allocations, summary, accountEquity, availableMargin }) {
  if (!allocations || allocations.length === 0) {
    return React.createElement('div', { style: { color: COLORS.textTertiary, fontSize: 13 } }, 'Generating margin allocations...');
  }
  
  return React.createElement('div', null,
    accountEquity > 0 && React.createElement('div', { style: { display: 'flex', gap: 16, marginBottom: 16, fontSize: 12, color: COLORS.textSecondary } },
      React.createElement('span', null, 'Account Equity: ', React.createElement('span', { style: { color: COLORS.text, fontWeight: 600 } }, fmtCur(accountEquity))),
      React.createElement('span', null, 'Available Margin: ', React.createElement('span', { style: { color: COLORS.text, fontWeight: 600 } }, fmtCur(availableMargin)))
    ),
    summary && React.createElement('div', { style: { background: COLORS.bgHover, borderRadius: 8, padding: '16px', marginBottom: 16, fontSize: 12, lineHeight: 1.6, color: COLORS.textSecondary } },
      React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 8 } }, 'Why these recommendations'),
      summary.split('\n').map((line, i) => React.createElement('div', { key: i, style: { paddingLeft: line.startsWith('  ') ? 16 : 0 } }, line))
    ),
    React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 10 } },
      allocations.map((a, i) => {
        const dirColor = a.direction === 'long' ? COLORS.green : a.direction === 'short' ? COLORS.red : COLORS.amber;
        const dirLabel = a.direction === 'long' ? 'LONG' : a.direction === 'short' ? 'SHORT' : 'FLAT';
        const marginPct = a.recommended_margin_pct || 0;
        const profitColor = (a.estimated_profit_usd || 0) >= 0 ? COLORS.green : COLORS.red;
        
        return React.createElement('div', { key: i, style: { background: COLORS.bgHover, borderRadius: 8, padding: '16px' } },
          React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 } },
            React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 10 } },
              React.createElement('span', { style: { fontSize: 16, fontWeight: 700, color: COLORS.text } }, a.symbol),
              React.createElement('span', { style: { fontSize: 11, padding: '3px 10px', borderRadius: 4, background: dirColor + '20', color: dirColor, fontWeight: 700, border: `1px solid ${dirColor}40` } }, dirLabel)
            ),
            React.createElement('div', { style: { textAlign: 'right' } },
              React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, marginBottom: 2 } }, 'Profit Probability'),
              React.createElement('div', { style: { fontSize: 18, fontWeight: 700, color: (a.profit_probability||0) > 0.6 ? COLORS.green : COLORS.amber } }, ((a.profit_probability||0)*100).toFixed(0) + '%')
            )
          ),
          React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 12 } },
            React.createElement('div', { style: { background: COLORS.bgSurface, borderRadius: 6, padding: '10px 12px', textAlign: 'center' } },
              React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 4 } }, 'Margin Allotment'),
              React.createElement('div', { style: { fontSize: 16, fontWeight: 700, color: COLORS.cyan } }, fmtCur(a.recommended_margin_usd)),
              React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginTop: 2 } }, marginPct.toFixed(1) + '% of equity')
            ),
            React.createElement('div', { style: { background: COLORS.bgSurface, borderRadius: 6, padding: '10px 12px', textAlign: 'center' } },
              React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 4 } }, 'Leverage'),
              React.createElement('div', { style: { fontSize: 16, fontWeight: 700, color: COLORS.text } }, a.leverage.toFixed(1) + 'x')
            ),
            React.createElement('div', { style: { background: COLORS.bgSurface, borderRadius: 6, padding: '10px 12px', textAlign: 'center' } },
              React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 4 } }, 'Est. Profit'),
              React.createElement('div', { style: { fontSize: 16, fontWeight: 700, color: profitColor } }, fmtCur(a.estimated_profit_usd))
            ),
            React.createElement('div', { style: { background: COLORS.bgSurface, borderRadius: 6, padding: '10px 12px', textAlign: 'center' } },
              React.createElement('div', { style: { fontSize: 10, color: COLORS.textTertiary, marginBottom: 4 } }, 'Est. Risk'),
              React.createElement('div', { style: { fontSize: 16, fontWeight: 700, color: COLORS.red } }, fmtCur(a.estimated_risk_usd))
            )
          ),
          React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 12 } },
            React.createElement('div', { style: { fontSize: 11, color: COLORS.textSecondary } }, 'Volatility: ', React.createElement('span', { style: { color: COLORS.text } }, (a.volatility_atr_pct||0).toFixed(2) + '%')),
            React.createElement('div', { style: { fontSize: 11, color: COLORS.textSecondary } }, 'Volume: ', React.createElement('span', { style: { color: COLORS.text } }, (a.volume_ratio||0).toFixed(1) + 'x')),
            React.createElement('div', { style: { fontSize: 11, color: COLORS.textSecondary } }, 'R:R: ', React.createElement('span', { style: { color: COLORS.text } }, (a.risk_reward_ratio||0).toFixed(2))),
            React.createElement('div', { style: { fontSize: 11, color: COLORS.textSecondary } }, 'Liquidity: ', React.createElement('span', { style: { color: COLORS.text } }, fmtCur(a.liquidity_depth_usd)))
          ),
          a.reasoning && a.reasoning.length > 0 && React.createElement('div', { style: { fontSize: 11, color: COLORS.textTertiary, lineHeight: 1.5, borderTop: `1px solid ${COLORS.border}`, paddingTop: 8 } },
            a.reasoning.slice(0, 4).map((r, j) => React.createElement('div', { key: j }, '• ' + r))
          )
        );
      })
    )
  );
}

function OptionsPanel({ candidates, payoff, onSelectOption }) {
  if (!candidates) return React.createElement('div', { style: { color: COLORS.textTertiary, fontSize: 13 } }, 'Scanning Delta options...');
  
  return React.createElement('div', null,
    React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 } },
      React.createElement('div', { style: { fontSize: 12, color: COLORS.textSecondary } },
        'Inflated OTM contracts found: ', React.createElement('span', { style: { color: COLORS.text, fontWeight: 600 } }, candidates.length)
      ),
      React.createElement('div', { style: { fontSize: 12, color: COLORS.textTertiary, textAlign: 'right' } },
        'Click a contract to view payoff simulation'
      )
    ),
    React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '2fr 1fr', gap: 16 } },
      React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 8, maxHeight: 500, overflow: 'auto' } },
        candidates.length === 0
          ? React.createElement('div', { style: { color: COLORS.textTertiary, fontSize: 13 } }, 'No matching options found')
          : candidates.map((c, i) => {
              const premiumColor = (c.premium_pct || 0) > 50 ? COLORS.green : (c.premium_pct || 0) > 20 ? COLORS.amber : COLORS.textSecondary;
              return React.createElement('div', {
                key: i,
                onClick: () => onSelectOption(c),
                style: {
                  background: COLORS.bgHover, borderRadius: 8, padding: '12px 16px', cursor: 'pointer',
                  border: `1px solid ${COLORS.border}`, transition: 'border 0.15s'
                },
                onMouseEnter: e => { e.target.style.borderColor = COLORS.blue; },
                onMouseLeave: e => { e.target.style.borderColor = COLORS.border; },
              },
                React.createElement('div', { style: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 } },
                  React.createElement('span', { style: { fontSize: 13, fontWeight: 700, color: COLORS.text, fontFamily: 'monospace' } }, c.symbol),
                  React.createElement('span', { style: { fontSize: 13, fontWeight: 700, color: premiumColor } }, '+' + (c.premium_pct || 0).toFixed(1) + '%')
                ),
                React.createElement('div', { style: { fontSize: 11, color: COLORS.textSecondary, lineHeight: 1.5 } },
                  React.createElement('div', null, c.option_type.toUpperCase(), ' • Strike: ', c.strike, ' • Spot: ', c.spot_price),
                  React.createElement('div', null, 'OTM: ', (c.otm_pct || 0).toFixed(1) + '% • Days: ', (c.days_to_expiry || 0).toFixed(1)),
                  React.createElement('div', null, 'IV: ', (c.iv || 0).toFixed(0) + '% • Mark: $', (c.mark_price || 0).toFixed(2))
                )
              );
            })
      ),
      React.createElement(OptionPayoffChart, { payoff })
    )
  );
}

function OptionPayoffChart({ payoff }) {
  if (!payoff) return React.createElement('div', { style: { color: COLORS.textTertiary, fontSize: 13, padding: 20 } }, 'Select an option to view payoff');
  
  const width = 400;
  const height = 250;
  const padding = 30;
  const prices = payoff.spot_prices || [];
  const shortCall = payoff.short_call_pnl || [];
  const shortPut = payoff.short_put_pnl || [];
  const longCall = payoff.long_call_pnl || [];
  const longPut = payoff.long_put_pnl || [];
  
  if (prices.length === 0) return React.createElement('div', { style: { color: COLORS.textTertiary, fontSize: 13 } }, 'No payoff data');
  
  const allValues = [...shortCall, ...shortPut, ...longCall, ...longPut].filter(v => isFinite(v));
  const minVal = Math.min(...allValues);
  const maxVal = Math.max(...allValues);
  const range = maxVal - minVal || 1;
  const minPrice = Math.min(...prices);
  const maxPrice = Math.max(...prices);
  const priceRange = maxPrice - minPrice || 1;
  
  const xScale = (v) => padding + ((v - minPrice) / priceRange) * (width - padding * 2);
  const yScale = (v) => height - padding - ((v - minVal) / range) * (height - padding * 2);
  
  const line = (data, color) => {
    return React.createElement('path', {
      d: data.map((v, i) => (i === 0 ? 'M' : 'L') + xScale(prices[i]).toFixed(1) + ' ' + yScale(v).toFixed(1)).join(' '),
      stroke: color, fill: 'none', strokeWidth: 2,
    });
  };
  
  return React.createElement('div', null,
    React.createElement('div', { style: { fontSize: 12, color: COLORS.textTertiary, marginBottom: 8 } }, 'Payoff Simulation'),
    React.createElement('svg', { width: '100%', height: height, viewBox: `0 0 ${width} ${height}` },
      React.createElement('line', { x1: padding, y1: yScale(0), x2: width - padding, y2: yScale(0), stroke: COLORS.border, strokeWidth: 1, strokeDasharray: '4 2' }),
      React.createElement('line', { x1: padding, y1: 10, x2: padding, y2: height - padding, stroke: COLORS.border, strokeWidth: 1 }),
      line(shortCall, COLORS.green),
      line(shortPut, COLORS.red),
      line(longCall, COLORS.cyan),
      line(longPut, COLORS.amber)
    ),
    React.createElement('div', { style: { display: 'flex', gap: 12, fontSize: 10, color: COLORS.textTertiary, marginTop: 8, flexWrap: 'wrap' } },
      React.createElement('span', { style: { color: COLORS.green } }, 'Short Call'),
      React.createElement('span', { style: { color: COLORS.red } }, 'Short Put'),
      React.createElement('span', { style: { color: COLORS.cyan } }, 'Long Call'),
      React.createElement('span', { style: { color: COLORS.amber } }, 'Long Put')
    ),
    payoff.break_even_short_call && React.createElement('div', { style: { fontSize: 11, color: COLORS.textSecondary, marginTop: 8 } },
      'Break-even (short call): $' + payoff.break_even_short_call.toFixed(2)
    )
  );
}

function App() {
  const [activeView, setActiveView] = useState('overview');
  const [status, setStatus] = useState({ running: false, agents: {} });
  const [signals, setSignals] = useState([]);
  const [connected, setConnected] = useState(false);
  const [corr, setCorr] = useState(null);
  const [exposure, setExposure] = useState(null);
  const [hedge, setHedge] = useState(null);
  const [perfSol, setPerfSol] = useState(null);
  const [perfXaut, setPerfXaut] = useState(null);
  const [deltaHealth, setDeltaHealth] = useState(null);
  const [deltaGainers, setDeltaGainers] = useState([]);
  const [deltaBalance, setDeltaBalance] = useState(null);
  const [deltaPositions, setDeltaPositions] = useState([]);
  const [strategy, setStrategy] = useState(null);
  const [ccxtHealth, setCcxtHealth] = useState(null);
  const [ccxtGainers, setCcxtGainers] = useState([]);
  const [marketSummary, setMarketSummary] = useState(null);
  const [spotDerivs, setSpotDerivs] = useState(null);
  const [xauStatus, setXauStatus] = useState(null);
  const [xauSmc, setXauSmc] = useState(null);
  const [xauKelly, setXauKelly] = useState(null);
  const [xauRisk, setXauRisk] = useState(null);
  const [recommendations, setRecommendations] = useState({});
  const [topGainerChart, setTopGainerChart] = useState(null);
  const [tradingSuggestions, setTradingSuggestions] = useState([]);
  const [openPositions, setOpenPositions] = useState([]);
  const [allocations, setAllocations] = useState([]);
  const [allocationSummary, setAllocationSummary] = useState('');
  const [accountEquity, setAccountEquity] = useState(0);
  const [availableMargin, setAvailableMargin] = useState(0);
  const [optionCandidates, setOptionCandidates] = useState([]);
  const [optionPayoff, setOptionPayoff] = useState(null);
  const [logs, setLogs] = useState([]);
  const eventRef = useRef(null);

  const fetchJSON = async (path, opts) => { try { const r = await fetch(API + path, opts); return r.ok ? r.json() : null; } catch(e) { return null; } };

  useEffect(() => {
    const poll = async () => {
      const [s, sig, c, e, h, ps, px, dh, dg, db, dp, st, ch, cg, ms, sd, xs, xsmc, xk, xr, rec, tgc, tsg, alloc, opts] = await Promise.all([
        fetchJSON('/status'),
        fetchJSON('/signals?limit=10'),
        fetchJSON('/metrics/correlation'),
        fetchJSON('/metrics/exposure'),
        fetchJSON('/metrics/hedge'),
        fetchJSON('/metrics/performance/SOLUSDT'),
        fetchJSON('/metrics/performance/XAUTUSDT'),
        fetchJSON('/delta/health'),
        fetchJSON('/delta/top-gainers?limit=10'),
        fetchJSON('/delta/balance'),
        fetchJSON('/delta/positions'),
        fetchJSON('/strategy/deployed'),
        fetchJSON('/ccxt/health'),
        fetchJSON('/ccxt/top-gainers?limit=10'),
        fetchJSON('/ccxt/market-summary'),
        fetchJSON('/ccxt/markets'),
        fetchJSON('/xau/status'),
        fetchJSON('/xau/smc?symbol=XAUTUSDT&timeframe=15m'),
        fetchJSON('/xau/kelly?win_rate=0.55&avg_win=8.0&avg_loss=4.0'),
        fetchJSON('/xau/risk'),
        fetchJSON('/recommendations'),
        fetchJSON('/delta/top-gainer-chart'),
        fetchJSON('/trading/suggestions'),
        fetchJSON('/trading/allocations'),
        fetchJSON('/options/scan?limit=30'),
      ]);
      if (s) setStatus(s);
      if (sig) setSignals(sig.signals || []);
      if (c) setCorr(c);
      if (e) setExposure(e);
      if (h) setHedge(h);
      if (ps) setPerfSol(ps);
      if (px) setPerfXaut(px);
      if (dh) setDeltaHealth(dh);
      if (dg && dg.gainers) setDeltaGainers(dg.gainers);
      if (db) setDeltaBalance(db);
      if (dp && dp.positions) setDeltaPositions(dp.positions);
      if (st && st.deployed) setStrategy(st.deployed);
      if (ch) setCcxtHealth(ch);
      if (cg && cg.gainers) setCcxtGainers(cg.gainers);
      if (ms) setMarketSummary(ms);
      if (sd && sd.spot_vs_derivatives) setSpotDerivs(sd.spot_vs_derivatives);
      if (xs) setXauStatus(xs);
      if (xsmc) setXauSmc(xsmc);
      if (xk) setXauKelly(xk);
      if (xr) setXauRisk(xr);
      if (rec && rec.recommendations) setRecommendations(rec.recommendations);
      if (tgc) setTopGainerChart(tgc);
      if (tsg) {
        setTradingSuggestions(tsg.suggestions || []);
        setOpenPositions(tsg.open_positions || []);
      }
      if (alloc) {
        setAllocations(alloc.allocations || []);
        setAllocationSummary(alloc.summary || '');
        setAccountEquity(alloc.account_equity || 0);
        setAvailableMargin(alloc.available_margin || 0);
      }
      if (opts && opts.candidates) setOptionCandidates(opts.candidates);
    };
    poll();
    const interval = setInterval(poll, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    const es = new EventSource(API + '/events');
    es.onopen = () => setConnected(true);
    es.onmessage = (ev) => {
      try {
        const d = JSON.parse(ev.data);
        if (d.type === 'keepalive') return;
        setLogs(prev => [{ time: ts(), type: d.type, source: d.source, payload: JSON.stringify(d.payload).slice(0, 200) }, ...prev].slice(0, 80));
      } catch(e) {}
    };
    es.onerror = () => setConnected(false);
    eventRef.current = es;
    return () => es.close();
  }, []);

  const selectOptionForPayoff = async (option) => {
    if (!option) return;
    const query = `/options/payoff?spot=${option.spot_price}&strike=${option.strike}&premium=${option.mark_price}&option_type=${option.option_type}&range_pct=0.3`;
    const data = await fetchJSON(query);
    if (data) setOptionPayoff(data);
  };

  const sendCommand = async (cmd, params={}) => {
    try { await fetch(API+'/command', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({command: cmd, params}) }); }
    catch(e) { console.error(e); }
  };

  const switchDeltaMode = async (mode) => {
    try {
      const res = await fetch(API + '/delta/mode', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({mode}) });
      if (res.ok) {
        const data = await res.json();
        if (data.mode) setDeltaHealth(prev => ({...prev, mode: data.mode}));
        // Re-poll to get balance/positions if switching to trading
        setTimeout(() => {
          fetchJSON('/delta/balance').then(b => setDeltaBalance(b));
          fetchJSON('/delta/positions').then(p => setDeltaPositions(p.positions || []));
        }, 500);
      }
    } catch(e) { console.error(e); }
  };

  const tabs = [
    { key: 'overview', label: 'Overview', icon: 'layout-dashboard' },
    { key: 'suggestions', label: 'Live Suggestions', icon: 'compass' },
    { key: 'allocations', label: 'Margin Allocations', icon: 'scale' },
    { key: 'options', label: 'Options', icon: 'layers' },
    { key: 'recommendations', label: 'Recommendations', icon: 'target' },
    { key: 'delta', label: 'Delta Exchange', icon: 'plug' },
    { key: 'markets', label: 'Markets', icon: 'globe' },
    { key: 'strategy', label: 'Deployed Strategy', icon: 'brain' },
    { key: 'xau', label: 'XAU AI', icon: 'shield' },
    { key: 'correlation', label: 'Correlation', icon: 'git-compare' },
    { key: 'exposure', label: 'Exposure', icon: 'pie-chart' },
    { key: 'hedge', label: 'Hedge', icon: 'activity' },
    { key: 'performance', label: 'Performance', icon: 'trending-up' },
    { key: 'agents', label: 'Agents', icon: 'cpu' },
    { key: 'controls', label: 'Controls', icon: 'sliders-horizontal' },
    { key: 'logs', label: 'Events', icon: 'list' },
  ];

  return React.createElement('div', { style: { minHeight: '100vh', background: COLORS.bgRoot } },
    React.createElement('header', {
      style: {
        background: COLORS.bgSurface, borderBottom: `1px solid ${COLORS.border}`,
        padding: '0 24px', height: 56, display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        position: 'sticky', top: 0, zIndex: 100
      }
    },
      React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 10 } },
        React.createElement('i', { 'data-lucide': 'activity', style: { width: 22, height: 22, color: COLORS.blue } }),
        React.createElement('span', { style: { fontSize: 16, fontWeight: 700, letterSpacing: '-0.01em' } }, 'Trading Command Center'),
        React.createElement('span', { style: { fontSize: 11, color: COLORS.textTertiary, padding: '2px 8px', background: COLORS.bgHover, borderRadius: 4 } }, 'v3.0')
      ),
      React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 16 } },
        React.createElement('div', { style: { display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: COLORS.textSecondary } },
          React.createElement(StatusDot, { on: connected }),
          connected ? 'Live' : 'Offline'
        ),
        React.createElement('div', { style: { fontSize: 12, color: COLORS.textTertiary } },
          'CCXT: ', React.createElement('span', { style: { color: ccxtHealth?.connected ? COLORS.green : COLORS.red, fontWeight: 600 } }, ccxtHealth?.connected ? 'Connected' : 'Offline')
        ),
        React.createElement('div', { style: { fontSize: 12, color: COLORS.textTertiary } },
          'Delta: ', React.createElement('span', { style: { color: deltaHealth?.connected ? COLORS.green : COLORS.red, fontWeight: 600 } }, deltaHealth?.connected ? 'Connected' : 'Offline')
        ),
        React.createElement('div', { style: { fontSize: 12, color: COLORS.textTertiary } },
          'Agents: ', React.createElement('span', { style: { color: COLORS.text, fontWeight: 600 } }, Object.keys(status.agents||{}).length)
        )
      )
    ),
    React.createElement('nav', {
      style: {
        display: 'flex', gap: 2, padding: '12px 24px 0', background: COLORS.bgSurface,
        borderBottom: `1px solid ${COLORS.border}`, overflowX: 'auto'
      }
    },
      tabs.map(t => React.createElement('button', {
        key: t.key, onClick: () => setActiveView(t.key),
        style: {
          display: 'flex', alignItems: 'center', gap: 6,
          padding: '8px 16px', borderRadius: '6px 6px 0 0',
          fontSize: 13, fontWeight: 500, border: 'none', cursor: 'pointer',
          color: activeView === t.key ? COLORS.text : COLORS.textSecondary,
          background: activeView === t.key ? COLORS.bgRoot : 'transparent',
          borderBottom: activeView === t.key ? `2px solid ${COLORS.blue}` : '2px solid transparent',
          transition: 'all 0.15s'
        }
      },
        React.createElement('i', { 'data-lucide': t.icon, style: { width: 14, height: 14 } }),
        t.label
      ))
    ),
    React.createElement('main', { style: { padding: 24, maxWidth: 1440, margin: '0 auto' } },
      activeView === 'overview' && React.createElement('div', null,
        React.createElement('div', { style: { display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12, marginBottom: 20 } },
          React.createElement(MetricCard, { label: 'System Status', value: status.running ? 'RUNNING' : 'STOPPED', sub: connected ? 'Bridge Connected' : 'Bridge Offline', icon: 'activity', color: status.running ? COLORS.green : COLORS.red }),
          React.createElement(MetricCard, { label: 'Delta Mode', value: deltaHealth?.mode === 'trading' ? 'TRADING' : 'READ ONLY', sub: deltaHealth?.connected ? 'Connected' : 'Offline', icon: 'plug', color: deltaHealth?.mode === 'trading' ? COLORS.green : COLORS.amber }),
          React.createElement(MetricCard, { label: 'Active Agents', value: Object.keys(status.agents||{}).length, sub: 'Online / Registered', icon: 'cpu', color: COLORS.blue }),
          React.createElement(MetricCard, { label: 'Optimized Strategy', value: strategy ? strategy.timeframe : '--', sub: strategy ? strategy.symbol : 'Not deployed', icon: 'target', color: COLORS.cyan }),
          React.createElement(MetricCard, { label: 'Recent Signals', value: signals.length, sub: 'Last 10 signals', icon: 'zap', color: COLORS.amber }),
          React.createElement(MetricCard, { label: 'Correlation SOL-XAUT', value: (corr?.current||0).toFixed(2), sub: '1d rolling', icon: 'git-compare', color: Math.abs(corr?.current||0) > 0.7 ? COLORS.red : COLORS.green, trend: corr?.trend }),
        ),
        React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 } },
          React.createElement(Section, { title: 'Optimized Strategy' },
            React.createElement(StrategyPanel, { strategy })
          ),
          React.createElement(Section, { title: 'Delta Connection' },
            React.createElement(DeltaStatusPanel, { health: deltaHealth, onSwitchMode: switchDeltaMode })
          )
        ),
        React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 } },
          React.createElement(Section, { title: 'SOLUSDT Performance' },
            React.createElement(PerformancePanel, { data: perfSol, symbol: 'SOLUSDT' })
          ),
          React.createElement(Section, { title: 'XAUTUSDT Performance' },
            React.createElement(PerformancePanel, { data: perfXaut, symbol: 'XAUTUSDT' })
          )
        ),
        React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 } },
          React.createElement(Section, { title: 'Exposure Allocation' },
            React.createElement(ExposureGauge, { data: exposure })
          ),
          React.createElement(Section, { title: 'Hedge Status' },
            React.createElement(HedgePanel, { data: hedge })
          )
        )
      ),
      activeView === 'suggestions' && React.createElement(Section, { title: 'Live Trading Suggestions' },
        React.createElement(TradingSuggestionsPanel, { suggestions: tradingSuggestions, openPositions })
      ),
      activeView === 'allocations' && React.createElement(Section, { title: 'Margin Allocations & Profit Potential' },
        React.createElement(MarginAllocationPanel, { allocations, summary: allocationSummary, accountEquity, availableMargin })
      ),
      activeView === 'options' && React.createElement(Section, { title: 'Options Scanner — Inflated OTM Contracts' },
        React.createElement(OptionsPanel, { candidates: optionCandidates, payoff: optionPayoff, onSelectOption: selectOptionForPayoff })
      ),
      activeView === 'recommendations' && React.createElement(Section, { title: 'Timeframe Recommendations — All Agent Signals Confluent' },
        React.createElement(RecommendationPanel, { recommendations })
      ),
      activeView === 'delta' && React.createElement('div', null,
        React.createElement(Section, { title: 'Delta Exchange Connection' },
          React.createElement(DeltaStatusPanel, { health: deltaHealth, onSwitchMode: switchDeltaMode })
        ),
        React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 } },
          React.createElement(Section, { title: 'Balance & Margin' },
            React.createElement(DeltaBalancePanel, { balance: deltaBalance, mode: deltaHealth?.mode })
          ),
          React.createElement(Section, { title: 'Open Positions' },
            React.createElement(DeltaPositionsPanel, { positions: deltaPositions })
          )
        ),
        React.createElement(Section, { title: 'Top Gainers (24h) — CCXT' },
          React.createElement(TopGainersPanel, { gainers: ccxtGainers })
        )
      ),
      activeView === 'markets' && React.createElement('div', null,
        React.createElement(Section, { title: 'CCXT Market Overview' },
          React.createElement(MarketSummaryPanel, { summary: marketSummary })
        ),
        React.createElement(Section, { title: 'Highest Gainer Chart' },
          React.createElement(TopGainerChart, { chart: topGainerChart })
        ),
        React.createElement(Section, { title: 'Spot vs Derivatives' },
          React.createElement(SpotDerivativesPanel, { data: spotDerivs })
        ),
        React.createElement(Section, { title: 'Top Gainers (24h)' },
          React.createElement(TopGainersPanel, { gainers: ccxtGainers })
        )
      ),
      activeView === 'xau' && React.createElement('div', null,
        React.createElement(Section, { title: 'XAU AI Trading Bot Integration' },
          React.createElement(XAUStatusPanel, { status: xauStatus, smc: xauSmc, kelly: xauKelly, risk: xauRisk })
        )
      ),
      activeView === 'strategy' && React.createElement(Section, { title: 'Optimized Strategy Deployment' },
        React.createElement(StrategyPanel, { strategy })
      ),
      activeView === 'correlation' && React.createElement(Section, { title: 'Crypto — RWA Correlation Matrix' },
        React.createElement(CorrelationMatrix, { data: corr })
      ),
      activeView === 'exposure' && React.createElement(Section, { title: 'Crypto vs Real-World Asset Exposure' },
        React.createElement(ExposureGauge, { data: exposure })
      ),
      activeView === 'hedge' && React.createElement(Section, { title: 'Hedge Effectiveness & Risk Offset' },
        React.createElement(HedgePanel, { data: hedge })
      ),
      activeView === 'performance' && React.createElement('div', { style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 } },
        React.createElement(Section, { title: 'SOLUSDT Performance' },
          React.createElement(PerformancePanel, { data: perfSol, symbol: 'SOLUSDT' })
        ),
        React.createElement(Section, { title: 'XAUTUSDT Performance' },
          React.createElement(PerformancePanel, { data: perfXaut, symbol: 'XAUTUSDT' })
        )
      ),
      activeView === 'agents' && React.createElement(Section, { title: 'Agent Monitor' },
        React.createElement(AgentList, { agents: status.agents })
      ),
      activeView === 'controls' && React.createElement(Section, { title: 'System Controls' },
        React.createElement('div', { style: { marginBottom: 24 } },
          React.createElement('h3', { style: { fontSize: 13, color: COLORS.textSecondary, marginBottom: 12 } }, 'Mode Switching'),
          React.createElement(Controls, { sendCommand })
        ),
        React.createElement('div', null,
          React.createElement('h3', { style: { fontSize: 13, color: COLORS.textSecondary, marginBottom: 12 } }, 'Recent Signals'),
          React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 6, maxHeight: 300, overflow: 'auto' } },
            signals.map((sig, i) => React.createElement('div', { key: i, style: { padding: '8px 12px', background: COLORS.bgHover, borderRadius: 6, fontSize: 12 } },
              React.createElement('span', { style: { color: COLORS.textTertiary } }, new Date(sig.timestamp).toLocaleTimeString()),
              React.createElement('span', { style: { color: COLORS.blue, marginLeft: 8 } }, sig.type),
              React.createElement('span', { style: { color: COLORS.textSecondary, marginLeft: 8, fontFamily: 'monospace', fontSize: 11 } }, JSON.stringify(sig.payload).slice(0, 100))
            ))
          )
        )
      ),
      activeView === 'logs' && React.createElement(Section, { title: 'Live Event Stream' },
        React.createElement('div', { style: { display: 'flex', flexDirection: 'column', gap: 4, maxHeight: 'calc(100vh - 200px)', overflow: 'auto', fontFamily: 'SF Mono, Menlo, monospace', fontSize: 12 } },
          logs.map((l, i) => React.createElement('div', { key: i, style: { padding: '6px 10px', background: COLORS.bgHover, borderRadius: 4 } },
            React.createElement('span', { style: { color: COLORS.textTertiary } }, '['+l.time+']'),
            React.createElement('span', { style: { color: COLORS.blue, marginLeft: 8 } }, l.type),
            React.createElement('span', { style: { color: COLORS.green, marginLeft: 8 } }, l.source),
            React.createElement('span', { style: { color: COLORS.textSecondary, marginLeft: 8, wordBreak: 'break-all' } }, l.payload)
          ))
        )
      )
    ),
    React.createElement('div', {
      style: {
        position: 'fixed', bottom: 0, left: 0, right: 0, height: 28,
        background: COLORS.bgSurface, borderTop: `1px solid ${COLORS.border}`,
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '0 24px', fontSize: 11, color: COLORS.textTertiary
      }
    },
      React.createElement('span', null, 'CCXT • Delta Exchange • SOLUSDT • XAUTUSDT • Bridge: ' + (connected ? 'Connected' : 'Offline')),
      React.createElement('span', null, 'Command Center v3.0 • ' + new Date().toLocaleTimeString())
    )
  );
}

ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(App));

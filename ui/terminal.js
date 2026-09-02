/* terminal.js — interactive REPL terminal view */
var _API = 'http://127.0.0.1:8088';
function _tFetch(path) {
  return fetch(_API + path).then(function (r) {
    if (!r.ok) { return r.text().then(function (t) { throw new Error('HTTP ' + r.status + ': ' + t); }); }
    return r.json();
  });
}

window.TerminalCmdsList = [
  { name: 'help', desc: 'list all commands' },
  { name: 'clear', desc: 'clear terminal output' },
  { name: 'status', desc: 'bridge health status' },
  { name: 'positions', desc: 'open positions' },
  { name: 'tickers', desc: 'live ticker prices' },
  { name: 'calendar', desc: 'upcoming economic events' },
  { name: 'strategies', desc: 'registered strategies' },
  { name: 'journal', desc: 'journal stats' },
  { name: 'log', desc: 'recent journal entries' },
  { name: 'trade', desc: 'recent trades' },
  { name: 'notify', desc: 'notification count' },
  { name: 'echo', desc: 'echo arguments' },
  { name: 'date', desc: 'current date/time' },
  { name: 'version', desc: 'system version' },
];

window.TerminalCmds = new Map();
window.TerminalCmds.set('help', function () {
  return window.TerminalCmdsList.map(function (c) {
    return '  ' + c.name + '  —  ' + c.desc;
  }).join('\n');
});
window.TerminalCmds.set('clear', function () { return '__CLEAR__'; });
window.TerminalCmds.set('status', function (_, ctx) {
  return ctx.fetch('/health').then(function (d) {
    return Object.keys(d).map(function (k) { return '  ' + k + ': ' + JSON.stringify(d[k]); }).join('\n');
  });
});
window.TerminalCmds.set('positions', function (_, ctx) {
  return ctx.fetch('/positions').then(function (d) {
    var arr = Array.isArray(d) ? d : (d.positions || []);
    if (!arr.length) return '  no open positions';
    return arr.map(function (p) {
      return '  ' + (p.symbol || '-') + '  ' + (p.quantity || p.size || '-') + '@' + (p.price || p.avg_price || '-') + '  pnl=' + (p.pnl || p.unrealized_pnl || '-');
    }).join('\n');
  });
});
window.TerminalCmds.set('tickers', function (_, ctx) {
  return ctx.fetch('/tickers').then(function (d) {
    var arr = Array.isArray(d) ? d : (d.tickers || []);
    return arr.map(function (t) { return (t.symbol || '-') + ': ' + (t.price || '-'); }).join(', ');
  });
});
window.TerminalCmds.set('calendar', function (_, ctx) {
  return ctx.fetch('/calendar').then(function (d) {
    var arr = (d.upcoming || d.events || []).slice(0, 5);
    if (!arr.length) return '  no upcoming events';
    return arr.map(function (e) {
      var dt = e.timestamp ? new Date(e.timestamp * 1000).toLocaleString() : (e.time || '-');
      return '  ' + dt + '  [' + (e.impact || '-') + ']  ' + (e.title || '-');
    }).join('\n');
  });
});
window.TerminalCmds.set('strategies', function (_, ctx) {
  return ctx.fetch('/strategies/list').then(function (d) {
    var arr = d.strategies || d || [];
    if (!arr.length) return '  no strategies loaded';
    return arr.map(function (s) {
      var tags = (s.tags || s.class || []).toString();
      return '  ' + (s.name || s.id || '-') + '  [' + tags + ']';
    }).join('\n');
  });
});
window.TerminalCmds.set('journal', function (_, ctx) {
  return ctx.fetch('/journal/stats').then(function (d) {
    return Object.keys(d).map(function (k) { return '  ' + k + ': ' + JSON.stringify(d[k]); }).join('\n');
  });
});
window.TerminalCmds.set('log', function (_, ctx) {
  return ctx.fetch('/journal/log').then(function (d) {
    var arr = (d.entries || d.log || d || []).slice(0, 10);
    if (!arr.length) return '  no log entries';
    return arr.map(function (e) {
      return '  [' + (e.timestamp || '-') + '] ' + (e.message || e.msg || JSON.stringify(e));
    }).join('\n');
  });
});
window.TerminalCmds.set('trade', function (_, ctx) {
  return ctx.fetch('/journal/trades').then(function (d) {
    var arr = (d.trades || d || []).slice(0, 10);
    if (!arr.length) return '  no trades';
    return arr.map(function (t) {
      return '  ' + (t.id || '-') + '  ' + (t.status || '-') + '  ' + (t.symbol || '-') + '  pnl=' + (t.pnl || '-');
    }).join('\n');
  });
});
window.TerminalCmds.set('notify', function (_, ctx) {
  return ctx.fetch('/journal/notifications').then(function (d) {
    var arr = d.notifications || d || [];
    return '  ' + (Array.isArray(arr) ? arr.length : 0) + ' notifications';
  });
});
window.TerminalCmds.set('echo', function (args) { return args.join(' ') || ''; });
window.TerminalCmds.set('date', function () { return new Date().toString(); });
window.TerminalCmds.set('version', function () { return 'Delta Command Center v2.4.1 (bridge :8088)'; });

window.TerminalView = React.memo(function TerminalView(props) {
  var _s = React.useState;
  var _r = React.useRef;
  var _m = React.useMemo;
  var E = (window.Theme && window.Theme.EXTRA) || {};
  var LIME = E.lime || '#bef264';
  var GLASS = E.glass || 'rgba(17,19,24,0.72)';
  var BORDER = E.glassBorder || 'rgba(34,36,44,0.6)';
  var MONO = E.fontMono || 'monospace';

  var linesRef = _r(null);
  var inputRef = _r(null);
  var historyRef = _r([]);
  var histIdx = _r(-1);
  var _lines = _s([]);
  var lines = _lines[0], setLines = _lines[1];
  var _val = _s('');
  var val = _val[0], setVal = _val[1];
  var _busy = _s(false);
  var busy = _busy[0], setBusy = _busy[1];

  var scrollBottom = function () {
    var el = linesRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  };

  React.useEffect(function () { scrollBottom(); }, [lines]);

  var runCommand = function (raw) {
    var trimmed = raw.trim();
    if (!trimmed) return;
    var parts = trimmed.split(/\s+/);
    var name = parts[0].toLowerCase();
    var args = parts.slice(1);
    var hist = historyRef.current;
    if (hist.length === 0 || hist[hist.length - 1] !== trimmed) {
      hist.push(trimmed);
      if (hist.length > 50) hist.shift();
    }
    histIdx.current = -1;
    setLines(function (prev) { return prev.concat([{ type: 'in', text: trimmed }]); });
    setVal('');
    setBusy(true);
    var cmd = window.TerminalCmds.get(name);
    var promise;
    if (cmd) {
      promise = cmd(args, { api: _API, fetch: _tFetch });
    } else {
      promise = Promise.resolve('unknown command: ' + name + ' — type help');
    }
    Promise.resolve(promise).then(function (result) {
      if (result === '__CLEAR__') {
        setLines([]);
      } else if (result != null) {
        var text = Array.isArray(result) ? result.join('\n') : String(result);
        setLines(function (prev) { return prev.concat([{ type: 'out', text: text }]); });
      }
    }).catch(function (err) {
      setLines(function (prev) { return prev.concat([{ type: 'err', text: 'error: ' + (err.message || String(err)) }]); });
    }).finally(function () { setBusy(false); });
  };

  var handleKeyDown = function (e) {
    if (e.key === 'Enter' && !busy) {
      runCommand(val);
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      var h = historyRef.current;
      if (!h.length) return;
      var idx = histIdx.current;
      if (idx < h.length - 1) {
        idx++;
        histIdx.current = idx;
        setVal(h[h.length - 1 - idx]);
      }
      return;
    }
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      var h2 = historyRef.current;
      var idx2 = histIdx.current;
      if (idx2 > 0) {
        idx2--;
        histIdx.current = idx2;
        setVal(h2[h2.length - 1 - idx2]);
      } else if (idx2 === 0) {
        histIdx.current = -1;
        setVal('');
      }
      return;
    }
    if (e.key === 'Tab') {
      e.preventDefault();
      var cur = val.split(/\s+/);
      var token = cur[0] || '';
      if (token && !e.shiftKey && cur.length <= 1) {
        var lower = token.toLowerCase();
        var matches = window.TerminalCmdsList.filter(function (c) { return c.name.indexOf(lower) === 0; });
        if (matches.length === 1) setVal(matches[0].name + ' ');
      }
      return;
    }
  };

  var lineStyle = function (type) {
    if (type === 'in') return { color: '#7a9a5c', fontFamily: MONO, fontSize: 12, lineHeight: 1.6, paddingLeft: 2 };
    if (type === 'err') return { color: '#ef4444', fontFamily: MONO, fontSize: 12, lineHeight: 1.6, paddingLeft: 2 };
    return { color: LIME, fontFamily: MONO, fontSize: 12, lineHeight: 1.6, paddingLeft: 2 };
  };

  return React.createElement('div', {
    style: {
      display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0,
      background: GLASS, border: '1px solid ' + BORDER, borderRadius: 12,
      fontFamily: MONO, overflow: 'hidden',
    }
  },
    React.createElement('div', {
      style: {
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        padding: '8px 14px', borderBottom: '1px solid ' + BORDER,
        background: 'rgba(0,0,0,0.25)', flexShrink: 0,
      }
    },
      React.createElement('span', { style: { fontSize: 12, color: '#5a5e6f', fontFamily: MONO } },
        'TERM // bridge://127.0.0.1:8088\u2501\u2501\u2501'),
      React.createElement('button', {
        onClick: function () { setLines([]); },
        style: {
          background: 'transparent', border: '1px solid ' + BORDER, borderRadius: 6,
          color: '#5a5e6f', fontSize: 11, padding: '2px 8px', cursor: 'pointer',
          fontFamily: MONO, lineHeight: 1.4,
        }
      }, '[x]')
    ),
    React.createElement('div', {
      ref: linesRef,
      style: { flex: 1, overflowY: 'auto', padding: '10px 14px', minHeight: 0 },
    },
      lines.map(function (ln, i) {
        var prefix = ln.type === 'in' ? 'user@cc:~$ ' : '';
        return React.createElement('div', { key: i, className: 'term-line', style: lineStyle(ln.type) },
          prefix + ln.text
        );
      })
    ),
    React.createElement('div', {
      style: {
        display: 'flex', alignItems: 'center', padding: '6px 14px',
        borderTop: '1px solid ' + BORDER, background: 'rgba(0,0,0,0.15)', flexShrink: 0,
      }
    },
      React.createElement('span', { style: { color: LIME, fontSize: 13, marginRight: 6, fontFamily: MONO } }, '>'),
      React.createElement('input', {
        ref: inputRef,
        value: val,
        onChange: function (e) { setVal(e.target.value); },
        onKeyDown: handleKeyDown,
        disabled: busy,
        autoFocus: true,
        spellCheck: false,
        style: {
          flex: 1, background: 'transparent', border: 'none', outline: 'none',
          color: LIME, fontSize: 13, fontFamily: MONO, caretColor: LIME,
        }
      })
    )
  );
});

window.TerminalView.displayName = 'TerminalView';

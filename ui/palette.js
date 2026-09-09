/* palette.js — Cmd+K / Ctrl+K command palette */
var _pAPI = '';
function _pFetch(path) {
  return fetch(_pAPI + path).then(function (r) {
    if (!r.ok) return r.text().then(function (t) { throw new Error('HTTP ' + r.status + ': ' + t); });
    return r.json();
  });
}

var _NAV_ITEMS = [
  { key: 'dashboard',  label: 'Dashboard',      group: 'NAVIGATE', kind: 'nav' },
  { key: 'options',    label: 'Options',         group: 'NAVIGATE', kind: 'nav' },
  { key: 'strategies', label: 'Strategies',      group: 'NAVIGATE', kind: 'nav' },
  { key: 'calendar',   label: 'Calendar',        group: 'NAVIGATE', kind: 'nav' },
  { key: 'library',    label: 'Strategy Library', group: 'NAVIGATE', kind: 'nav' },
  { key: 'journal',    label: 'Journal',         group: 'NAVIGATE', kind: 'nav' },
  { key: 'analytics',  label: 'Analytics',       group: 'NAVIGATE', kind: 'nav' },
  { key: 'terminal',   label: 'Terminal',        group: 'NAVIGATE', kind: 'nav' },
];

var _BRIDGE_ITEMS = [
  { key: 'status',     label: 'Bridge Status',   group: 'BRIDGE', kind: 'info', path: '/health' },
  { key: 'positions',  label: 'Open Positions',   group: 'BRIDGE', kind: 'info', path: '/delta/positions' },
  { key: 'tickers',    label: 'Live Tickers',     group: 'BRIDGE', kind: 'info', path: '/delta/tickers' },
  { key: 'bcal',       label: 'Econ Calendar',    group: 'BRIDGE', kind: 'info', path: '/calendar/events' },
  { key: 'bstrat',     label: 'Bridge Strategies', group: 'BRIDGE', kind: 'info', path: '/strategies/library' },
];

var _ALL_ITEMS = _NAV_ITEMS.concat(_BRIDGE_ITEMS);

var _ce = React.createElement;

window.Palette = (function () {
  var _terminalRunner = null;
  var _rootEl = null;
  var _opts = {};

  /* --- internal component --- */
  var PaletteApp = React.memo(function PaletteApp() {
    var _e = (window.Theme && window.Theme.EXTRA) || {};
    var LIME     = _e.lime || '#bef264';
    var LIME_DIM = _e.limeDim || 'rgba(190,242,100,0.27)';
    var GLASS    = _e.glass || 'rgba(17,19,24,0.72)';
    var BORDER   = _e.glassBorder || 'rgba(34,36,44,0.6)';
    var MONO     = _e.fontMono || 'monospace';

    var useState  = React.useState;
    var useEffect = React.useEffect;
    var useRef    = React.useRef;
    var useMemo   = React.useMemo;

    var _sOpen = useState(false);
    var open = _sOpen[0], setOpen = _sOpen[1];
    var _sQuery = useState('');
    var query = _sQuery[0], setQuery = _sQuery[1];
    var _sActive = useState(0);
    var active = _sActive[0], setActive = _sActive[1];
    var _sPreview = useState(null);
    var preview = _sPreview[0], setPreview = _sPreview[1];
    var _sBusy = useState(false);
    var busy = _sBusy[0], setBusy = _sBusy[1];

    var inputRef = useRef(null);

    var isTerminalMode = query.length > 0 && query.charAt(0) === '>';

    var filtered = useMemo(function () {
      if (isTerminalMode) return [];
      if (!query) return _ALL_ITEMS;
      var q = query.toLowerCase();
      return _ALL_ITEMS.filter(function (item) {
        return item.label.toLowerCase().indexOf(q) !== -1 ||
               item.key.toLowerCase().indexOf(q) !== -1;
      });
    }, [query, isTerminalMode]);

    /* group filtered items for rendering */
    var groups = useMemo(function () {
      var map = {};
      filtered.forEach(function (item) {
        if (!map[item.group]) map[item.group] = [];
        map[item.group].push(item);
      });
      return map;
    }, [filtered]);

    var resetState = function () {
      setQuery('');
      setActive(0);
      setPreview(null);
      setBusy(false);
    };

    /* expose open/close/toggle */
    window.Palette.open = function () { resetState(); setOpen(true); };
    window.Palette.close = function () { setOpen(false); resetState(); };
    window.Palette.toggle = function () { open ? window.Palette.close() : window.Palette.open(); };

    /* focus input on open */
    useEffect(function () {
      if (open && inputRef.current) {
        setTimeout(function () { inputRef.current && inputRef.current.focus(); }, 40);
      }
    }, [open]);

    var handleSelect = function (item) {
      if (item.kind === 'nav') {
        if (_opts.onNavigate) _opts.onNavigate(item.key);
        window.Palette.close();
      } else if (item.kind === 'info') {
        setBusy(true);
        setPreview('Loading ' + item.label + '...');
        _pFetch(item.path).then(function (data) {
          var txt = JSON.stringify(data, null, 2);
          if (txt.length > 1200) txt = txt.substring(0, 1200) + '\n...';
          setPreview(txt);
          if (window.Chrome && window.Chrome.audio && window.Chrome.audio.blip) {
            window.Chrome.audio.blip();
          }
        }).catch(function (err) {
          setPreview('Error: ' + (err.message || String(err)));
        }).finally(function () { setBusy(false); });
      }
    };

    var handleEnter = function () {
      if (isTerminalMode) {
        var cmd = query.substring(1).trim();
        window.Palette.close();
        if (_terminalRunner) _terminalRunner(cmd);
        return;
      }
      if (filtered.length > 0) {
        handleSelect(filtered[Math.min(active, filtered.length - 1)]);
      }
    };

    var handleKeyDown = function (e) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        var len = isTerminalMode ? 0 : filtered.length;
        if (len > 0) setActive((active + 1) % len);
      } else if (e.key === 'ArrowUp') {
        e.preventDefault();
        var len2 = isTerminalMode ? 0 : filtered.length;
        if (len2 > 0) setActive((active - 1 + len2) % len2);
      } else if (e.key === 'Enter') {
        e.preventDefault();
        handleEnter();
      } else if (e.key === 'Escape') {
        e.preventDefault();
        window.Palette.close();
      }
    };

    if (!open) return null;

    /* compute global index for highlight tracking */
    var flatIdx = 0;

    var sBackdrop = {
      position: 'fixed', inset: 0, zIndex: 9990,
      background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(6px)', WebkitBackdropFilter: 'blur(6px)',
      display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
      paddingTop: '12vh',
    };
    var sPanel = {
      width: 560, maxHeight: 420, background: GLASS, border: '1px solid ' + BORDER,
      borderRadius: 12, boxShadow: '0 24px 80px rgba(0,0,0,0.6)', fontFamily: MONO,
      display: 'flex', flexDirection: 'column', overflow: 'hidden',
      backdropFilter: 'blur(' + (_e.glassBlur || '12px') + ')',
      WebkitBackdropFilter: 'blur(' + (_e.glassBlur || '12px') + ')',
    };
    var sInput = {
      width: '100%', background: 'transparent', border: 'none', outline: 'none',
      color: LIME, fontSize: 14, fontFamily: MONO, padding: '14px 16px 10px',
      caretColor: LIME, boxSizing: 'border-box',
    };
    var sList = { flex: 1, overflowY: 'auto', padding: '4px 0', minHeight: 0 };
    var sGroupLabel = {
      fontSize: 10, color: '#5a5e6f', fontFamily: MONO, padding: '8px 16px 3px',
      letterSpacing: '0.08em', textTransform: 'uppercase', userSelect: 'none',
    };
    var sItem = {
      display: 'flex', alignItems: 'center', padding: '7px 16px', cursor: 'pointer',
      fontFamily: MONO, fontSize: 13, color: '#c0c4cc', transition: 'background 0.1s',
    };
    var sItemActive = {
      background: LIME_DIM, color: LIME,
    };
    var sBadge = {
      fontSize: 9, padding: '1px 6px', borderRadius: 4, marginLeft: 8,
      background: 'rgba(190,242,100,0.12)', color: '#5a7a3c', letterSpacing: '0.04em',
    };
    var sPreviewWrap = {
      maxHeight: 120, overflowY: 'auto', padding: '8px 16px',
      borderTop: '1px solid ' + BORDER, background: 'rgba(0,0,0,0.2)',
    };
    var sPreviewText = {
      fontSize: 11, fontFamily: MONO, color: LIME, whiteSpace: 'pre-wrap', margin: 0, lineHeight: 1.5,
    };
    var sFooter = {
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      padding: '6px 16px', borderTop: '1px solid ' + BORDER, fontSize: 11,
      color: '#5a5e6f', fontFamily: MONO,
    };

    var children = [];

    /* search input */
    children.push(_ce('input', {
      key: 'inp',
      ref: inputRef,
      value: query,
      onChange: function (e) { setQuery(e.target.value); setActive(0); },
      onKeyDown: handleKeyDown,
      placeholder: isTerminalMode ? 'Enter terminal command...' : 'Type a command or > to run terminal...',
      spellCheck: false,
      style: sInput,
    }));

    /* result list */
    var listChildren = [];

    if (isTerminalMode) {
      listChildren.push(_ce('div', { key: 'term-hint', style: sGroupLabel }, 'TERMINAL'));
      listChildren.push(_ce('div', { key: 'term-item', style: Object.assign({}, sItem, sItemActive) },
        React.createElement('span', { style: { color: LIME } }, '\u00BB '),
        'Run in terminal: ',
        React.createElement('span', { style: { color: LIME, fontWeight: 600 } }, query.substring(1))
      ));
    } else {
      var groupOrder = ['NAVIGATE', 'BRIDGE'];
      var gIdx = 0;
      groupOrder.forEach(function (gName) {
        var items = groups[gName];
        if (!items || !items.length) return;
        listChildren.push(_ce('div', { key: 'gh-' + gName, style: sGroupLabel }, gName));
        items.forEach(function (item) {
          var i = gIdx;
          var isActive = i === active;
          var itemStyle = Object.assign({}, sItem, isActive ? sItemActive : null);
          var badge = item.kind === 'info' ? _ce('span', { style: sBadge }, 'BRIDGE') : null;
          listChildren.push(_ce('div', {
            key: item.key,
            style: itemStyle,
            onMouseEnter: function () { setActive(i); },
            onClick: function () { handleSelect(item); },
          },
            React.createElement('span', { style: { color: isActive ? LIME : '#5a5e6f', marginRight: 8, fontSize: 11 } },
              item.kind === 'nav' ? '\u2318' : '\u21BB'),
            item.label,
            badge
          ));
          gIdx++;
        });
      });
    }

    children.push(_ce('div', { key: 'list', style: sList }, listChildren));

    /* preview strip */
    if (preview) {
      children.push(_ce('div', { key: 'preview', style: sPreviewWrap },
        _ce('pre', { style: sPreviewText }, preview)
      ));
    }

    /* footer */
    children.push(_ce('div', { key: 'footer', style: sFooter },
      _ce('span', null, '\u2191\u2193 navigate \u00B7 \u21B5 select \u00B7 esc close'),
      _ce('span', null, '\u2318K palette')
    ));

    /* backdrop click to close */
    return _ce('div', {
      style: sBackdrop,
      onMouseDown: function (e) { if (e.target === e.currentTarget) window.Palette.close(); },
    }, _ce('div', { style: sPanel, onMouseDown: function (e) { e.stopPropagation(); } }, children));
  });

  PaletteApp.displayName = 'PaletteApp';

  /* --- public API --- */
  return {
    mount: function (rootEl, opts) {
      _rootEl = rootEl;
      _opts = opts || {};
      ReactDOM.createRoot(rootEl).render(_ce(PaletteApp));
    },
    runTerminal: function (cmd) {
      if (_terminalRunner) _terminalRunner(cmd);
    },
    setTerminalRunner: function (fn) { _terminalRunner = fn; },
    open: function () {},
    close: function () {},
    toggle: function () {},
  };
})();

/* global keydown: Cmd+K / Ctrl+K → open, Esc → close */
document.addEventListener('keydown', function (e) {
  var mod = e.metaKey || e.ctrlKey;
  if (mod && e.key === 'k') {
    e.preventDefault();
    window.Palette.toggle();
  }
});

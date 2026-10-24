// App shell: top-bar destinations, section tabs, the Workshop menu and shared driver focus.
// navigate() (workbench.js) still owns view switching; syncShell() mirrors it in the bar.

function syncShell(view) {
  const item = document.querySelector(`.sub-nav .nav-item[data-view="${view}"]`);
  const dest = item?.closest('.nav-group')?.dataset.dest || 'weekend';
  document.querySelectorAll('.dest-item').forEach(el => {
    const on = el.dataset.dest === dest;
    el.classList.toggle('active', on);
    el.setAttribute('aria-current', on ? 'page' : 'false');
  });
  document.querySelectorAll('.sub-nav .nav-group').forEach(group => { group.hidden = group.dataset.dest !== dest; });
  // A destination with one view needs no tab row.
  const tabs = document.querySelectorAll(`.sub-nav .nav-group[data-dest="${dest}"] .nav-item`).length;
  document.querySelector('.sub-nav').hidden = tabs < 2;
  document.querySelector('.workshop summary').classList.toggle('active', dest === 'workshop');
  applyDriverFocus();
}

// ---------- driver focus ----------
// Click a driver row in any table or chart to highlight that driver everywhere on the page;
// Shift-click adds a second driver to compare. Esc or the focus chip clears it.
const driverFocus = [];
const DRIVER_COLUMN = /^(driver|code|abbreviation|driver code)$/i;
const ROW_SELECTOR = 'tr, .probability-row, .range-row, .bar-row';

function rowDriver(row) {
  if (row.dataset.driver) return row.dataset.driver;
  if (row.tagName === 'TR') {
    const table = row.closest('table');
    const heads = [...(table?.querySelectorAll('thead th') || [])];
    const index = heads.findIndex(th => DRIVER_COLUMN.test((th.dataset.column || th.textContent || '').trim()));
    if (index < 0 || row.parentElement?.tagName === 'THEAD') return '';
    return (row.children[index]?.textContent || '').trim();
  }
  return (row.querySelector('b, .bar-label')?.textContent || '').trim();
}

function applyDriverFocus() {
  const main = document.querySelector('.main');
  const active = driverFocus.length > 0;
  document.documentElement.classList.toggle('has-driver-focus', active);
  main.querySelectorAll('.is-driver-focus').forEach(el => el.classList.remove('is-driver-focus'));
  if (active) {
    main.querySelector('.view.active')?.querySelectorAll(ROW_SELECTOR).forEach(row => {
      if (driverFocus.includes(rowDriver(row))) row.classList.add('is-driver-focus');
    });
  }
  const chip = document.getElementById('focusChip');
  chip.hidden = !active;
  document.getElementById('focusLabel').textContent = driverFocus.join(' vs ');
}

// Plain click focuses one driver (clicking them again clears it); Shift-click keeps up to two.
function nextDriverFocus(current, code, add) {
  const at = current.indexOf(code);
  if (add) return at >= 0 ? current.filter(c => c !== code) : [...current.slice(-1), code];
  return at >= 0 && current.length === 1 ? [] : [code];
}

function toggleDriverFocus(code, add) {
  driverFocus.splice(0, driverFocus.length, ...nextDriverFocus(driverFocus, code, add));
  applyDriverFocus();
}

function clearDriverFocus() {
  driverFocus.length = 0;
  applyDriverFocus();
}

function setupShell() {
  document.querySelectorAll('.dest-item').forEach(button => button.addEventListener('click', () => navigate(button.dataset.first)));
  document.querySelectorAll('.workshop-item[data-go]').forEach(button => button.addEventListener('click', () => {
    button.closest('details').open = false;
    navigate(button.dataset.go);
  }));
  document.getElementById('focusChip').addEventListener('click', clearDriverFocus);

  const main = document.querySelector('.main');
  main.addEventListener('click', event => {
    // Replay keeps its own driver selection; controls inside rows keep their own behaviour.
    if (event.target.closest('#view-replay, button, a, input, select, label, summary')) return;
    const row = event.target.closest(ROW_SELECTOR);
    const code = row && rowDriver(row);
    if (code) toggleDriverFocus(code, event.shiftKey);
  });
  // Views re-render their tables after data loads; keep the highlight on the new rows.
  let pending = 0;
  new MutationObserver(() => {
    if (!driverFocus.length || pending) return;
    pending = requestAnimationFrame(() => { pending = 0; applyDriverFocus(); });
  }).observe(main, { childList: true, subtree: true });

  document.addEventListener('keydown', event => {
    if (event.target.closest('input, select, textarea, [contenteditable="true"]') || event.metaKey || event.ctrlKey || event.altKey) return;
    if (event.key === 'Escape') {
      const menu = document.querySelector('.workshop[open]');
      if (menu) { menu.open = false; return; }
      if (driverFocus.length) clearDriverFocus();
      return;
    }
    const dest = document.querySelectorAll('.dest-item')[Number(event.key) - 1];
    if (/^[1-9]$/.test(event.key) && dest) navigate(dest.dataset.first);
  });
  document.addEventListener('click', event => {
    const menu = document.querySelector('.workshop[open]');
    if (menu && !menu.contains(event.target)) menu.open = false;
  });
  syncShell(state.view || 'setup');
}

if (typeof module !== 'undefined' && module.exports) module.exports = { nextDriverFocus };
else setupShell();

/* Render saved recommendations as sequences. No pit-lap estimates are invented. */
(function (root) {
  'use strict';
  const compounds = ['soft', 'medium', 'hard', 'intermediate', 'wet'];
  const text = value => value == null ? '' : String(value).trim();
  const escape = value => text(value).replace(/[&<>"']/g, c => ({'&':'&amp;', '<':'&lt;', '>':'&gt;', '"':'&quot;', "'":'&#39;'}[c]));
  const number = value => text(value) && Number.isFinite(Number(value)) ? Number(value) : null;
  const first = (row, keys) => keys.map(key => text(row[key])).find(value => value && !/^(nan|none|null)$/i.test(value)) || '';

  function parseSequence(value) {
    if (!text(value) || /^(unknown|unavailable|nan|none|null|—)$/i.test(text(value))) return [];
    return text(value).split(/\s*(?:→|->|>)\s*/).filter(Boolean).map(token => {
      const match = token.match(/^([a-z]+)(?:\s*\(([^)]+)\))?$/i);
      const compound = match && compounds.includes(match[1].toLowerCase()) ? match[1].toLowerCase() : 'unknown';
      const usage = match && /^(new|used)$/i.test(match[2] || '') ? match[2].toLowerCase() : 'unknown';
      return {compound, usage, label: token};
    });
  }

  function plans(table, plan = 'primary', order = 'grid') {
    const rows = (table?.rows || []).map(row => {
      const sequence = first(row, plan === 'alternative' ? ['alternative_strategy', 'AlternativeStrategy'] :
        ['history_adjusted_strategy', 'PredictedStrategy', 'primary_strategy', 'PrimaryStrategy']);
      const stints = parseSequence(sequence);
      const gridValue = number(row.GridPosition) ?? number(text(row.Grid).replace(/^P/i, ''));
      return {row, driver: first(row, ['Driver']) || 'Unknown', team: first(row, ['Team']) || 'Team unknown',
        grid: gridValue > 0 ? gridValue : null, sequence, stints,
        stops: stints.length ? stints.length - 1 : null};
    });
    return rows.sort((a, b) => {
      const byGrid = (a.grid ?? Infinity) - (b.grid ?? Infinity) || a.driver.localeCompare(b.driver);
      if (order === 'team') return a.team.localeCompare(b.team) || byGrid;
      if (order === 'stops') return (a.stops ?? Infinity) - (b.stops ?? Infinity) || byGrid;
      return byGrid;
    });
  }

  let outputs = {}, activePlan = 'primary', selectedDriver = null, bound = false;
  const el = id => document.getElementById(id);
  const gridLabel = () => outputs.gridFreshness?.saved_grid_source === 'fia_official_grid' ? 'FIA grid' : 'Saved model grid';

  function driverDetails(plan) {
    const panel = el('tyreDriverPanel');
    panel.hidden = !plan;
    if (!plan) return;
    const row = plan.row;
    const field = keys => first(row, keys) || 'Not recorded';
    const confidence = field(['strategy_confidence', 'StrategyConfidence']);
    const risk = field(['strategy_risk_level', 'risk_level', 'RiskLevel']);
    const score = field(activePlan === 'alternative' ? ['alternative_strategy_score', 'AlternativeStrategyScore'] : ['selected_strategy_score', 'SelectedStrategyScore']);
    panel.innerHTML = `<div class="panel-header"><div><h2>${escape(plan.driver)} <span class="tyre-detail-team">${escape(plan.team)}</span></h2><p>${escape(plan.sequence || 'No saved strategy')}</p></div><button type="button" id="tyreCloseDetails" aria-label="Close driver strategy details">Close</button></div>
      <div class="tyre-detail-metrics">${[['Recommendation confidence', confidence], ['Recommendation risk', risk], ['Candidate score', score], ['Inferred fresh sets · H / M / S', ['FreshHardRemaining','FreshMediumRemaining','FreshSoftRemaining'].map(key => number(row[key]) ?? '—').join(' / ')]].map(([label, value]) => `<div><small>${escape(label)}</small><strong>${escape(value)}</strong></div>`).join('')}</div>
      ${activePlan === 'alternative' ? '<p class="footnote">Confidence, risk and rationale describe the recommended plan. Separate alternative-plan confidence is not recorded.</p>' : ''}
      <p class="tyre-reason">${escape(field(['strategy_reason', 'StrategyReason', 'Notes']))}</p><p class="footnote">${escape(field(['confidence_reason', 'ConfidenceReason', 'tyre_confidence_reason']))}</p>`;
    el('tyreCloseDetails').addEventListener('click', () => {
      selectedDriver = null; draw();
      Array.from(el('tyreTimeline').querySelectorAll('[data-tyre-driver]')).find(button => button.dataset.tyreDriver === plan.driver)?.focus();
    });
  }

  function draw() {
    const rows = plans(outputs.strategy, activePlan, el('tyreSort').value);
    const maxStints = Math.max(2, ...rows.map(row => row.stints.length));
    const knownRows = rows.filter(row => row.stops != null);
    el('tyreTotal').textContent = knownRows.length ? knownRows.reduce((total, row) => total + row.stops, 0) : '—';
    el('tyreTotalLabel').textContent = `${activePlan === 'primary' ? 'Recommended' : 'Alternative'} stops${knownRows.length < rows.length ? ` · ${knownRows.length}/${rows.length} drivers` : ''}`;
    const alternative = plans(outputs.strategy, 'alternative').some(row => row.stints.length);
    document.querySelectorAll('[data-tyre-plan]').forEach(button => {
      button.disabled = button.dataset.tyrePlan === 'alternative' && !alternative;
      button.setAttribute('aria-pressed', String(button.dataset.tyrePlan === activePlan));
    });
    el('tyreTimeline').style.setProperty('--stint-count', maxStints);
    el('tyreTimeline').innerHTML = rows.length ? `<div class="tyre-axis" aria-hidden="true"><span>Driver / ${gridLabel()}</span><div>${Array.from({length:maxStints}, (_, i) => `<span>${i ? `After stop ${i}` : 'Opening stint'}</span>`).join('')}</div><span>Stops</span></div>` + rows.map(plan => {
      const description = `${plan.driver}, ${plan.grid ? `${gridLabel()} P${plan.grid}` : 'grid unknown'}, ${plan.sequence || 'strategy unavailable'}, ${plan.stops ?? 'unknown'} stops. Line lengths do not represent laps.`;
      const segments = plan.stints.map((stint, i) => `<span class="tyre-stint tyre-${stint.compound} ${stint.usage}" style="grid-column:${i + 1}${i === plan.stints.length - 1 ? '/-1' : ''}"><small>${escape(stint.compound === 'unknown' ? stint.label : stint.compound)} <em>${escape(stint.usage)}</em></small><i></i>${i < plan.stints.length - 1 ? `<b class="tyre-stop" aria-hidden="true">${i + 1}</b>` : '<b class="tyre-finish" aria-hidden="true">END</b>'}</span>`).join('');
      return `<button type="button" class="tyre-driver-row" data-tyre-driver="${escape(plan.driver)}" aria-label="${escape(description)}" aria-expanded="${selectedDriver === plan.driver}" aria-controls="tyreDriverPanel"><span class="tyre-driver"><strong>${escape(plan.driver)}</strong><small>${escape(plan.team)}</small><b>${plan.grid ? `P${plan.grid}` : '—'}</b></span><span class="tyre-stints">${segments || '<span class="tyre-unavailable">No saved strategy</span>'}</span><span class="tyre-stop-count">${plan.stops ?? '—'}</span></button>`;
    }).join('') : '<div class="empty">No tyre recommendations saved. Run a simulation or follow a completed PC forecast to see driver stint plans.</div>';
    el('tyreTimeline').querySelectorAll('[data-tyre-driver]').forEach(button => button.addEventListener('click', () => {
      selectedDriver = selectedDriver === button.dataset.tyreDriver ? null : button.dataset.tyreDriver;
      draw();
      Array.from(el('tyreTimeline').querySelectorAll('[data-tyre-driver]')).find(next => next.dataset.tyreDriver === button.dataset.tyreDriver)?.focus();
      if (selectedDriver) el('tyreDriverPanel').scrollIntoView({block:'nearest'});
    }));
    driverDetails(rows.find(row => row.driver === selectedDriver));
  }

  function render(savedOutputs) {
    outputs = savedOutputs || {};
    if (!el('tyreTimeline')) return;
    if (!bound) {
      el('tyreSort').addEventListener('change', draw);
      document.querySelectorAll('[data-tyre-plan]').forEach(button => button.addEventListener('click', () => {activePlan = button.dataset.tyrePlan; draw();}));
      bound = true;
    }
    if (activePlan === 'alternative' && !plans(outputs.strategy, 'alternative').some(row => row.stints.length)) activePlan = 'primary';
    const context = outputs.savedContext || {}, venue = outputs.details?.venue || {};
    el('tyreSort').querySelector('option[value="grid"]').textContent = gridLabel();
    const freshness = outputs.gridFreshness || {}, notice = el('gridFreshnessNotice');
    if (notice) {
      notice.hidden = freshness.status !== 'grid_update_available';
      const changes = (freshness.changes || []).slice().sort((a,b)=>Math.abs(b.latest_position-b.saved_position)-Math.abs(a.latest_position-a.saved_position));
      notice.textContent = `Newer FIA grid available: ${changes.slice(0,3).map(row=>`${row.Driver} P${row.saved_position} → ${row.pit_lane_start ? 'pit lane' : `P${row.latest_position}`}`).join('; ')}${changes.length>3 ? `; ${changes.length-3} other changes` : ''}. Saved probabilities and strategies still use the previous grid. A fresh forecast is required.`;
    }
    const eventName = typeof displayEventName === 'function' ? displayEventName(context.event) : context.event;
    el('tyreEvent').textContent = [context.year, eventName, context.session ? `${context.session} cutoff` : ''].filter(Boolean).join(' · ') || 'Saved race';
    el('tyreCircuit').textContent = venue.circuit_name || eventName || 'Tyre strategy';
    el('tyreDistance').textContent = number(venue.race_laps) > 0 ? `${venue.race_laps} race laps` : 'Race distance not recorded';
    draw();
  }

  root.TyreStrategy = {render, plans, parseSequence};
  if (typeof module !== 'undefined' && module.exports) module.exports = root.TyreStrategy;
})(typeof window === 'undefined' ? globalThis : window);

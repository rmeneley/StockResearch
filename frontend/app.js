/**
 * AlphaRadar — Multi-Factor Stock Research Dashboard
 * Handles real-time factor weight recalculation, dynamic ranking, and SEC Form 4 modal.
 */

// Application State
const state = {
  stocks: [],
  activeTab: 'all', // 'all', 'bullish', 'bearish'
  searchQuery: '',
  weights: {
    tech: 0.35,
    insider: 0.25,
    vol: 0.20,
    sent: 0.20,
  },
  presets: {
    balanced: { tech: 35, insider: 25, vol: 20, sent: 20 },
    technicals: { tech: 60, insider: 10, vol: 20, sent: 10 },
    insider: { tech: 15, insider: 60, vol: 10, sent: 15 },
    volume: { tech: 25, insider: 15, vol: 50, sent: 10 },
  },
};

// DOM Elements
const elements = {
  // Sliders & Labels
  sliderTech: document.getElementById('sliderTech'),
  sliderInsider: document.getElementById('sliderInsider'),
  sliderVol: document.getElementById('sliderVol'),
  sliderSent: document.getElementById('sliderSent'),
  wTechVal: document.getElementById('wTechVal'),
  wInsiderVal: document.getElementById('wInsiderVal'),
  wVolVal: document.getElementById('wVolVal'),
  wSentVal: document.getElementById('wSentVal'),
  normTechLabel: document.getElementById('normTechLabel'),
  normInsiderLabel: document.getElementById('normInsiderLabel'),
  normVolLabel: document.getElementById('normVolLabel'),
  normSentLabel: document.getElementById('normSentLabel'),

  // KPIs
  kpiBullishTicker: document.getElementById('kpiBullishTicker'),
  kpiBullishScore: document.getElementById('kpiBullishScore'),
  kpiBearishTicker: document.getElementById('kpiBearishTicker'),
  kpiBearishScore: document.getElementById('kpiBearishScore'),
  kpiAvgScore: document.getElementById('kpiAvgScore'),
  kpiMarketTone: document.getElementById('kpiMarketTone'),
  kpiTrackedCount: document.getElementById('kpiTrackedCount'),

  // Table
  tableBody: document.getElementById('rankingsTableBody'),
  searchInput: document.getElementById('searchInput'),
  tabAll: document.getElementById('tabAll'),
  tabBullish: document.getElementById('tabBullish'),
  tabBearish: document.getElementById('tabBearish'),

  // Buttons & Forms
  refreshBtn: document.getElementById('refreshBtn'),
  refreshIcon: document.getElementById('refreshIcon'),
  addTickerForm: document.getElementById('addTickerForm'),
  newTickerInput: document.getElementById('newTickerInput'),
  addTickerBtn: document.getElementById('addTickerBtn'),
  presetBtns: document.querySelectorAll('.preset-btn'),

  // Modal
  insiderModal: document.getElementById('insiderModal'),
  closeModalBtn: document.getElementById('closeModalBtn'),
  modalDismissBtn: document.getElementById('modalDismissBtn'),
  modalTickerTitle: document.getElementById('modalTickerTitle'),
  modalSubtitle: document.getElementById('modalSubtitle'),
  modalDiscretionaryBadge: document.getElementById('modalDiscretionaryBadge'),
  modalTotalValue: document.getElementById('modalTotalValue'),
  modalUniqueCount: document.getElementById('modalUniqueCount'),
  modalPlanType: document.getElementById('modalPlanType'),
  modalTableBody: document.getElementById('modalTableBody'),
  healthBadge: document.getElementById('healthBadge'),
  healthText: document.getElementById('healthText'),
};

// -----------------------------------------------------------------------------
// Scoring & Calculations
// -----------------------------------------------------------------------------

function getNormalizedWeights() {
  const rawTech = parseFloat(elements.sliderTech.value) || 0;
  const rawInsider = parseFloat(elements.sliderInsider.value) || 0;
  const rawVol = parseFloat(elements.sliderVol.value) || 0;
  const rawSent = parseFloat(elements.sliderSent.value) || 0;

  const sum = rawTech + rawInsider + rawVol + rawSent || 1.0;
  return {
    tech: rawTech / sum,
    insider: rawInsider / sum,
    vol: rawVol / sum,
    sent: rawSent / sum,
  };
}

function updateSliderLabels() {
  const weights = getNormalizedWeights();
  state.weights = weights;

  elements.wTechVal.textContent = `${Math.round(weights.tech * 100)}%`;
  elements.wInsiderVal.textContent = `${Math.round(weights.insider * 100)}%`;
  elements.wVolVal.textContent = `${Math.round(weights.vol * 100)}%`;
  elements.wSentVal.textContent = `${Math.round(weights.sent * 100)}%`;

  elements.normTechLabel.textContent = weights.tech.toFixed(2);
  elements.normInsiderLabel.textContent = weights.insider.toFixed(2);
  elements.normVolLabel.textContent = weights.vol.toFixed(2);
  elements.normSentLabel.textContent = weights.sent.toFixed(2);
}

function computeDynamicComposite(stock, weights) {
  const comp = (
    (stock.technical_score * weights.tech) +
    (stock.insider_score * weights.insider) +
    (stock.volume_score * weights.vol) +
    (stock.sentiment_score * weights.sent)
  );
  return Math.min(1.0, Math.max(-1.0, comp));
}

function getSignalLabel(score) {
  if (score >= 0.40) return { label: 'Strong Bullish', color: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30' };
  if (score >= 0.12) return { label: 'Bullish', color: 'text-emerald-300 bg-emerald-500/10 border-emerald-500/20' };
  if (score <= -0.40) return { label: 'Strong Bearish', color: 'text-rose-400 bg-rose-500/10 border-rose-500/30' };
  if (score <= -0.12) return { label: 'Bearish', color: 'text-rose-300 bg-rose-500/10 border-rose-500/20' };
  return { label: 'Neutral', color: 'text-slate-400 bg-slate-800 border-slate-700' };
}

// -----------------------------------------------------------------------------
// Rendering Functions
// -----------------------------------------------------------------------------

function renderDashboard() {
  const weights = state.weights;

  // Recalculate composite scores for all stocks
  const evaluated = state.stocks.map(s => {
    const score = computeDynamicComposite(s, weights);
    return { ...s, dynamicScore: score };
  });

  // Filter based on tab and search query
  let filtered = evaluated.filter(s => {
    const matchesSearch = s.ticker.toLowerCase().includes(state.searchQuery.toLowerCase()) ||
                          s.company_name.toLowerCase().includes(state.searchQuery.toLowerCase());
    if (!matchesSearch) return false;

    if (state.activeTab === 'bullish') return s.dynamicScore > 0.05;
    if (state.activeTab === 'bearish') return s.dynamicScore < -0.05;
    return true;
  });

  // Sort
  if (state.activeTab === 'bearish') {
    filtered.sort((a, b) => a.dynamicScore - b.dynamicScore); // Most negative first
  } else {
    filtered.sort((a, b) => b.dynamicScore - a.dynamicScore); // Highest positive first
  }

  // Update KPIs
  updateKPIs(evaluated);

  // Render Table Rows
  if (filtered.length === 0) {
    elements.tableBody.innerHTML = `
      <tr>
        <td colspan="9" class="py-8 text-center text-slate-500 text-sm">
          No stocks match the selected criteria or search term.
        </td>
      </tr>
    `;
    return;
  }

  elements.tableBody.innerHTML = filtered.map((stock, index) => {
    const signal = getSignalLabel(stock.dynamicScore);
    const scorePct = Math.round(Math.abs(stock.dynamicScore) * 100);
    const isPositive = stock.dynamicScore >= 0;
    const chgPositive = stock.price_change_pct >= 0;

    const insiderCount = stock.insider?.recent_buys_count || 0;
    const insiderVal = stock.insider?.total_buy_value || 0;
    const hasDiscretionary = stock.insider?.has_discretionary_buy;

    return `
      <tr class="hover:bg-slate-800/40 transition group">
        <!-- Rank # -->
        <td class="py-4 pl-4 pr-2 text-center text-slate-500 font-mono text-xs">
          ${index + 1}
        </td>

        <!-- Ticker & Company -->
        <td class="py-4 px-3">
          <div class="flex flex-col">
            <span class="font-bold text-white group-hover:text-indigo-400 transition cursor-pointer flex items-center gap-1.5" onclick="openInsiderModal('${stock.ticker}')">
              ${stock.ticker}
              <i class="ph-bold ph-arrow-up-right text-xs opacity-0 group-hover:opacity-100 transition"></i>
            </span>
            <span class="text-xs text-slate-400 truncate max-w-[140px]" title="${stock.company_name}">
              ${stock.company_name}
            </span>
          </div>
        </td>

        <!-- Price & 1D Change -->
        <td class="py-4 px-3">
          <div class="flex flex-col">
            <span class="font-mono font-medium text-slate-200">$${stock.current_price.toFixed(2)}</span>
            <span class="text-[11px] font-mono ${chgPositive ? 'text-emerald-400' : 'text-rose-400'}">
              ${chgPositive ? '+' : ''}${stock.price_change_pct.toFixed(2)}%
            </span>
          </div>
        </td>

        <!-- Composite Score -->
        <td class="py-4 px-3">
          <div class="space-y-1">
            <div class="flex items-center space-x-2">
              <span class="font-mono font-bold text-sm ${isPositive ? 'text-emerald-400' : 'text-rose-400'}">
                ${stock.dynamicScore > 0 ? '+' : ''}${stock.dynamicScore.toFixed(3)}
              </span>
              <span class="px-2 py-0.5 rounded-full text-[10px] font-semibold border ${signal.color}">
                ${signal.label}
              </span>
            </div>
            <div class="score-track">
              <div class="${isPositive ? 'score-fill-positive' : 'score-fill-negative'}" style="width: ${scorePct}%;"></div>
            </div>
          </div>
        </td>

        <!-- Factor Breakdown Meters -->
        <td class="py-4 px-3">
          <div class="grid grid-cols-2 gap-x-2 gap-y-1 text-[10px] font-mono text-slate-400">
            <span title="Technical Score: ${stock.technical_score}">T: <span class="${stock.technical_score >= 0 ? 'text-blue-400' : 'text-rose-400'}">${stock.technical_score.toFixed(2)}</span></span>
            <span title="Insider Score: ${stock.insider_score}">I: <span class="${stock.insider_score > 0 ? 'text-emerald-400' : 'text-slate-500'}">${stock.insider_score.toFixed(2)}</span></span>
            <span title="Volume Score: ${stock.volume_score}">V: <span class="${stock.volume_score >= 0 ? 'text-amber-400' : 'text-rose-400'}">${stock.volume_score.toFixed(2)}</span></span>
            <span title="Sentiment Score: ${stock.sentiment_score}">S: <span class="${stock.sentiment_score >= 0 ? 'text-purple-400' : 'text-rose-400'}">${stock.sentiment_score.toFixed(2)}</span></span>
          </div>
        </td>

        <!-- Technicals (RSI & Trend) -->
        <td class="py-4 px-3">
          <div class="flex flex-col text-xs font-mono">
            <span class="text-slate-300">RSI: <strong class="${stock.rsi > 70 ? 'text-amber-400 font-bold' : stock.rsi < 30 ? 'text-blue-400 font-bold' : 'text-slate-300'}">${stock.rsi.toFixed(1)}</strong></span>
            <span class="text-[10px] text-slate-500">${stock.technicals?.trend_signal || 'Consolidation'}</span>
          </div>
        </td>

        <!-- RVOL -->
        <td class="py-4 px-3">
          <div class="flex items-center space-x-1">
            <span class="font-mono text-xs ${stock.rvol >= 1.5 ? 'text-amber-400 font-bold' : 'text-slate-300'}">
              ${stock.rvol.toFixed(2)}x
            </span>
            ${stock.rvol >= 2.0 ? '<i class="ph-fill ph-fire text-amber-400 text-sm" title="Surge Volume"></i>' : ''}
          </div>
        </td>

        <!-- Insider Conviction -->
        <td class="py-4 px-3">
          ${insiderCount > 0 ? `
            <div class="flex flex-col cursor-pointer" onclick="openInsiderModal('${stock.ticker}')">
              <span class="text-xs font-semibold text-emerald-400 flex items-center gap-1">
                ${insiderCount} Buys ($${(insiderVal / 1000).toFixed(0)}k)
              </span>
              <span class="text-[10px] ${hasDiscretionary ? 'text-emerald-300 font-medium' : 'text-slate-400'}">
                ${hasDiscretionary ? '★ Discretionary' : '10b5-1 Plan'}
              </span>
            </div>
          ` : `
            <span class="text-xs text-slate-500">No recent buys</span>
          `}
        </td>

        <!-- Action -->
        <td class="py-4 pr-4 pl-2 text-right">
          <button onclick="openInsiderModal('${stock.ticker}')" class="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 text-xs font-medium transition active:scale-95 inline-flex items-center space-x-1">
            <i class="ph-bold ph-file-text"></i>
            <span>Form 4</span>
          </button>
        </td>
      </tr>
    `;
  }).join('');
}

function updateKPIs(evaluatedStocks) {
  if (!evaluatedStocks || evaluatedStocks.length === 0) return;

  // Sort clone descending
  const sorted = [...evaluatedStocks].sort((a, b) => b.dynamicScore - a.dynamicScore);
  const topBullish = sorted[0];
  const topBearish = sorted[sorted.length - 1];

  // Average
  const totalScore = sorted.reduce((acc, curr) => acc + curr.dynamicScore, 0);
  const avg = totalScore / sorted.length;

  elements.kpiBullishTicker.textContent = topBullish.ticker;
  elements.kpiBullishScore.textContent = `Score: ${topBullish.dynamicScore > 0 ? '+' : ''}${topBullish.dynamicScore.toFixed(3)}`;

  elements.kpiBearishTicker.textContent = topBearish.ticker;
  elements.kpiBearishScore.textContent = `Score: ${topBearish.dynamicScore > 0 ? '+' : ''}${topBearish.dynamicScore.toFixed(3)}`;

  elements.kpiAvgScore.textContent = `${avg > 0 ? '+' : ''}${avg.toFixed(3)}`;
  elements.kpiMarketTone.textContent = avg > 0.1 ? 'Bullish Tilt' : avg < -0.1 ? 'Bearish Tilt' : 'Neutral Range';
  elements.kpiTrackedCount.textContent = evaluatedStocks.length;
}

// -----------------------------------------------------------------------------
// Data Fetching
// -----------------------------------------------------------------------------

async function loadRankings(forceRefresh = false) {
  try {
    elements.refreshIcon.classList.add('animate-spin');
    const url = `/api/rankings?force_refresh=${forceRefresh}`;
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);

    const data = await res.json();
    state.stocks = data.stocks || [];
    renderDashboard();
  } catch (err) {
    console.error('Failed to load rankings:', err);
    elements.tableBody.innerHTML = `
      <tr>
        <td colspan="9" class="py-8 text-center text-rose-400 text-sm">
          Failed to load ranking data from backend: ${err.message}
        </td>
      </tr>
    `;
  } finally {
    elements.refreshIcon.classList.remove('animate-spin');
  }
}

async function checkHealth() {
  try {
    const res = await fetch('/api/health');
    const data = await res.json();
    if (data.status === 'healthy') {
      elements.healthBadge.classList.remove('hidden');
      elements.healthText.textContent = `Live (${data.cached_tickers_count} cached)`;
    }
  } catch (err) {
    console.warn('Health check warning:', err);
  }
}

// -----------------------------------------------------------------------------
// SEC Form 4 Modal Handler
// -----------------------------------------------------------------------------

window.openInsiderModal = async function(ticker) {
  elements.insiderModal.classList.remove('hidden');
  elements.modalTickerTitle.textContent = ticker;
  elements.modalSubtitle.textContent = `Loading Form 4 transactions for ${ticker}...`;
  elements.modalTableBody.innerHTML = `
    <tr>
      <td colspan="7" class="py-8 text-center text-slate-500">
        <i class="ph-bold ph-spinner animate-spin text-xl mb-1 block mx-auto text-indigo-400"></i>
        Parsing SEC Form 4 filings via edgartools...
      </td>
    </tr>
  `;

  try {
    const res = await fetch(`/api/insider/${ticker}`);
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    const data = await res.json();

    const summary = data.summary || {};
    const txs = data.transactions || [];

    elements.modalSubtitle.textContent = `${txs.length} Open-Market Code 'P' Buys in Last 90 Days`;
    elements.modalTotalValue.textContent = `$${(summary.total_buy_value || 0).toLocaleString()}`;
    elements.modalUniqueCount.textContent = summary.unique_insiders_count || 0;
    elements.modalPlanType.textContent = summary.has_discretionary_buy ? 'Yes (Discretionary)' : (txs.length > 0 ? '10b5-1 Only' : 'None');

    if (summary.has_discretionary_buy) {
      elements.modalDiscretionaryBadge.className = 'px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30';
      elements.modalDiscretionaryBadge.textContent = '★ High Conviction Discretionary';
    } else if (txs.length > 0) {
      elements.modalDiscretionaryBadge.className = 'px-2 py-0.5 rounded text-[11px] font-semibold bg-blue-500/20 text-blue-400 border border-blue-500/30';
      elements.modalDiscretionaryBadge.textContent = 'Rule 10b5-1 Plan';
    } else {
      elements.modalDiscretionaryBadge.className = 'px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-800 text-slate-400 border border-slate-700';
      elements.modalDiscretionaryBadge.textContent = 'No Recent Buys';
    }

    if (txs.length === 0) {
      elements.modalTableBody.innerHTML = `
        <tr>
          <td colspan="7" class="py-8 text-center text-slate-500">
            No recent Form 4 open-market purchases (Code 'P') found for ${ticker}.
          </td>
        </tr>
      `;
      return;
    }

    elements.modalTableBody.innerHTML = txs.map(tx => {
      const isDiscretionary = !tx.is_10b5_1;
      return `
        <tr class="hover:bg-slate-900/40 transition">
          <td class="py-2.5 px-3 font-mono text-slate-300">${tx.filing_date}</td>
          <td class="py-2.5 px-3 font-medium text-white">${tx.insider_name}</td>
          <td class="py-2.5 px-3 text-slate-400">${tx.insider_title || 'Officer'}</td>
          <td class="py-2.5 px-3 text-right font-mono text-slate-300">${Math.round(tx.shares).toLocaleString()}</td>
          <td class="py-2.5 px-3 text-right font-mono text-slate-300">$${tx.price_per_share.toFixed(2)}</td>
          <td class="py-2.5 px-3 text-right font-mono font-semibold text-emerald-400">$${Math.round(tx.total_value).toLocaleString()}</td>
          <td class="py-2.5 px-3 text-center">
            <span class="px-2 py-0.5 rounded text-[10px] font-medium border ${isDiscretionary ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' : 'bg-slate-800 text-slate-400 border-slate-700'}">
              ${isDiscretionary ? 'Discretionary' : 'Rule 10b5-1'}
            </span>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    elements.modalTableBody.innerHTML = `
      <tr>
        <td colspan="7" class="py-8 text-center text-rose-400">
          Failed to load insider transactions: ${err.message}
        </td>
      </tr>
    `;
  }
};

function closeInsiderModal() {
  elements.insiderModal.classList.add('hidden');
}

// -----------------------------------------------------------------------------
// Event Listeners
// -----------------------------------------------------------------------------

function setupEventListeners() {
  // Sliders input
  [elements.sliderTech, elements.sliderInsider, elements.sliderVol, elements.sliderSent].forEach(slider => {
    slider.addEventListener('input', () => {
      updateSliderLabels();
      renderDashboard();
    });
  });

  // Preset Buttons
  elements.presetBtns.forEach(btn => {
    btn.addEventListener('click', () => {
      const presetName = btn.dataset.preset;
      const preset = state.presets[presetName];
      if (preset) {
        elements.sliderTech.value = preset.tech;
        elements.sliderInsider.value = preset.insider;
        elements.sliderVol.value = preset.vol;
        elements.sliderSent.value = preset.sent;
        updateSliderLabels();
        renderDashboard();
      }
    });
  });

  // Tabs
  elements.tabAll.addEventListener('click', () => setTab('all'));
  elements.tabBullish.addEventListener('click', () => setTab('bullish'));
  elements.tabBearish.addEventListener('click', () => setTab('bearish'));

  function setTab(tab) {
    state.activeTab = tab;
    [elements.tabAll, elements.tabBullish, elements.tabBearish].forEach(t => {
      t.className = 'tab-btn px-4 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-white transition';
    });
    if (tab === 'all') elements.tabAll.className = 'tab-btn px-4 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 text-white shadow transition';
    if (tab === 'bullish') elements.tabBullish.className = 'tab-btn px-4 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 text-white shadow transition';
    if (tab === 'bearish') elements.tabBearish.className = 'tab-btn px-4 py-1.5 rounded-lg text-xs font-semibold bg-rose-600 text-white shadow transition';
    renderDashboard();
  }

  // Search input
  elements.searchInput.addEventListener('input', (e) => {
    state.searchQuery = e.target.value.trim();
    renderDashboard();
  });

  // Add Ticker form
  elements.addTickerForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const ticker = elements.newTickerInput.value.trim().toUpperCase();
    if (!ticker) return;

    elements.addTickerBtn.disabled = true;
    elements.addTickerBtn.innerHTML = '<i class="ph-bold ph-spinner animate-spin"></i>';

    try {
      const res = await fetch(`/api/ticker/${ticker}`, { method: 'POST' });
      if (!res.ok) {
        const errorData = await res.json();
        alert(errorData.detail || 'Failed to add ticker.');
      } else {
        elements.newTickerInput.value = '';
        await loadRankings(false);
      }
    } catch (err) {
      alert(`Network error adding ticker: ${err.message}`);
    } finally {
      elements.addTickerBtn.disabled = false;
      elements.addTickerBtn.innerHTML = '<i class="ph-bold ph-plus"></i><span>Add</span>';
    }
  });

  // Refresh button
  elements.refreshBtn.addEventListener('click', () => {
    loadRankings(true);
  });

  // Modal close handlers
  elements.closeModalBtn.addEventListener('click', closeInsiderModal);
  elements.modalDismissBtn.addEventListener('click', closeInsiderModal);
  elements.insiderModal.addEventListener('click', (e) => {
    if (e.target === elements.insiderModal) closeInsiderModal();
  });
  window.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeInsiderModal();
  });
}

// -----------------------------------------------------------------------------
// Initialization
// -----------------------------------------------------------------------------

document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  updateSliderLabels();
  loadRankings(false);
  checkHealth();
});


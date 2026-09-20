/**
 * AlphaRadar — Multi-Factor Stock Research Dashboard
 * Handles real-time factor weight recalculation, dynamic ranking, and SEC Form 4 modal.
 */

// Application State
const state = {
  stocks: [],
  activeTab: 'all', // 'all', 'bullish', 'bearish'
  searchQuery: '',
  activeModalTab: 'news', // 'news', 'insider'
  currentModalTicker: null,
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
  modalPriceBadge: document.getElementById('modalPriceBadge'),
  modalDiscretionaryBadge: document.getElementById('modalDiscretionaryBadge'),
  modalTabNews: document.getElementById('modalTabNews'),
  modalTabInsider: document.getElementById('modalTabInsider'),
  modalNewsCountBadge: document.getElementById('modalNewsCountBadge'),
  modalInsiderCountBadge: document.getElementById('modalInsiderCountBadge'),
  modalPanelNews: document.getElementById('modalPanelNews'),
  modalPanelInsider: document.getElementById('modalPanelInsider'),
  modalBullishRatio: document.getElementById('modalBullishRatio'),
  modalBearishRatio: document.getElementById('modalBearishRatio'),
  modalSentimentStatus: document.getElementById('modalSentimentStatus'),
  modalNewsContainer: document.getElementById('modalNewsContainer'),
  modalTotalValue: document.getElementById('modalTotalValue'),
  modalTotalSold: document.getElementById('modalTotalSold'),
  modalNetFlow: document.getElementById('modalNetFlow'),
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
        <td colspan="10" class="py-8 text-center text-slate-500 text-sm">
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
            <span class="font-bold text-white group-hover:text-indigo-400 transition cursor-pointer flex items-center gap-1.5" onclick="openTickerModal('${stock.ticker}', 'news')" title="View ${stock.ticker} news & articles">
              ${stock.ticker}
              <i class="ph-bold ph-newspaper text-xs opacity-0 group-hover:opacity-100 transition text-purple-400"></i>
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
          ${(() => {
            const buys = stock.insider?.recent_buys_count || 0;
            const buyVal = stock.insider?.total_buy_value || 0;
            const sells = stock.insider?.recent_sells_count || 0;
            const sellVal = stock.insider?.total_sell_value || 0;
            const hasDiscBuy = stock.insider?.has_discretionary_buy;
            const hasDiscSell = stock.insider?.has_discretionary_sell;

            if (buys > 0) {
              return `
                <div class="flex flex-col cursor-pointer" onclick="openTickerModal('${stock.ticker}', 'insider')">
                  <span class="text-xs font-semibold text-emerald-400 flex items-center gap-1">
                    ${buys} Buys ($${(buyVal / 1000).toFixed(0)}k)
                  </span>
                  <span class="text-[10px] ${hasDiscBuy ? 'text-emerald-300 font-medium' : 'text-slate-400'}">
                    ${hasDiscBuy ? '★ Discretionary Buy' : '10b5-1 Plan'}
                  </span>
                </div>
              `;
            } else if (sells > 0) {
              const sellStr = sellVal >= 1000000 ? `$${(sellVal / 1000000).toFixed(1)}M` : `$${(sellVal / 1000).toFixed(0)}k`;
              return `
                <div class="flex flex-col cursor-pointer" onclick="openTickerModal('${stock.ticker}', 'insider')">
                  <span class="text-xs font-semibold ${hasDiscSell ? 'text-rose-400' : 'text-amber-400'} flex items-center gap-1">
                    ${sells} Sells (${sellStr})
                  </span>
                  <span class="text-[10px] ${hasDiscSell ? 'text-rose-300 font-medium' : 'text-slate-400'}">
                    ${hasDiscSell ? '⚠ Discretionary' : '10b5-1 Plan'}
                  </span>
                </div>
              `;
            } else {
              return `<span class="text-xs text-slate-500">No recent activity</span>`;
            }
          })()}
        </td>

        <!-- Next Earnings -->
        <td class="py-4 px-3">
          ${(() => {
            const ed = stock.next_earnings_date;
            if (!ed) return `<span class="text-xs text-slate-500 font-mono">—</span>`;
            try {
              const parts = ed.split('T')[0].split('-').map(Number);
              const target = new Date(parts[0], parts[1] - 1, parts[2]);
              const now = new Date();
              now.setHours(0, 0, 0, 0);
              const diffTime = target - now;
              const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));

              const formatted = target.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });

              if (diffDays >= 0 && diffDays <= 7) {
                return `
                  <div class="flex flex-col">
                    <span class="text-xs font-bold text-amber-400 font-mono">${formatted}</span>
                    <span class="text-[10px] text-amber-300 font-semibold flex items-center gap-0.5">
                      <i class="ph-bold ph-warning"></i> in ${diffDays === 0 ? 'today' : diffDays + 'd'}
                    </span>
                  </div>
                `;
              } else if (diffDays > 7 && diffDays <= 30) {
                return `
                  <div class="flex flex-col">
                    <span class="text-xs font-semibold text-slate-200 font-mono">${formatted}</span>
                    <span class="text-[10px] text-indigo-400 font-mono">in ${diffDays}d</span>
                  </div>
                `;
              } else if (diffDays > 30) {
                return `
                  <div class="flex flex-col">
                    <span class="text-xs text-slate-300 font-mono">${formatted}</span>
                    <span class="text-[10px] text-slate-500 font-mono">in ${diffDays}d</span>
                  </div>
                `;
              } else {
                return `<span class="text-xs text-slate-400 font-mono">${formatted}</span>`;
              }
            } catch (e) {
              return `<span class="text-xs text-slate-300 font-mono">${ed}</span>`;
            }
          })()}
        </td>

        <!-- Action -->
        <td class="py-4 pr-4 pl-2 text-right">

          <div class="flex items-center justify-end space-x-1.5">
            <button onclick="openTickerModal('${stock.ticker}', 'news')" class="px-2 py-1 rounded bg-purple-500/10 hover:bg-purple-500/20 text-purple-300 border border-purple-500/30 text-xs font-medium transition active:scale-95 inline-flex items-center space-x-1" title="View company news">
              <i class="ph-bold ph-newspaper"></i>
              <span class="hidden sm:inline">News</span>
            </button>
            <button onclick="openTickerModal('${stock.ticker}', 'insider')" class="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700 text-xs font-medium transition active:scale-95 inline-flex items-center space-x-1" title="View SEC Form 4 filings">
              <i class="ph-bold ph-file-text"></i>
              <span class="hidden sm:inline">Form 4</span>
            </button>
          </div>
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
// Ticker Research & Detail Modal (News + SEC Form 4)
// -----------------------------------------------------------------------------

function formatTimeAgo(dateStr) {
  if (!dateStr) return '';
  try {
    const date = new Date(dateStr);
    const now = new Date();
    const diffSec = Math.floor((now - date) / 1000);
    if (isNaN(diffSec) || diffSec < 0) return dateStr.split('T')[0] || dateStr;
    if (diffSec < 60) return 'Just now';
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    if (diffSec < 604800) return `${Math.floor(diffSec / 86400)}d ago`;
    return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
  } catch (e) {
    return dateStr;
  }
}

function renderNewsCards(articles) {
  if (!articles || articles.length === 0) {
    return `
      <div class="py-12 text-center text-slate-500">
        <i class="ph-bold ph-newspaper-clipping text-3xl mb-2 block mx-auto text-slate-600"></i>
        <p class="text-sm font-medium text-slate-400">No recent news articles found for this company.</p>
        <p class="text-xs text-slate-600 mt-1">Check back soon as new financial feeds are published.</p>
      </div>
    `;
  }

  return articles.map(art => {
    const timeAgo = formatTimeAgo(art.published_at);
    const hasThumb = Boolean(art.thumbnail && art.thumbnail.startsWith('http'));
    const sentLabel = art.sentiment || 'Neutral';
    const sentColor = sentLabel === 'Bullish' ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/25' :
                      sentLabel === 'Bearish' ? 'bg-rose-500/10 text-rose-400 border-rose-500/25' :
                      'bg-slate-800 text-slate-400 border-slate-700/60';

    return `
      <div class="news-card flex flex-col sm:flex-row items-start gap-4">
        ${hasThumb ? `
          <div class="w-full sm:w-40 h-24 sm:h-24 flex-shrink-0 bg-slate-800 rounded-lg overflow-hidden border border-slate-700/60">
            <img src="${art.thumbnail}" alt="" class="news-card-thumb" loading="lazy" onerror="this.parentElement.style.display='none'">
          </div>
        ` : ''}
        <div class="flex-1 min-w-0 space-y-1.5 w-full">
          <div class="flex items-center justify-between text-[11px] text-slate-400 gap-2">
            <div class="flex items-center gap-2">
              <span class="px-2 py-0.5 rounded bg-purple-500/10 text-purple-300 font-semibold border border-purple-500/20">
                ${art.publisher || 'Financial Press'}
              </span>
              <span class="px-1.5 py-0.5 rounded text-[10px] font-semibold border ${sentColor}">
                ${sentLabel}
              </span>
            </div>
            <span class="font-mono text-slate-500 text-[11px]">${timeAgo}</span>
          </div>
          <a href="${art.url}" target="_blank" rel="noopener noreferrer" class="font-bold text-white hover:text-indigo-300 text-sm line-clamp-2 transition flex items-start gap-1 group">
            <span>${art.title}</span>
            <i class="ph-bold ph-arrow-up-right text-xs opacity-70 group-hover:opacity-100 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition flex-shrink-0 mt-1"></i>
          </a>
          ${art.summary ? `
            <p class="text-xs text-slate-400 line-clamp-2 leading-relaxed">
              ${art.summary}
            </p>
          ` : ''}
        </div>
      </div>
    `;
  }).join('');
}

window.switchModalTab = function(tab) {
  state.activeModalTab = tab;
  if (!elements.modalTabNews || !elements.modalTabInsider) return;

  if (tab === 'news') {
    elements.modalTabNews.classList.add('active');
    elements.modalTabNews.classList.remove('text-slate-400', 'border-transparent');
    elements.modalTabInsider.classList.remove('active');
    elements.modalTabInsider.classList.add('text-slate-400', 'border-transparent');

    elements.modalPanelNews.classList.remove('hidden');
    elements.modalPanelInsider.classList.add('hidden');
  } else {
    elements.modalTabInsider.classList.add('active');
    elements.modalTabInsider.classList.remove('text-slate-400', 'border-transparent');
    elements.modalTabNews.classList.remove('active');
    elements.modalTabNews.classList.add('text-slate-400', 'border-transparent');

    elements.modalPanelInsider.classList.remove('hidden');
    elements.modalPanelNews.classList.add('hidden');
  }
};

window.openTickerModal = async function(ticker, defaultTab = 'news') {
  state.currentModalTicker = ticker;
  elements.insiderModal.classList.remove('hidden');
  switchModalTab(defaultTab);

  const stock = state.stocks.find(s => s.ticker === ticker);
  elements.modalTickerTitle.textContent = ticker;
  elements.modalSubtitle.textContent = stock ? stock.company_name : `Loading details for ${ticker}...`;

  if (elements.modalPriceBadge) {
    if (stock) {
      const chg = stock.price_change_pct;
      elements.modalPriceBadge.textContent = `$${stock.current_price.toFixed(2)} (${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%)`;
      elements.modalPriceBadge.className = `font-mono text-xs font-semibold px-2.5 py-0.5 rounded-lg border ${chg >= 0 ? 'bg-emerald-500/10 text-emerald-300 border-emerald-500/30' : 'bg-rose-500/10 text-rose-300 border-rose-500/30'}`;
    } else {
      elements.modalPriceBadge.textContent = '';
    }
  }

  // Reset counters & show loading indicators
  if (elements.modalNewsCountBadge) elements.modalNewsCountBadge.textContent = '...';
  if (elements.modalInsiderCountBadge) elements.modalInsiderCountBadge.textContent = '...';

  elements.modalNewsContainer.innerHTML = `
    <div class="py-12 text-center text-slate-500 text-sm">
      <i class="ph-bold ph-spinner animate-spin text-2xl mb-2 block mx-auto text-purple-400"></i>
      Fetching latest news articles and headlines for ${ticker}...
    </div>
  `;

  elements.modalTableBody.innerHTML = `
    <tr>
      <td colspan="8" class="py-8 text-center text-slate-500">
        <i class="ph-bold ph-spinner animate-spin text-xl mb-1 block mx-auto text-indigo-400"></i>
        Parsing SEC Form 4 filings via edgartools...
      </td>
    </tr>
  `;

  // Fetch News and Form 4 in parallel
  loadTickerNews(ticker, stock);
  loadTickerInsider(ticker);
};

window.openInsiderModal = function(ticker) {
  openTickerModal(ticker, 'insider');
};

async function loadTickerNews(ticker, stock) {
  try {
    const res = await fetch(`/api/news/${ticker}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const articles = data.articles || [];

    if (elements.modalNewsCountBadge) {
      elements.modalNewsCountBadge.textContent = articles.length;
    }

    // Calculate live sentiment ratios from loaded articles
    let bullCount = 0, bearCount = 0, neuCount = 0;
    articles.forEach(a => {
      if (a.sentiment === 'Bullish') bullCount++;
      else if (a.sentiment === 'Bearish') bearCount++;
      else neuCount++;
    });
    const total = articles.length || 1;
    const bullPct = Math.round(((bullCount + 0.5 * neuCount) / total) * 100);
    const bearPct = Math.round(((bearCount + 0.5 * neuCount) / total) * 100);

    if (elements.modalBullishRatio) elements.modalBullishRatio.textContent = `${bullPct}%`;
    if (elements.modalBearishRatio) elements.modalBearishRatio.textContent = `${bearPct}%`;
    if (elements.modalSentimentStatus) {
      const net = bullPct - bearPct;
      let toneText = 'Neutral Balance';
      let toneColor = 'text-slate-300';
      if (net >= 25) {
        toneText = `+${net}% Strong Bullish Bias`;
        toneColor = 'text-emerald-400';
      } else if (net > 0) {
        toneText = `+${net}% Mild Bullish Bias`;
        toneColor = 'text-emerald-300';
      } else if (net <= -25) {
        toneText = `${net}% Strong Bearish Bias`;
        toneColor = 'text-rose-400';
      } else if (net < 0) {
        toneText = `${net}% Mild Bearish Bias`;
        toneColor = 'text-rose-300';
      }
      elements.modalSentimentStatus.textContent = `${toneText} (${articles.length} articles analyzed)`;
      elements.modalSentimentStatus.className = `text-xs font-semibold ${toneColor}`;
    }

    elements.modalNewsContainer.innerHTML = renderNewsCards(articles);
  } catch (err) {
    if (elements.modalNewsCountBadge) elements.modalNewsCountBadge.textContent = '0';
    elements.modalNewsContainer.innerHTML = `
      <div class="py-8 text-center text-rose-400 text-sm">
        <i class="ph-bold ph-warning text-2xl mb-1 block mx-auto"></i>
        Failed to load news articles: ${err.message}
      </div>
    `;
  }
}


async function loadTickerInsider(ticker) {
  try {
    const res = await fetch(`/api/insider/${ticker}`);
    if (!res.ok) throw new Error(`HTTP error ${res.status}`);
    const data = await res.json();

    const summary = data.summary || {};
    const txs = data.transactions || [];
    const buysCount = summary.recent_buys_count || 0;
    const sellsCount = summary.recent_sells_count || 0;
    const buyVal = summary.total_buy_value || 0;
    const sellVal = summary.total_sell_value || 0;
    const netVal = summary.net_value !== undefined ? summary.net_value : (buyVal - sellVal);

    if (elements.modalInsiderCountBadge) {
      elements.modalInsiderCountBadge.textContent = txs.length;
    }

    elements.modalTotalValue.textContent = `$${buyVal.toLocaleString(undefined, {maximumFractionDigits: 0})}`;
    if (elements.modalTotalSold) {
      elements.modalTotalSold.textContent = `$${sellVal.toLocaleString(undefined, {maximumFractionDigits: 0})}`;
    }
    if (elements.modalNetFlow) {
      elements.modalNetFlow.textContent = `${netVal >= 0 ? '+' : '-'}$${Math.abs(netVal).toLocaleString(undefined, {maximumFractionDigits: 0})}`;
      elements.modalNetFlow.className = `text-sm font-bold ${netVal > 0 ? 'text-emerald-400' : netVal < 0 ? 'text-rose-400' : 'text-slate-200'}`;
    }

    let planLabel = 'None';
    if (summary.has_discretionary_buy) planLabel = '★ Discretionary Buy';
    else if (summary.has_discretionary_sell) planLabel = '⚠ Discretionary Sell';
    else if (txs.length > 0) planLabel = 'Rule 10b5-1 Plan';
    elements.modalPlanType.textContent = planLabel;

    if (summary.has_discretionary_buy) {
      elements.modalDiscretionaryBadge.className = 'px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30';
      elements.modalDiscretionaryBadge.textContent = '★ Discretionary Insider Buying';
    } else if (buysCount > 0) {
      elements.modalDiscretionaryBadge.className = 'px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30';
      elements.modalDiscretionaryBadge.textContent = 'Insider Buying';
    } else if (summary.has_discretionary_sell) {
      elements.modalDiscretionaryBadge.className = 'px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-500/20 text-rose-400 border border-rose-500/30';
      elements.modalDiscretionaryBadge.textContent = '⚠ Discretionary Insider Selling';
    } else if (sellsCount > 0) {
      elements.modalDiscretionaryBadge.className = 'px-2 py-0.5 rounded text-[11px] font-semibold bg-blue-500/20 text-blue-400 border border-blue-500/30';
      elements.modalDiscretionaryBadge.textContent = 'Rule 10b5-1 Selling Plan';
    } else {
      elements.modalDiscretionaryBadge.className = 'px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-800 text-slate-400 border border-slate-700';
      elements.modalDiscretionaryBadge.textContent = 'No Recent Activity';
    }

    if (txs.length === 0) {
      elements.modalTableBody.innerHTML = `
        <tr>
          <td colspan="8" class="py-8 text-center text-slate-500">
            No recent Form 4 open-market transactions found for ${ticker}.
          </td>
        </tr>
      `;
      return;
    }

    elements.modalTableBody.innerHTML = txs.map(tx => {
      const isBuy = (tx.transaction_code === 'P' || (tx.transaction_type && tx.transaction_type.toLowerCase().includes('buy')));
      const isDiscretionary = !tx.is_10b5_1;
      return `
        <tr class="hover:bg-slate-900/40 transition">
          <td class="py-2.5 px-3 font-mono text-slate-300">${tx.filing_date}</td>
          <td class="py-2.5 px-3 font-medium text-white">${tx.insider_name}</td>
          <td class="py-2.5 px-3 text-slate-400">${tx.insider_title || 'Officer'}</td>
          <td class="py-2.5 px-3 text-center">
            <span class="px-2 py-0.5 rounded text-[10px] font-bold border ${isBuy ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' : 'bg-rose-500/10 text-rose-400 border-rose-500/30'}">
              ${isBuy ? 'BUY' : 'SELL'}
            </span>
          </td>
          <td class="py-2.5 px-3 text-right font-mono text-slate-300">${Math.round(tx.shares).toLocaleString()}</td>
          <td class="py-2.5 px-3 text-right font-mono text-slate-300">$${tx.price_per_share.toFixed(2)}</td>
          <td class="py-2.5 px-3 text-right font-mono font-semibold ${isBuy ? 'text-emerald-400' : 'text-rose-400'}">
            $${Math.round(tx.total_value).toLocaleString()}
          </td>
          <td class="py-2.5 px-3 text-center">
            <span class="px-2 py-0.5 rounded text-[10px] font-medium border ${isDiscretionary ? (isBuy ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30' : 'bg-rose-500/10 text-rose-400 border-rose-500/30') : 'bg-slate-800 text-slate-400 border-slate-700'}">
              ${isDiscretionary ? (isBuy ? '★ Discretionary' : '⚠ Discretionary') : 'Rule 10b5-1'}
            </span>
          </td>
        </tr>
      `;
    }).join('');
  } catch (err) {
    if (elements.modalInsiderCountBadge) elements.modalInsiderCountBadge.textContent = '0';
    elements.modalTableBody.innerHTML = `
      <tr>
        <td colspan="8" class="py-8 text-center text-rose-400">
          Failed to load insider transactions: ${err.message}
        </td>
      </tr>
    `;
  }
}

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


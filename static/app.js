// --- TradingBOT Dashboard Application Script ---

let tickerChart = null;
let equityChart = null;

// Global state variables
let portfolio = null;
let currentPrices = {}; // Cache of latest prices for PnL calculation
let rawTickerData = []; // Store raw records fetched from API
let currentTimeframeDays = "all"; // Default Max (all cached intraday data)

document.addEventListener("DOMContentLoaded", () => {
    // Initial fetch of portfolio status
    fetchPortfolioData().then(() => {
        const defaultTicker = document.getElementById("ticker-select").value;
        loadTickerChart(defaultTicker);
    });

    // Event listeners
    document.getElementById("ticker-select").addEventListener("change", (e) => {
        loadTickerChart(e.target.value);
    });

    // Timeframe selector buttons event listeners
    const tfButtons = document.querySelectorAll(".tf-btn");
    tfButtons.forEach(btn => {
        btn.addEventListener("click", (e) => {
            tfButtons.forEach(b => b.classList.remove("active"));
            e.target.classList.add("active");
            
            const days = e.target.getAttribute("data-days");
            currentTimeframeDays = days === "all" ? "all" : parseInt(days);
            
            const ticker = document.getElementById("ticker-select").value;
            filterAndRenderTickerChart(ticker);
        });
    });

    // Legend Checkboxes event listeners
    const legendToggles = [
        { id: "toggle-price", datasetIndex: 0 },
        { id: "toggle-dma50", datasetIndex: 1 },
        { id: "toggle-dma200", datasetIndex: 2 },
        { id: "toggle-volume", datasetIndex: 5 }
    ];
    legendToggles.forEach(toggle => {
        document.getElementById(toggle.id).addEventListener("change", (e) => {
            if (tickerChart) {
                tickerChart.setDatasetVisibility(toggle.datasetIndex, e.target.checked);
                tickerChart.update();
            }
        });
    });

    document.getElementById("profile-select").addEventListener("change", () => {
        fetchPortfolioData();
    });
    document.getElementById("reset-portfolio-btn").addEventListener("click", handleResetPortfolio);

    document.getElementById("run-bot-btn").addEventListener("click", triggerAgentScan);
    document.getElementById("clear-logs").addEventListener("click", () => {
        document.getElementById("log-output").innerHTML = "[System] Log history cleared.";
    });

    // Set intervals for automatic background polling
    fetchLogs();
    setInterval(fetchLogs, 5000); // Poll logs every 5 seconds
    setInterval(fetchPortfolioData, 3000); // Poll portfolio stats every 3 seconds for instant feedback
    
    // Auto-update the active ticker chart every 10 seconds to avoid unnecessary UI thrashing
    setInterval(() => {
        const activeTicker = document.getElementById("ticker-select").value;
        loadTickerChart(activeTicker);
    }, 10000);
});

async function handleResetPortfolio() {
    const profileSelect = document.getElementById("profile-select");
    const activeProfile = profileSelect ? profileSelect.value : "macro";
    const profileName = profileSelect ? profileSelect.options[profileSelect.selectedIndex].text : "Active Profile";
    
    if (!confirm(`Are you sure you want to reset capital back to INR 100,000 for '${profileName}'? This will clear all active holdings and trade history for this profile.`)) {
        return;
    }
    
    try {
        const response = await fetch("/api/reset_portfolio", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ profile: activeProfile })
        });
        const res = await response.json();
        if (res.status === "success") {
            alert(res.message);
            await fetchPortfolioData();
        } else {
            alert("Failed to reset portfolio: " + (res.message || "Unknown error"));
        }
    } catch (err) {
        alert("Error resetting portfolio: " + err.message);
    }
}

async function fetchPortfolioData() {
    try {
        const profileSelect = document.getElementById("profile-select");
        const activeProfile = profileSelect ? profileSelect.value : "macro";
        const response = await fetch(`/api/portfolio?profile=${activeProfile}`);
        if (!response.ok) throw new Error("Portfolio API response error");
        portfolio = await response.json();
        
        if (portfolio.current_prices) {
            Object.assign(currentPrices, portfolio.current_prices);
        }

        updateKPIs();
        updateTables();
        renderEquityChart();
    } catch (err) {
        console.error("Failed to load portfolio:", err);
        appendTerminalLog(`[Error] Failed to fetch portfolio data: ${err.message}`, "error");
    }
}

function updateKPIs() {
    if (!portfolio) return;

    const initial = parseFloat(portfolio.initial_capital);
    const cash = parseFloat(portfolio.current_cash);
    
    let holdingsValue = 0;
    const positionsList = Object.keys(portfolio.active_positions);
    
    positionsList.forEach(ticker => {
        const position = portfolio.active_positions[ticker];
        const currentPrice = currentPrices[ticker] || parseFloat(position.entry_price);
        holdingsValue += position.shares * currentPrice;
    });

    const totalValuation = cash + holdingsValue;
    const netReturn = ((totalValuation - initial) / initial) * 100;

    document.getElementById("val-total-val").textContent = `INR ${totalValuation.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
    document.getElementById("val-cash").textContent = `INR ${cash.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;

    const netReturnEl = document.getElementById("val-net-return");
    netReturnEl.textContent = `${netReturn >= 0 ? '+' : ''}${netReturn.toFixed(2)}%`;
    netReturnEl.className = `kpi-value ${netReturn >= 0 ? 'positive' : 'negative'}`;

    const trades = portfolio.trade_log || [];
    const wins = trades.filter(t => parseFloat(t.Profit_Loss) > 0).length;
    const winRate = trades.length > 0 ? (wins / trades.length) * 100 : 0;

    document.getElementById("val-win-rate").textContent = `${winRate.toFixed(1)}%`;
    document.getElementById("val-trades-count").textContent = `${trades.length} Closed Trades`;
    document.getElementById("val-positions-count").textContent = `${positionsList.length} Positions`;
}

function updateTables() {
    const posTableBody = document.querySelector("#positions-table tbody");
    posTableBody.innerHTML = "";
    
    const positionsList = Object.keys(portfolio.active_positions);
    if (positionsList.length === 0) {
        posTableBody.innerHTML = `<tr class="empty-row"><td colspan="6">No active positions. Trigger a scan or wait for signals.</td></tr>`;
    } else {
        positionsList.forEach(ticker => {
            const pos = portfolio.active_positions[ticker];
            const currentPrice = currentPrices[ticker] || parseFloat(pos.entry_price);
            const pnl = (currentPrice - parseFloat(pos.entry_price)) * pos.shares;
            
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><strong>${ticker}</strong></td>
                <td>${pos.entry_date}</td>
                <td>${pos.shares}</td>
                <td>INR ${parseFloat(pos.entry_price).toFixed(2)}</td>
                <td>INR ${currentPrice.toFixed(2)}</td>
                <td class="${pnl >= 0 ? 'positive' : 'negative'}" style="font-weight:600">
                    INR ${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
                </td>
            `;
            posTableBody.appendChild(tr);
        });
    }

    const ledgerTableBody = document.querySelector("#ledger-table tbody");
    ledgerTableBody.innerHTML = "";
    
    const trades = portfolio.trade_log || [];
    if (trades.length === 0) {
        ledgerTableBody.innerHTML = `<tr class="empty-row"><td colspan="7">No closed transactions yet.</td></tr>`;
    } else {
        [...trades].reverse().forEach(trade => {
            const pnl = parseFloat(trade.Profit_Loss);
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td><strong>${trade.Ticker}</strong></td>
                <td>${trade.Entry_Date}</td>
                <td>${trade.Exit_Date}</td>
                <td>INR ${parseFloat(trade.Entry_Price).toFixed(2)}</td>
                <td>INR ${parseFloat(trade.Exit_Price).toFixed(2)}</td>
                <td class="${pnl >= 0 ? 'positive' : 'negative'}" style="font-weight:600">
                    INR ${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}
                </td>
                <td><span class="badge">${trade.Exit_Reason}</span></td>
            `;
            ledgerTableBody.appendChild(tr);
        });
    }
}

async function loadTickerChart(ticker) {
    try {
        const response = await fetch(`/api/ticker/${ticker}`);
        if (!response.ok) throw new Error("Ticker data API error");
        rawTickerData = await response.json();
        
        if (rawTickerData.length > 0) {
            currentPrices[ticker] = rawTickerData[rawTickerData.length - 1].Close;
            updateKPIs();
            updateTables();
        }

        filterAndRenderTickerChart(ticker);
    } catch (err) {
        console.error(`Failed to load data for ${ticker}:`, err);
        appendTerminalLog(`[Error] Failed to fetch data for ${ticker}: ${err.message}`, "error");
    }
}

function filterAndRenderTickerChart(ticker) {
    let filteredData = rawTickerData;
    if (currentTimeframeDays !== "all") {
        filteredData = rawTickerData.slice(-currentTimeframeDays);
    }
    renderTickerChart(ticker, filteredData);
}

function renderTickerChart(ticker, data) {
    const ctx = document.getElementById("tickerChart").getContext("2d");
    
    const labels = data.map(r => r.Date);
    const closePrices = data.map(r => r.Close);
    const dma50 = data.map(r => r.MA50);
    const dma200 = data.map(r => r.MA200);
    const volumes = data.map(r => r.Volume);

    // Filter trade points for buy/sell markers
    const buyPoints = [];
    const sellPoints = [];

    const trades = portfolio ? (portfolio.trade_log || []) : [];
    trades.forEach(trade => {
        if (trade.Ticker === ticker) {
            const exitIndex = labels.indexOf(trade.Exit_Date);
            if (exitIndex !== -1) {
                sellPoints.push({ x: trade.Exit_Date, y: parseFloat(trade.Exit_Price) });
            }
            const entryIndex = labels.indexOf(trade.Entry_Date);
            if (entryIndex !== -1) {
                buyPoints.push({ x: trade.Entry_Date, y: parseFloat(trade.Entry_Price) });
            }
        }
    });

    if (portfolio && portfolio.active_positions[ticker]) {
        const activePos = portfolio.active_positions[ticker];
        const entryIndex = labels.indexOf(activePos.entry_date);
        if (entryIndex !== -1) {
            buyPoints.push({ x: activePos.entry_date, y: parseFloat(activePos.entry_price) });
        }
    }

    // Calculate dynamic scaling for volume axis to keep it in the bottom 25% of chart
    const maxVolume = Math.max(...volumes, 1);

    // Track checkbox states to preserve visibility on re-render
    const showPrice = document.getElementById("toggle-price").checked;
    const showDMA50 = document.getElementById("toggle-dma50").checked;
    const showDMA200 = document.getElementById("toggle-dma200").checked;
    const showVolume = document.getElementById("toggle-volume").checked;

    if (tickerChart) {
        tickerChart.data.labels = labels;
        tickerChart.data.datasets[0].data = closePrices;
        tickerChart.data.datasets[1].data = dma50;
        tickerChart.data.datasets[2].data = dma200;
        tickerChart.data.datasets[3].data = buyPoints;
        tickerChart.data.datasets[4].data = sellPoints;
        tickerChart.data.datasets[5].data = volumes;
        
        tickerChart.data.datasets[0].hidden = !showPrice;
        tickerChart.data.datasets[1].hidden = !showDMA50;
        tickerChart.data.datasets[2].hidden = !showDMA200;
        tickerChart.data.datasets[5].hidden = !showVolume;
        
        tickerChart.options.scales.y1.max = maxVolume * 4;
        tickerChart.update('none');
        return;
    }

    tickerChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: labels,
            datasets: [
                {
                    label: "Price on NSE",
                    data: closePrices,
                    borderColor: "#3b82f6",
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.15,
                    yAxisID: "y",
                    hidden: !showPrice
                },
                {
                    label: "50 DMA",
                    data: dma50,
                    borderColor: "#10b981",
                    borderWidth: 1.5,
                    borderDash: [3, 3],
                    pointRadius: 0,
                    fill: false,
                    yAxisID: "y",
                    hidden: !showDMA50
                },
                {
                    label: "200 DMA",
                    data: dma200,
                    borderColor: "#ef4444",
                    borderWidth: 1.5,
                    borderDash: [3, 3],
                    pointRadius: 0,
                    fill: false,
                    yAxisID: "y",
                    hidden: !showDMA200
                },
                {
                    label: "BUY Flags",
                    data: buyPoints,
                    type: "scatter",
                    backgroundColor: "#10b981",
                    borderColor: "#ffffff",
                    borderWidth: 1.5,
                    pointStyle: "triangle",
                    pointRadius: 9,
                    pointHoverRadius: 11,
                    yAxisID: "y"
                },
                {
                    label: "SELL Flags",
                    data: sellPoints,
                    type: "scatter",
                    backgroundColor: "#ef4444",
                    borderColor: "#ffffff",
                    borderWidth: 1.5,
                    pointStyle: "rectRot",
                    pointRadius: 9,
                    pointHoverRadius: 11,
                    yAxisID: "y"
                },
                {
                    label: "Volume",
                    data: volumes,
                    type: "bar",
                    backgroundColor: "rgba(99, 102, 241, 0.2)",
                    hoverBackgroundColor: "rgba(99, 102, 241, 0.45)",
                    borderWidth: 0,
                    yAxisID: "y1",
                    hidden: !showVolume,
                    barPercentage: 0.7
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: "index",
                intersect: false
            },
            plugins: {
                legend: {
                    display: false // Using custom HTML checkbox legend instead
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) label += ': ';
                            if (context.datasetIndex === 5) {
                                label += parseInt(context.parsed.y).toLocaleString();
                            } else if (context.parsed.y !== null) {
                                label += 'INR ' + context.parsed.y.toFixed(2);
                            }
                            return label;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { color: "rgba(255,255,255,0.03)" },
                    ticks: { color: "#9ca3af", font: { family: "Outfit" }, maxTicksLimit: 12 }
                },
                y: {
                    type: "linear",
                    position: "right",
                    grid: { color: "rgba(255,255,255,0.03)" },
                    ticks: { color: "#9ca3af", font: { family: "Outfit" } },
                    title: { display: true, text: "Price on NSE (INR)", color: "#9ca3af" }
                },
                y1: {
                    type: "linear",
                    position: "left",
                    grid: { display: false },
                    ticks: { 
                        color: "#9ca3af", 
                        font: { family: "Outfit" },
                        callback: function(value) {
                            if (value >= 1000000) return (value / 1000000).toFixed(1) + 'M';
                            if (value >= 1000) return (value / 1000).toFixed(0) + 'k';
                            return value;
                        }
                    },
                    title: { display: true, text: "Volume", color: "#9ca3af" },
                    max: maxVolume * 4 // Pushes volume bars to the bottom 25%
                }
            }
        }
    });
}

function renderEquityChart() {
    const ctx = document.getElementById("equityChart").getContext("2d");
    
    const initialCapital = portfolio ? parseFloat(portfolio.initial_capital) : 100000.0;
    
    const dates = ["Start Balance"];
    const values = [initialCapital];
    
    let currentBalance = initialCapital;
    const trades = portfolio ? (portfolio.trade_log || []) : [];
    
    const sortedTrades = [...trades].sort((a, b) => new Date(a.Exit_Date) - new Date(b.Exit_Date));
    
    sortedTrades.forEach(trade => {
        currentBalance += parseFloat(trade.Profit_Loss);
        dates.push(trade.Exit_Date);
        values.push(currentBalance);
    });

    if (equityChart) equityChart.destroy();

    const gradient = ctx.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, "rgba(59, 130, 246, 0.3)");
    gradient.addColorStop(1, "rgba(59, 130, 246, 0)");

    equityChart = new Chart(ctx, {
        type: "line",
        data: {
            labels: dates,
            datasets: [{
                label: "Account Equity Value",
                data: values,
                borderColor: "#60a5fa",
                borderWidth: 2.5,
                backgroundColor: gradient,
                fill: true,
                tension: 0.2,
                pointBackgroundColor: "#3b82f6",
                pointRadius: dates.length > 15 ? 1 : 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: {
                    grid: { color: "rgba(255,255,255,0.03)" },
                    ticks: { color: "#9ca3af", font: { family: "Outfit" }, maxTicksLimit: 8 }
                },
                y: {
                    grid: { color: "rgba(255,255,255,0.03)" },
                    ticks: { color: "#9ca3af", font: { family: "Outfit" } }
                }
            }
        }
    });
}

async function triggerAgentScan() {
    const btn = document.getElementById("run-bot-btn");
    const icon = btn.querySelector("i");
    const span = btn.querySelector("span");
    
    btn.disabled = true;
    btn.classList.add("loading");
    span.textContent = "SCANNING MARKET...";
    icon.style.display = "inline-block";

    appendTerminalLog("[System] Launching live paper runner daily scan cycle...", "info");

    try {
        const response = await fetch("/api/run_bot", { method: "POST" });
        const result = await response.json();
        
        if (result.status === "success") {
            appendTerminalLog(result.logs, "success");
            appendTerminalLog("[System] Scan cycle completed successfully. Updating portfolio metrics...", "info");
        } else {
            appendTerminalLog(`[Error] Execution failed: ${result.message}\n${result.logs || ''}`, "error");
        }

        await fetchPortfolioData();
        const currentTicker = document.getElementById("ticker-select").value;
        await loadTickerChart(currentTicker);

    } catch (err) {
        console.error("Scan trigger failed:", err);
        appendTerminalLog(`[Error] Connection failure: ${err.message}`, "error");
    } finally {
        btn.disabled = false;
        btn.classList.remove("loading");
        span.textContent = "SCAN MARKET NOW";
        icon.style.display = "none";
    }
}

async function fetchLogs() {
    try {
        const response = await fetch("/api/logs");
        if (!response.ok) throw new Error("Logs API response error");
        const data = await response.json();
        const logOutput = document.getElementById("log-output");
        
        const cleanText = data.logs.replace(/\[\**\d+%\**\]\s+\d+ of \d+ completed\n?/g, "");
        
        logOutput.innerText = cleanText;
        logOutput.scrollTop = logOutput.scrollHeight;
    } catch (err) {
        console.error("Failed to fetch logs:", err);
    }
}

function appendTerminalLog(text, type = "info") {
    const el = document.getElementById("log-output");
    const cleanText = text.replace(/\[\**\d+%\**\]\s+\d+ of \d+ completed\n?/g, "");
    
    const div = document.createElement("div");
    div.style.marginBottom = "8px";
    
    if (type === "error") {
        div.style.color = "#f87171";
    } else if (type === "success") {
        div.style.color = "#34d399";
    } else {
        div.style.color = "#9ca3af";
    }
    
    div.innerText = cleanText;
    el.appendChild(div);
    el.scrollTop = el.scrollHeight;
}

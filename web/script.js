let ammoData = [];
let sparklineCharts = [];
let modalChartInstance = null;
let adminPassword = "";

document.addEventListener("DOMContentLoaded", () => {
    fetchData();

    // Event Listeners
    document.getElementById("caliber-filter").addEventListener("change", renderTable);
    document.getElementById("brand-filter").addEventListener("change", renderTable);
    document.getElementById("shop-filter").addEventListener("change", renderTable);
    document.getElementById("sort-select").addEventListener("change", renderTable);
    document.getElementById("search-input").addEventListener("input", renderTable);
    
    document.getElementById("admin-btn").addEventListener("click", () => {
        document.getElementById("admin-panel").classList.toggle("hidden");
    });
    
    document.getElementById("admin-unlock-btn").addEventListener("click", unlockAdmin);

    document.getElementById("add-url-btn").addEventListener("click", addUrl);
    document.getElementById("delete-item-btn").addEventListener("click", deleteItem);
    
    document.getElementById("auto-repair-btn").addEventListener("click", async () => {
        const msgEl = document.getElementById("repair-msg");
        msgEl.style.color = "var(--text-secondary)";
        msgEl.textContent = "Searching and repairing errors...";
        try {
            const response = await fetch('/api/auto-repair', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: "", password: adminPassword })
            });
            
            if (response.ok) {
                const data = await response.json();
                msgEl.style.color = "var(--accent-color)";
                msgEl.textContent = `Success! ${data.fixed_count} erroneous entries fixed. Reloading table...`;
                fetchData();
            } else {
                msgEl.style.color = "#ef4444";
                msgEl.textContent = "Error: Wrong password or server error.";
            }
        } catch (error) {
            msgEl.textContent = "Network error.";
        }
    });
    
    document.getElementById("cleanup-btn").addEventListener("click", async () => {
        const msgEl = document.getElementById("cleanup-msg");
        msgEl.textContent = "Cleanup in progress...";
        try {
            const response = await fetch('/api/cleanup-duplicates', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: "", password: adminPassword })
            });
            
            if (response.ok) {
                const data = await response.json();
                msgEl.style.color = "var(--accent-color)";
                msgEl.textContent = `Success! ${data.merged} duplicates merged. Reloading table...`;
                fetchData();
            } else if (response.status === 401) {
                msgEl.style.color = "#ef4444";
                msgEl.textContent = "Error: Session expired or wrong password.";
            } else {
                msgEl.style.color = "#ef4444";
                msgEl.textContent = `Server error (${response.status}). Please check container logs.`;
            }
        } catch (error) {
            msgEl.textContent = "Network error.";
        }
    });
    
    document.getElementById("nuke-btn").addEventListener("click", async () => {
        if (!confirm("Are you sure? This deletes ALL previous price histories and data! This action cannot be undone.")) return;
        
        const msgEl = document.getElementById("nuke-msg");
        msgEl.style.color = "var(--text-secondary)";
        msgEl.textContent = "Database is being deleted and new search started (this may take a while)...";
        try {
            const response = await fetch('/api/nuke-db', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: "", password: adminPassword })
            });
            
            if (response.ok) {
                msgEl.style.color = "var(--accent-color)";
                msgEl.textContent = "Database deleted! AI is now searching in the background from scratch. The table will remain empty until the server finishes (approx. 5-10 minutes).";
                fetchData(); // Will show "No data" message
            } else {
                msgEl.style.color = "#ef4444";
                msgEl.textContent = "Error during reset.";
            }
        } catch (error) {
            msgEl.textContent = "Network error.";
        }
    });
});

function getDailyHistory(history) {
    const dailyHistory = [];
    const seenDates = new Set();
    
    for (let i = history.length - 1; i >= 0; i--) {
        const h = history[i];
        const d = new Date(h.date);
        const dateString = `${d.getFullYear()}-${d.getMonth()}-${d.getDate()}`;
        
        if (!seenDates.has(dateString)) {
            seenDates.add(dateString);
            dailyHistory.unshift(h);
        }
    }
    return dailyHistory;
}

async function unlockAdmin() {
    const pw = document.getElementById("admin-master-pw").value;
    const msgEl = document.getElementById("admin-login-msg");
    
    try {
        const response = await fetch('/api/verify-admin', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: "", password: pw })
        });
        
        if (response.ok) {
            adminPassword = pw;
            document.getElementById("admin-login-view").classList.add("hidden");
            document.getElementById("admin-tools-view").classList.remove("hidden");
            document.getElementById("admin-master-pw").value = "";
        } else {
            msgEl.style.color = "#ef4444";
            msgEl.textContent = "Wrong password.";
        }
    } catch (error) {
        msgEl.textContent = "Network error.";
    }
}

async function fetchData() {
    try {
        // Fetch direct aus Nginx static volume
        const response = await fetch('/data/munition_daten.json?t=' + new Date().getTime());
        if (!response.ok) throw new Error("Data not found");
        
        ammoData = await response.json();
        updateDashboard();
        populateFilters();
        renderTable();
    } catch (error) {
        console.error("Error loading:", error);
        document.getElementById("table-body").innerHTML = `<tr><td colspan="10">No data available or not yet scraped. Waiting for worker...</td></tr>`;
    }
}

function updateDashboard() {
    const findBest = (caliber) => {
        const matches = ammoData.filter(i => i.caliber === caliber && i.history && i.history.length > 0);
        if (matches.length === 0) return "No data";
        const best = matches.reduce((min, cur) => {
            const curLatest = cur.history[cur.history.length-1].price_per_round;
            const minLatest = min.history[min.history.length-1].price_per_round;
            return curLatest < minLatest ? cur : min;
        }, matches[0]);
        const bestPrice = best.history[best.history.length-1].price_per_round;
        return `${bestPrice.toFixed(2)} CHF / Round <span style="font-size: 0.9rem; color: var(--text-secondary); display: block;">${best.shop}</span>`;
    };
    
    document.getElementById("widget-9mm").innerHTML = findBest("9x19mm");
    document.getElementById("widget-223").innerHTML = findBest(".223 Rem / 5.56x45");
    document.getElementById("widget-762").innerHTML = findBest("7.62x39mm");
}

function populateFilters() {
    const caliberFilter = document.getElementById("caliber-filter");
    const brandFilter = document.getElementById("brand-filter");
    const shopFilter = document.getElementById("shop-filter");
    
    // Store current values
    const selKaliber = caliberFilter.value;
    const selMarke = brandFilter.value;
    const selShop = shopFilter.value;

    const calibers = [...new Set(ammoData.map(item => item.caliber))].sort();
    const brandn = [...new Set(ammoData.map(item => item.brand))].sort();
    const shops = [...new Set(ammoData.map(item => item.shop))].sort();
    
    caliberFilter.innerHTML = '<option value="all">All Calibers</option>';
    calibers.forEach(k => caliberFilter.appendChild(new Option(k, k)));
    
    brandFilter.innerHTML = '<option value="all">All Brands</option>';
    brandn.forEach(m => brandFilter.appendChild(new Option(m, m)));
    
    shopFilter.innerHTML = '<option value="all">All Shops</option>';
    shops.forEach(s => shopFilter.appendChild(new Option(s, s)));

    // Restore selected values
    if (calibers.includes(selKaliber)) caliberFilter.value = selKaliber;
    if (brandn.includes(selMarke)) brandFilter.value = selMarke;
    if (shops.includes(selShop)) shopFilter.value = selShop;
    
    // Populate Delete Dropdown
    const deleteSelect = document.getElementById("delete-item-select");
    deleteSelect.innerHTML = '<option value="">Select product...</option>';
    
    // Sort items by Shop then Marke
    const sortedData = [...ammoData].sort((a, b) => {
        if(a.shop < b.shop) return -1;
        if(a.shop > b.shop) return 1;
        return a.brand.localeCompare(b.brand);
    });
    
    sortedData.forEach(item => {
        const option = document.createElement('option');
        option.value = item.id;
        option.textContent = `${item.shop} | ${item.brand} ${item.caliber} (${item.amount} Stk.)`;
        deleteSelect.appendChild(option);
    });
}

function renderTable() {
    const tbody = document.getElementById("table-body");
    tbody.innerHTML = '';
    
    sparklineCharts.forEach(chart => chart.destroy());
    sparklineCharts = [];
    
    const fKaliber = document.getElementById("caliber-filter").value;
    const fMarke = document.getElementById("brand-filter").value;
    const fShop = document.getElementById("shop-filter").value;
    const sortVal = document.getElementById("sort-select").value;
    const searchStr = document.getElementById("search-input").value.toLowerCase();
    
    let filteredData = ammoData.filter(item => {
        if (fKaliber !== "all" && item.caliber !== fKaliber) return false;
        if (fMarke !== "all" && item.brand !== fMarke) return false;
        if (fShop !== "all" && item.shop !== fShop) return false;
        
        if (searchStr) {
            const textToSearch = `${item.brand} ${item.shop} ${item.caliber}`.toLowerCase();
            if (!textToSearch.includes(searchStr)) return false;
        }
        
        if (!item.history || item.history.length === 0) return false;
        
        return true;
    });
    
    // Sortieren
    filteredData.sort((a, b) => {
        const aLatest = (a.history && a.history.length > 0) ? a.history[a.history.length-1].price_per_round : 999;
        const bLatest = (b.history && b.history.length > 0) ? b.history[b.history.length-1].price_per_round : 999;
        
        if (sortVal === "price_asc") {
            return aLatest - bLatest;
        } else if (sortVal === "price_desc") {
            return bLatest - aLatest;
        } else if (sortVal === "date_desc") {
            return new Date(b.last_update) - new Date(a.last_update);
        }
        return 0;
    });
    
    filteredData.forEach(item => {
        const tr = document.createElement("tr");
        
        const dateObj = new Date(item.last_update);
        const dateStr = `${dateObj.getDate().toString().padStart(2, '0')}.${(dateObj.getMonth() + 1).toString().padStart(2, '0')}.${dateObj.getFullYear().toString().slice(-2)}`;
        const latestHistory = item.history[item.history.length-1];
        
        const dailyHistory = getDailyHistory(item.history);
        
        let trendHtml = '';
        if (dailyHistory.length > 1) {
            const latestHistoryDay = dailyHistory[dailyHistory.length-1];
            const previousHistoryDay = dailyHistory[dailyHistory.length-2];
            if (latestHistoryDay.price_per_round < previousHistoryDay.price_per_round) {
                trendHtml = '<span class="trend-down" title="Price decreased">↘</span>';
            } else if (latestHistoryDay.price_per_round > previousHistoryDay.price_per_round) {
                trendHtml = '<span class="trend-up" title="Price increased">↗</span>';
            }
        }
        
        const preisPro1000 = (latestHistory.price_per_round * 1000).toFixed(2);
        
        tr.innerHTML = `
            <td>${item.caliber}</td>
            <td>${item.brand}</td>
            <td>${item.shop}</td>
            <td>${latestHistory.amount} Stk.</td>
            <td>${latestHistory.total_price_chf.toFixed(2)} CHF</td>
            <td class="price-highlight">${latestHistory.price_per_round.toFixed(2)} CHF${trendHtml}</td>
            <td style="font-weight: bold;">${preisPro1000} CHF</td>
            <td>${dateStr}</td>
            <td>
                <a href="${item.url}" target="_blank" class="action-link">To Shop</a>
            </td>
            <td>
                <div style="width: 100px; height: 30px; cursor: pointer;" onclick="openChartModal('${item.id}')" title="Click to enlarge">
                    <canvas id="sparkline-${item.id}"></canvas>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
        
        // Initialize Sparkline
        const ctx = document.getElementById(`sparkline-${item.id}`).getContext('2d');
        const dataPoints = dailyHistory.map(h => h.price_per_round);
        const labels = dailyHistory.map(h => new Date(h.date).toLocaleDateString('de-CH'));
        
        const chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [{
                    data: dataPoints,
                    borderColor: '#10b981',
                    borderWidth: 2,
                    pointRadius: 0,
                    pointHoverRadius: 4,
                    tension: 0.3
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false },
                    tooltip: {
                        displayColors: false,
                        callbacks: {
                            label: function(context) { return context.parsed.y.toFixed(2) + ' CHF'; }
                        }
                    }
                },
                scales: {
                    x: { display: false },
                    y: { 
                        display: false, 
                        min: Math.min(...dataPoints) * 0.98,
                        max: Math.max(...dataPoints) * 1.02
                    }
                },
                layout: { padding: 0 }
            }
        });
        sparklineCharts.push(chart);
    });
}

async function addUrl() {
    const url = document.getElementById("new-url").value;
    const msgEl = document.getElementById("admin-msg");
    
    try {
        const response = await fetch('/api/urls', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url, password: adminPassword })
        });
        
        if (response.ok) {
            msgEl.style.color = "var(--accent-color)";
            msgEl.textContent = "URL added successfully!";
            document.getElementById("new-url").value = '';
            
            // Optional: trigger scrape immediately
            fetch('/api/scrape', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: "", password: adminPassword })
            });
        } else {
            msgEl.style.color = "#ef4444";
            msgEl.textContent = "Error: Wrong password or invalid URL.";
        }
    } catch (error) {
        msgEl.textContent = "Network error.";
    }
}

async function deleteItem() {
    const itemId = document.getElementById("delete-item-select").value;
    const msgEl = document.getElementById("admin-del-msg");
    
    if (!itemId) {
        msgEl.textContent = "Please select a product.";
        return;
    }
    
    try {
        const response = await fetch('/api/delete-item', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: itemId, password: adminPassword })
        });
        
        if (response.ok) {
            msgEl.style.color = "var(--accent-color)";
            msgEl.textContent = "Product permanently deleted and blacklisted.";
            // Refresh data
            fetchData();
        } else {
            msgEl.style.color = "#ef4444";
            msgEl.textContent = "Error: Wrong password.";
        }
    } catch (error) {
        msgEl.textContent = "Network error.";
    }
}

function openChartModal(itemId) {
    const item = ammoData.find(i => i.id === itemId);
    if (!item) return;
    
    document.getElementById("modal-title").textContent = `Price History: ${item.brand} ${item.caliber} (${item.shop})`;
    
    // Setup Reset Tracker Button
    const resetBtn = document.getElementById("reset-tracker-btn");
    if (resetBtn) {
        resetBtn.onclick = () => resetItemTracker(itemId);
    }
    
    // Setup Clear History Button
    const clearHistoryBtn = document.getElementById("clear-history-btn");
    if (clearHistoryBtn) {
        clearHistoryBtn.onclick = () => clearItemHistory(itemId);
    }
    
    document.getElementById("chart-modal").classList.remove("hidden");
    
    const ctx = document.getElementById('modalChart').getContext('2d');
    
    if (modalChartInstance) {
        modalChartInstance.destroy();
    }
    
    const dailyHistory = getDailyHistory(item.history);
    
    const labels = dailyHistory.map(h => {
        const d = new Date(h.date);
        return `${d.getDate().toString().padStart(2, '0')}.${(d.getMonth()+1).toString().padStart(2, '0')}.${d.getFullYear()}`;
    });
    
    const dataPoints = dailyHistory.map(h => h.price_per_round);
    
    modalChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'CHF per Round',
                data: dataPoints,
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                borderWidth: 2,
                fill: true,
                tension: 0.3
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            color: '#f8fafc',
            scales: {
                y: {
                    ticks: { 
                        color: '#94a3b8',
                        callback: function(value) { return value.toFixed(2); }
                    },
                    grid: { color: 'rgba(255,255,255,0.1)' }
                },
                x: {
                    ticks: { color: '#94a3b8' },
                    grid: { color: 'rgba(255,255,255,0.1)' }
                }
            },
            plugins: {
                legend: { labels: { color: '#f8fafc' } }
            }
        }
    });
}

function closeChartModal() {
    document.getElementById("chart-modal").classList.add("hidden");
}

async function resetItemTracker(itemId) {
    if (!adminPassword) {
        alert("Please unlock the admin panel first to fix errors.");
        return;
    }
    
    if (!confirm("This deletes the LAST erroneous price and tells the AI to re-scan the price on the shop website. Continue?")) {
        return;
    }
    
    try {
        const response = await fetch('/api/reset-item', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: itemId, password: adminPassword })
        });
        
        if (response.ok) {
            alert("Last price deleted. The price will be re-evaluated during the next automatic run.");
            closeChartModal();
            fetchData();
        } else {
            alert("Error repairing.");
        }
    } catch (e) {
        alert("Network error.");
    }
}

async function clearItemHistory(itemId) {
    if (!adminPassword) {
        alert("Please unlock the admin panel first to fix errors.");
        return;
    }
    
    if (!confirm("This deletes the ENTIRE OLD HISTORY of this product. Only the most recent price will remain. Continue?")) {
        return;
    }
    
    try {
        const response = await fetch('/api/clear-history', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: itemId, password: adminPassword })
        });
        
        if (response.ok) {
            alert("Old history deleted successfully.");
            closeChartModal();
            fetchData();
        } else {
            alert("Error deleting history.");
        }
    } catch (e) {
        alert("Network error.");
    }
}


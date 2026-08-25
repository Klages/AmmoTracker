let ammoData = [];
let sparklineCharts = [];
let modalChartInstance = null;
let adminPassword = "";

document.addEventListener("DOMContentLoaded", () => {
    fetchData();

    // Event Listeners
    document.getElementById("kaliber-filter").addEventListener("change", renderTable);
    document.getElementById("marke-filter").addEventListener("change", renderTable);
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
        msgEl.textContent = "Suche und repariere Fehler...";
        try {
            const response = await fetch('/api/auto-repair', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: "", password: adminPassword })
            });
            
            if (response.ok) {
                const data = await response.json();
                msgEl.style.color = "var(--accent-color)";
                msgEl.textContent = `Erfolgreich! ${data.fixed_count} fehlerhafte Einträge wurden korrigiert. Tabelle wird neu geladen...`;
                fetchData();
            } else {
                msgEl.style.color = "#ef4444";
                msgEl.textContent = "Fehler: Passwort falsch oder Server-Error.";
            }
        } catch (error) {
            msgEl.textContent = "Netzwerkfehler.";
        }
    });
    
    document.getElementById("cleanup-btn").addEventListener("click", async () => {
        const msgEl = document.getElementById("cleanup-msg");
        msgEl.textContent = "Bereinigung läuft...";
        try {
            const response = await fetch('/api/cleanup-duplicates', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: "", password: adminPassword })
            });
            
            if (response.ok) {
                const data = await response.json();
                msgEl.style.color = "var(--accent-color)";
                msgEl.textContent = `Erfolgreich! ${data.merged} Duplikate wurden vereint. Tabelle wird neu geladen...`;
                fetchData();
            } else if (response.status === 401) {
                msgEl.style.color = "#ef4444";
                msgEl.textContent = "Fehler: Sitzung abgelaufen oder Passwort falsch.";
            } else {
                msgEl.style.color = "#ef4444";
                msgEl.textContent = `Server-Fehler (${response.status}). Bitte Container-Logs prüfen.`;
            }
        } catch (error) {
            msgEl.textContent = "Netzwerkfehler.";
        }
    });
    
    document.getElementById("nuke-btn").addEventListener("click", async () => {
        if (!confirm("Bist du sicher? Dies löscht ALLE bisherigen Preisverläufe und Daten! Der Vorgang kann nicht rückgängig gemacht werden.")) return;
        
        const msgEl = document.getElementById("nuke-msg");
        msgEl.style.color = "var(--text-secondary)";
        msgEl.textContent = "Datenbank wird gelöscht und Neu-Suche gestartet (das kann dauern)...";
        try {
            const response = await fetch('/api/nuke-db', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: "", password: adminPassword })
            });
            
            if (response.ok) {
                msgEl.style.color = "var(--accent-color)";
                msgEl.textContent = "Datenbank gelöscht! Die KI sucht jetzt im Hintergrund komplett neu. Die Tabelle bleibt leer, bis der Server fertig ist (ca. 5-10 Minuten).";
                fetchData(); // Will show "Keine Daten" message
            } else {
                msgEl.style.color = "#ef4444";
                msgEl.textContent = "Fehler beim Zurücksetzen.";
            }
        } catch (error) {
            msgEl.textContent = "Netzwerkfehler.";
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
            msgEl.textContent = "Falsches Passwort.";
        }
    } catch (error) {
        msgEl.textContent = "Netzwerkfehler.";
    }
}

async function fetchData() {
    try {
        // Fetch direct aus Nginx static volume
        const response = await fetch('/data/munition_daten.json?t=' + new Date().getTime());
        if (!response.ok) throw new Error("Daten nicht gefunden");
        
        ammoData = await response.json();
        updateDashboard();
        populateFilters();
        renderTable();
    } catch (error) {
        console.error("Fehler beim Laden:", error);
        document.getElementById("table-body").innerHTML = `<tr><td colspan="10">Keine Daten verfügbar oder noch nicht gescrapet. Warte auf den Worker...</td></tr>`;
    }
}

function updateDashboard() {
    const findBest = (kaliber) => {
        const matches = ammoData.filter(i => i.kaliber === kaliber && i.history && i.history.length > 0);
        if (matches.length === 0) return "Keine Daten";
        const best = matches.reduce((min, cur) => {
            const curLatest = cur.history[cur.history.length-1].preis_pro_schuss;
            const minLatest = min.history[min.history.length-1].preis_pro_schuss;
            return curLatest < minLatest ? cur : min;
        }, matches[0]);
        const bestPrice = best.history[best.history.length-1].preis_pro_schuss;
        return `${bestPrice.toFixed(2)} CHF / Patrone <span style="font-size: 0.9rem; color: var(--text-secondary); display: block;">${best.shop}</span>`;
    };
    
    document.getElementById("widget-9mm").innerHTML = findBest("9x19mm");
    document.getElementById("widget-223").innerHTML = findBest(".223 Rem / 5.56x45");
    document.getElementById("widget-762").innerHTML = findBest("7.62x39mm");
}

function populateFilters() {
    const kaliberFilter = document.getElementById("kaliber-filter");
    const markeFilter = document.getElementById("marke-filter");
    const shopFilter = document.getElementById("shop-filter");
    
    // Store current values
    const selKaliber = kaliberFilter.value;
    const selMarke = markeFilter.value;
    const selShop = shopFilter.value;

    const kalibers = [...new Set(ammoData.map(item => item.kaliber))].sort();
    const marken = [...new Set(ammoData.map(item => item.marke))].sort();
    const shops = [...new Set(ammoData.map(item => item.shop))].sort();
    
    kaliberFilter.innerHTML = '<option value="all">Alle Kaliber</option>';
    kalibers.forEach(k => kaliberFilter.appendChild(new Option(k, k)));
    
    markeFilter.innerHTML = '<option value="all">Alle Marken</option>';
    marken.forEach(m => markeFilter.appendChild(new Option(m, m)));
    
    shopFilter.innerHTML = '<option value="all">Alle Shops</option>';
    shops.forEach(s => shopFilter.appendChild(new Option(s, s)));

    // Restore selected values
    if (kalibers.includes(selKaliber)) kaliberFilter.value = selKaliber;
    if (marken.includes(selMarke)) markeFilter.value = selMarke;
    if (shops.includes(selShop)) shopFilter.value = selShop;
    
    // Populate Delete Dropdown
    const deleteSelect = document.getElementById("delete-item-select");
    deleteSelect.innerHTML = '<option value="">Produkt auswählen...</option>';
    
    // Sort items by Shop then Marke
    const sortedData = [...ammoData].sort((a, b) => {
        if(a.shop < b.shop) return -1;
        if(a.shop > b.shop) return 1;
        return a.marke.localeCompare(b.marke);
    });
    
    sortedData.forEach(item => {
        const option = document.createElement('option');
        option.value = item.id;
        option.textContent = `${item.shop} | ${item.marke} ${item.kaliber} (${item.menge} Stk.)`;
        deleteSelect.appendChild(option);
    });
}

function renderTable() {
    const tbody = document.getElementById("table-body");
    tbody.innerHTML = '';
    
    sparklineCharts.forEach(chart => chart.destroy());
    sparklineCharts = [];
    
    const fKaliber = document.getElementById("kaliber-filter").value;
    const fMarke = document.getElementById("marke-filter").value;
    const fShop = document.getElementById("shop-filter").value;
    const sortVal = document.getElementById("sort-select").value;
    const searchStr = document.getElementById("search-input").value.toLowerCase();
    
    let filteredData = ammoData.filter(item => {
        if (fKaliber !== "all" && item.kaliber !== fKaliber) return false;
        if (fMarke !== "all" && item.marke !== fMarke) return false;
        if (fShop !== "all" && item.shop !== fShop) return false;
        
        if (searchStr) {
            const textToSearch = `${item.marke} ${item.shop} ${item.kaliber}`.toLowerCase();
            if (!textToSearch.includes(searchStr)) return false;
        }
        
        if (!item.history || item.history.length === 0) return false;
        
        return true;
    });
    
    // Sortieren
    filteredData.sort((a, b) => {
        const aLatest = (a.history && a.history.length > 0) ? a.history[a.history.length-1].preis_pro_schuss : 999;
        const bLatest = (b.history && b.history.length > 0) ? b.history[b.history.length-1].preis_pro_schuss : 999;
        
        if (sortVal === "price_asc") {
            return aLatest - bLatest;
        } else if (sortVal === "price_desc") {
            return bLatest - aLatest;
        } else if (sortVal === "date_desc") {
            return new Date(b.letztes_update) - new Date(a.letztes_update);
        }
        return 0;
    });
    
    filteredData.forEach(item => {
        const tr = document.createElement("tr");
        
        const dateObj = new Date(item.letztes_update);
        const dateStr = `${dateObj.getDate().toString().padStart(2, '0')}.${(dateObj.getMonth() + 1).toString().padStart(2, '0')}.${dateObj.getFullYear().toString().slice(-2)}`;
        const latestHistory = item.history[item.history.length-1];
        
        const dailyHistory = getDailyHistory(item.history);
        
        // Trend berechnen basierend auf Tages-Historie
        let trendHtml = '';
        if (dailyHistory.length > 1) {
            const latestHistoryDay = dailyHistory[dailyHistory.length-1];
            const previousHistoryDay = dailyHistory[dailyHistory.length-2];
            if (latestHistoryDay.preis_pro_schuss < previousHistoryDay.preis_pro_schuss) {
                trendHtml = '<span class="trend-down" title="Preis gesunken">↘</span>';
            } else if (latestHistoryDay.preis_pro_schuss > previousHistoryDay.preis_pro_schuss) {
                trendHtml = '<span class="trend-up" title="Preis gestiegen">↗</span>';
            }
        }
        
        const preisPro1000 = (latestHistory.preis_pro_schuss * 1000).toFixed(2);
        
        tr.innerHTML = `
            <td>${item.kaliber}</td>
            <td>${item.marke}</td>
            <td>${item.shop}</td>
            <td>${latestHistory.menge} Stk.</td>
            <td>${latestHistory.preis_total_chf.toFixed(2)} CHF</td>
            <td class="price-highlight">${latestHistory.preis_pro_schuss.toFixed(2)} CHF${trendHtml}</td>
            <td style="font-weight: bold;">${preisPro1000} CHF</td>
            <td>${dateStr}</td>
            <td>
                <a href="${item.url}" target="_blank" class="action-link">Zum Shop</a>
            </td>
            <td>
                <div style="width: 100px; height: 30px; cursor: pointer;" onclick="openChartModal('${item.id}')" title="Klicken zum Vergrössern">
                    <canvas id="sparkline-${item.id}"></canvas>
                </div>
            </td>
        `;
        tbody.appendChild(tr);
        
        // Initialize Sparkline
        const ctx = document.getElementById(`sparkline-${item.id}`).getContext('2d');
        const dataPoints = dailyHistory.map(h => h.preis_pro_schuss);
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
            msgEl.textContent = "URL erfolgreich hinzugefügt!";
            document.getElementById("new-url").value = '';
            
            // Optional: trigger scrape immediately
            fetch('/api/scrape', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url: "", password: adminPassword })
            });
        } else {
            msgEl.style.color = "#ef4444";
            msgEl.textContent = "Fehler: Falsches Passwort oder URL ungültig.";
        }
    } catch (error) {
        msgEl.textContent = "Netzwerkfehler.";
    }
}

async function deleteItem() {
    const itemId = document.getElementById("delete-item-select").value;
    const msgEl = document.getElementById("admin-del-msg");
    
    if (!itemId) {
        msgEl.textContent = "Bitte ein Produkt auswählen.";
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
            msgEl.textContent = "Produkt dauerhaft gelöscht und auf Blacklist gesetzt.";
            // Refresh data
            fetchData();
        } else {
            msgEl.style.color = "#ef4444";
            msgEl.textContent = "Fehler: Falsches Passwort.";
        }
    } catch (error) {
        msgEl.textContent = "Netzwerkfehler.";
    }
}

function openChartModal(itemId) {
    const item = ammoData.find(i => i.id === itemId);
    if (!item) return;
    
    document.getElementById("modal-title").textContent = `Preisverlauf: ${item.marke} ${item.kaliber} (${item.shop})`;
    
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
    
    const dataPoints = dailyHistory.map(h => h.preis_pro_schuss);
    
    modalChartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'CHF pro Patrone',
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
        alert("Bitte zuerst das Admin Panel entsperren, um Fehler zu korrigieren.");
        return;
    }
    
    if (!confirm("Dies löscht den LETZTEN fehlerhaften Preis und weist die KI an, den Preis auf der Shop-Webseite neu zu suchen. Fortfahren?")) {
        return;
    }
    
    try {
        const response = await fetch('/api/reset-item', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: itemId, password: adminPassword })
        });
        
        if (response.ok) {
            alert("Letzter Preis gelöscht. Der Preis wird beim nächsten automatischen Durchlauf neu evaluiert.");
            closeChartModal();
            fetchData();
        } else {
            alert("Fehler beim Reparieren.");
        }
    } catch (e) {
        alert("Netzwerkfehler.");
    }
}

async function clearItemHistory(itemId) {
    if (!adminPassword) {
        alert("Bitte zuerst das Admin Panel entsperren, um Fehler zu korrigieren.");
        return;
    }
    
    if (!confirm("Dies löscht den GESAMTEN ALTEN VERLAUF dieses Produktes. Nur der aktuellste Preis bleibt bestehen. Fortfahren?")) {
        return;
    }
    
    try {
        const response = await fetch('/api/clear-history', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ id: itemId, password: adminPassword })
        });
        
        if (response.ok) {
            alert("Alter Verlauf erfolgreich gelöscht.");
            closeChartModal();
            fetchData();
        } else {
            alert("Fehler beim Löschen des Verlaufs.");
        }
    } catch (e) {
        alert("Netzwerkfehler.");
    }
}


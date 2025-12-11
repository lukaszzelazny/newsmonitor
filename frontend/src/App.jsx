import React, { useState, useEffect, useRef } from 'react';
import { createChart, ColorType } from 'lightweight-charts';

// Komponent wykresu (Lightweight Charts)
function PriceChart({ ticker, priceHistory, brokerageAnalyses, analyses, onNewsClick }) {
    const chartContainerRef = useRef(null);
    const chartRef = useRef(null);
    const [chartType, setChartType] = useState('candlestick');
    const [showVolume, setShowVolume] = useState(true);
    const [transactions, setTransactions] = useState([]);

    // Pobierz transakcje z backendu dla tego tickera (jeśli są)
    useEffect(() => {
        if (!ticker) return;
        fetch(`/api/portfolio/transactions?ticker=${encodeURIComponent(ticker)}`)
            .then(res => res.json())
            .then(data => {
                if (Array.isArray(data)) setTransactions(data);
                else setTransactions([]);
            })
            .catch(err => {
                console.error('Error fetching transactions:', err);
                setTransactions([]);
            });

        // Tymczasowy mock (jeśli backend zwraca pustą listę) — ułatwia test wizualny
        const mock = [
            { id: 'm1', transaction_type: 'buy', quantity: 100, price: 45.2, transaction_date: '2025-12-01' },
            { id: 'm2', transaction_type: 'sell', quantity: 50, price: 47.8, transaction_date: '2025-12-05' },
            { id: 'm3', transaction_type: 'buy', quantity: 200, price: 44.0, transaction_date: '2025-11-28' },
        ];
        // Ustaw mock tylko jeśli backend nie dostarczy danych po krótkim timeoutcie
        const t = setTimeout(() => {
            setTransactions(prev => (prev && prev.length > 0) ? prev : mock);
        }, 350);
        return () => clearTimeout(t);
    }, [ticker]);

    useEffect(() => {
        if (!chartContainerRef.current || !priceHistory || priceHistory.length === 0) return;

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: 'white' },
                textColor: 'black',
            },
            width: chartContainerRef.current.clientWidth,
            height: 400,
            grid: {
                vertLines: { color: '#f0f0f0' },
                horzLines: { color: '#f0f0f0' },
            },
            rightPriceScale: {
                borderColor: '#d1d4dc',
                scaleMargins: {
                    top: 0.1,
                    bottom: showVolume ? 0.08 : 0.02,
                },
            },
            timeScale: {
                borderColor: '#d1d4dc',
            },
        });
        chartRef.current = chart;

        // Volume Series
        if (showVolume) {
            const volumeSeries = chart.addHistogramSeries({
                color: '#26a69a',
                priceFormat: {
                    type: 'volume',
                },
                priceScaleId: '', // Overlay
                scaleMargins: {
                    top: 0.92, // Show at bottom
                    bottom: 0,
                },
            });
            
            const volumeData = priceHistory.map(d => ({
                time: d.date,
                value: d.volume,
                color: (d.close >= d.open) ? '#26a69a' : '#ef5350',
            }));
            volumeSeries.setData(volumeData);
        }

        // Main Series
        let mainSeries;
        if (chartType === 'candlestick') {
            mainSeries = chart.addCandlestickSeries({
                upColor: '#26a69a',
                downColor: '#ef5350',
                borderVisible: false,
                wickUpColor: '#26a69a',
                wickDownColor: '#ef5350',
            });
            const candleData = priceHistory.map(d => ({
                time: d.date,
                open: d.open ?? d.price, // Fallback to price if open missing
                high: d.high ?? d.price,
                low: d.low ?? d.price,
                close: d.close ?? d.price,
            }));
            mainSeries.setData(candleData);
        } else {
            mainSeries = chart.addLineSeries({
                color: '#2962FF',
                lineWidth: 2,
            });
            const lineData = priceHistory.map(d => ({
                time: d.date,
                value: d.close ?? d.price,
            }));
            mainSeries.setData(lineData);
        }

        // News Markers
        if (analyses && analyses.length > 0) {
            const markers = [];
            analyses.forEach(news => {
                let color = '#9ca3af';
                let shape = 'circle';
                if (news.impact > 0.2) { color = '#10b981'; shape = 'arrowUp'; }
                else if (news.impact < -0.2) { color = '#ef5350'; shape = 'arrowDown'; }
                
                markers.push({
                    time: news.date,
                    position: news.impact > 0 ? 'belowBar' : 'aboveBar',
                    color: color,
                    shape: shape,
                    text: 'News',
                    id: news.news_id
                });
            });
            markers.sort((a, b) => new Date(a.time) - new Date(b.time));
            mainSeries.setMarkers(markers);
        }

        // Brokerage Target Line
        const latestBrokerage = brokerageAnalyses?.find(b => b.price_new);
        if (latestBrokerage && latestBrokerage.price_new) {
             const priceLine = {
                price: latestBrokerage.price_new,
                color: '#10b981',
                lineWidth: 2,
                lineStyle: 2, // Dashed
                axisLabelVisible: true,
                title: 'Cel',
            };
            mainSeries.createPriceLine(priceLine);
        }

        chart.timeScale().fitContent();

        // Overlay for transaction markers (custom scaled circles)
        const overlay = document.createElement('div');
        overlay.style.position = 'absolute';
        overlay.style.left = '0';
        overlay.style.top = '0';
        overlay.style.right = '0';
        overlay.style.bottom = '0';
        overlay.style.pointerEvents = 'none';
        chartContainerRef.current.style.position = 'relative';
        chartContainerRef.current.appendChild(overlay);

        const renderTransactions = () => {
            if (!overlay) return;
            overlay.innerHTML = '';
            if (!transactions || transactions.length === 0) return;

            // map quantities to sizes
            const quantities = transactions.map(t => Number(t.quantity) || 0).filter(q => !isNaN(q));
            const qmin = quantities.length ? Math.min(...quantities) : 0;
            const qmax = quantities.length ? Math.max(...quantities) : 0;

            // Build quick index of priceHistory dates for fallback
            const timeIndex = (priceHistory || []).map(p => p.time || p.date || p.date_string || p["date"]).filter(Boolean);

            // Also collect markers fallback for lightweight-charts
            const fallbackMarkers = [];

            transactions.forEach(t => {
                // transaction_date expected as YYYY-MM-DD
                const time = t.transaction_date;
                const price = Number(t.price);
                if (!time || !price) return;

                let x = null, y = null;
                try {
                    // try direct mapping first
                    const timeCoord = chart.timeScale().timeToCoordinate(time);
                    const priceCoord = mainSeries.priceToCoordinate(price);
                    x = timeCoord;
                    y = priceCoord;
                } catch (e) {
                    // ignore here, try fallback below
                }

                // Fallback: if mapping failed, find closest date in priceHistory and map that bar's coordinate
                if ((x === null || y === null || isNaN(x) || isNaN(y)) && timeIndex.length > 0) {
                    // Find nearest date string in timeIndex
                    let nearest = null;
                    let nearestDiff = Infinity;
                    const tx = new Date(time).getTime();
                    for (let d of timeIndex) {
                        const dt = new Date(d).getTime();
                        const diff = Math.abs(dt - tx);
                        if (diff < nearestDiff) { nearestDiff = diff; nearest = d; }
                    }
                    if (nearest) {
                        try {
                            const timeCoord = chart.timeScale().timeToCoordinate(nearest);
                            // use price mapping as before
                            const priceCoord = mainSeries.priceToCoordinate(price);
                            x = timeCoord;
                            y = priceCoord;
                        } catch (e) {
                            // give up mapping this tx
                            console.debug('Fallback mapping failed for tx', t, e);
                        }
                    }
                }

                if (x === null || y === null || isNaN(x) || isNaN(y)) {
                    // As a backup: create a lightweight-charts marker so at least it's visible on the chart
                    fallbackMarkers.push({
                        time: time,
                        position: 'belowBar',
                        color: (String(t.transaction_type).toLowerCase() === 'buy') ? '#10b981' : '#ef5350',
                        shape: (String(t.transaction_type).toLowerCase() === 'buy') ? 'circle' : 'circle',
                        text: (String(t.transaction_type).toUpperCase()),
                        id: `tx-${t.id}`
                    });
                    return;
                }

                const qty = Number(t.quantity) || 0;
                const size = qmax > qmin ? 6 + ((qty - qmin) / (qmax - qmin)) * 26 : 10;

                const el = document.createElement('div');
                el.title = `${(t.transaction_type || '').toUpperCase()}: ${qty} @ ${price}`;
                el.style.position = 'absolute';
                el.style.left = `${x}px`;
                el.style.top = `${y}px`;
                el.style.transform = 'translate(-50%, -50%)';
                el.style.width = `${size}px`;
                el.style.height = `${size}px`;
                el.style.borderRadius = '50%';
                el.style.background = (String(t.transaction_type).toLowerCase() === 'buy') ? 'rgba(16,185,129,0.95)' : 'rgba(239,83,80,0.95)';
                el.style.boxShadow = '0 0 0 2px rgba(255,255,255,0.85)';
                el.style.pointerEvents = 'auto';
                el.style.border = '1px solid rgba(0,0,0,0.08)';
                // small label inside for quantities (optional)
                const lbl = document.createElement('span');
                lbl.style.fontSize = '10px';
                lbl.style.color = 'white';
                lbl.style.fontWeight = '600';
                lbl.style.position = 'absolute';
                lbl.style.left = '50%';
                lbl.style.top = '50%';
                lbl.style.transform = 'translate(-50%, -50%)';
                lbl.innerText = '';// qty.toString(); // keep empty to avoid clutter
                el.appendChild(lbl);

                overlay.appendChild(el);
            });

            // apply fallback markers to series if any
            if (fallbackMarkers.length > 0) {
                try {
                    mainSeries.setMarkers(fallbackMarkers.concat(analyses?.map(n => ({ time: n.date, position: n.impact>0?'belowBar':'aboveBar', color: '#9ca3af', shape: 'circle', text: 'News' }))) || []);
                } catch (e) {
                    console.debug('Failed to set fallback markers:', e);
                }
            }
        };

        // Initial render
        renderTransactions();

        // Re-render on resize and visible range change
        const handleResize = () => {
            if (chartContainerRef.current) {
                chart.applyOptions({ width: chartContainerRef.current.clientWidth });
            }
            renderTransactions();
        };
        window.addEventListener('resize', handleResize);

        let unsubVisible = null;
        try {
            unsubVisible = chart.timeScale().subscribeVisibleTimeRangeChange(() => {
                renderTransactions();
            });
        } catch (e) {
            // some versions may not support this subscription
        }

        return () => {
            window.removeEventListener('resize', handleResize);
            if (unsubVisible && typeof unsubVisible === 'function') unsubVisible();
            if (overlay && overlay.parentNode) overlay.parentNode.removeChild(overlay);
            chart.remove();
        };
    }, [priceHistory, chartType, showVolume, analyses, brokerageAnalyses, transactions]);


    if (!priceHistory || priceHistory.length === 0) {
        return (
            <div className="bg-white rounded-lg shadow-lg p-6 mb-6">
                <div className="text-center text-gray-500 py-8">
                    <p>Brak danych o cenach dla {ticker}</p>
                </div>
            </div>
        );
    }

    const latestPrice = priceHistory[priceHistory.length - 1]?.price ?? priceHistory[priceHistory.length - 1]?.close;
    const firstPrice = priceHistory[0]?.price ?? priceHistory[0]?.close;
    const priceChange = latestPrice && firstPrice ? ((latestPrice - firstPrice) / firstPrice * 100) : 0;
    const latestBrokerage = brokerageAnalyses?.find(b => b.price_new);

    return (
        <div className="bg-white rounded-lg shadow-lg p-6">
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h3 className="text-xl font-bold text-gray-900">Wykres kursu {ticker}</h3>
                    <p className="text-sm text-gray-600">Ostatnie {priceHistory.length} dni</p>
                </div>
                <div className="text-right">
                    <div className="text-2xl font-bold text-gray-900">
                        {latestPrice?.toFixed(2)} PLN
                    </div>
                    <div className={`text-sm font-semibold ${priceChange >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(2)}%
                    </div>
                </div>
            </div>

            {/* Toggle Buttons */}
            <div className="flex gap-2 mb-2 justify-end text-xs">
               <button 
                   onClick={() => setChartType('candlestick')} 
                   className={`px-3 py-1 rounded ${chartType==='candlestick' ? 'bg-blue-100 text-blue-700 font-bold' : 'bg-gray-100 text-gray-600'}`}
               >
                   Świece
               </button>
               <button 
                   onClick={() => setChartType('line')} 
                   className={`px-3 py-1 rounded ${chartType==='line' ? 'bg-blue-100 text-blue-700 font-bold' : 'bg-gray-100 text-gray-600'}`}
               >
                   Linia
               </button>
               <label className="flex items-center gap-1 cursor-pointer bg-gray-100 px-2 py-1 rounded hover:bg-gray-200 ml-2">
                   <input 
                       type="checkbox" 
                       checked={showVolume} 
                       onChange={(e) => setShowVolume(e.target.checked)} 
                       className="cursor-pointer w-3 h-3 accent-blue-600"
                   />
                   <span className="text-gray-600 font-medium">Wolumen</span>
               </label>
            </div>

            <div ref={chartContainerRef} className="w-full h-[400px]" />

            {/* Debug / transactions overview (visible to help troubleshooting) */}
            <div className="mt-2 text-xs text-gray-700">
                <div className="mb-1 font-semibold">Transakcje: {transactions.length}</div>
                {transactions.length === 0 ? (
                    <div className="text-gray-500">Brak transakcji dla tego tickera</div>
                ) : (
                    <div className="grid grid-cols-2 gap-2">
                        {transactions.map((t) => (
                            <div key={t.id} className="p-1 bg-gray-50 border rounded">
                                <div className="font-medium">{t.transaction_type?.toUpperCase() || ''} {t.quantity}</div>
                                <div className="text-gray-500">{t.transaction_date} • {t.price}</div>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            <div className="mt-4 flex items-center gap-4 text-xs text-gray-600">
                <span className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full bg-green-500"></span>
                    {'Pozytywny (impact > 0.2)'}
                </span>
                <span className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full bg-red-500"></span>
                    {'Negatywny (impact < -0.2)'}
                </span>
                 <span className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full bg-gray-400"></span>
                    Neutralny
                </span>
            </div>


            {latestBrokerage && (
                <div className="mt-4 p-3 bg-green-50 rounded-lg">
                    <div className="flex items-center justify-between text-sm">
                        <span className="text-gray-700">
                            Cena docelowa wg <strong>{latestBrokerage.brokerage_house}</strong>:
                        </span>
                        <div className="flex items-center gap-4">
                            <span className="font-bold text-green-700">
                                {latestBrokerage.price_new?.toFixed(2)} PLN
                            </span>
                            {latestBrokerage.upside_percent !== null && (
                                <span className={`font-semibold ${latestBrokerage.upside_percent >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                    ({latestBrokerage.upside_percent >= 0 ? '+' : ''}{latestBrokerage.upside_percent.toFixed(1)}%)
                                </span>
                            )}
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

// Komponent analizy technicznej
function TechnicalAnalysis({ ticker }) {
    const [technicalData, setTechnicalData] = useState(null);
    const [loading, setLoading] = useState(false);
    const [showDetails, setShowDetails] = useState(false);
    const [error, setError] = useState(null);

    useEffect(() => {
        if (ticker) {
            fetchTechnicalAnalysis();
        }
    }, [ticker]);

    const fetchTechnicalAnalysis = async () => {
        setLoading(true);
        setError(null);
        try {
            const response = await fetch(`/api/technical_analysis/${ticker}?period=1y`);
            const data = await response.json();

            if (data.error) {
                setError(data.error);
                setTechnicalData(null);
            } else {
                setTechnicalData(data);
            }
        } catch (error) {
            console.error('Error fetching technical analysis:', error);
            setError('Błąd pobierania danych');
            setTechnicalData(null);
        } finally {
            setLoading(false);
        }
    };

    if (loading) {
        return (
            <div className="bg-white rounded-lg shadow p-6">
                <h3 className="text-lg font-bold text-gray-900 mb-4">Analiza Techniczna</h3>
                <div className="flex items-center justify-center py-8">
                    <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-500"></div>
                </div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="bg-white rounded-lg shadow p-6">
                <h3 className="text-lg font-bold text-gray-900 mb-4">Analiza Techniczna</h3>
                <div className="text-center text-gray-500 py-4">
                    <p>{error}</p>
                </div>
            </div>
        );
    }

    if (!technicalData || !technicalData.summary) {
        return null;
    }

    const { summary, details } = technicalData;

    return (
        <div className="bg-white rounded-lg shadow p-6">
            <div className="flex items-center justify-between mb-4">
                <h3 className="text-lg font-bold text-gray-900">Analiza Techniczna</h3>
                <button
                    onClick={() => setShowDetails(!showDetails)}
                    className="text-sm text-blue-600 hover:text-blue-800 font-medium"
                >
                    {showDetails ? 'Ukryj szczegóły ▲' : 'Pokaż szczegóły ▼'}
                </button>
            </div>

            {/* Podsumowanie */}
            <div className="grid grid-cols-2 gap-4 mb-4">
                {/* Wskaźniki */}
                <div
                    className="p-4 rounded-lg border-2"
                    style={{
                        backgroundColor: summary.indicators.bg_color,
                        borderColor: summary.indicators.color
                    }}
                >
                    <div className="text-sm font-medium text-gray-600 mb-2">Wskaźniki</div>
                    <div
                        className="text-2xl font-bold"
                        style={{ color: summary.indicators.color }}
                    >
                        {summary.indicators.label}
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                        Score: {summary.indicators.score}
                    </div>
                </div>

                {/* Średnie kroczące */}
                <div
                    className="p-4 rounded-lg border-2"
                    style={{
                        backgroundColor: summary.moving_averages.bg_color,
                        borderColor: summary.moving_averages.color
                    }}
                >
                    <div className="text-sm font-medium text-gray-600 mb-2">Średnie kroczące</div>
                    <div
                        className="text-2xl font-bold"
                        style={{ color: summary.moving_averages.color }}
                    >
                        {summary.moving_averages.label}
                    </div>
                    <div className="text-xs text-gray-500 mt-1">
                        Kupuj: {summary.moving_averages.buy_count} | Sprzedaj: {summary.moving_averages.sell_count}
                    </div>
                </div>
            </div>

            {/* Szczegóły (rozwijane) */}
            {showDetails && details && (
                <div className="border-t pt-4">
                    <div className="grid grid-cols-2 gap-6">
                        {/* Szczegóły wskaźników */}
                        <div>
                            <h4 className="text-sm font-semibold text-gray-900 mb-3">Szczegóły wskaźników</h4>
                            <div className="space-y-1 text-xs font-mono">
                                {details.indicators && details.indicators.map((indicator, idx) => (
                                    <div key={idx} className="text-gray-700">
                                        {indicator}
                                    </div>
                                ))}
                            </div>
                        </div>

                        {/* Szczegóły średnich kroczących */}
                        <div>
                            <h4 className="text-sm font-semibold text-gray-900 mb-3">
                                Średnie kroczące (Aktualna cena: {details.current_price})
                            </h4>
                            <div className="space-y-2">
                                {details.moving_averages && details.moving_averages.map((ma, idx) => (
                                    <div key={idx} className="flex items-center justify-between text-xs p-2 bg-gray-50 rounded">
                                        <span className="font-semibold">{ma.name}</span>
                                        <span className="text-gray-600">{ma.value}</span>
                                        <span
                                            className={`font-medium ${ma.signal === 'kupuj' ? 'text-green-600' :
                                                ma.signal === 'sprzedaj' ? 'text-red-600' :
                                                    'text-gray-500'
                                                }`}
                                        >
                                            {ma.signal}
                                        </span>
                                        <span
                                            className={`font-mono ${ma.difference.startsWith('+') ? 'text-green-600' : 'text-red-600'
                                                }`}
                                        >
                                            {ma.difference}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

// Komponent MultiSelect
function TickerSelect({ analysisId, onSave, allTickers = [] }) {
    const [selectedTickers, setSelectedTickers] = useState([]);
    const [isLoading, setIsLoading] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');

    const handleSave = async () => {
        setIsLoading(true);
        try {
            const response = await fetch('/api/update_analysis_tickers', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    analysis_id: analysisId,
                    tickers: selectedTickers
                })
            });
            if (response.ok) {
                if (onSave) {
                    onSave(true, 'Tickery zaktualizowane pomyślnie.');
                }
            } else {
                if (onSave) {
                    onSave(false, 'Błąd podczas zapisywania tickerów.');
                }
            }
        } catch (error) {
            console.error('Error saving tickers:', error);
            if (onSave) {
                onSave(false, 'Błąd sieci podczas zapisywania.');
            }
        } finally {
            setIsLoading(false);
        }
    };

    const toggleTicker = (tickerValue) => {
        setSelectedTickers(prev =>
            prev.includes(tickerValue)
                ? prev.filter(t => t !== tickerValue)
                : [...prev, tickerValue]
        );
    };

    const filteredTickers = allTickers.filter(ticker =>
        ticker.label.toLowerCase().includes(searchTerm.toLowerCase())
    );

    const toggleSelectAll = () => {
        const allVisibleTickerValues = filteredTickers.map(t => t.value);
        const allSelected = allVisibleTickerValues.every(v => selectedTickers.includes(v));

        if (allSelected) {
            // Deselect all visible
            setSelectedTickers(prev => prev.filter(t => !allVisibleTickerValues.includes(t)));
        } else {
            // Select all visible
            setSelectedTickers(prev => [...new Set([...prev, ...allVisibleTickerValues])]);
        }
    };

    return (
        <div className="mt-2 p-2 border border-blue-200 bg-blue-50 rounded-lg">
            <p className="text-xs font-semibold text-blue-800 mb-2">Przypisz tickery do tej analizy:</p>
            <div className="flex items-center gap-2 mb-2">
                <input
                    type="text"
                    placeholder="Szukaj tickera..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="flex-grow px-2 py-1 text-xs border border-gray-300 rounded-md"
                />
                <button
                    onClick={toggleSelectAll}
                    className="px-2 py-1 text-xs font-semibold text-white bg-blue-500 rounded-md hover:bg-blue-600 transition-colors"
                >
                    Zaznacz/Odznacz
                </button>
            </div>
            <div className="max-h-32 overflow-y-auto border bg-white rounded p-1 text-xs mb-2">
                {filteredTickers.map(ticker => (
                    <label key={ticker.value} className="flex items-center p-1 hover:bg-gray-100 rounded">
                        <input
                            type="checkbox"
                            checked={selectedTickers.includes(ticker.value)}
                            onChange={() => toggleTicker(ticker.value)}
                            className="h-3 w-3 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                        />
                        <span className="ml-2 text-gray-700">{ticker.label}</span>
                    </label>
                ))}
            </div>
            <button
                onClick={handleSave}
                disabled={isLoading || selectedTickers.length === 0}
                className={`w-full px-2 py-1 text-xs font-semibold text-white rounded-md transition-colors ${
                    (isLoading || selectedTickers.length === 0)
                        ? 'bg-gray-400 cursor-not-allowed'
                        : 'bg-blue-600 hover:bg-blue-700'
                    }`}
            >
                {isLoading ? 'Zapisywanie...' : 'Zapisz'}
            </button>
        </div>
    );
}

// Komponent widoku kalendarzowego
function CalendarView({ days, onBack, onTickerSelect, showNotification }) {
    const [calendarStats, setCalendarStats] = useState([]);
    const [selectedDate, setSelectedDate] = useState(null);
    const [newsForDate, setNewsForDate] = useState([]);
    const [loading, setLoading] = useState(false);
    const [currentMonth, setCurrentMonth] = useState(new Date());
    const [activeTickerFilters, setActiveTickerFilters] = useState([]);
    const [showUnassigned, setShowUnassigned] = useState(true);
    const [allTickers, setAllTickers] = useState([]);

    useEffect(() => {
        fetchCalendarStats();
        fetchAllTickers();
    }, [days]);

    const fetchAllTickers = () => {
        fetch('/api/all_tickers')
            .then(res => res.json())
            .then(data => setAllTickers(data))
            .catch(err => console.error("Error fetching all tickers:", err));
    };

    const fetchCalendarStats = async () => {
        try {
            const response = await fetch(`/api/calendar_stats?days=${days}`);
            const data = await response.json();
            setCalendarStats(data);
        } catch (error) {
            console.error('Error fetching calendar stats:', error);
        }
    };

    const fetchNewsForDate = async (date) => {
        setLoading(true);
        try {
            const response = await fetch(`/api/news_by_date/${date}`);
            const data = await response.json();
            setNewsForDate(data);
            setSelectedDate(date);
            const allTickers = data.flatMap(news => news.tickers.map(t => t.ticker));
            const uniqueTickers = [...new Set(allTickers)].sort();
            setActiveTickerFilters(uniqueTickers);
            setShowUnassigned(true);
        } catch (error) {
            console.error('Error fetching news for date:', error);
        } finally {
            setLoading(false);
        }
    };

    const handleTickerSave = (success, message) => {
        if (showNotification) {
            showNotification(message, success ? 'success' : 'error');
        }
        fetchNewsForDate(selectedDate);
    };

    const markAsDuplicate = async (newsId) => {
        // Optimistic UI update
        const originalNews = [...newsForDate];
        const updatedNews = newsForDate.filter(news => news.news_id !== newsId);
        setNewsForDate(updatedNews);

        try {
            const response = await fetch('/api/mark_duplicate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ news_id: newsId })
            });

            if (response.ok) {
                if (showNotification) showNotification('News oznaczony jako duplikat', 'success');
                fetchCalendarStats(); // Refresh calendar colors
            } else {
                // Revert on failure
                setNewsForDate(originalNews);
                if (showNotification) showNotification('Błąd przy oznaczaniu newsa jako duplikat', 'error');
            }
        } catch (error) {
            console.error('Error marking as duplicate:', error);
            setNewsForDate(originalNews); // Revert on network error
            if (showNotification) showNotification('Błąd połączenia z serwerem', 'error');
        }
    };

    const getDayStats = (dateStr) => {
        return calendarStats.find(s => s.date === dateStr);
    };

    const getDayColor = (stats) => {
        if (!stats || stats.news_count === 0) return 'bg-gray-50';

        const avgImpact = stats.avg_impact;
        const count = stats.news_count;

        // Intensywność bazowana na liczbie newsów
        if (avgImpact > 0.1) {
            if (count > 5) return 'bg-green-500 text-white';
            if (count > 2) return 'bg-green-400 text-white';
            return 'bg-green-300';
        } else if (avgImpact < -0.1) {
            if (count > 5) return 'bg-red-500 text-white';
            if (count > 2) return 'bg-red-400 text-white';
            return 'bg-red-300';
        } else {
            if (count > 5) return 'bg-yellow-500';
            if (count > 2) return 'bg-yellow-400';
            return 'bg-yellow-300';
        }
    };

    const getImpactColor = (impact) => {
        const val = Math.abs(impact);
        if (val < 0.05) return 'bg-gray-400';
        if (impact > 0.5) return 'bg-green-600';
        if (impact > 0.2) return 'bg-green-500';
        if (impact > 0.05) return 'bg-green-400';
        if (impact > -0.05) return 'bg-gray-400';
        if (impact > -0.2) return 'bg-orange-400';
        if (impact > -0.5) return 'bg-orange-500';
        return 'bg-red-600';
    };

    const getSentimentColor = (sentiment) => {
        const val = Math.abs(sentiment);
        if (val < 0.05) return 'text-gray-500';
        if (sentiment > 0.3) return 'text-green-600';
        if (sentiment > 0) return 'text-green-400';
        if (sentiment > -0.3) return 'text-yellow-500';
        return 'text-red-500';
    };

    const getSentimentBg = (sentiment) => {
        const val = Math.abs(sentiment);
        if (val < 0.05) return 'bg-gray-100';
        if (sentiment > 0.3) return 'bg-green-100';
        if (sentiment > 0) return 'bg-green-50';
        if (sentiment > -0.3) return 'bg-yellow-50';
        return 'bg-red-50';
    };

    // Generuj dni dla kalendarza
    const generateCalendarDays = () => {
        const year = currentMonth.getFullYear();
        const month = currentMonth.getMonth();

        const firstDay = new Date(year, month, 1);
        const lastDay = new Date(year, month + 1, 0);

        const daysInMonth = lastDay.getDate();
        const startDayOfWeek = (firstDay.getDay() + 6) % 7; // Monday = 0, Sunday = 6

        const days = [];

        // Puste dni przed pierwszym dniem miesiąca
        for (let i = 0; i < startDayOfWeek; i++) {
            days.push(null);
        }

        // Dni miesiąca
        for (let day = 1; day <= daysInMonth; day++) {
            days.push(new Date(year, month, day));
        }

        return days;
    };

    const calendarDays = generateCalendarDays();
    const monthNames = ['Styczeń', 'Luty', 'Marzec', 'Kwiecień', 'Maj', 'Czerwiec',
        'Lipiec', 'Sierpień', 'Wrzesień', 'Październik', 'Listopad', 'Grudzień'];

    const dayTickers = React.useMemo(() => {
        if (!newsForDate || newsForDate.length === 0) return [];
        const allTickers = newsForDate.flatMap(news => news.tickers.map(t => t.ticker));
        return [...new Set(allTickers)].sort();
    }, [newsForDate]);

    const dayTickerStats = React.useMemo(() => {
        if (!newsForDate || newsForDate.length === 0) return {};
        const stats = {};
        newsForDate.forEach(news => {
             news.tickers.forEach(t => {
                 if (!stats[t.ticker]) {
                     stats[t.ticker] = { totalImpact: 0, count: 0 };
                 }
                 stats[t.ticker].totalImpact += t.impact;
                 stats[t.ticker].count += 1;
             });
        });
        const result = {};
        Object.keys(stats).forEach(ticker => {
             result[ticker] = stats[ticker].totalImpact / stats[ticker].count;
        });
        return result;
    }, [newsForDate]);

    const handleTickerFilterClick = (ticker) => {
        setActiveTickerFilters(prev =>
            prev.includes(ticker)
                ? prev.filter(t => t !== ticker)
                : [...prev, ticker]
        );
    };

    const selectAllDayTickers = () => {
        setActiveTickerFilters(dayTickers);
        setShowUnassigned(true);
    };

    const deselectAllDayTickers = () => {
        setActiveTickerFilters([]);
        setShowUnassigned(false);
    };

    const hasUnassignedNews = React.useMemo(() => {
        return newsForDate.some(news => news.tickers.length === 0);
    }, [newsForDate]);

    const filteredNews = React.useMemo(() => {
        return newsForDate.filter(news => {
            const hasTickers = news.tickers.length > 0;
            if (hasTickers) {
                return news.tickers.some(t => activeTickerFilters.includes(t.ticker));
            } else {
                return showUnassigned;
            }
        });
    }, [newsForDate, activeTickerFilters, showUnassigned]);

    return (
        <div className="space-y-4">
            <div className="bg-white rounded-lg shadow p-4">
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-xl font-bold text-gray-900">
                        {monthNames[currentMonth.getMonth()]} {currentMonth.getFullYear()}
                    </h2>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1))}
                            className="px-3 py-1 bg-gray-200 hover:bg-gray-300 rounded-lg"
                        >
                            ←
                        </button>
                        <button
                            onClick={() => setCurrentMonth(new Date())}
                            className="px-3 py-1 bg-blue-500 hover:bg-blue-600 text-white rounded-lg text-sm"
                        >
                            Dziś
                        </button>
                        <button
                            onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1))}
                            className="px-3 py-1 bg-gray-200 hover:bg-gray-300 rounded-lg"
                        >
                            →
                        </button>
                    </div>
                </div>

                {/* Legenda */}
                <div className="mb-4 flex items-center gap-4 text-xs text-gray-600 flex-wrap">
                    <span className="flex items-center gap-2">
                        <span className="w-4 h-4 rounded bg-green-500"></span>
                        Pozytywne (wiele newsów)
                    </span>
                    <span className="flex items-center gap-2">
                        <span className="w-4 h-4 rounded bg-green-300"></span>
                        Pozytywne (kilka)
                    </span>
                    <span className="flex items-center gap-2">
                        <span className="w-4 h-4 rounded bg-yellow-400"></span>
                        Mieszane/Neutralne
                    </span>
                    <span className="flex items-center gap-2">
                        <span className="w-4 h-4 rounded bg-red-300"></span>
                        Negatywne (kilka)
                    </span>
                    <span className="flex items-center gap-2">
                        <span className="w-4 h-4 rounded bg-red-500"></span>
                        Negatywne (wiele)
                    </span>
                </div>

                {/* Kalendarz */}
                <div className="grid grid-cols-7 gap-2">
                    {['Pn', 'Wt', 'Śr', 'Cz', 'Pt', 'Sb', 'Nd'].map(day => (
                        <div key={day} className="text-center font-bold text-sm text-gray-600 py-2">
                            {day}
                        </div>
                    ))}

                    {calendarDays.map((date, idx) => {
                        if (!date) {
                            return <div key={idx} className="p-2"></div>;
                        }

                        const year = date.getFullYear();
                        const month = (date.getMonth() + 1).toString().padStart(2, '0');
                        const day = date.getDate().toString().padStart(2, '0');
                        const dateStr = `${year}-${month}-${day}`;

                        const stats = getDayStats(dateStr);
                        const dayColor = getDayColor(stats);
                        const isSelected = selectedDate === dateStr;

                        return (
                            <button
                                key={idx}
                                onClick={() => fetchNewsForDate(dateStr)}
                                className={`p-2 text-center ${dayColor} rounded-lg hover:ring-2 hover:ring-blue-500 transition-all relative
                          ${isSelected ? 'ring-2 ring-blue-600' : ''}
                        `}
                            >
                                <div className={`font-bold text-sm ${stats && (stats.news_count > 5 || Math.abs(stats.avg_impact) > 0.1) ? 'text-white' : 'text-gray-800'}`}>
                                    {date.getDate()}
                                </div>
                                {stats && stats.news_count > 0 && (
                                    <div className={`text-xs font-bold mt-1 ${stats && (stats.news_count > 5 || Math.abs(stats.avg_impact) > 0.1) ? 'text-white' : 'text-gray-700'}`}>
                                        {stats.news_count} news
                                    </div>
                                )}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Lista newsów z wybranego dnia */}
            {selectedDate && (
                <div className="bg-white rounded-lg shadow p-4">
                    <h3 className="text-lg font-bold text-gray-900 mb-3">
                        Newsy z {selectedDate} ({filteredNews.length})
                    </h3>

                    {(dayTickers.length > 0 || hasUnassignedNews) && (
                        <div className="flex items-center gap-2 mb-4 flex-wrap p-2 bg-gray-50 rounded-lg">
                            <span className="text-sm font-semibold text-gray-700">Filtruj:</span>
                            <div className="flex items-center gap-1">
                                <button onClick={selectAllDayTickers} className="px-2 py-0.5 text-xs bg-gray-600 text-white rounded hover:bg-gray-700">Wszystkie</button>
                                <button onClick={deselectAllDayTickers} className="px-2 py-0.5 text-xs bg-gray-600 text-white rounded hover:bg-gray-700">Żadne</button>
                            </div>
                            <div className="border-l border-gray-300 h-5 mx-1"></div>
                            {dayTickers.map(ticker => {
                                const isActive = activeTickerFilters.includes(ticker);
                                const impact = dayTickerStats[ticker] || 0;
                                let bgClass = '';
                                
                                if (impact > 0.2) {
                                    bgClass = isActive 
                                        ? 'bg-green-600 text-white shadow-md hover:bg-green-700' 
                                        : 'bg-green-100 text-green-800 hover:bg-green-200 border border-green-300';
                                } else if (impact < -0.2) {
                                    bgClass = isActive 
                                        ? 'bg-red-600 text-white shadow-md hover:bg-red-700' 
                                        : 'bg-red-100 text-red-800 hover:bg-red-200 border border-red-300';
                                } else {
                                    bgClass = isActive 
                                        ? 'bg-gray-600 text-white shadow-md hover:bg-gray-700' 
                                        : 'bg-gray-100 text-gray-800 hover:bg-gray-200 border border-gray-300';
                                }

                                return (
                                    <button
                                        key={ticker}
                                        onClick={() => handleTickerFilterClick(ticker)}
                                        className={`px-3 py-1 text-xs font-bold rounded-full transition-all duration-200 ${bgClass}`}
                                    >
                                        {ticker}
                                    </button>
                                );
                            })}
                            {hasUnassignedNews && (
                                <button
                                    onClick={() => setShowUnassigned(prev => !prev)}
                                    className={`px-3 py-1 text-xs font-bold rounded-full transition-all duration-200 ${showUnassigned
                                            ? 'bg-blue-600 text-white shadow'
                                            : 'bg-gray-200 text-gray-800 hover:bg-gray-300'
                                        }`}
                                >
                                    NIEPRZYPISANE
                                </button>
                            )}
                        </div>
                    )}

                    {loading ? (
                        <div className="flex items-center justify-center py-12">
                            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                        </div>
                    ) : filteredNews.length === 0 ? (
                        <p className="text-gray-500 text-center py-8">Brak newsów spełniających kryteria</p>
                    ) : (
                        <div className="space-y-3">
                            {filteredNews.map((news, idx) => (
                                <div key={idx} className="border border-gray-200 rounded-lg p-4 hover:shadow-md transition-shadow relative">
                                    <button
                                        onClick={() => markAsDuplicate(news.news_id)}
                                        className="absolute top-2 right-2 text-gray-400 hover:text-red-500"
                                        title="Oznacz jako duplikat"
                                    >
                                        ✕
                                    </button>
                                    
                                    <div className="flex items-start gap-3">
                                        <div className="flex-shrink-0">
                                            <div className={`w-2 h-16 ${getImpactColor(news.impact)} rounded`}></div>
                                        </div>
                                        
                                        <div className="flex-1">
                                            <div className="flex items-center justify-between mb-1">
                                                <h4 className="font-semibold text-sm text-gray-900">{news.title}</h4>
                                            </div>
                                            
                                            <div className="flex items-center gap-2 text-xs text-gray-500 mb-2">
                                                <span>{news.source}</span>
                                                <span>•</span>
                                                <span>{news.published_at || news.date}</span>
                                                {news.url && (
                                                    <><span>•</span><a href={news.url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">Link</a></>
                                                )}
                                            </div>

                                            {news.tickers && news.tickers.length > 0 ? (
                                                <div className="flex flex-wrap gap-1 mb-2">
                                                    {news.tickers.map((t, i) => (
                                                        <button
                                                            key={i}
                                                            onClick={() => onTickerSelect && onTickerSelect(t.ticker)}
                                                            className="px-2 py-0.5 rounded text-xs font-bold cursor-pointer hover:opacity-80 transition-opacity bg-blue-100 text-blue-800 border border-blue-200"
                                                            title={`Pokaż analizę dla ${t.ticker}`}
                                                        >
                                                            {t.ticker} ({t.impact > 0 ? '+' : ''}{t.impact.toFixed(2)})
                                                        </button>
                                                    ))}
                                                </div>
                                            ) : (
                                                <div className="mb-2">
                                                    <TickerSelect 
                                                        analysisId={news.analysis_id} 
                                                        onSave={handleTickerSave}
                                                        allTickers={allTickers}
                                                    />
                                                </div>
                                            )}

                                            <div className="flex items-center gap-3 mb-2">
                                                <div className="flex items-center gap-1.5">
                                                    <span className="text-xs text-gray-600">Impact:</span>
                                                    <span className={`font-bold text-sm ${getSentimentColor(news.impact)}`}>
                                                        {news.impact > 0 ? '+' : ''}{Number(news.impact).toFixed(2)}
                                                    </span>
                                                </div>
                                                <div className="flex items-center gap-1.5">
                                                    <span className="text-xs text-gray-600">Confidence:</span>
                                                    <span className="font-bold text-sm text-blue-600">
                                                        {(Number(news.confidence) * 100).toFixed(0)}%
                                                    </span>
                                                </div>
                                            </div>

                                            {news.summary && (
                                                <div className="text-xs text-gray-700 leading-relaxed" dangerouslySetInnerHTML={{ __html: news.summary }} />
                                            )}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

// Komponent widoku odrzuconych newsów (kalendarz)
function CalendarRejectedView({ days }) {
    const [calendarStats, setCalendarStats] = useState([]);
    const [selectedDate, setSelectedDate] = useState(null);
    const [newsForDate, setNewsForDate] = useState([]);
    const [loading, setLoading] = useState(false);
    const [currentMonth, setCurrentMonth] = useState(new Date());
    const [reanalyzing, setReanalyzing] = useState({});
    const [reanalysisStatus, setReanalysisStatus] = useState({});

    useEffect(() => {
        fetchCalendarStats();
    }, [days]);

    const fetchCalendarStats = async () => {
        try {
            const response = await fetch(`/api/rejected_calendar_stats?days=${days}`);
            const data = await response.json();
            
            // Agregacja po dacie, bo endpoint zwraca wiersze per (data, reason)
            const aggregated = {};
            data.forEach(item => {
                if (!aggregated[item.date]) {
                    aggregated[item.date] = { date: item.date, news_count: 0, reasons: {} };
                }
                aggregated[item.date].news_count += item.news_count;
                aggregated[item.date].reasons[item.reason] = (aggregated[item.date].reasons[item.reason] || 0) + item.news_count;
            });
            
            setCalendarStats(Object.values(aggregated));
        } catch (error) {
            console.error('Error fetching rejected calendar stats:', error);
        }
    };

    const fetchNewsForDate = async (date) => {
        setLoading(true);
        try {
            const response = await fetch(`/api/rejected_news_by_date/${date}`);
            const data = await response.json();
            setNewsForDate(data);
            setSelectedDate(date);
        } catch (error) {
            console.error('Error fetching rejected news for date:', error);
        } finally {
            setLoading(false);
        }
    };

    const reanalyzeNews = async (newsId) => {
        setReanalyzing(prev => ({ ...prev, [newsId]: true }));
        try {
            const response = await fetch('/api/reanalyze_news', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ news_id: newsId })
            });
            const data = await response.json();
            if (response.ok) {
                setReanalysisStatus(prev => ({ ...prev, [newsId]: 'success' }));
                // Usuń z listy po sukcesie (opcjonalne)
                // setNewsForDate(prev => prev.filter(n => n.news_id !== newsId));
            } else {
                setReanalysisStatus(prev => ({ ...prev, [newsId]: 'error' }));
                console.error('Error reanalyzing:', data.error);
            }
        } catch (error) {
            console.error('Error reanalyzing:', error);
            setReanalysisStatus(prev => ({ ...prev, [newsId]: 'error' }));
        } finally {
            setReanalyzing(prev => ({ ...prev, [newsId]: false }));
        }
    };

    const getDayStats = (dateStr) => {
        return calendarStats.find(s => s.date === dateStr);
    };

    const getDayColor = (stats) => {
        if (!stats || stats.news_count === 0) return 'bg-gray-50';
        const count = stats.news_count;
        if (count > 10) return 'bg-red-600 text-white';
        if (count > 5) return 'bg-red-400 text-white';
        if (count > 2) return 'bg-red-300';
        return 'bg-red-100';
    };

    const generateCalendarDays = () => {
        const year = currentMonth.getFullYear();
        const month = currentMonth.getMonth();
        const firstDay = new Date(year, month, 1);
        const lastDay = new Date(year, month + 1, 0);
        const daysInMonth = lastDay.getDate();
        const startDayOfWeek = (firstDay.getDay() + 6) % 7; 
        const days = [];
        for (let i = 0; i < startDayOfWeek; i++) days.push(null);
        for (let day = 1; day <= daysInMonth; day++) days.push(new Date(year, month, day));
        return days;
    };

    const calendarDays = generateCalendarDays();
    const monthNames = ['Styczeń', 'Luty', 'Marzec', 'Kwiecień', 'Maj', 'Czerwiec',
        'Lipiec', 'Sierpień', 'Wrzesień', 'Październik', 'Listopad', 'Grudzień'];

    return (
        <div className="space-y-4">
            <div className="bg-white rounded-lg shadow p-4">
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-xl font-bold text-gray-900">
                        Odrzucone Newsy: {monthNames[currentMonth.getMonth()]} {currentMonth.getFullYear()}
                    </h2>
                    <div className="flex items-center gap-2">
                        <button onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1))} className="px-3 py-1 bg-gray-200 hover:bg-gray-300 rounded-lg">←</button>
                        <button onClick={() => setCurrentMonth(new Date())} className="px-3 py-1 bg-blue-500 hover:bg-blue-600 text-white rounded-lg text-sm">Dziś</button>
                        <button onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1))} className="px-3 py-1 bg-gray-200 hover:bg-gray-300 rounded-lg">→</button>
                    </div>
                </div>

                <div className="grid grid-cols-7 gap-2">
                    {['Pn', 'Wt', 'Śr', 'Cz', 'Pt', 'Sb', 'Nd'].map(day => (
                        <div key={day} className="text-center font-bold text-sm text-gray-600 py-2">{day}</div>
                    ))}
                    {calendarDays.map((date, idx) => {
                        if (!date) return <div key={idx} className="p-2"></div>;
                        const year = date.getFullYear();
                        const month = (date.getMonth() + 1).toString().padStart(2, '0');
                        const day = date.getDate().toString().padStart(2, '0');
                        const dateStr = `${year}-${month}-${day}`;
                        const stats = getDayStats(dateStr);
                        const dayColor = getDayColor(stats);
                        const isSelected = selectedDate === dateStr;

                        return (
                            <button
                                key={idx}
                                onClick={() => fetchNewsForDate(dateStr)}
                                className={`p-2 text-center ${dayColor} rounded-lg hover:ring-2 hover:ring-blue-500 transition-all relative ${isSelected ? 'ring-2 ring-blue-600' : ''}`}
                            >
                                <div className={`font-bold text-sm ${stats && stats.news_count > 5 ? 'text-white' : 'text-gray-800'}`}>
                                    {date.getDate()}
                                </div>
                                {stats && stats.news_count > 0 && (
                                    <div className={`text-xs font-bold mt-1 ${stats.news_count > 5 ? 'text-white' : 'text-gray-700'}`}>
                                        {stats.news_count}
                                    </div>
                                )}
                            </button>
                        );
                    })}
                </div>
            </div>

            {selectedDate && (
                <div className="bg-white rounded-lg shadow p-4">
                    <h3 className="text-lg font-bold text-gray-900 mb-3">
                        Odrzucone z {selectedDate} ({newsForDate.length})
                    </h3>
                    {loading ? (
                        <div className="flex items-center justify-center py-12">
                            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-red-500"></div>
                        </div>
                    ) : newsForDate.length === 0 ? (
                        <p className="text-gray-500 text-center py-8">Brak odrzuconych newsów z tego dnia</p>
                    ) : (
                        <div className="space-y-3">
                            {newsForDate.map((news, idx) => (
                                <div key={idx} className="border border-red-200 rounded-lg p-4 hover:shadow-md transition-shadow bg-red-50">
                                    <div className="flex items-start justify-between gap-3">
                                        <div className="flex-1">
                                            <h4 className="font-semibold text-sm text-gray-900 mb-2">{news.title}</h4>
                                            <div className="flex items-center gap-2 text-xs text-gray-500 mb-2">
                                                <span>{news.source}</span>
                                                {news.url && (
                                                    <><span>•</span><a href={news.url} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:underline">Link</a></>
                                                )}
                                            </div>
                                            <div className="mb-2 p-2 bg-red-100 rounded border border-red-300">
                                                <div className="text-xs font-semibold text-red-900 mb-1">Powód odrzucenia:</div>
                                                <div className="text-xs text-red-800">{news.reason}</div>
                                                <div className="text-xs text-red-600 mt-1">Score: {(news.relevance_score * 100).toFixed(1)}%</div>
                                            </div>
                                            {news.content && (
                                                <div className="text-xs text-gray-700 leading-relaxed mb-2">
                                                    {news.content.substring(0, 200)}...
                                                </div>
                                            )}
                                        </div>
                                        <button
                                            onClick={() => reanalyzeNews(news.news_id)}
                                            disabled={reanalyzing[news.news_id] || reanalysisStatus[news.news_id] === 'success'}
                                            className={`flex-shrink-0 px-4 py-2 rounded-lg font-semibold text-sm transition-colors w-28 text-center ${
                                                reanalyzing[news.news_id] ? 'bg-gray-300 text-gray-600 cursor-not-allowed' :
                                                reanalysisStatus[news.news_id] === 'success' ? 'bg-green-500 text-white' :
                                                reanalysisStatus[news.news_id] === 'error' ? 'bg-red-500 text-white' :
                                                'bg-blue-500 hover:bg-blue-600 text-white'
                                            }`}
                                        >
                                            {reanalyzing[news.news_id] ? 'Analizowanie...' :
                                             reanalysisStatus[news.news_id] === 'success' ? 'Przeanalizowano' :
                                             reanalysisStatus[news.news_id] === 'error' ? 'Błąd' : 'Analizuj AI'}
                                        </button>
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}

/* Komponent widoku portfela */
function PortfolioView({ days }) {
    const [overview, setOverview] = useState(null);
    const [fullRoiSeries, setFullRoiSeries] = useState([]); // Pełne dane
    const [roiSeries, setRoiSeries] = useState([]); // Przefiltrowane dane
    const [monthlyProfits, setMonthlyProfits] = useState([]); // Dane miesięczne
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [timeRange, setTimeRange] = useState('ALL');
    const [sortConfig, setSortConfig] = useState({ key: 'value', direction: 'desc' });
    const chartContainerRef = useRef(null);
    const chartRef = useRef(null);

    const fmt = (n, digits = 2) => (n === null || n === undefined ? '-' : Number(n).toFixed(digits));

    // Przetwarzanie danych miesięcznych do tabeli Year x Month
    const monthlyTableData = React.useMemo(() => {
        if (!monthlyProfits.length) return [];
        const years = {};
        
        monthlyProfits.forEach(item => {
            const [year, month] = item.month.split('-'); // YYYY-MM
            if (!years[year]) years[year] = Array(12).fill(0);
            years[year][parseInt(month) - 1] = item.profit;
        });
        
        // Sort years desc
        return Object.keys(years).sort().reverse().map(year => ({
            year,
            months: years[year],
            total: years[year].reduce((a, b) => a + b, 0)
        }));
    }, [monthlyProfits]);

    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            setError(null);
            try {
                const [ovrRes, roiRes, monthlyRes] = await Promise.all([
                    fetch('/api/portfolio/overview'),
                    fetch('/api/portfolio/roi'),
                    fetch('/api/portfolio/monthly_profit')
                ]);
                const ovr = await ovrRes.json();
                const roi = await roiRes.json();
                const monthly = await monthlyRes.json();
                
                setOverview(ovr);
                setMonthlyProfits(Array.isArray(monthly) ? monthly : []);
                const series = Array.isArray(roi) ? roi : [];
                setFullRoiSeries(series);
                filterData(series, 'ALL');
            } catch (e) {
                console.error('Error fetching portfolio data:', e);
                setError('Błąd pobierania danych portfela');
            } finally {
                setLoading(false);
            }
        };
        fetchData();
    }, []); // Pobieramy dane tylko raz po zamontowaniu komponentu

    const filterData = (data, range) => {
        if (!data || data.length === 0) {
            setRoiSeries([]);
            return;
        }

        const now = new Date();
        let cutoffDate = new Date(data[0].date); 

        if (range === '1M') cutoffDate = new Date(now.setMonth(now.getMonth() - 1));
        else if (range === '3M') cutoffDate = new Date(now.setMonth(now.getMonth() - 3));
        else if (range === '6M') cutoffDate = new Date(now.setMonth(now.getMonth() - 6));
        else if (range === '1Y') cutoffDate = new Date(now.setFullYear(now.getFullYear() - 1));
        
        // Find closest start date
        const startIndex = data.findIndex(d => new Date(d.date) >= cutoffDate);
        if (startIndex === -1) {
             setRoiSeries([]);
             return;
        }

        const rawFiltered = data.slice(startIndex);
        
        // Normalizacja ROI do 0% na początku wybranego okresu
        if (rawFiltered.length > 0) {
            const startRoi = rawFiltered[0].rate_of_return;
            // TWR: (1 + total) = (1 + start) * (1 + period)
            // (1 + period) = (1 + total) / (1 + start)
            // period = ... - 1
            
            const startFactor = 1 + (startRoi / 100.0);
            
            const rebased = rawFiltered.map(item => ({
                ...item,
                rate_of_return: (((1 + item.rate_of_return / 100.0) / startFactor) - 1) * 100.0
            }));
            setRoiSeries(rebased);
        } else {
            setRoiSeries(rawFiltered);
        }
    };

    const handleTimeRangeChange = (range) => {
        setTimeRange(range);
        filterData(fullRoiSeries, range);
    };

    useEffect(() => {
        if (!chartContainerRef.current || !roiSeries || roiSeries.length === 0) return;

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: 'white' },
                textColor: 'black',
            },
            width: chartContainerRef.current.clientWidth,
            height: 300,
            grid: {
                vertLines: { color: '#f0f0f0' },
                horzLines: { color: '#f0f0f0' },
            },
            rightPriceScale: {
                borderColor: '#d1d4dc',
            },
            timeScale: {
                borderColor: '#d1d4dc',
            },
        });
        chartRef.current = chart;

        // Baseline Series for ROI
        const series = chart.addBaselineSeries({
            baseValue: { type: 'price', price: 0 },
            topLineColor: '#10b981', // Green
            topFillColor1: 'rgba(16, 185, 129, 0.28)',
            topFillColor2: 'rgba(16, 185, 129, 0.05)',
            bottomLineColor: '#ef4444', // Red
            bottomFillColor1: 'rgba(239, 68, 68, 0.05)',
            bottomFillColor2: 'rgba(239, 68, 68, 0.28)',
        });

        const data = roiSeries.map(d => ({
            time: d.date,
            value: d.rate_of_return
        }));
        
        // Ensure sorted by time
        data.sort((a, b) => new Date(a.time) - new Date(b.time));
        
        series.setData(data);
        chart.timeScale().fitContent();

        const handleResize = () => {
            if (chartContainerRef.current) {
                chart.applyOptions({ width: chartContainerRef.current.clientWidth });
            }
        };
        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            chart.remove();
        };
    }, [roiSeries]);

    if (loading) {
        return (
            <div className="bg-white rounded-lg shadow p-6 flex items-center justify-center" style={{ minHeight: '300px' }}>
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="bg-white rounded-lg shadow p-6">
                <div className="text-center text-red-600 py-8">{error}</div>
            </div>
        );
    }

    if (!overview) {
        return (
            <div className="bg-white rounded-lg shadow p-6">
                <div className="text-center text-gray-500 py-8">Brak danych o portfelu</div>
            </div>
        );
    }

    const changeColor = overview.daily_change_value >= 0 ? 'text-green-600' : 'text-red-600';
    const roiColor = (overview.roi_pct || 0) >= 0 ? 'text-green-600' : 'text-red-600';
    const profitColor = (overview.total_profit || 0) >= 0 ? 'text-green-600' : 'text-red-600';

    const handleSort = (key) => {
        let direction = 'desc';
        if (sortConfig.key === key && sortConfig.direction === 'desc') {
            direction = 'asc';
        }
        setSortConfig({ key, direction });
    };

    const sortedAssets = [...(overview.assets || [])].sort((a, b) => {
        if (a[sortConfig.key] < b[sortConfig.key]) {
            return sortConfig.direction === 'asc' ? -1 : 1;
        }
        if (a[sortConfig.key] > b[sortConfig.key]) {
            return sortConfig.direction === 'asc' ? 1 : -1;
        }
        return 0;
    });

    const SortIcon = ({ column }) => {
        if (sortConfig.key !== column) return <span className="text-gray-300 ml-1">⇅</span>;
        return sortConfig.direction === 'asc' ? <span className="ml-1">▲</span> : <span className="ml-1">▼</span>;
    };

    const getProfitColor = (val) => {
        if (val > 0) return 'text-green-600 bg-green-50';
        if (val < 0) return 'text-red-600 bg-red-50';
        return 'text-gray-400';
    };

    return (
        <div className="space-y-4">
            <div className="grid grid-cols-6 gap-3">
                <div className="bg-white rounded-lg shadow p-4">
                    <div className="text-xs text-gray-600">Wartość portfela</div>
                    <div className="text-2xl font-bold text-gray-900">{fmt(overview.value)} PLN</div>
                </div>
                <div className="bg-white rounded-lg shadow p-4">
                    <div className="text-xs text-gray-600">Dzisiejsza zmiana</div>
                    <div className={`text-lg font-bold ${changeColor}`}>
                        {overview.daily_change_value >= 0 ? '+' : ''}{fmt(overview.daily_change_value)} PLN
                        <span className="ml-2 text-sm">({overview.daily_change_pct >= 0 ? '+' : ''}{fmt(overview.daily_change_pct, 2)}%)</span>
                    </div>
                </div>
                <div className="bg-white rounded-lg shadow p-4">
                    <div className="text-xs text-gray-600">Zysk łącznie</div>
                    <div className={`text-lg font-bold ${profitColor}`}>{overview.total_profit >= 0 ? '+' : ''}{fmt(overview.total_profit)} PLN</div>
                </div>
                <div className="bg-white rounded-lg shadow p-4">
                    <div className="text-xs text-gray-600">ROI (TWR)</div>
                    <div className={`text-lg font-bold ${roiColor}`}>{overview.roi_pct >= 0 ? '+' : ''}{fmt(overview.roi_pct, 2)}%</div>
                </div>
                <div className="bg-white rounded-lg shadow p-4">
                    <div className="text-xs text-gray-600">Bieżący zysk</div>
                    <div className={`text-lg font-bold ${overview.current_profit >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                        {overview.current_profit >= 0 ? '+' : ''}{fmt(overview.current_profit)} PLN
                    </div>
                </div>
                <div className="bg-white rounded-lg shadow p-4">
                    <div className="text-xs text-gray-600">Stopa roczna (TWR)</div>
                    <div className="text-lg font-bold text-gray-900">{fmt(overview.annualized_return_pct, 2)}%</div>
                </div>
            </div>

            <div className="bg-white rounded-lg shadow-lg p-6 relative">
                <div className="flex items-center justify-between mb-4">
                    <div>
                        <h3 className="text-xl font-bold text-gray-900">Wykres ROI (MWR) portfela</h3>
                        <p className="text-sm text-gray-600">
                            {roiSeries.length > 0 ? `${roiSeries.length} punktów` : 'Brak danych'}
                        </p>
                    </div>
                    <div className="flex bg-gray-100 rounded-lg p-1">
                        {['1M', '3M', '6M', '1Y', 'ALL'].map(range => (
                            <button
                                key={range}
                                onClick={() => handleTimeRangeChange(range)}
                                className={`px-3 py-1 text-xs font-semibold rounded-md transition-colors ${
                                    timeRange === range ? 'bg-white text-blue-600 shadow' : 'text-gray-500 hover:bg-gray-200'
                                }`}
                            >
                                {range}
                            </button>
                        ))}
                    </div>
                </div>
                
                <div ref={chartContainerRef} className="w-full h-[300px]" />
            </div>

            {overview.assets && overview.assets.length > 0 && (
                <div className="bg-white rounded-lg shadow-lg overflow-hidden">
                    <div className="px-6 py-4 border-b border-gray-200">
                        <h3 className="text-lg font-bold text-gray-900">Aktywa w portfelu</h3>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gray-50 select-none">
                                <tr>
                                    <th onClick={() => handleSort('ticker')} className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100">
                                        Ticker <SortIcon column="ticker" />
                                    </th>
                                    <th onClick={() => handleSort('daily_change')} className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100">
                                        Zmiana 1D <SortIcon column="daily_change" />
                                    </th>
                                    <th onClick={() => handleSort('quantity')} className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100">
                                        Ilość <SortIcon column="quantity" />
                                    </th>
                                    <th onClick={() => handleSort('avg_purchase_price')} className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100">
                                        Śr. cena zakupu <SortIcon column="avg_purchase_price" />
                                    </th>
                                    <th onClick={() => handleSort('current_price')} className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100">
                                        Cena akt. <SortIcon column="current_price" />
                                    </th>
                                    <th onClick={() => handleSort('value')} className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100">
                                        Wartość [PLN] <SortIcon column="value" />
                                    </th>
                                    <th onClick={() => handleSort('share_pct')} className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100">
                                        Udział % <SortIcon column="share_pct" />
                                    </th>
                                    <th onClick={() => handleSort('return_pct')} className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100">
                                        Zwrot % <SortIcon column="return_pct" />
                                    </th>
                                    <th onClick={() => handleSort('profit_pln')} className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100">
                                        Zysk [PLN] <SortIcon column="profit_pln" />
                                    </th>
                                </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-200">
                                {sortedAssets.map((asset, idx) => (
                                    <tr key={asset.ticker} className="hover:bg-gray-50">
                                        <td className="px-6 py-4 whitespace-nowrap text-sm font-bold text-gray-900">{asset.ticker}</td>
                                        <td className={`px-6 py-4 whitespace-nowrap text-sm text-right font-semibold ${asset.daily_change >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                            {asset.daily_change >= 0 ? '+' : ''}{fmt(asset.daily_change, 2)}%
                                        </td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-500">{fmt(asset.quantity, 4)}</td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-500">{fmt(asset.avg_purchase_price, 2)}</td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-900 font-medium">{fmt(asset.current_price, 2)}</td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-900 font-bold">{fmt(asset.value, 2)}</td>
                                        <td className="px-6 py-4 whitespace-nowrap text-sm text-right text-gray-500">{fmt(asset.share_pct, 1)}%</td>
                                        <td className={`px-6 py-4 whitespace-nowrap text-sm text-right font-bold ${asset.return_pct >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                            {asset.return_pct >= 0 ? '+' : ''}{fmt(asset.return_pct, 2)}%
                                        </td>
                                        <td className={`px-6 py-4 whitespace-nowrap text-sm text-right font-bold ${asset.profit_pln >= 0 ? 'text-green-600' : 'text-red-600'}`}>
                                            {asset.profit_pln >= 0 ? '+' : ''}{fmt(asset.profit_pln, 2)}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}

            {monthlyTableData.length > 0 && (
                <div className="bg-white rounded-lg shadow-lg overflow-hidden mt-6">
                    <div className="px-6 py-4 border-b border-gray-200">
                        <h3 className="text-lg font-bold text-gray-900">Zysk Miesięczny [PLN]</h3>
                    </div>
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200">
                            <thead className="bg-gray-50">
                                <tr>
                                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Rok</th>
                                    {['Sty', 'Lut', 'Mar', 'Kwi', 'Maj', 'Cze', 'Lip', 'Sie', 'Wrz', 'Paź', 'Lis', 'Gru'].map(m => (
                                        <th key={m} className="px-2 py-2 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">{m}</th>
                                    ))}
                                    <th className="px-3 py-2 text-right text-xs font-bold text-gray-700 uppercase tracking-wider">Razem</th>
                                </tr>
                            </thead>
                            <tbody className="bg-white divide-y divide-gray-200">
                                {monthlyTableData.map((row) => (
                                    <tr key={row.year} className="hover:bg-gray-50">
                                        <td className="px-3 py-2 whitespace-nowrap text-sm font-bold text-gray-900">{row.year}</td>
                                        {row.months.map((val, idx) => (
                                            <td key={idx} className={`px-2 py-2 whitespace-nowrap text-xs text-right font-medium ${getProfitColor(val)}`}>
                                                {val !== 0 ? fmt(val, 0) : '-'}
                                            </td>
                                        ))}
                                        <td className={`px-3 py-2 whitespace-nowrap text-sm text-right font-bold ${row.total >= 0 ? 'text-green-700' : 'text-red-700'}`}>
                                            {fmt(row.total, 0)}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                </div>
            )}
        </div>
    );
}

// Główny komponent dashboardu
function TickerDashboard() {
    const [tickers, setTickers] = useState([]);
    const [selectedTicker, setSelectedTicker] = useState(null);
    const [analyses, setAnalyses] = useState([]);
    const [brokerageAnalyses, setBrokerageAnalyses] = useState([]);
    const [priceHistory, setPriceHistory] = useState([]);
    const [loading, setLoading] = useState(false);
    const [loadingChart, setLoadingChart] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [days, setDays] = useState(30);
    const [filterImpact, setFilterImpact] = useState('all');
    const [showStats, setShowStats] = useState(true);
    const [viewMode, setViewMode] = useState('tickers'); // 'tickers', 'calendar', 'rejected' lub 'portfolio'
    const [scrapingTicker, setScrapingTicker] = useState(null);
    const [notification, setNotification] = useState(null);
    const notificationTimeout = useRef(null);

    const showNotification = (message, type = 'success') => {
        setNotification({ message, type });

        if (notificationTimeout.current) {
            clearTimeout(notificationTimeout.current);
        }

        notificationTimeout.current = setTimeout(() => {
            setNotification(null);
        }, 5000);
    };

    const handleTickerSelectFromCalendar = (tickerSymbol) => {
        const tickerData = tickers.find(t => t.ticker === tickerSymbol);
        if (tickerData) {
            setSelectedTicker(tickerData);
        } else {
            setSelectedTicker({ ticker: tickerSymbol });
        }
        setViewMode('tickers');
    };

    useEffect(() => {
        fetchTickers();
    }, [days]);

    useEffect(() => {
        if (selectedTicker) {
            fetchAnalyses(selectedTicker.ticker);
            fetchBrokerageAnalyses(selectedTicker.ticker);
            fetchPriceHistory(selectedTicker.ticker);
        }
    }, [selectedTicker, days]);

    const fetchTickers = async () => {
        try {
            const response = await fetch(`/api/tickers?days=${days}`);
            const data = await response.json();
            setTickers(data);
        } catch (error) {
            console.error('Error fetching tickers:', error);
        }
    };

    const fetchAnalyses = async (ticker) => {
        setLoading(true);
        try {
            const response = await fetch(`/api/analyses/${ticker}?days=${days}`);
            const data = await response.json();
            setAnalyses(data);
        } catch (error) {
            console.error('Error fetching analyses:', error);
        } finally {
            setLoading(false);
        }
    };

    const fetchBrokerageAnalyses = async (ticker) => {
        try {
            const response = await fetch(`/api/brokerage/${ticker}?days=${days}`);
            const data = await response.json();
            setBrokerageAnalyses(data);
        } catch (error) {
            console.error('Error fetching brokerage analyses:', error);
        }
    };

    const fetchPriceHistory = async (ticker) => {
        setLoadingChart(true);
        try {
            const response = await fetch(`/api/price_history/${ticker}?days=${days}`);
            const data = await response.json();
            setPriceHistory(data);
        } catch (error) {
            console.error('Error fetching price history:', error);
            setPriceHistory([]);
        } finally {
            setLoadingChart(false);
        }
    };

    const markAsDuplicate = async (newsId) => {
        // Optimistic UI update
        const originalAnalyses = [...analyses];
        const updatedAnalyses = analyses.filter(a => a.news_id !== newsId);
        setAnalyses(updatedAnalyses);

        try {
            const response = await fetch('/api/mark_duplicate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ news_id: newsId })
            });

            if (response.ok) {
                showNotification('News oznaczony jako duplikat.', 'success');
                fetchTickers(); // Odśwież statystyki tickerów
            } else {
                setAnalyses(originalAnalyses); // Revert on failure
                showNotification('Błąd przy oznaczaniu newsa jako duplikat.', 'error');
            }
        } catch (error) {
            console.error('Error marking as duplicate:', error);
            setAnalyses(originalAnalyses); // Revert on error
            showNotification('Błąd sieci przy oznaczaniu jako duplikat.', 'error');
        }
    };

    const filteredTickers = tickers.filter(t =>
        t.ticker.toLowerCase().includes(searchTerm.toLowerCase()) ||
        (t.company_name && t.company_name.toLowerCase().includes(searchTerm.toLowerCase()))
    );

    const sortedTickers = [...filteredTickers].sort((a, b) => {
        // Sortowanie: portfolio -> ulubione -> impact
        if (a.in_portfolio !== b.in_portfolio) {
            return b.in_portfolio - a.in_portfolio;
        }
        if (a.is_favorite !== b.is_favorite) {
            return b.is_favorite - a.is_favorite;
        }
    return b.avg_sentiment - a.avg_sentiment;
});
    const listForView = viewMode === 'portfolio' ? sortedTickers.filter(t => t.in_portfolio) : sortedTickers;

    // Auto-select first portfolio ticker when switching to Portfolio view
    useEffect(() => {
        if (viewMode === 'portfolio') {
            const first = sortedTickers.find(t => t.in_portfolio);
            if (first && (!selectedTicker || selectedTicker.ticker !== first.ticker)) {
                setSelectedTicker(first);
            }
        }
    }, [viewMode, sortedTickers]);

    const filteredAnalyses = analyses.filter(a => {
        if (filterImpact === 'all') return true;
        if (filterImpact === 'positive') return a.impact > 0.05;
        if (filterImpact === 'negative') return a.impact < -0.05;
        if (filterImpact === 'neutral') return Math.abs(a.impact) <= 0.05;
        return true;
    });

    const getSentimentColor = (sentiment) => {
        const val = Math.abs(sentiment);
        if (val < 0.05) return 'text-gray-500';
        if (sentiment > 0.3) return 'text-green-600';
        if (sentiment > 0) return 'text-green-400';
        if (sentiment > -0.3) return 'text-yellow-500';
        return 'text-red-500';
    };

    const getSentimentBg = (sentiment) => {
        const val = Math.abs(sentiment);
        if (val < 0.05) return 'bg-gray-100';
        if (sentiment > 0.3) return 'bg-green-100';
        if (sentiment > 0) return 'bg-green-50';
        if (sentiment > -0.3) return 'bg-yellow-50';
        return 'bg-red-50';
    };

    const getRecommendationColor = (recommendation) => {
        if (!recommendation) return 'text-gray-600';
        const rec = recommendation.toLowerCase();
        if (rec.includes('kupuj') || rec.includes('buy') || rec.includes('accumulate')) {
            return 'text-green-600 font-bold';
        }
        if (rec.includes('trzymaj') || rec.includes('hold') || rec.includes('neutral')) {
            return 'text-yellow-600 font-bold';
        }
        if (rec.includes('sprzedaj') || rec.includes('sell') || rec.includes('reduce')) {
            return 'text-red-600 font-bold';
        }
        return 'text-gray-600';
    };

    const getUpsideColor = (upside) => {
        if (upside === null || upside === undefined) return 'text-gray-600';
        if (upside > 30) return 'text-green-700 font-bold';
        if (upside > 15) return 'text-green-600 font-semibold';
        if (upside > 5) return 'text-green-500';
        if (upside > -5) return 'text-gray-600';
        if (upside > -15) return 'text-red-500';
        if (upside > -30) return 'text-red-600 font-semibold';
        return 'text-red-700 font-bold';
    };

    const getUpsideBg = (upside) => {
        if (upside === null || upside === undefined) return 'bg-gray-50';
        if (upside > 20) return 'bg-green-100';
        if (upside > 10) return 'bg-green-50';
        if (upside > -10) return 'bg-gray-50';
        if (upside > -20) return 'bg-red-50';
        return 'bg-red-100';
    };

    const getImpactColor = (impact) => {
        const val = Math.abs(impact);
        if (val < 0.05) return 'bg-gray-400';
        if (impact > 0.5) return 'bg-green-600';
        if (impact > 0.2) return 'bg-green-500';
        if (impact > 0.05) return 'bg-green-400';
        if (impact > -0.05) return 'bg-gray-400';
        if (impact > -0.2) return 'bg-orange-400';
        if (impact > -0.5) return 'bg-orange-500';
        return 'bg-red-600';
    };

    // Statystyki dla wybranego tickera
    const tickerStats = selectedTicker ? {
        totalNews: analyses.length,
        positiveNews: analyses.filter(a => a.impact > 0.05).length,
        negativeNews: analyses.filter(a => a.impact < -0.05).length,
        neutralNews: analyses.filter(a => Math.abs(a.impact) <= 0.05).length,
        avgImpact: analyses.length > 0 ? (analyses.reduce((sum, a) => sum + a.impact, 0) / analyses.length) : 0,
        avgConfidence: analyses.length > 0 ? (analyses.reduce((sum, a) => sum + a.confidence, 0) / analyses.length) : 0
    } : null;

    return (
        <div className="min-h-screen bg-gray-50 p-4">
            <div className="max-w-7xl mx-auto">
                    <div className="flex items-center justify-between mb-4">
                        <h1 className="text-2xl font-bold text-gray-900">
                            Analiza Sentymentu Tickerów
                        </h1>
                        <div className="flex items-center gap-3">
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={() => setViewMode('tickers')}
                                    className={`px-3 py-1 text-sm rounded-lg transition-colors ${viewMode === 'tickers'
                                        ? 'bg-blue-500 text-white'
                                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                                    }`}
                                >
                                    Widok Tickerów
                                </button>
                                <button
                                    onClick={() => setViewMode('calendar')}
                                    className={`px-3 py-1 text-sm rounded-lg transition-colors ${viewMode === 'calendar'
                                        ? 'bg-blue-500 text-white'
                                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                                    }`}
                                >
                                    Kalendarz Analiz
                                </button>
                                <button
                                    onClick={() => setViewMode('rejected')}
                                    className={`px-3 py-1 text-sm rounded-lg transition-colors ${viewMode === 'rejected'
                                        ? 'bg-red-500 text-white'
                                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                                    }`}
                                >
                                    Odrzucone Newsy
                                </button>
                                <button
                                    onClick={() => setViewMode('portfolio')}
                                    className={`px-3 py-1 text-sm rounded-lg transition-colors ${viewMode === 'portfolio'
                                        ? 'bg-green-600 text-white'
                                        : 'bg-gray-200 text-gray-700 hover:bg-gray-300'
                                    }`}
                                >
                                    Portfolio
                                </button>
                            </div>
                            <div className="flex items-center gap-2">
                                <label className="text-xs text-gray-600">Okres:</label>
                            <select
                                value={days}
                                onChange={(e) => setDays(Number(e.target.value))}
                                className="px-2 py-1 text-sm border border-gray-300 rounded-lg"
                            >
                                <option value="7">7 dni</option>
                                <option value="14">14 dni</option>
                                <option value="30">1 miesiąc</option>
                                <option value="90">3 miesiące</option>
                                <option value="180">6 miesięcy</option>
                                <option value="365">1 rok</option>
                            </select>
                        </div>
                    </div>
                </div>

                {notification && (
                    <div
                        className={`fixed top-5 right-5 p-4 rounded-lg shadow-lg text-sm z-50 transition-opacity duration-300 ${notification.type === 'success' ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'}`}
                        onClick={() => setNotification(null)}
                    >
                        {notification.message}
                    </div>
                )}

                {viewMode === 'calendar' ? (
                    <CalendarView days={days} onTickerSelect={handleTickerSelectFromCalendar} showNotification={showNotification} />
                ) : viewMode === 'rejected' ? (
                    <CalendarRejectedView days={days} />
                ) : viewMode === 'portfolio' ? (
                    <PortfolioView days={days} />
                ) : (
                    <div className="grid grid-cols-12 gap-4">
                        <div className="col-span-3 bg-white rounded-lg shadow p-3 sticky top-4 self-start" style={{ maxHeight: 'calc(100vh - 2rem)' }}>
                            <div className="mb-3">
                                <input
                                    type="text"
                                    placeholder="Szukaj tickera..."
                                    className="w-full px-3 py-1.5 text-sm border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                    value={searchTerm}
                                    onChange={(e) => setSearchTerm(e.target.value)}
                                />
                            </div>

                            <div className="space-y-1.5 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 10rem)' }}>
                                {listForView.map((ticker) => {
                                    const togglePortfolio = async (e) => {
                                        e.stopPropagation();
                                        try {
                                            const response = await fetch('/api/toggle_portfolio', {
                                                method: 'POST',
                                                headers: { 'Content-Type': 'application/json' },
                                                body: JSON.stringify({
                                                    ticker: ticker.ticker,
                                                    in_portfolio: !ticker.in_portfolio
                                                })
                                            });
                                            if (response.ok) {
                                                fetchTickers();
                                            }
                                        } catch (error) {
                                            console.error('Error toggling portfolio:', error);
                                        }
                                    };
                                    const toggleFavorite = async (e) => {
                                        e.stopPropagation();
                                        try {
                                            const response = await fetch('/api/toggle_favorite', {
                                                method: 'POST',
                                                headers: { 'Content-Type': 'application/json' },
                                                body: JSON.stringify({
                                                    ticker: ticker.ticker,
                                                    is_favorite: !ticker.is_favorite
                                                })
                                            });
                                            if (response.ok) {
                                                fetchTickers();
                                            }
                                        } catch (error) {
                                            console.error('Error toggling favorite:', error);
                                        }
                                    };

                                    const handleScrape = async (e) => {
                                        e.stopPropagation();

                                        setScrapingTicker(ticker.ticker);
                                        showNotification(`Rozpoczynam scraping dla ${ticker.ticker}...`, 'success');

                                        try {
                                            const response = await fetch('/api/scrape_ticker', {
                                                method: 'POST',
                                                headers: { 'Content-Type': 'application/json' },
                                                body: JSON.stringify({ ticker: ticker.ticker })
                                            });
                                            const data = await response.json();

                                            if (response.ok) {
                                                showNotification(`Scraping dla ${ticker.ticker} zakończony! Nowe artykuły: ${data.new_articles}`, 'success');
                                                fetchAnalyses(ticker.ticker);
                                            } else {
                                                showNotification(`Błąd podczas scrapingu ${ticker.ticker}: ${data.error}`, 'error');
                                            }
                                        } catch (error) {
                                            showNotification(`Błąd sieci podczas scrapingu ${ticker.ticker}.`, 'error');
                                        } finally {
                                            setScrapingTicker(null);
                                        }
                                    };

                                    return (
                                        <div
                                            key={ticker.ticker}
                                            onClick={() => setSelectedTicker(ticker)}
                                            className={`p-2 rounded-lg cursor-pointer transition-all relative ${ticker.in_portfolio
                                                    ? (selectedTicker?.ticker === ticker.ticker
                                                        ? 'bg-gradient-to-r from-green-100 to-emerald-100 border-2 border-blue-500'
                                                        : 'bg-gradient-to-r from-green-50 to-emerald-50 hover:from-green-100 hover:to-emerald-100 border-2 border-green-200')
                                                    : ticker.is_favorite
                                                        ? (selectedTicker?.ticker === ticker.ticker
                                                            ? 'bg-gradient-to-r from-blue-100 to-cyan-100 border-2 border-blue-500'
                                                            : 'bg-gradient-to-r from-blue-50 to-cyan-50 hover:from-blue-100 hover:to-cyan-100 border-2 border-blue-200')
                                                        : (selectedTicker?.ticker === ticker.ticker
                                                            ? 'bg-blue-50 border-2 border-blue-500'
                                                            : 'bg-gray-50 hover:bg-gray-100 border-2 border-transparent')
                                                }`}
                                        >
                                            <div className="flex items-center justify-between">
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-1.5">
                                                        <span className={`text-base ${ticker.in_portfolio ? 'font-extrabold text-green-900' : 'font-bold text-gray-900'}`}>
                                                            {ticker.ticker}
                                                        </span>
                                                        {ticker.in_portfolio && (
                                                            <span className="text-xs bg-green-600 text-white px-1.5 py-0.5 rounded-full font-semibold">
                                                                Portfolio
                                                            </span>
                                                        )}
                                                        {ticker.is_favorite && (
                                                            <span className="text-xs bg-blue-600 text-white px-1.5 py-0.5 rounded-full font-semibold">
                                                                Ulubione
                                                            </span>
                                                        )}
                                                    </div>
                                                    <p className="text-xs text-gray-600 truncate">{ticker.company_name || 'Brak nazwy'}</p>
                                                    <p className="text-xs text-gray-500">{ticker.sector || 'Brak sektora'}</p>
                                                </div>
                                                <div className="flex flex-col items-center gap-2 ml-2">
                                                    <button onClick={handleScrape} disabled={scrapingTicker === ticker.ticker} className={`text-white px-2 py-1 rounded text-xs ${scrapingTicker === ticker.ticker ? 'bg-gray-400' : 'bg-blue-500'}`}>
                                                        {scrapingTicker === ticker.ticker ? 'Scraping...' : 'Scrape'}
                                                    </button>
                                                    <div className="text-right">
                                                        <div className={`text-base font-bold ${getSentimentColor(ticker.avg_sentiment)}`}>
                                                            {ticker.avg_sentiment > 0 ? '+' : ''}{Number(ticker.avg_sentiment).toFixed(2)}
                                                        </div>
                                                        <div className="text-xs text-gray-500">
                                                            {ticker.mentions} wzm.
                                                        </div>
                                                    </div>
                                                    <div className="flex items-center gap-2">
                                                        <input
                                                            type="checkbox"
                                                            checked={ticker.is_favorite}
                                                            onChange={toggleFavorite}
                                                            className="w-4 h-4 cursor-pointer accent-blue-600"
                                                            title="Dodaj/usuń z ulubionych"
                                                        />
                                                        <input
                                                            type="checkbox"
                                                            checked={ticker.in_portfolio}
                                                            onChange={togglePortfolio}
                                                            className="w-4 h-4 cursor-pointer accent-green-600"
                                                            title="Dodaj/usuń z portfolio"
                                                        />
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    );
                                })}
                            </div>
                        </div>

                        <div className="col-span-9">
                            {!selectedTicker ? (
                                <div className="bg-white rounded-lg shadow p-6 flex items-center justify-center" style={{ minHeight: '300px' }}>
                                    <div className="text-center text-gray-400">
                                        <p className="text-lg">Wybierz ticker z listy po lewej</p>
                                    </div>
                                </div>
                            ) : (
                                <div className="space-y-4">
                                    <div className={`p-3 rounded-lg shadow ${getSentimentBg(selectedTicker.avg_sentiment)}`}>
                                        <div className="flex items-center justify-between">
                                            <div>
                                                <h2 className="text-xl font-bold text-gray-900">
                                                    {selectedTicker.ticker} - {selectedTicker.company_name || 'Brak nazwy'}
                                                </h2>
                                                <p className="text-sm text-gray-600">{selectedTicker.sector || 'Brak sektora'}</p>
                                            </div>
                                            <div className="text-right">
                                                <div className={`text-2xl font-bold ${getSentimentColor(selectedTicker.avg_sentiment)}`}>
                                                    {selectedTicker.avg_sentiment > 0 ? '+' : ''}{Number(selectedTicker.avg_sentiment).toFixed(2)}
                                                </div>
                                                <div className="text-xs text-gray-600">
                                                    Średni sentyment
                                                </div>
                                            </div>
                                        </div>
                                    </div>

                                    {tickerStats && showStats && (
                                        <div className="bg-white rounded-lg shadow p-4">
                                            <div className="flex items-center justify-between mb-3">
                                                <h3 className="text-base font-semibold text-gray-900">Statystyki</h3>
                                                <button
                                                    onClick={() => setShowStats(false)}
                                                    className="text-gray-400 hover:text-gray-600 text-sm"
                                                >
                                                    ✕
                                                </button>
                                            </div>
                                            <div className="grid grid-cols-3 gap-3">
                                                <div className="bg-gray-50 p-3 rounded-lg">
                                                    <div className="text-xl font-bold text-gray-900">{tickerStats.totalNews}</div>
                                                    <div className="text-xs text-gray-600">Wszystkie</div>
                                                </div>
                                                <div className="bg-green-50 p-3 rounded-lg">
                                                    <div className="text-xl font-bold text-green-600">{tickerStats.positiveNews}</div>
                                                    <div className="text-xs text-gray-600">Pozytywne</div>
                                                </div>
                                                <div className="bg-red-50 p-3 rounded-lg">
                                                    <div className="text-xl font-bold text-red-600">{tickerStats.negativeNews}</div>
                                                    <div className="text-xs text-gray-600">Negatywne</div>
                                                </div>
                                                <div className="bg-gray-50 p-3 rounded-lg">
                                                    <div className="text-xl font-bold text-gray-600">{tickerStats.neutralNews}</div>
                                                    <div className="text-xs text-gray-600">Neutralne</div>
                                                </div>
                                                <div className="bg-blue-50 p-3 rounded-lg">
                                                    <div className={`text-xl font-bold ${getSentimentColor(tickerStats.avgImpact)}`}>
                                                        {tickerStats.avgImpact > 0 ? '+' : ''}{tickerStats.avgImpact.toFixed(3)}
                                                    </div>
                                                    <div className="text-xs text-gray-600">Śr. impact</div>
                                                </div>
                                                <div className="bg-purple-50 p-3 rounded-lg">
                                                    <div className="text-xl font-bold text-purple-600">
                                                        {(tickerStats.avgConfidence * 100).toFixed(0)}%
                                                    </div>
                                                    <div className="text-xs text-gray-600">Śr. pewność</div>
                                                </div>
                                            </div>
                                        </div>
                                    )}

                                    {loadingChart ? (
                                        <div className="bg-white rounded-lg shadow-lg p-6 flex items-center justify-center">
                                            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                                        </div>
                                    ) : (
                                        <PriceChart
                                            ticker={selectedTicker.ticker}
                                            priceHistory={priceHistory}
                                            brokerageAnalyses={brokerageAnalyses}
                                            analyses={filteredAnalyses}
                                        />
                                    )}

                                    {/* Analiza Techniczna */}
                                    <TechnicalAnalysis ticker={selectedTicker.ticker} />

                                    {loading ? (
                                        <div className="bg-white rounded-lg shadow-lg p-6 flex items-center justify-center py-12">
                                            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                                        </div>
                                    ) : (
                                        <div className="bg-white rounded-lg shadow p-4">
                                            <div className="space-y-4">
                                                <div>
                                                    <div className="flex items-center justify-between mb-2">
                                                        <h3 className="text-base font-semibold text-gray-900">
                                                            Analizy newsowe ({filteredAnalyses.length})
                                                        </h3>
                                                        <div className="flex items-center gap-2">
                                                            <label className="text-xs text-gray-600">Filtruj:</label>
                                                            <select
                                                                value={filterImpact}
                                                                onChange={(e) => setFilterImpact(e.target.value)}
                                                                className="px-2 py-1 text-xs border border-gray-300 rounded-lg"
                                                            >
                                                                <option value="all">Wszystkie</option>
                                                                <option value="positive">Pozytywne</option>
                                                                <option value="negative">Negatywne</option>
                                                                <option value="neutral">Neutralne</option>
                                                            </select>
                                                        </div>
                                                    </div>
                                                    {filteredAnalyses.length === 0 ? (
                                                        <p className="text-gray-500 text-xs">Brak analiz newsowych</p>
                                                    ) : (
                                                        <div className="space-y-2">
                                                            {filteredAnalyses.map((analysis, idx) => (
                                                                <div
                                                                    key={idx}
                                                                    className="border border-gray-200 rounded-lg p-3 hover:shadow-md transition-shadow relative"
                                                                >
                                                                    <button
                                                                        onClick={() => markAsDuplicate(analysis.news_id)}
                                                                        className="absolute top-1.5 right-1.5 w-6 h-6 flex items-center justify-center bg-red-500 hover:bg-red-600 text-white rounded-full text-sm font-bold transition-colors"
                                                                        title="Oznacz jako duplikat"
                                                                    >
                                                                        ✕
                                                                    </button>

                                                                    <div className="flex items-start gap-3">
                                                                        <div className="flex-shrink-0">
                                                                            <div className={`w-2 h-16 ${getImpactColor(analysis.impact)} rounded`}></div>
                                                                        </div>

                                                                        <div className="flex-1 pr-8">
                                                                            <div className="flex items-start justify-between mb-1.5">
                                                                                <div className="flex-1">
                                                                                    <h3 className="font-semibold text-sm text-gray-900 mb-0.5">
                                                                                        {analysis.title}
                                                                                    </h3>
                                                                                    <div className="flex items-center gap-2 text-xs text-gray-500">
                                                                                        <span>{analysis.date}</span>
                                                                                        <span>•</span>
                                                                                        <span>{analysis.source}</span>
                                                                                        {analysis.url && (
                                                                                            <>
                                                                                                <span>•</span>
                                                                                                <a
                                                                                                    href={analysis.url}
                                                                                                    target="_blank"
                                                                                                    rel="noopener noreferrer"
                                                                                                    className="text-blue-600 hover:underline"
                                                                                                >
                                                                                                    Link
                                                                                                </a>
                                                                                            </>
                                                                                        )}
                                                                                    </div>
                                                                                </div>
                                                                            </div>

                                                                            <div className="flex items-center gap-3 mb-2">
                                                                                <div className="flex items-center gap-1.5">
                                                                                    <span className="text-xs text-gray-600">Impact:</span>
                                                                                    <span className={`font-bold text-sm ${getSentimentColor(analysis.impact)}`}>
                                                                                        {analysis.impact > 0 ? '+' : ''}{Number(analysis.impact).toFixed(2)}
                                                                                    </span>
                                                                                </div>
                                                                                <div className="flex items-center gap-1.5">
                                                                                    <span className="text-xs text-gray-600">Confidence:</span>
                                                                                    <span className="font-bold text-sm text-blue-600">
                                                                                        {(Number(analysis.confidence) * 100).toFixed(0)}%
                                                                                    </span>
                                                                                </div>
                                                                                {analysis.occasion && (
                                                                                    <div className="flex items-center gap-1.5">
                                                                                        <span className="px-2 py-0.5 bg-blue-100 text-blue-700 text-xs rounded-full">
                                                                                            {analysis.occasion}
                                                                                        </span>
                                                                                    </div>
                                                                                )}
                                                                            </div>

                                                                            {analysis.summary && (
                                                                                <div
                                                                                    className="text-xs text-gray-700 leading-relaxed"
                                                                                    dangerouslySetInnerHTML={{ __html: analysis.summary }}
                                                                                />
                                                                            )}
                                                                        </div>
                                                                    </div>
                                                                </div>
                                                            ))}
                                                        </div>
                                                    )}
                                                </div>

                                                {brokerageAnalyses.length > 0 && (
                                                    <div className="mt-4 pt-4 border-t border-gray-200">
                                                        <h3 className="text-base font-semibold text-gray-900 mb-2">
                                                            Rekomendacje domów maklerskich ({brokerageAnalyses.length})
                                                        </h3>
                                                        <div className="overflow-x-auto">
                                                            <table className="min-w-full divide-y divide-gray-200">
                                                                <thead className="bg-gray-50">
                                                                    <tr>
                                                                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                                                                            Data
                                                                        </th>
                                                                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                                                                            Dom maklerski
                                                                        </th>
                                                                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                                                                            Rekomendacja
                                                                        </th>
                                                                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                                                                            Cena obecna
                                                                        </th>
                                                                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                                                                            Cena docelowa
                                                                        </th>
                                                                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                                                                            Zmiana %
                                                                        </th>
                                                                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 uppercase">
                                                                            Upside %
                                                                        </th>
                                                                    </tr>
                                                                </thead>
                                                                <tbody className="bg-white divide-y divide-gray-200">
                                                                    {brokerageAnalyses.map((brokerage, idx) => (
                                                                        <tr key={idx} className={getUpsideBg(brokerage.upside_percent)}>
                                                                            <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-700">
                                                                                {brokerage.date}
                                                                            </td>
                                                                            <td className="px-3 py-2 text-xs text-gray-900 font-medium">
                                                                                {brokerage.brokerage_house}
                                                                            </td>
                                                                            <td className={`px-3 py-2 whitespace-nowrap text-xs ${getRecommendationColor(brokerage.recommendation)}`}>
                                                                                {brokerage.recommendation || '-'}
                                                                            </td>
                                                                            <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-900 font-semibold">
                                                                                {brokerage.current_price
                                                                                    ? `${brokerage.current_price.toFixed(2)}`
                                                                                    : (brokerage.price_old ? brokerage.price_old.toFixed(2) : '-')}
                                                                            </td>
                                                                            <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-900 font-semibold">
                                                                                {brokerage.price_new ? brokerage.price_new.toFixed(2) : '-'}
                                                                            </td>
                                                                            <td className={`px-3 py-2 whitespace-nowrap text-xs ${getUpsideColor(brokerage.price_change_percent)}`}>
                                                                                {brokerage.price_change_percent !== null
                                                                                    ? `${brokerage.price_change_percent > 0 ? '+' : ''}${brokerage.price_change_percent.toFixed(1)}%`
                                                                                    : '-'}
                                                                            </td>
                                                                            <td className={`px-3 py-2 whitespace-nowrap text-xs ${getUpsideColor(brokerage.upside_percent)}`}>
                                                                                {brokerage.upside_percent !== null
                                                                                    ? `${brokerage.upside_percent > 0 ? '+' : ''}${brokerage.upside_percent.toFixed(1)}%`
                                                                                    : '-'}
                                                                            </td>
                                                                        </tr>
                                                                    ))}
                                                                </tbody>
                                                            </table>
                                                        </div>
                                                    </div>
                                                )}
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}

export default TickerDashboard;

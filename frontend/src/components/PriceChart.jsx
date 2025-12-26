import React, { useState, useEffect, useRef, useMemo } from 'react';
import { createChart, ColorType } from 'lightweight-charts';
import { useTheme } from '../context/ThemeContext';

export default function PriceChart({ ticker, priceHistory, brokerageAnalyses, analyses, onNewsClick, showNews: propShowNews = true, onToggleNews, showVolume: propShowVolume = false, onToggleVolume, showTransactions: propShowTransactions = true, onToggleTransactions }) {
    const { theme } = useTheme();
    const chartContainerRef = useRef(null);
    const chartRef = useRef(null);
    const mainSeriesRef = useRef(null);
    const [chartType, setChartType] = useState('candlestick');
    const [showVolume, setShowVolume] = useState(propShowVolume);
    const [showNews, setShowNews] = useState(propShowNews);
    const [showTransactions, setShowTransactions] = useState(propShowTransactions);
    const [transactions, setTransactions] = useState([]);

    // Grupowanie transakcji według dnia i typu (kupno/sprzedaż)
    const groupedTransactions = useMemo(() => {
        const groups = {};
        transactions.forEach(t => {
            const date = t.transaction_date;
            const type = String(t.transaction_type).toLowerCase();
            const key = `${date}_${type}`;
            
            if (!groups[key]) {
                groups[key] = {
                    transaction_date: date,
                    transaction_type: type,
                    total_quantity: 0,
                    total_value: 0,
                    transactions: []
                };
            }
            
            const quantity = Number(t.quantity) || 0;
            const price = Number(t.price) || 0;
            
            groups[key].total_quantity += quantity;
            groups[key].total_value += quantity * price;
            groups[key].transactions.push(t);
        });

        return Object.values(groups).map(group => ({
            ...group,
            average_price: group.total_value / group.total_quantity,
            display_quantity: group.total_quantity,
            display_price: group.total_value / group.total_quantity
        }));
    }, [transactions]);

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
    }, [ticker]);

    useEffect(() => {
        if (!chartContainerRef.current || !priceHistory || priceHistory.length === 0) return;

        const isDark = theme === 'dark';
        chartContainerRef.current.innerHTML = ''; // Clear container

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: isDark ? '#1f2937' : 'white' },
                textColor: isDark ? '#f3f4f6' : '#1f2937',
            },
            width: chartContainerRef.current.clientWidth,
            height: 400,
            grid: {
                vertLines: { color: isDark ? '#374151' : '#f0f0f0' },
                horzLines: { color: isDark ? '#374151' : '#f0f0f0' },
            },
            rightPriceScale: {
                borderColor: isDark ? '#4b5563' : '#d1d4dc',
                scaleMargins: {
                    top: 0.1,
                    bottom: showVolume ? 0.08 : 0.02,
                },
            },
            timeScale: {
                borderColor: isDark ? '#4b5563' : '#d1d4dc',
            },
        });
        chartRef.current = chart;

        if (showVolume) {
            const volumeSeries = chart.addHistogramSeries({
                color: isDark ? '#26a69a88' : '#26a69a',
                priceFormat: { type: 'volume' },
                priceScaleId: '',
                scaleMargins: { top: 0.92, bottom: 0 },
            });

            const volumeData = priceHistory.map(d => ({
                time: d.date,
                value: d.volume,
                color: (d.close >= d.open) ? '#26a69a' : '#ef5350',
            }));
            volumeSeries.setData(volumeData);
        }

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
                open: d.open ?? d.price,
                high: d.high ?? d.price,
                low: d.low ?? d.price,
                close: d.close ?? d.price,
            }));
            mainSeries.setData(candleData);
        } else {
            mainSeries = chart.addLineSeries({ color: isDark ? '#3b82f6' : '#2962FF', lineWidth: 2 });
            const lineData = priceHistory.map(d => ({ time: d.date, value: d.close ?? d.price }));
            mainSeries.setData(lineData);
        }

        // keep reference to main series so we can update markers without full chart recreation
        mainSeriesRef.current = mainSeries;

        if (showNews && analyses && analyses.length > 0) {
            const markers = [];
            analyses.forEach(news => {
                let color = isDark ? '#9ca3af' : '#9ca3af';
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
        } else {
            try { mainSeries.setMarkers([]); } catch (e) { /* ignore if series not ready */ }
        }

        const latestBrokerage = brokerageAnalyses?.find(b => b.price_new);
        if (latestBrokerage && latestBrokerage.price_new) {
            const priceLine = {
                price: latestBrokerage.price_new,
                color: '#10b981',
                lineWidth: 2,
                lineStyle: 2,
                axisLabelVisible: true,
                title: 'Cel',
            };
            mainSeries.createPriceLine(priceLine);
        }

        chart.timeScale().fitContent();

        const overlay = document.createElement('div');
        overlay.style.position = 'absolute';
        overlay.style.left = '0';
        overlay.style.top = '0';
        overlay.style.right = '0';
        overlay.style.bottom = '0';
        overlay.style.pointerEvents = 'none';
        overlay.style.zIndex = '10';
        chartContainerRef.current.style.position = 'relative';
        chartContainerRef.current.appendChild(overlay);

        const renderTransactions = () => {
            if (!overlay) return;
            overlay.innerHTML = '';
            if (!showTransactions || !groupedTransactions || groupedTransactions.length === 0) return;

            const markerSize = 12;

            groupedTransactions.forEach(t => {
                const time = t.transaction_date;
                const price = t.display_price;
                if (!time || !price) return;

                let x = null, y = null;

                try {
                    const timeCoord = chart.timeScale().timeToCoordinate(time);
                    const priceCoord = mainSeries.priceToCoordinate(price);

                    if (timeCoord !== null && priceCoord !== null) {
                        x = timeCoord;
                        y = priceCoord;
                    }
                } catch (e) {
                    console.debug('Failed to map transaction coordinates:', e);
                }

                if (x === null || y === null || isNaN(x) || isNaN(y)) {
                    console.debug('Skipping transaction - invalid coordinates:', { time, price, x, y });
                    return;
                }

                const el = document.createElement('div');
                const isBuy = String(t.transaction_type).toLowerCase() === 'buy';
                const qty = t.display_quantity;
                const avgPrice = t.display_price;

                el.title = `${isBuy ? 'KUPNO' : 'SPRZEDAŻ'}: ${qty} szt. (średnia: ${avgPrice.toFixed(2)} PLN)`;
                el.style.position = 'absolute';
                el.style.left = `${x}px`;
                el.style.top = `${y}px`;
                el.style.transform = 'translate(-50%, -50%)';
                el.style.width = `${markerSize}px`;
                el.style.height = `${markerSize}px`;
                el.style.borderRadius = '50%';
                el.style.background = isBuy ? '#10b981' : '#ef4444';
                el.style.boxShadow = isDark ? `0 0 0 2px rgba(31,41,55,0.9), 0 2px 6px rgba(0,0,0,0.5)` : `0 0 0 2px rgba(255,255,255,0.9), 0 2px 6px rgba(0,0,0,0.3)`;
                el.style.pointerEvents = 'auto';
                el.style.cursor = 'pointer';
                el.style.transition = 'transform 0.2s ease';
                el.style.zIndex = '100';

                el.addEventListener('mouseenter', () => {
                    el.style.transform = 'translate(-50%, -50%) scale(1.5)';
                    el.style.zIndex = '101';
                });

                el.addEventListener('mouseleave', () => {
                    el.style.transform = 'translate(-50%, -50%) scale(1)';
                    el.style.zIndex = '100';
                });

                overlay.appendChild(el);
            });
        };
        renderTransactions();

        const handleResize = () => {
            if (chartContainerRef.current && chartRef.current) {
                chartRef.current.applyOptions({ width: chartContainerRef.current.clientWidth });
                renderTransactions();
            }
        };

        window.addEventListener('resize', handleResize);

        let unsubVisible = null;
        try {
            unsubVisible = chart.timeScale().subscribeVisibleTimeRangeChange(() => {
                requestAnimationFrame(renderTransactions);
            });
        } catch (e) {
            console.debug('Could not subscribe to visible range changes:', e);
        }

            return () => {
            window.removeEventListener('resize', handleResize);
            if (unsubVisible && typeof unsubVisible === 'function') {
                try {
                    unsubVisible();
                } catch (e) {
                    console.debug('Error unsubscribing:', e);
                }
            }
            if (overlay && overlay.parentNode) {
                overlay.parentNode.removeChild(overlay);
            }
            try {
                if (chartRef.current && typeof chartRef.current.remove === 'function') {
                    chartRef.current.remove();
                }
            } catch (e) {
                console.debug('Error removing chart (already disposed?):', e);
            }
            chartRef.current = null;
            mainSeriesRef.current = null;
        };
    }, [priceHistory, chartType, showVolume, showNews, showTransactions, analyses, brokerageAnalyses, transactions, theme]);

    // update markers on the existing main series when user toggles showNews (so toggle is immediate)
    useEffect(() => {
        const series = mainSeriesRef.current;
        const chart = chartRef.current;
        if (!series) return;

        if (showNews && analyses && analyses.length > 0) {
            try {
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
                series.setMarkers(markers);
                // ensure timeScale updates so markers become visible
                try { chart?.timeScale()?.fitContent?.(); } catch (e) { /* ignore */ }
            } catch (e) {
                console.debug('Failed to set markers on series:', e);
            }
        } else {
            try { series.setMarkers([]); } catch (e) { /* ignore */ }
            try { chart?.timeScale()?.fitContent?.(); } catch (e) { /* ignore */ }
        }
    }, [showNews, analyses]);


    if (!priceHistory || priceHistory.length === 0) {
        return (
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 mb-6">
                <div className="text-center text-gray-500 dark:text-gray-400 py-8">
                    <p>Brak danych o cenach dla {ticker}</p>
                </div>
            </div>
        );
    }

    const latestPrice = priceHistory[priceHistory.length - 1]?.price ?? priceHistory[priceHistory.length - 1]?.close;
    const firstPrice = priceHistory[0]?.price ?? priceHistory[0]?.close;
    const priceChange = latestPrice && firstPrice ? ((latestPrice - firstPrice) / firstPrice * 100) : 0;
    const latestBrokerage = brokerageAnalyses?.find(b => b.price_new);

    // Calculate profit/loss summary for transactions
    const calculateProfitLoss = () => {
        if (!transactions.length || !latestPrice) return null;
        
        let totalBuyQuantity = 0;
        let totalBuyCost = 0;
        let totalSellQuantity = 0;
        let totalSellRevenue = 0;
        
        transactions.forEach(t => {
            const qty = Number(t.quantity) || 0;
            const price = Number(t.price) || 0;
            const isBuy = String(t.transaction_type).toLowerCase() === 'buy';
            
            if (isBuy) {
                totalBuyQuantity += qty;
                totalBuyCost += qty * price;
            } else {
                totalSellQuantity += qty;
                totalSellRevenue += qty * price;
            }
        });
        
        const netQuantity = totalBuyQuantity - totalSellQuantity;
        const averageBuyPrice = totalBuyQuantity > 0 ? totalBuyCost / totalBuyQuantity : 0;
        
        // Realized P/L from sold shares
        const realizedPL = totalSellRevenue - (totalSellQuantity * averageBuyPrice);
        
        // Unrealized P/L from remaining shares
        const unrealizedPL = netQuantity * (latestPrice - averageBuyPrice);
        
        // Total P/L
        const totalPL = realizedPL + unrealizedPL;
        
        return {
            netQuantity,
            averageBuyPrice,
            realizedPL,
            unrealizedPL,
            totalPL,
            totalBuyCost,
            totalSellRevenue
        };
    };
    
    const profitLossData = calculateProfitLoss();

    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6">
            <div className="flex items-center justify-between mb-4">
                <div>
                    <h3 className="text-xl font-bold text-gray-900 dark:text-white">Wykres kursu {ticker}</h3>
                    <p className="text-sm text-gray-600 dark:text-gray-400">Ostatnie {priceHistory.length} dni</p>
                </div>
                <div className="text-right">
                    <div className="text-2xl font-bold text-gray-900 dark:text-white">
                        {latestPrice?.toFixed(2)} PLN
                    </div>
                    <div className={`text-sm font-semibold ${priceChange >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                        {priceChange >= 0 ? '+' : ''}{priceChange.toFixed(2)}%
                    </div>
                </div>
            </div>

            <div className="flex gap-2 mb-2 justify-end text-xs">
               <button 
                   onClick={() => setChartType('candlestick')} 
                   className={`px-3 py-1 rounded transition-colors ${chartType==='candlestick' ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-bold' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'}`}
               >
                   Świece
               </button>
               <button 
                   onClick={() => setChartType('line')} 
                   className={`px-3 py-1 rounded transition-colors ${chartType==='line' ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 font-bold' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'}`}
               >
                   Linia
               </button>
               <label className="flex items-center gap-1 cursor-pointer bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded hover:bg-gray-200 dark:hover:bg-gray-600 ml-2 transition-colors">
                   <input 
                       type="checkbox" 
                       checked={showVolume} 
                       onChange={(e) => { const v = e.target.checked; setShowVolume(v); try { onToggleVolume && onToggleVolume(v); } catch (err) {} }} 
                       className="cursor-pointer w-3 h-3 accent-blue-600"
                   />
                   <span className="text-gray-600 dark:text-gray-400 font-medium">Wolumen</span>
               </label>
               <label className="flex items-center gap-1 cursor-pointer bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded hover:bg-gray-200 dark:hover:bg-gray-600 ml-2 transition-colors">
                   <input 
                       type="checkbox" 
                       checked={showNews} 
                       onChange={(e) => { const v = e.target.checked; setShowNews(v); try { onToggleNews && onToggleNews(v); } catch (err) {} }} 
                       className="cursor-pointer w-3 h-3 accent-blue-600"
                   />
                   <span className="text-gray-600 dark:text-gray-400 font-medium">Newsy</span>
               </label>
               <label className="flex items-center gap-1 cursor-pointer bg-gray-100 dark:bg-gray-700 px-2 py-1 rounded hover:bg-gray-200 dark:hover:bg-gray-600 ml-2 transition-colors">
                   <input
                       type="checkbox"
                       checked={showTransactions}
                       onChange={(e) => { const v = e.target.checked; setShowTransactions(v); try { onToggleTransactions && onToggleTransactions(v); } catch (err) {} }}
                       className="cursor-pointer w-3 h-3 accent-blue-600"
                   />
                   <span className="text-gray-600 dark:text-gray-400 font-medium">Transakcje</span>
               </label>
            </div>

            <div ref={chartContainerRef} key={`chart-${theme}`} className="w-full h-[400px]" />

            {groupedTransactions.length > 0 && (
                <div className="mt-3 p-3 bg-gray-50 dark:bg-gray-900/50 rounded-lg border border-gray-200 dark:border-gray-700">
                    <div className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                        Transakcje na wykresie: {groupedTransactions.length} (zgrupowane)
                    </div>
                    <div className="grid grid-cols-2 gap-2 max-h-32 overflow-y-auto">
                        {groupedTransactions.map((t, index) => {
                            const isBuy = t.transaction_type === 'buy';
                            const qty = t.display_quantity;
                            const avgPrice = t.display_price;
                            
                            return (
                                <div key={`group_${t.transaction_date}_${t.transaction_type}_${index}`} className={`p-2 rounded text-xs ${
                                    isBuy
                                        ? 'bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800'
                                        : 'bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800'
                                }`}>
                                    <div className={`font-bold ${isBuy ? 'text-green-700 dark:text-green-400' : 'text-red-700 dark:text-red-400'}`}>
                                        {isBuy ? 'KUPNO' : 'SPRZEDAŻ'} {qty} szt.
                                    </div>
                                    <div className="text-gray-600 dark:text-gray-400">
                                        {t.transaction_date}
                                    </div>
                                    <div className="text-gray-800 dark:text-gray-200 font-semibold">
                                        {avgPrice.toFixed(2)} PLN
                                    </div>
                                    <div className="text-xs text-gray-500 dark:text-gray-500 mt-1">
                                        (średnia z {t.transactions.length} trans.)
                                    </div>
                                </div>
                            );
                        })}
                    </div>
                </div>
            )}

            {profitLossData && (
                <div className="mt-3 p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800">
                    <div className="text-sm font-semibold text-gray-700 dark:text-gray-300 mb-2">
                        Strata/Zysk dla {ticker}
                    </div>
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                        <div className="p-2 bg-white dark:bg-gray-800 rounded border dark:border-gray-700">
                            <div className="text-xs text-gray-500 dark:text-gray-400">Pozostało</div>
                            <div className="text-lg font-bold text-gray-800 dark:text-gray-100">
                                {profitLossData.netQuantity} szt.
                            </div>
                        </div>
                        <div className="p-2 bg-white dark:bg-gray-800 rounded border dark:border-gray-700">
                            <div className="text-xs text-gray-500 dark:text-gray-400">Średnia cena zakupu</div>
                            <div className="text-lg font-bold text-gray-800 dark:text-gray-100">
                                {profitLossData.averageBuyPrice.toFixed(2)} PLN
                            </div>
                        </div>
                        <div className="p-2 bg-white dark:bg-gray-800 rounded border dark:border-gray-700">
                            <div className="text-xs text-gray-500 dark:text-gray-400">Zrealizowany P/L</div>
                            <div className={`text-lg font-bold ${profitLossData.realizedPL >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                                {profitLossData.realizedPL.toFixed(2)} PLN
                            </div>
                        </div>
                        <div className="p-2 bg-white dark:bg-gray-800 rounded border dark:border-gray-700">
                            <div className="text-xs text-gray-500 dark:text-gray-400">Niezrealizowany P/L</div>
                            <div className={`text-lg font-bold ${profitLossData.unrealizedPL >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                                {profitLossData.unrealizedPL.toFixed(2)} PLN
                            </div>
                        </div>
                        <div className="p-2 bg-white dark:bg-gray-800 rounded border dark:border-gray-700">
                            <div className="text-xs text-gray-500 dark:text-gray-400">Całkowity P/L</div>
                            <div className={`text-lg font-bold ${profitLossData.totalPL >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
                                {profitLossData.totalPL.toFixed(2)} PLN
                            </div>
                        </div>
                    </div>
                    <div className="mt-2 text-xs text-gray-600 dark:text-gray-400">
                        Obliczono na podstawie {transactions.length} transakcji i aktualnej ceny {latestPrice?.toFixed(2)} PLN
                    </div>
                </div>
            )}

            <div className="mt-4 flex items-center gap-4 text-xs text-gray-600 dark:text-gray-400">
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
                <div className="mt-4 p-3 bg-green-50 dark:bg-green-900/20 rounded-lg">
                    <div className="flex items-center justify-between text-sm">
                        <span className="text-gray-700 dark:text-gray-300">
                            Cena docelowa wg <strong>{latestBrokerage.brokerage_house}</strong>:
                        </span>
                        <div className="flex items-center gap-4">
                            <span className="font-bold text-green-700 dark:text-green-400">
                                {latestBrokerage.price_new?.toFixed(2)} PLN
                            </span>
                            {latestBrokerage.upside_percent !== null && (
                                <span className={`font-semibold ${latestBrokerage.upside_percent >= 0 ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'}`}>
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

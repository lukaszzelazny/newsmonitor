import React, { useState, useEffect, useRef } from 'react';

// Komponent wykresu Canvas z punktami dla newsów
function PriceChart({ ticker, priceHistory, brokerageAnalyses, analyses, onNewsClick }) {
    const canvasRef = useRef(null);
    const [hoveredNews, setHoveredNews] = useState(null);

    useEffect(() => {
        if (!canvasRef.current || !priceHistory || priceHistory.length === 0) return;

        const canvas = canvasRef.current;
        const ctx = canvas.getContext('2d');
        const width = canvas.width;
        const height = canvas.height;

        ctx.clearRect(0, 0, width, height);

        const prices = priceHistory.map(p => p.price);
        const minPrice = Math.min(...prices);
        const maxPrice = Math.max(...prices);
        const priceRange = maxPrice - minPrice;

        const margin = { top: 20, right: 80, bottom: 40, left: 60 };
        const chartWidth = width - margin.left - margin.right;
        const chartHeight = height - margin.top - margin.bottom;

        // Funkcja do konwersji daty na pozycję X
        const dateToX = (dateStr) => {
            const targetDate = new Date(dateStr);
            const firstDate = new Date(priceHistory[0].date);
            const lastDate = new Date(priceHistory[priceHistory.length - 1].date);
            const totalRange = lastDate - firstDate;
            const datePos = targetDate - firstDate;
            return margin.left + (datePos / totalRange) * chartWidth;
        };

        // Osie
        ctx.strokeStyle = '#e5e7eb';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(margin.left, margin.top);
        ctx.lineTo(margin.left, height - margin.bottom);
        ctx.lineTo(width - margin.right, height - margin.bottom);
        ctx.stroke();

        // Siatka i etykiety Y
        ctx.fillStyle = '#6b7280';
        ctx.font = '12px sans-serif';
        const ySteps = 5;
        for (let i = 0; i <= ySteps; i++) {
            const y = margin.top + (chartHeight / ySteps) * i;
            const price = maxPrice - (priceRange / ySteps) * i;

            ctx.strokeStyle = '#f3f4f6';
            ctx.beginPath();
            ctx.moveTo(margin.left, y);
            ctx.lineTo(width - margin.right, y);
            ctx.stroke();

            ctx.fillStyle = '#6b7280';
            ctx.textAlign = 'right';
            ctx.fillText(price.toFixed(2), margin.left - 10, y + 4);
        }

        // Wykres
        ctx.strokeStyle = '#3b82f6';
        ctx.lineWidth = 2;
        ctx.beginPath();

        priceHistory.forEach((item, i) => {
            const x = margin.left + (chartWidth / (priceHistory.length - 1)) * i;
            const y = margin.top + chartHeight - ((item.price - minPrice) / priceRange) * chartHeight;

            if (i === 0) {
                ctx.moveTo(x, y);
            } else {
                ctx.lineTo(x, y);
            }
        });

        ctx.stroke();

        // Etykiety X
        ctx.fillStyle = '#6b7280';
        ctx.textAlign = 'center';
        const xSteps = Math.min(7, priceHistory.length);
        const xInterval = Math.floor(priceHistory.length / xSteps);

        for (let i = 0; i < priceHistory.length; i += xInterval) {
            const x = margin.left + (chartWidth / (priceHistory.length - 1)) * i;
            const date = new Date(priceHistory[i].date);
            const label = `${date.getDate()}/${date.getMonth() + 1}`;
            ctx.fillText(label, x, height - margin.bottom + 20);
        }

        // Rysowanie punktów dla newsów
        if (analyses && analyses.length > 0) {
            analyses.forEach((analysis) => {
                const x = dateToX(analysis.date);

                // Znajdź najbliższą cenę dla tej daty
                const analysisDate = new Date(analysis.date);
                const closestPrice = priceHistory.reduce((prev, curr) => {
                    const prevDiff = Math.abs(new Date(prev.date) - analysisDate);
                    const currDiff = Math.abs(new Date(curr.date) - analysisDate);
                    return currDiff < prevDiff ? curr : prev;
                });

                const y = margin.top + chartHeight - ((closestPrice.price - minPrice) / priceRange) * chartHeight;

                // Kolor punktu bazowany na impact
                let color;
                const impact = analysis.impact;
                if (Math.abs(impact) < 0.05) color = '#9ca3af'; // gray
                else if (impact > 0.5) color = '#059669'; // dark green
                else if (impact > 0.2) color = '#10b981'; // green
                else if (impact > 0.05) color = '#4ade80'; // light green
                else if (impact > -0.2) color = '#fb923c'; // light orange
                else if (impact > -0.5) color = '#f97316'; // orange
                else color = '#dc2626'; // red

                // Rysuj punkt
                ctx.fillStyle = color;
                ctx.beginPath();
                ctx.arc(x, y, 6, 0, 2 * Math.PI);
                ctx.fill();

                // Obramowanie
                ctx.strokeStyle = '#ffffff';
                ctx.lineWidth = 2;
                ctx.stroke();

                // Podświetlenie hoverowanego newsa
                if (hoveredNews && hoveredNews.date === analysis.date && hoveredNews.title === analysis.title) {
                    ctx.strokeStyle = '#000000';
                    ctx.lineWidth = 3;
                    ctx.beginPath();
                    ctx.arc(x, y, 8, 0, 2 * Math.PI);
                    ctx.stroke();
                }
            });
        }

        // Linia ceny docelowej
        const latestBrokerage = brokerageAnalyses?.find(b => b.price_new);
        if (latestBrokerage && latestBrokerage.price_new) {
            const targetPrice = latestBrokerage.price_new;
            const y = margin.top + chartHeight - ((targetPrice - minPrice) / priceRange) * chartHeight;

            ctx.strokeStyle = '#10b981';
            ctx.lineWidth = 2;
            ctx.setLineDash([5, 5]);
            ctx.beginPath();
            ctx.moveTo(margin.left, y);
            ctx.lineTo(width - margin.right, y);
            ctx.stroke();
            ctx.setLineDash([]);

            ctx.fillStyle = '#10b981';
            ctx.font = 'bold 12px sans-serif';
            ctx.textAlign = 'left';
            ctx.fillText(`Cel: ${targetPrice.toFixed(2)}`, width - margin.right + 5, y + 4);
        }

    }, [priceHistory, brokerageAnalyses, analyses, hoveredNews]);

    const handleCanvasClick = (e) => {
        if (!canvasRef.current || !analyses) return;

        const rect = canvasRef.current.getBoundingClientRect();
        const x = e.clientX - rect.left;
        const y = e.clientY - rect.top;

        // Sprawdź czy kliknięto w któryś punkt
        const clickRadius = 10;
        for (const analysis of analyses) {
            // Tutaj potrzebujemy odtworzyć pozycję punktu
            // (uproszczone - w produkcji lepiej przechowywać pozycje)
            if (onNewsClick) {
                onNewsClick(analysis);
                break;
            }
        }
    };

    if (!priceHistory || priceHistory.length === 0) {
        return (
            <div className="bg-white rounded-lg shadow-lg p-6 mb-6">
                <div className="text-center text-gray-500 py-8">
                    <p>Brak danych o cenach dla {ticker}</p>
                </div>
            </div>
        );
    }

    const latestPrice = priceHistory[priceHistory.length - 1]?.price;
    const firstPrice = priceHistory[0]?.price;
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

            <canvas
                ref={canvasRef}
                width={900}
                height={250}
                className="w-full cursor-pointer"
                style={{ maxWidth: '100%', height: 'auto' }}
                onClick={handleCanvasClick}
            />

            <div className="mt-4 flex items-center gap-4 text-xs text-gray-600">
                <span className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full bg-green-500"></span>
                    {'Pozytywny (impact > 0.3)'}
                </span>
                <span className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full bg-lime-500"></span>
                    Lekko pozytywny
                </span>
                <span className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full bg-gray-400"></span>
                    Neutralny
                </span>
                <span className="flex items-center gap-2">
                    <span className="w-3 h-3 rounded-full bg-orange-500"></span>
                    Lekko negatywny
                </span>
                <span className="flex items-center gap-2">
                  <span className="w-3 h-3 rounded-full bg-red-500"></span>
                  {'Negatywny (impact < -0.3)'}
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
function TickerSelect({ analysisId, onSave }) {
    const [allTickers, setAllTickers] = useState([]);
    const [selectedTickers, setSelectedTickers] = useState([]);
    const [isLoading, setIsLoading] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');

    useEffect(() => {
        fetch('/api/all_tickers')
            .then(res => res.json())
            .then(data => setAllTickers(data))
            .catch(err => console.error("Error fetching all tickers:", err));
    }, []);

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

    useEffect(() => {
        fetchCalendarStats();
    }, [days]);

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

            if (!response.ok) {
                // Revert on failure
                setNewsForDate(originalNews);
                if (showNotification) showNotification('Błąd przy oznaczaniu newsa jako duplikat', 'error');
            } else {
                if (showNotification) showNotification('News oznaczony jako duplikat', 'success');
                fetchCalendarStats(); // Refresh calendar colors
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
            if (count > 5) return 'bg-green-500';
            if (count > 2) return 'bg-green-400';
            return 'bg-green-300';
        } else if (avgImpact < -0.1) {
            if (count > 5) return 'bg-red-500';
            if (count > 2) return 'bg-red-400';
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
                                <div className="font-bold text-sm text-gray-800">
                                    {date.getDate()}
                                </div>
                                {stats && stats.news_count > 0 && (
                                    <div className="text-xs font-bold text-gray-700 mt-1">
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
                                return (
                                    <button
                                        key={ticker}
                                        onClick={() => handleTickerFilterClick(ticker)}
                                        className={`px-3 py-1 text-xs font-bold rounded-full transition-all duration-200 ${isActive
                                                ? 'bg-blue-600 text-white shadow'
                                                : 'bg-gray-200 text-gray-800 hover:bg-gray-300'
                                            }`}
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
                                            <h4 className="font-semibold text-sm text-gray-900 mb-2">
                                                {news.title}
                                            </h4>

                                            <div className="flex items-center gap-2 text-xs text-gray-500 mb-2">
                                                <span>{news.source}</span>
                                                {news.url && (
                                                    <>
                                                        <span>•</span>
                                                        <a
                                                            href={news.url}
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className="text-blue-600 hover:underline"
                                                        >
                                                            Link
                                                        </a>
                                                    </>
                                                )}
                                            </div>

                                            <div className="mb-2 p-2 bg-red-100 rounded border border-red-300">
                                                <div className="text-xs font-semibold text-red-900 mb-1">Powód odrzucenia:</div>
                                                <div className="text-xs text-red-800">{news.reason}</div>
                                                <div className="text-xs text-red-600 mt-1">
                                                    Score: {(news.relevance_score * 100).toFixed(1)}%
                                                </div>
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
                                            className={`flex-shrink-0 px-4 py-2 rounded-lg font-semibold text-sm transition-colors w-28 text-center ${reanalyzing[news.news_id]
                                                    ? 'bg-gray-300 text-gray-600 cursor-not-allowed'
                                                    : reanalysisStatus[news.news_id] === 'success'
                                                        ? 'bg-green-500 text-white'
                                                        : reanalysisStatus[news.news_id] === 'error'
                                                            ? 'bg-red-500 text-white'
                                                            : 'bg-blue-500 hover:bg-blue-600 text-white'
                                                }`}
                                        >
                                            {reanalyzing[news.news_id]
                                                ? 'Analizowanie...'
                                                : reanalysisStatus[news.news_id] === 'success'
                                                    ? 'Przeanalizowano'
                                                    : reanalysisStatus[news.news_id] === 'error'
                                                        ? 'Błąd'
                                                        : 'Analizuj AI'}
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
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [timeRange, setTimeRange] = useState('ALL');
    const [hoveredPoint, setHoveredPoint] = useState(null);
    const [mousePos, setMousePos] = useState({ x: 0, y: 0 });
    const canvasRef = useRef(null);

    const fmt = (n, digits = 2) => (n === null || n === undefined ? '-' : Number(n).toFixed(digits));

    useEffect(() => {
        const fetchData = async () => {
            setLoading(true);
            setError(null);
            try {
                const [ovrRes, roiRes] = await Promise.all([
                    fetch('/api/portfolio/overview'),
                    fetch('/api/portfolio/roi')
                ]);
                const ovr = await ovrRes.json();
                const roi = await roiRes.json();
                setOverview(ovr);
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
    }, [days]); // `days` wpływa na inne rzeczy w dashboardzie, ale ROI pobieramy raz i filtrujemy lokalnie

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
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        const width = canvas.width;
        const height = canvas.height;
        ctx.clearRect(0, 0, width, height);

        if (!roiSeries || roiSeries.length === 0) {
            // axes only
            ctx.strokeStyle = '#e5e7eb';
            ctx.beginPath();
            ctx.moveTo(60, 20);
            ctx.lineTo(60, height - 40);
            ctx.lineTo(width - 20, height - 40);
            ctx.stroke();
            return;
        }

        const margin = { top: 20, right: 20, bottom: 40, left: 60 };
        const chartW = width - margin.left - margin.right;
        const chartH = height - margin.top - margin.bottom;

        const values = roiSeries.map(p => Number(p.rate_of_return) || 0);
        const minV = Math.min(...values);
        const maxV = Math.max(...values);
        const range = (maxV - minV) || 1;

        // axes
        ctx.strokeStyle = '#e5e7eb';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(margin.left, margin.top);
        ctx.lineTo(margin.left, height - margin.bottom);
        ctx.lineTo(width - margin.right, height - margin.bottom);
        ctx.stroke();

        // grid + y labels
        ctx.fillStyle = '#6b7280';
        ctx.font = '12px sans-serif';
        const ySteps = 5;
        for (let i = 0; i <= ySteps; i++) {
            const y = margin.top + (chartH / ySteps) * i;
            const val = maxV - (range / ySteps) * i;
            ctx.strokeStyle = '#f3f4f6';
            ctx.beginPath();
            ctx.moveTo(margin.left, y);
            ctx.lineTo(width - margin.right, y);
            ctx.stroke();

            ctx.fillStyle = '#6b7280';
            ctx.textAlign = 'right';
            ctx.fillText(`${val.toFixed(1)}%`, margin.left - 10, y + 4);
        }

        // ROI line
        ctx.strokeStyle = '#0ea5e9';
        ctx.lineWidth = 2;
        ctx.beginPath();
        const denom = Math.max(1, roiSeries.length - 1);
        roiSeries.forEach((pt, i) => {
            const x = margin.left + (chartW / denom) * i;
            const y = margin.top + chartH - ((Number(pt.rate_of_return) - minV) / range) * chartH;
            if (i === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        });
        ctx.stroke();
        
        // Punkty na wykresie - tylko hover
        if (hoveredPoint) {
             const x = margin.left + (chartW / denom) * roiSeries.findIndex(p => p.date === hoveredPoint.date);
             const y = margin.top + chartH - ((Number(hoveredPoint.rate_of_return) - minV) / range) * chartH;
             
             ctx.fillStyle = '#0ea5e9';
             ctx.beginPath();
             ctx.arc(x, y, 5, 0, 2 * Math.PI);
             ctx.fill();
             ctx.strokeStyle = '#fff';
             ctx.lineWidth = 2;
             ctx.stroke();
        }

        // x labels - denser (roughly weekly if daily data)
        ctx.fillStyle = '#6b7280';
        ctx.textAlign = 'center';
        ctx.font = '10px sans-serif';
        
        // Calculate step to show labels roughly every 50-60px
        const labelWidth = 50; 
        const maxLabels = Math.floor(chartW / labelWidth);
        const step = Math.max(1, Math.floor(roiSeries.length / maxLabels));

        for (let i = 0; i < roiSeries.length; i += step) {
            const x = margin.left + (chartW / denom) * i;
            const d = new Date(roiSeries[i]?.date);
            
            // Obrot etykiet jesli gesto
            ctx.save();
            ctx.translate(x, height - margin.bottom + 25);
            ctx.rotate(-Math.PI / 4);
            ctx.textAlign = 'right';
            const label = d.toISOString().split('T')[0]; // YYYY-MM-DD
            ctx.fillText(label, 0, 0);
            ctx.restore();
        }
    }, [roiSeries, hoveredPoint]);

    const handleMouseMove = (e) => {
        const canvas = canvasRef.current;
        if (!canvas || roiSeries.length === 0) return;
        const rect = canvas.getBoundingClientRect();
        const mouseX = e.clientX - rect.left;
        const mouseY = e.clientY - rect.top;
        
        const width = canvas.width;
        const height = canvas.height;
        const margin = { top: 20, right: 20, bottom: 40, left: 60 };
        const chartW = width - margin.left - margin.right;
        const denom = Math.max(1, roiSeries.length - 1);

        // Znajdź najbliższy punkt na osi X
        let closestDist = Infinity;
        let closestPoint = null;
        let closestX = 0;
        let closestY = 0;
        
        const values = roiSeries.map(p => Number(p.rate_of_return) || 0);
        const minV = Math.min(...values);
        const maxV = Math.max(...values);
        const range = (maxV - minV) || 1;
        const chartH = height - margin.top - margin.bottom;

        roiSeries.forEach((pt, i) => {
            const x = margin.left + (chartW / denom) * i;
            const dist = Math.abs(mouseX - x);
            if (dist < closestDist) {
                closestDist = dist;
                closestPoint = pt;
                closestX = x;
                closestY = margin.top + chartH - ((Number(pt.rate_of_return) - minV) / range) * chartH;
            }
        });

        // Jeśli kursor jest wystarczająco blisko (np. 20px) w poziomie
        if (closestDist < 20) {
            setHoveredPoint(closestPoint);
            setMousePos({ x: closestX, y: closestY });
        } else {
            setHoveredPoint(null);
        }
    };

    const handleMouseLeave = () => {
        setHoveredPoint(null);
    };

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
                
                <div className="relative">
                    <canvas
                        ref={canvasRef}
                        width={900}
                        height={250}
                        className="w-full cursor-crosshair"
                        style={{ maxWidth: '100%', height: 'auto' }}
                        onMouseMove={handleMouseMove}
                        onMouseLeave={handleMouseLeave}
                    />
                    {hoveredPoint && (
                        <div
                            className="absolute bg-black bg-opacity-80 text-white text-xs p-2 rounded pointer-events-none z-10"
                            style={{
                                left: mousePos.x + 10,
                                top: mousePos.y - 40,
                                transform: 'translateX(-50%)'
                            }}
                        >
                            <div className="font-bold">{hoveredPoint.date}</div>
                            <div>ROI: {hoveredPoint.rate_of_return.toFixed(2)}%</div>
                            <div>Value: {hoveredPoint.market_value.toFixed(0)} PLN</div>
                        </div>
                    )}
                </div>
            </div>

            {(overview.gainers?.length || overview.decliners?.length) ? (
                <div className="grid grid-cols-2 gap-4">
                    <div className="bg-white rounded-lg shadow p-4">
                        <h4 className="text-sm font-semibold text-gray-900 mb-2">Najwięksi zwycięzcy (dzień/dzień)</h4>
                        <div className="space-y-1">
                            {(overview.gainers || []).map((g, idx) => (
                                <div key={idx} className="flex items-center justify-between text-sm">
                                    <span className="font-mono text-gray-800">{g.ticker}</span>
                                    <span className="font-semibold text-green-600">+{fmt(g.pct, 2)}%</span>
                                </div>
                            ))}
                        </div>
                    </div>
                    <div className="bg-white rounded-lg shadow p-4">
                        <h4 className="text-sm font-semibold text-gray-900 mb-2">Najwięksi przegrani (dzień/dzień)</h4>
                        <div className="space-y-1">
                            {(overview.decliners || []).map((d, idx) => (
                                <div key={idx} className="flex items-center justify-between text-sm">
                                    <span className="font-mono text-gray-800">{d.ticker}</span>
                                    <span className="font-semibold text-red-600">{fmt(d.pct, 2)}%</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            ) : null}
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

import React, { useState, useEffect } from 'react';
import TickerSelect from './TickerSelect';
import { useTheme } from '../context/ThemeContext';

export default function CalendarView({ days, onBack, onTickerSelect, showNotification }) {
    const { theme } = useTheme();
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
                fetchCalendarStats();
            } else {
                setNewsForDate(originalNews);
                if (showNotification) showNotification('Błąd przy oznaczaniu newsa jako duplikat', 'error');
            }
        } catch (error) {
            console.error('Error marking as duplicate:', error);
            setNewsForDate(originalNews);
            if (showNotification) showNotification('Błąd połączenia z serwerem', 'error');
        }
    };

    const getDayStats = (dateStr) => {
        return calendarStats.find(s => s.date === dateStr);
    };

    const getDayColor = (stats) => {
        const isDark = theme === 'dark';
        if (!stats || stats.news_count === 0) return isDark ? 'bg-gray-800' : 'bg-gray-50';

        const avgImpact = stats.avg_impact;
        const count = stats.news_count;

        if (avgImpact > 0.1) {
            if (count > 5) return 'bg-green-600 text-white';
            if (count > 2) return 'bg-green-500 text-white';
            return isDark ? 'bg-green-700/50 text-green-100' : 'bg-green-300';
        } else if (avgImpact < -0.1) {
            if (count > 5) return 'bg-red-600 text-white';
            if (count > 2) return 'bg-red-500 text-white';
            return isDark ? 'bg-red-700/50 text-red-100' : 'bg-red-300';
        } else {
            if (count > 5) return isDark ? 'bg-yellow-600 text-white' : 'bg-yellow-500 text-white';
            if (count > 2) return isDark ? 'bg-yellow-700/50 text-yellow-100' : 'bg-yellow-400';
            return isDark ? 'bg-yellow-800/30 text-yellow-200' : 'bg-yellow-300';
        }
    };

    const getImpactColor = (impact) => {
        const val = Math.abs(impact);
        if (val < 0.05) return 'bg-gray-400 dark:bg-gray-600';
        if (impact > 0.5) return 'bg-green-600 dark:bg-green-500';
        if (impact > 0.2) return 'bg-green-500 dark:bg-green-400';
        if (impact > 0.05) return 'bg-green-400 dark:bg-green-300';
        if (impact > -0.05) return 'bg-gray-400 dark:bg-gray-600';
        if (impact > -0.2) return 'bg-orange-400 dark:bg-orange-300';
        if (impact > -0.5) return 'bg-orange-500 dark:bg-orange-400';
        return 'bg-red-600 dark:bg-red-500';
    };

    const getSentimentColor = (sentiment) => {
        const val = Math.abs(sentiment);
        if (val < 0.05) return 'text-gray-500 dark:text-gray-400';
        if (sentiment > 0.3) return 'text-green-600 dark:text-green-400';
        if (sentiment > 0) return 'text-green-400 dark:text-green-300';
        if (sentiment > -0.3) return 'text-yellow-500 dark:text-yellow-400';
        return 'text-red-500 dark:text-red-400';
    };

    const getSentimentBg = (sentiment) => {
        const val = Math.abs(sentiment);
        if (val < 0.05) return 'bg-gray-100 dark:bg-gray-800';
        if (sentiment > 0.3) return 'bg-green-100 dark:bg-green-900/30';
        if (sentiment > 0) return 'bg-green-50 dark:bg-green-900/10';
        if (sentiment > -0.3) return 'bg-yellow-50 dark:bg-yellow-900/10';
        return 'bg-red-50 dark:bg-red-900/10';
    };

    const generateCalendarDays = () => {
        const year = currentMonth.getFullYear();
        const month = currentMonth.getMonth();

        const firstDay = new Date(year, month, 1);
        const lastDay = new Date(year, month + 1, 0);

        const daysInMonth = lastDay.getDate();
        const startDayOfWeek = (firstDay.getDay() + 6) % 7;

        const daysArr = [];

        for (let i = 0; i < startDayOfWeek; i++) {
            daysArr.push(null);
        }

        for (let day = 1; day <= daysInMonth; day++) {
            daysArr.push(new Date(year, month, day));
        }

        return daysArr;
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
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                        {monthNames[currentMonth.getMonth()]} {currentMonth.getFullYear()}
                    </h2>
                    <div className="flex items-center gap-2">
                        <button
                            onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1))}
                            className="px-3 py-1 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 rounded-lg dark:text-gray-200 transition-colors"
                        >
                            ←
                        </button>
                        <button
                            onClick={() => setCurrentMonth(new Date())}
                            className="px-3 py-1 bg-blue-500 hover:bg-blue-600 text-white rounded-lg text-sm transition-colors"
                        >
                            Dziś
                        </button>
                        <button
                            onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1))}
                            className="px-3 py-1 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 rounded-lg dark:text-gray-200 transition-colors"
                        >
                            →
                        </button>
                    </div>
                </div>

                <div className="mb-4 flex items-center gap-4 text-xs text-gray-600 dark:text-gray-400 flex-wrap border-b dark:border-gray-700 pb-4">
                    <span className="flex items-center gap-2">
                        <span className="w-4 h-4 rounded bg-green-500"></span>
                        Pozytywne (wiele newsów)
                    </span>
                    <span className="flex items-center gap-2">
                        <span className="w-4 h-4 rounded bg-green-300 dark:bg-green-700/50"></span>
                        Pozytywne (kilka)
                    </span>
                    <span className="flex items-center gap-2">
                        <span className="w-4 h-4 rounded bg-yellow-400"></span>
                        Mieszane/Neutralne
                    </span>
                    <span className="flex items-center gap-2">
                        <span className="w-4 h-4 rounded bg-red-300 dark:bg-red-700/50"></span>
                        Negatywne (kilka)
                    </span>
                    <span className="flex items-center gap-2">
                        <span className="w-4 h-4 rounded bg-red-500"></span>
                        Negatywne (wiele)
                    </span>
                </div>

                <div className="grid grid-cols-7 gap-2">
                    {['Pn', 'Wt', 'Śr', 'Cz', 'Pt', 'Sb', 'Nd'].map(day => (
                        <div key={day} className="text-center font-bold text-sm text-gray-600 dark:text-gray-400 py-2">
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
                                <div className={`font-bold text-sm ${stats && (stats.news_count > 5 || Math.abs(stats.avg_impact) > 0.1) ? 'text-white' : 'text-gray-800 dark:text-gray-200'}`}>
                                    {date.getDate()}
                                </div>
                                {stats && stats.news_count > 0 && (
                                    <div className={`text-xs font-bold mt-1 ${stats && (stats.news_count > 5 || Math.abs(stats.avg_impact) > 0.1) ? 'text-white' : 'text-gray-700 dark:text-gray-400'}`}>
                                        {stats.news_count} news
                                    </div>
                                )}
                            </button>
                        );
                    })}
                </div>
            </div>

            {selectedDate && (
                <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
                    <h3 className="text-lg font-bold text-gray-900 dark:text-white mb-3">
                        Newsy z {selectedDate} ({filteredNews.length})
                    </h3>

                    {(dayTickers.length > 0 || hasUnassignedNews) && (
                        <div className="flex items-center gap-2 mb-4 flex-wrap p-2 bg-gray-50 dark:bg-gray-900/50 rounded-lg">
                            <span className="text-sm font-semibold text-gray-700 dark:text-gray-300">Filtruj:</span>
                            <div className="flex items-center gap-1">
                                <button onClick={selectAllDayTickers} className="px-2 py-0.5 text-xs bg-gray-600 dark:bg-gray-700 text-white rounded hover:bg-gray-700 dark:hover:bg-gray-600 transition-colors">Wszystkie</button>
                                <button onClick={deselectAllDayTickers} className="px-2 py-0.5 text-xs bg-gray-600 dark:bg-gray-700 text-white rounded hover:bg-gray-700 dark:hover:bg-gray-600 transition-colors">Żadne</button>
                            </div>
                            <div className="border-l border-gray-300 dark:border-gray-700 h-5 mx-1"></div>
                            {dayTickers.map(ticker => {
                                const isActive = activeTickerFilters.includes(ticker);
                                const impact = dayTickerStats[ticker] || 0;
                                let bgClass = '';
                                
                                if (impact > 0.2) {
                                    bgClass = isActive 
                                        ? 'bg-green-600 text-white shadow-md hover:bg-green-700' 
                                        : 'bg-green-100 dark:bg-green-900/20 text-green-800 dark:text-green-400 hover:bg-green-200 dark:hover:bg-green-900/40 border border-green-300 dark:border-green-800';
                                } else if (impact < -0.2) {
                                    bgClass = isActive 
                                        ? 'bg-red-600 text-white shadow-md hover:bg-red-700' 
                                        : 'bg-red-100 dark:bg-red-900/20 text-red-800 dark:text-red-400 hover:bg-red-200 dark:hover:bg-red-900/40 border border-red-300 dark:border-red-800';
                                } else {
                                    bgClass = isActive 
                                        ? 'bg-gray-600 text-white shadow-md hover:bg-gray-700' 
                                        : 'bg-gray-100 dark:bg-gray-800 text-gray-800 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-700 border border-gray-300 dark:border-gray-700';
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
                                            : 'bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-300 hover:bg-gray-300 dark:hover:bg-gray-600'
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
                        <p className="text-gray-500 dark:text-gray-400 text-center py-8">Brak newsów spełniających kryteria</p>
                    ) : (
                        <div className="space-y-3">
                            {filteredNews.map((news, idx) => (
                                <div key={idx} className="border border-gray-200 dark:border-gray-700 rounded-lg p-4 hover:shadow-md transition-shadow relative bg-white dark:bg-gray-800">
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
                                                <h4 className="font-semibold text-sm text-gray-900 dark:text-white">{news.title}</h4>
                                            </div>
                                            
                                            <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 mb-2">
                                                <span>{news.source}</span>
                                                <span>•</span>
                                                <span>{news.published_at || news.date}</span>
                                                {news.url && (
                                                    <><span>•</span><a href={news.url} target="_blank" rel="noopener noreferrer" className="text-blue-600 dark:text-blue-400 hover:underline">Link</a></>
                                                )}
                                            </div>

                                            {news.tickers && news.tickers.length > 0 ? (
                                                <div className="flex flex-wrap gap-1 mb-2">
                                                    {news.tickers.map((t, i) => (
                                                        <button
                                                            key={i}
                                                            onClick={() => onTickerSelect && onTickerSelect(t.ticker)}
                                                            className="px-2 py-0.5 rounded text-xs font-bold cursor-pointer hover:opacity-80 transition-opacity bg-blue-100 dark:bg-blue-900/30 text-blue-800 dark:text-blue-300 border border-blue-200 dark:border-blue-800"
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
                                                    <span className="text-xs text-gray-600 dark:text-gray-400">Impact:</span>
                                                    <span className={`font-bold text-sm ${getSentimentColor(news.impact)}`}>
                                                        {news.impact > 0 ? '+' : ''}{Number(news.impact).toFixed(2)}
                                                    </span>
                                                </div>
                                                <div className="flex items-center gap-1.5">
                                                    <span className="text-xs text-gray-600 dark:text-gray-400">Confidence:</span>
                                                    <span className="font-bold text-sm text-blue-600 dark:text-blue-400">
                                                        {(Number(news.confidence) * 100).toFixed(0)}%
                                                    </span>
                                                </div>
                                            </div>

                                            {news.summary && (
                                                <div className="text-xs text-gray-700 dark:text-gray-300 leading-relaxed" dangerouslySetInnerHTML={{ __html: news.summary }} />
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

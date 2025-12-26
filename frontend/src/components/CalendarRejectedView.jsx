import React, { useState, useEffect } from 'react';
import { useTheme } from '../context/ThemeContext';

export default function CalendarRejectedView({ days }) {
    const { theme } = useTheme();
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
        const isDark = theme === 'dark';
        if (!stats || stats.news_count === 0) return isDark ? 'bg-gray-800' : 'bg-gray-50';
        const count = stats.news_count;
        if (count > 10) return 'bg-red-600 text-white';
        if (count > 5) return 'bg-red-500 text-white';
        if (count > 2) return isDark ? 'bg-red-700/50 text-red-100' : 'bg-red-300';
        return isDark ? 'bg-red-900/30 text-red-200' : 'bg-red-100';
    };

    const generateCalendarDays = () => {
        const year = currentMonth.getFullYear();
        const month = currentMonth.getMonth();
        const firstDay = new Date(year, month, 1);
        const lastDay = new Date(year, month + 1, 0);
        const daysInMonth = lastDay.getDate();
        const startDayOfWeek = (firstDay.getDay() + 6) % 7; 
        const daysArr = [];
        for (let i = 0; i < startDayOfWeek; i++) daysArr.push(null);
        for (let day = 1; day <= daysInMonth; day++) daysArr.push(new Date(year, month, day));
        return daysArr;
    };

    const calendarDays = generateCalendarDays();
    const monthNames = ['Styczeń', 'Luty', 'Marzec', 'Kwiecień', 'Maj', 'Czerwiec',
        'Lipiec', 'Sierpień', 'Wrzesień', 'Październik', 'Listopad', 'Grudzień'];

    return (
        <div className="space-y-4">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                        Odrzucone Newsy: {monthNames[currentMonth.getMonth()]} {currentMonth.getFullYear()}
                    </h2>
                    <div className="flex items-center gap-2">
                        <button onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() - 1))} className="px-3 py-1 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 rounded-lg dark:text-gray-200 transition-colors">←</button>
                        <button onClick={() => setCurrentMonth(new Date())} className="px-3 py-1 bg-blue-500 hover:bg-blue-600 text-white rounded-lg text-sm transition-colors">Dziś</button>
                        <button onClick={() => setCurrentMonth(new Date(currentMonth.getFullYear(), currentMonth.getMonth() + 1))} className="px-3 py-1 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 rounded-lg dark:text-gray-200 transition-colors">→</button>
                    </div>
                </div>

                <div className="grid grid-cols-7 gap-2">
                    {['Pn', 'Wt', 'Śr', 'Cz', 'Pt', 'Sb', 'Nd'].map(day => (
                        <div key={day} className="text-center font-bold text-sm text-gray-600 dark:text-gray-400 py-2">{day}</div>
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
                                <div className={`font-bold text-sm ${stats && stats.news_count > 5 ? 'text-white' : 'text-gray-800 dark:text-gray-200'}`}>
                                    {date.getDate()}
                                </div>
                                {stats && stats.news_count > 0 && (
                                    <div className={`text-xs font-bold mt-1 ${stats.news_count > 5 ? 'text-white' : 'text-gray-700 dark:text-gray-400'}`}>
                                        {stats.news_count}
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
                        Odrzucone z {selectedDate} ({newsForDate.length})
                    </h3>
                    {loading ? (
                        <div className="flex items-center justify-center py-12">
                            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-red-500"></div>
                        </div>
                    ) : newsForDate.length === 0 ? (
                        <p className="text-gray-500 dark:text-gray-400 text-center py-8">Brak odrzuconych newsów z tego dnia</p>
                    ) : (
                        <div className="space-y-3">
                            {newsForDate.map((news, idx) => (
                                <div key={idx} className="border border-red-200 dark:border-red-900/50 rounded-lg p-4 hover:shadow-md transition-shadow bg-red-50 dark:bg-red-900/10">
                                    <div className="flex items-start justify-between gap-3">
                                        <div className="flex-1">
                                            <h4 className="font-semibold text-sm text-gray-900 dark:text-white mb-2">{news.title}</h4>
                                            <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400 mb-2">
                                                <span>{news.source}</span>
                                                {news.url && (
                                                    <><span>•</span><a href={news.url} target="_blank" rel="noopener noreferrer" className="text-blue-600 dark:text-blue-400 hover:underline">Link</a></>
                                                )}
                                            </div>
                                            <div className="mb-2 p-2 bg-red-100 dark:bg-red-900/30 rounded border border-red-300 dark:border-red-800">
                                                <div className="text-xs font-semibold text-red-900 dark:text-red-300 mb-1">Powód odrzucenia:</div>
                                                <div className="text-xs text-red-800 dark:text-red-400">{news.reason}</div>
                                                <div className="text-xs text-red-600 dark:text-red-500 mt-1">Score: {(news.relevance_score * 100).toFixed(1)}%</div>
                                            </div>
                                            {news.content && (
                                                <div className="text-xs text-gray-700 dark:text-gray-300 leading-relaxed mb-2">
                                                    {news.content.substring(0, 200)}...
                                                </div>
                                            )}
                                        </div>
                                        <button
                                            onClick={() => reanalyzeNews(news.news_id)}
                                            disabled={reanalyzing[news.news_id] || reanalysisStatus[news.news_id] === 'success'}
                                            className={`flex-shrink-0 px-4 py-2 rounded-lg font-semibold text-sm transition-colors w-28 text-center ${
                                                reanalyzing[news.news_id] ? 'bg-gray-300 dark:bg-gray-700 text-gray-600 dark:text-gray-400 cursor-not-allowed' :
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

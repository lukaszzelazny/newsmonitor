import React, { useState, useEffect, useRef } from 'react';
import PriceChart from './PriceChart';
import TechnicalAnalysis from './TechnicalAnalysis';
import TickerNotes from './TickerNotes';
import AddTickerModal from './AddTickerModal';
import TickerSelect from './TickerSelect';
import CalendarView from './CalendarView';
import CalendarRejectedView from './CalendarRejectedView';
import PortfolioView from './PortfolioView';
import RecommendationsView from './RecommendationsView';
import { useTheme } from '../context/ThemeContext';

const CollapsibleSection = ({ title, children, defaultExpanded = true, count = null }) => {
    const [isExpanded, setIsExpanded] = useState(defaultExpanded);
    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow overflow-hidden mb-4">
            <button 
                onClick={() => setIsExpanded(!isExpanded)}
                className="w-full px-4 py-3 bg-gray-50 dark:bg-gray-700 flex items-center justify-between text-left focus:outline-none hover:bg-gray-100 dark:hover:bg-gray-600 transition-colors"
            >
                <div className="flex items-center gap-2">
                    <span className="font-semibold text-gray-900 dark:text-white">{title}</span>
                    {count !== null && (
                         <span className="text-xs bg-gray-200 dark:bg-gray-600 px-2 py-0.5 rounded-full text-gray-700 dark:text-gray-200">
                             {count}
                         </span>
                    )}
                </div>
                <span className="text-gray-500 dark:text-gray-400 text-sm">
                    {isExpanded ? '▲ Zwiń' : '▼ Rozwiń'}
                </span>
            </button>
            {isExpanded && (
                <div className="p-4 border-t border-gray-200 dark:border-gray-700">
                    {children}
                </div>
            )}
        </div>
    );
};

export default function TickerDashboard() {
    const { theme, toggleTheme } = useTheme();
    const [showAddTickerModal, setShowAddTickerModal] = useState(false);
    const [tickers, setTickers] = useState([]);
    const [selectedTicker, setSelectedTicker] = useState(null);
    const [analyses, setAnalyses] = useState([]);
    const [brokerageAnalyses, setBrokerageAnalyses] = useState([]);
    const [priceHistory, setPriceHistory] = useState([]);
    const [fundamentalData, setFundamentalData] = useState([]);
    const [contracts, setContracts] = useState([]);
    const [loading, setLoading] = useState(false);
    const [loadingContracts, setLoadingContracts] = useState(false);
    const [loadingChart, setLoadingChart] = useState(false);
    const [loadingFundamental, setLoadingFundamental] = useState(false);
    const [loadingPrices, setLoadingPrices] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [listDays, setListDays] = useState(30);
    const [chartDays, setChartDays] = useState(365);
    const [filterImpact, setFilterImpact] = useState('all');
    const [showStats, setShowStats] = useState(true);
    const [showNews, setShowNews] = useState(() => {
        try {
            const v = localStorage.getItem('pricechart_showNews');
            return v === null ? true : v === 'true';
        } catch (e) {
            return true;
        }
    });
    const [showVolume, setShowVolume] = useState(() => {
        try {
            const v = localStorage.getItem('pricechart_showVolume');
            return v === null ? false : v === 'true';
        } catch (e) {
            return false;
        }
    });
    const [showTransactions, setShowTransactions] = useState(() => {
        try {
            const v = localStorage.getItem('pricechart_showTransactions');
            return v === null ? true : v === 'true';
        } catch (e) {
            return true;
        }
    });
    const [showContracts, setShowContracts] = useState(() => {
        try {
            const v = localStorage.getItem('pricechart_showContracts');
            return v === null ? true : v === 'true';
        } catch (e) {
            return true;
        }
    });
    const [viewMode, setViewMode] = useState('tickers'); // 'tickers', 'calendar', 'rejected', 'portfolio', 'recommendations'
    const [scrapingTicker, setScrapingTicker] = useState(null);
    const [notification, setNotification] = useState(null);
    const notificationTimeout = useRef(null);

    const [isEditingDetails, setIsEditingDetails] = useState(false);
    const [savingDetails, setSavingDetails] = useState(false);
    const [editForm, setEditForm] = useState({ company_name: '', sector: '', scrape_url: '' });
    const [scrapeType, setScrapeType] = useState('all');
    const [stopAtExisting, setStopAtExisting] = useState(true);

    useEffect(() => {
        if (editForm.scrape_url && (editForm.scrape_url.includes('pap.pl') || editForm.scrape_url.includes('espi'))) {
            setScrapeType('contracts');
        } else {
            setScrapeType('all');
        }
    }, [editForm.scrape_url]);

    const showNotification = (message, type = 'success') => {
        setNotification({ message, type });

        if (notificationTimeout.current) {
            clearTimeout(notificationTimeout.current);
        }

        notificationTimeout.current = setTimeout(() => {
            setNotification(null);
        }, 5000);
    };

    const handleTickerSelect = (tickerSymbol) => {
        const tickerData = tickers.find(t => t.ticker === tickerSymbol);
        if (tickerData) {
            setSelectedTicker(tickerData);
        } else {
            setSelectedTicker({ ticker: tickerSymbol });
        }
        setViewMode('tickers');
    };

    const handleEditClick = () => {
        setEditForm({
            company_name: selectedTicker.company_name || '',
            sector: selectedTicker.sector || '',
            scrape_url: selectedTicker.scrape_url || ''
        });
        setIsEditingDetails(true);
    };

    const handleSaveDetails = async () => {
        setSavingDetails(true);
        try {
            const res = await fetch(`/api/tickers/${selectedTicker.ticker}/update`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(editForm)
            });
            if (res.ok) {
                try {
                    const response = await fetch(`/api/tickers?days=${listDays}`);
                    const data = await response.json();
                    setTickers(data);
                    const updated = data.find(t => t.ticker === selectedTicker.ticker);
                    if (updated) setSelectedTicker(updated);
                } catch (refreshError) {
                    console.error('Error refreshing tickers:', refreshError);
                }
                
                setIsEditingDetails(false);
                showNotification('Zaktualizowano dane tickera', 'success');
            } else {
                 showNotification('Błąd aktualizacji', 'error');
            }
        } catch (e) {
             console.error(e);
             showNotification('Błąd sieci', 'error');
        } finally {
            setSavingDetails(false);
        }
    };

    const handleUpdatePrices = async () => {
        if (!selectedTicker) return;
        setLoadingPrices(true);
        try {
            const response = await fetch(`/api/tickers/${selectedTicker.ticker}/sync_prices`, {
                method: 'POST'
            });
            const data = await response.json();
            if (response.ok) {
                showNotification(`Zaktualizowano ceny. Pobrano ${data.count} nowych notowań.`, 'success');
                fetchPriceHistory(selectedTicker.ticker);
            } else {
                showNotification(`Błąd aktualizacji cen: ${data.message || 'Nieznany błąd'}`, 'error');
            }
        } catch (error) {
            console.error('Error updating prices:', error);
            showNotification('Błąd sieci podczas aktualizacji cen.', 'error');
        } finally {
            setLoadingPrices(false);
        }
    };

    const handleScrapeSelected = async () => {
        if (!selectedTicker) return;
        
        setScrapingTicker(selectedTicker.ticker);
        const modeText = stopAtExisting ? "(nowe)" : "(wszystkie)";
        showNotification(`Rozpoczynam scraping ${modeText} dla ${selectedTicker.ticker}...`, 'success');

        try {
            const response = await fetch('/api/scrape_ticker', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ticker: selectedTicker.ticker, stop_at_existing: stopAtExisting })
            });
            const data = await response.json();

            if (response.ok) {
                showNotification(`Scraping dla ${selectedTicker.ticker} zakończony! Nowe artykuły: ${data.new_articles}`, 'success');
                fetchAnalyses(selectedTicker.ticker);
            } else {
                showNotification(`Błąd podczas scrapingu ${selectedTicker.ticker}: ${data.error}`, 'error');
            }
        } catch (error) {
            showNotification(`Błąd sieci podczas scrapingu ${selectedTicker.ticker}.`, 'error');
        } finally {
            setScrapingTicker(null);
        }
    };

    const handleFetchFundamental = async () => {
        if (!selectedTicker) return;
        setLoadingFundamental(true);
        try {
            // Step 1: POST to trigger the data fetch from Yahoo Finance and save to DB
            const postResponse = await fetch(`/api/tickers/${selectedTicker.ticker}/fundamental`, {
                method: 'POST'
            });
            const postData = await postResponse.json();

            if (!postResponse.ok) {
                throw new Error(postData.error || 'Failed to fetch and save fundamental data.');
            }

            // Step 2: GET to retrieve the (now updated) data from our DB
            const getResponse = await fetch(`/api/tickers/${selectedTicker.ticker}/fundamental`);
            const getData = await getResponse.json();

            if (getResponse.ok) {
                setFundamentalData(getData);
                showNotification('Pobrano dane fundamentalne.', 'success');
            } else {
                 throw new Error(getData.error || 'Failed to retrieve fundamental data after fetching.');
            }

        } catch (error) {
            console.error('Error with fundamental data:', error);
            showNotification(`Błąd: ${error.message}`, 'error');
        } finally {
            setLoadingFundamental(false);
        }
    };

    const formatLargeNumber = (num) => {
        if (num === null || num === undefined) return '-';
        if (num >= 1_000_000_000) {
            return (num / 1_000_000_000).toFixed(2) + ' mld';
        }
        if (num >= 1_000_000) {
            return (num / 1_000_000).toFixed(2) + ' mln';
        }
        if (num >= 1_000) {
            return (num / 1_000).toFixed(2) + ' tys';
        }
        return num.toString();
    };


    const fetchFundamentalData = async (ticker) => {
        try {
            const response = await fetch(`/api/tickers/${ticker}/fundamental`);
            const data = await response.json();
            setFundamentalData(data);
        } catch (error) {
            console.error('Error fetching fundamental data:', error);
            setFundamentalData([]);
        }
    };

    const fetchContracts = async (ticker) => {
        setLoadingContracts(true);
        try {
            const response = await fetch(`/api/contracts/${ticker}`);
            const data = await response.json();
            setContracts(data);
        } catch (error) {
            console.error('Error fetching contracts:', error);
            setContracts([]);
        } finally {
            setLoadingContracts(false);
        }
    };

    useEffect(() => {
        fetchTickers();
    }, [listDays]);

    useEffect(() => {
        if (selectedTicker) {
            fetchAnalyses(selectedTicker.ticker);
            fetchBrokerageAnalyses(selectedTicker.ticker);
            fetchPriceHistory(selectedTicker.ticker);
            fetchFundamentalData(selectedTicker.ticker);
            fetchContracts(selectedTicker.ticker);
        }
    }, [selectedTicker, chartDays]);

    const fetchTickers = async () => {
        try {
            const response = await fetch(`/api/tickers?days=${listDays}`);
            const data = await response.json();
            setTickers(data);
        } catch (error) {
            console.error('Error fetching tickers:', error);
        }
    };

    const fetchAnalyses = async (ticker) => {
        setLoading(true);
        try {
            const response = await fetch(`/api/analyses/${ticker}?days=${chartDays}`);
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
            const response = await fetch(`/api/brokerage/${ticker}?days=${chartDays}`);
            const data = await response.json();
            setBrokerageAnalyses(data);
        } catch (error) {
            console.error('Error fetching brokerage analyses:', error);
        }
    };

    const fetchPriceHistory = async (ticker) => {
        setLoadingChart(true);
        try {
            const response = await fetch(`/api/price_history/${ticker}?days=${chartDays}`);
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

        const originalContracts = [...contracts];
        const updatedContracts = contracts.filter(c => c.news_id !== newsId);
        setContracts(updatedContracts);

        try {
            const response = await fetch('/api/mark_duplicate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ news_id: newsId })
            });

            if (response.ok) {
                showNotification('Wpis oznaczony jako duplikat.', 'success');
                fetchTickers(); // Odśwież statystyki tickerów
            } else {
                setAnalyses(originalAnalyses); // Revert on failure
                setContracts(originalContracts);
                showNotification('Błąd przy oznaczaniu jako duplikat.', 'error');
            }
        } catch (error) {
            console.error('Error marking as duplicate:', error);
            setAnalyses(originalAnalyses); // Revert on error
            setContracts(originalContracts);
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

    useEffect(() => {
        if (viewMode === 'portfolio') {
            const first = sortedTickers.find(t => t.in_portfolio);
            if (first && (!selectedTicker || selectedTicker.ticker !== first.ticker)) {
                setSelectedTicker(first);
            }
        }
    }, [viewMode, sortedTickers]);

    const filteredAnalyses = analyses.filter(a => {
        if (a.occasion === 'contract') return false; // Hide contracts from this list
        if (filterImpact === 'all') return true;
        if (filterImpact === 'positive') return a.impact > 0.05;
        if (filterImpact === 'negative') return a.impact < -0.05;
        if (filterImpact === 'neutral') return Math.abs(a.impact) <= 0.05;
        return true;
    });

    const chartAnalyses = analyses.filter(a => {
        // Include contracts in chart data
        if (filterImpact === 'all') return true;
        if (filterImpact === 'positive') return a.impact > 0.05;
        if (filterImpact === 'negative') return a.impact < -0.05;
        if (filterImpact === 'neutral') return Math.abs(a.impact) <= 0.05;
        return true;
    });

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

    const getRecommendationColor = (recommendation) => {
        if (!recommendation) return 'text-gray-600 dark:text-gray-400';
        const rec = recommendation.toLowerCase();
        if (rec.includes('kupuj') || rec.includes('buy') || rec.includes('accumulate')) {
            return 'text-green-600 dark:text-green-400 font-bold';
        }
        if (rec.includes('trzymaj') || rec.includes('hold') || rec.includes('neutral')) {
            return 'text-yellow-600 dark:text-yellow-400 font-bold';
        }
        if (rec.includes('sprzedaj') || rec.includes('sell') || rec.includes('reduce')) {
            return 'text-red-600 dark:text-red-400 font-bold';
        }
        return 'text-gray-600 dark:text-gray-400';
    };

    const getUpsideColor = (upside) => {
        if (upside === null || upside === undefined) return 'text-gray-600 dark:text-gray-400';
        if (upside > 30) return 'text-green-700 dark:text-green-400 font-bold';
        if (upside > 15) return 'text-green-600 dark:text-green-500 font-semibold';
        if (upside > 5) return 'text-green-500 dark:text-green-400';
        if (upside > -5) return 'text-gray-600 dark:text-gray-400';
        if (upside > -15) return 'text-red-500 dark:text-red-400';
        if (upside > -30) return 'text-red-600 dark:text-red-500 font-semibold';
        return 'text-red-700 dark:text-red-600 font-bold';
    };

    const getUpsideBg = (upside) => {
        if (upside === null || upside === undefined) return 'bg-gray-50 dark:bg-gray-800';
        if (upside > 20) return 'bg-green-100 dark:bg-green-900/30';
        if (upside > 10) return 'bg-green-50 dark:bg-green-900/10';
        if (upside > -10) return 'bg-gray-50 dark:bg-gray-800';
        if (upside > -20) return 'bg-red-50 dark:bg-red-900/10';
        return 'bg-red-100 dark:bg-red-900/30';
    };

    const getImpactColor = (impact) => {
        const val = Math.abs(impact);
        if (val < 0.05) return 'bg-gray-400 dark:bg-gray-500';
        if (impact > 0.5) return 'bg-green-600 dark:bg-green-500';
        if (impact > 0.2) return 'bg-green-500 dark:bg-green-400';
        if (impact > 0.05) return 'bg-green-400 dark:bg-green-300';
        if (impact > -0.05) return 'bg-gray-400 dark:bg-gray-500';
        if (impact > -0.2) return 'bg-orange-400 dark:bg-orange-300';
        if (impact > -0.5) return 'bg-orange-500 dark:bg-orange-400';
        return 'bg-red-600 dark:bg-red-500';
    };

    const tickerStats = selectedTicker ? {
        totalNews: analyses.length,
        positiveNews: analyses.filter(a => a.impact > 0.05).length,
        negativeNews: analyses.filter(a => a.impact < -0.05).length,
        neutralNews: analyses.filter(a => Math.abs(a.impact) <= 0.05).length,
        avgImpact: analyses.length > 0 ? (analyses.reduce((sum, a) => sum + a.impact, 0) / analyses.length) : 0,
        avgConfidence: analyses.length > 0 ? (analyses.reduce((sum, a) => sum + a.confidence, 0) / analyses.length) : 0
    } : null;

    return (
        <div className="min-h-screen bg-white dark:bg-gray-900 p-4 transition-colors duration-200">
            <div className="max-w-7xl mx-auto">
                    <div className="flex items-center justify-between mb-4">
                        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                            XTB
                        </h1>
                        <div className="flex items-center gap-3">
                            <button
                                onClick={toggleTheme}
                                className="p-2 rounded-lg bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
                                title={theme === 'dark' ? 'Przełącz na jasny motyw' : 'Przełącz na ciemny motyw'}
                            >
                                {theme === 'dark' ? '☀️' : '🌙'}
                            </button>
                            <div className="flex items-center gap-2">
                                <button
                                    onClick={() => setViewMode('tickers')}
                                    className={`px-3 py-1 text-sm rounded-lg transition-colors ${viewMode === 'tickers'
                                        ? 'bg-blue-500 text-white'
                                        : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-600'
                                    }`}
                                >
                                    Widok Tickerów
                                </button>
                                <button
                                    onClick={() => setViewMode('calendar')}
                                    className={`px-3 py-1 text-sm rounded-lg transition-colors ${viewMode === 'calendar'
                                        ? 'bg-blue-500 text-white'
                                        : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-600'
                                    }`}
                                >
                                    Kalendarz Analiz
                                </button>
                                <button
                                    onClick={() => setViewMode('rejected')}
                                    className={`px-3 py-1 text-sm rounded-lg transition-colors ${viewMode === 'rejected'
                                        ? 'bg-red-500 text-white'
                                        : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-600'
                                    }`}
                                >
                                    Odrzucone Newsy
                                </button>
                                <button
                                    onClick={() => setViewMode('portfolio')}
                                    className={`px-3 py-1 text-sm rounded-lg transition-colors ${viewMode === 'portfolio'
                                        ? 'bg-green-600 text-white'
                                        : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-600'
                                    }`}
                                >
                                    Portfolio
                                </button>
                                <button
                                    onClick={() => setViewMode('recommendations')}
                                    className={`px-3 py-1 text-sm rounded-lg transition-colors ${viewMode === 'recommendations'
                                        ? 'bg-purple-600 text-white'
                                        : 'bg-gray-200 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-300 dark:hover:bg-gray-600'
                                    }`}
                                >
                                    Rekomendacje
                                </button>
                            </div>
                            <div className="flex items-center gap-2">
                                <label className="text-xs text-gray-600 dark:text-gray-400">Okres listy:</label>
                                <select
                                    value={listDays}
                                    onChange={(e) => setListDays(Number(e.target.value))}
                                    className="px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
                                >
                                    <option value="30">1 miesiąc</option>
                                    <option value="90">3 miesiące</option>
                                    <option value="180">6 miesięcy</option>
                                    <option value="365">1 rok</option>
                                    <option value="730">2 lata</option>
                                    <option value="1095">3 lata</option>
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
                    <CalendarView days={listDays} onTickerSelect={handleTickerSelect} showNotification={showNotification} />
                ) : viewMode === 'rejected' ? (
                    <CalendarRejectedView days={listDays} />
                ) : viewMode === 'portfolio' ? (
                    <PortfolioView days={listDays} />
                ) : viewMode === 'recommendations' ? (
                    <RecommendationsView days={listDays} onTickerSelect={handleTickerSelect} />
                ) : (
                    <div className="grid grid-cols-12 gap-4">
                        <div className="col-span-3 bg-white dark:bg-gray-800 rounded-lg shadow p-3 sticky top-4 self-start" style={{ maxHeight: 'calc(100vh - 2rem)' }}>
                            <div className="mb-3 flex gap-2">
                                <div className="relative flex-grow">
                                    <input
                                        type="text"
                                        placeholder="Szukaj tickera..."
                                        className="w-full px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 pr-8"
                                        value={searchTerm}
                                        onChange={(e) => setSearchTerm(e.target.value)}
                                    />
                                    {searchTerm && (
                                        <button
                                            onClick={() => setSearchTerm('')}
                                            className="absolute right-2 top-1/2 transform -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300"
                                            title="Wyczyść wyszukiwanie"
                                        >
                                            ✕
                                        </button>
                                    )}
                                </div>
                                <button
                                    onClick={() => setShowAddTickerModal(true)}
                                    className="px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-xl font-bold flex items-center justify-center"
                                    title="Dodaj nowy ticker"
                                >
                                    +
                                </button>
                            </div>

                            <div className="space-y-1.5 overflow-y-auto" style={{ maxHeight: 'calc(100vh - 10rem)' }}>
                                {listForView.map((ticker) => {
                                    const togglePortfolio = async (e) => {
                                        e.stopPropagation();
                                        try {
                                            const response = await fetch('/api/toggle_portfolio', {
                                                method: 'POST',
                                                headers: { 'Content-Type': 'application/json' },
                                                body: JSON.stringify({ ticker: ticker.ticker, in_portfolio: !ticker.in_portfolio })
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
                                                body: JSON.stringify({ ticker: ticker.ticker, is_favorite: !ticker.is_favorite })
                                            });
                                            if (response.ok) {
                                                fetchTickers();
                                            }
                                        } catch (error) {
                                            console.error('Error toggling favorite:', error);
                                        }
                                    };

                                    return (
                                        <div
                                            key={ticker.ticker}
                                            onClick={() => setSelectedTicker(ticker)}
                                            className={`p-2 rounded-lg cursor-pointer transition-all relative ${ticker.in_portfolio
                                                    ? (selectedTicker?.ticker === ticker.ticker
                                                        ? 'bg-gradient-to-r from-green-100 to-emerald-100 dark:from-green-900 dark:to-emerald-900 border-2 border-blue-500'
                                                        : 'bg-gradient-to-r from-green-50 to-emerald-50 dark:from-green-950 dark:to-emerald-950 hover:from-green-100 hover:to-emerald-100 dark:hover:from-green-900 dark:hover:to-emerald-900 border-2 border-green-200 dark:border-green-800')
                                                    : ticker.is_favorite
                                                        ? (selectedTicker?.ticker === ticker.ticker
                                                            ? 'bg-gradient-to-r from-blue-100 to-cyan-100 dark:from-blue-900 dark:to-cyan-900 border-2 border-blue-500'
                                                            : 'bg-gradient-to-r from-blue-50 to-cyan-50 dark:from-blue-950 dark:to-cyan-950 hover:from-blue-100 hover:to-cyan-100 dark:hover:from-blue-900 dark:hover:to-cyan-900 border-2 border-blue-200 dark:border-blue-800')
                                                        : (selectedTicker?.ticker === ticker.ticker
                                                            ? 'bg-blue-50 dark:bg-blue-900 border-2 border-blue-500'
                                                            : 'bg-gray-50 dark:bg-gray-800 hover:bg-gray-100 dark:hover:bg-gray-700 border-2 border-transparent')
                                                }`}
                                        >
                                            <div className="flex items-center justify-between">
                                                <div className="flex-1 min-w-0">
                                                    <div className="flex items-center gap-1.5">
                                                        <span className={`text-base ${ticker.in_portfolio ? 'font-extrabold text-green-900 dark:text-green-300' : 'font-bold text-gray-900 dark:text-gray-100'}`}>
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
                                                    <p className="text-xs text-gray-600 dark:text-gray-400 truncate">{ticker.company_name || 'Brak nazwy'}</p>
                                                    <p className="text-xs text-gray-500 dark:text-gray-500">{ticker.sector || 'Brak sektora'}</p>
                                                </div>
                                                <div className="flex flex-col items-center gap-2 ml-2">
                                                    <div className="text-right">
                                                        <div className={`text-base font-bold ${getSentimentColor(ticker.avg_sentiment)}`}>
                                                            {ticker.avg_sentiment > 0 ? '+' : ''}{Number(ticker.avg_sentiment).toFixed(2)}
                                                        </div>
                                                        <div className="text-xs text-gray-500 dark:text-gray-400">
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
                                <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-6 flex items-center justify-center" style={{ minHeight: '300px' }}>
                                    <div className="text-center text-gray-400">
                                        <p className="text-lg">Wybierz ticker z listy po lewej</p>
                                    </div>
                                </div>
                            ) : (
                                <div className="space-y-4">
                                    <div className={`p-3 rounded-lg shadow ${getSentimentBg(selectedTicker.avg_sentiment)}`}>
                                    <div className="flex items-center justify-between">
                                        <div className="flex-1">
                                            {isEditingDetails ? (
                                                <div className="flex flex-col gap-2 max-w-md">
                                                    <div className="flex gap-2">
                                                        <input 
                                                            type="text" 
                                                            value={editForm.company_name}
                                                            onChange={(e) => setEditForm({...editForm, company_name: e.target.value})}
                                                            placeholder="Nazwa firmy"
                                                            className="px-2 py-1 border rounded text-sm dark:bg-gray-700 dark:text-white dark:border-gray-600"
                                                        />
                                                    </div>
                                                    <div className="flex gap-2">
                                                        <input 
                                                            type="text" 
                                                            value={editForm.sector}
                                                            onChange={(e) => setEditForm({...editForm, sector: e.target.value})}
                                                            placeholder="Sektor"
                                                            className="px-2 py-1 border rounded text-sm dark:bg-gray-700 dark:text-white dark:border-gray-600"
                                                        />
                                                    </div>
                                                    <div className="flex gap-2">
                                                        <input 
                                                            type="text" 
                                                            value={editForm.scrape_url}
                                                            onChange={(e) => setEditForm({...editForm, scrape_url: e.target.value})}
                                                            placeholder="URL do scrapowania (opcjonalnie)"
                                                            className="px-2 py-1 border rounded text-sm dark:bg-gray-700 dark:text-white dark:border-gray-600 w-full"
                                                        />
                                                        <select
                                                            value={scrapeType}
                                                            disabled={true}
                                                            className="px-2 py-1 border rounded text-sm dark:bg-gray-700 dark:text-white dark:border-gray-600 bg-gray-100 dark:bg-gray-600 cursor-not-allowed"
                                                            title="Typ scrapowania (wykrywany automatycznie na podstawie URL)"
                                                        >
                                                            <option value="all">Wszystkie</option>
                                                            <option value="contracts">Umowy</option>
                                                        </select>
                                                    </div>
                                                    <div className="flex gap-2 items-center">
                                                        <input 
                                                            type="checkbox" 
                                                            checked={stopAtExisting} 
                                                            onChange={(e) => setStopAtExisting(e.target.checked)}
                                                            className="w-4 h-4 cursor-pointer accent-blue-600"
                                                            id="stopAtExisting"
                                                        />
                                                        <label htmlFor="stopAtExisting" className="text-xs text-gray-700 dark:text-gray-300 cursor-pointer select-none">
                                                            Zatrzymaj na istniejącym (tylko nowe)
                                                        </label>
                                                    </div>
                                                    <div className="flex gap-2">
                                                        <button 
                                                            onClick={handleSaveDetails} 
                                                            disabled={savingDetails}
                                                            className={`bg-green-600 text-white px-3 py-1 rounded text-sm hover:bg-green-700 ${savingDetails ? 'opacity-50 cursor-not-allowed' : ''}`}
                                                        >
                                                            {savingDetails ? 'Zapisywanie...' : 'Zapisz'}
                                                        </button>
                                                        <button 
                                                            onClick={() => setIsEditingDetails(false)} 
                                                            disabled={savingDetails}
                                                            className="bg-gray-400 text-white px-3 py-1 rounded text-sm hover:bg-gray-500"
                                                        >
                                                            Anuluj
                                                        </button>
                                                    </div>
                                                </div>
                                            ) : (
                                                <div className="group">
                                                    <div className="flex items-center gap-2">
                                                        <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                                                            {selectedTicker.ticker} - {selectedTicker.company_name || 'Brak nazwy'}
                                                        </h2>
                                                        <button 
                                                            onClick={handleEditClick}
                                                            className="opacity-0 group-hover:opacity-100 transition-opacity text-gray-400 hover:text-blue-500"
                                                            title="Edytuj nazwę"
                                                        >
                                                            ✎
                                                        </button>
                                                    </div>
                                                    <p className="text-sm text-gray-600 dark:text-gray-400">{selectedTicker.sector || 'Brak sektora'}</p>
                                                </div>
                                            )}
                                        </div>
                                        <div className="text-right flex flex-col items-end">
                                            <div className={`text-2xl font-bold ${getSentimentColor(selectedTicker.avg_sentiment)}`}>
                                                {selectedTicker.avg_sentiment > 0 ? '+' : ''}{Number(selectedTicker.avg_sentiment).toFixed(2)}
                                            </div>
                                            <div className="text-xs text-gray-600 dark:text-gray-400">
                                                Średni sentyment
                                            </div>
                                            <button 
                                                onClick={handleScrapeSelected}
                                                disabled={scrapingTicker === selectedTicker.ticker}
                                                className={`mt-2 text-white px-3 py-1 rounded text-xs ${scrapingTicker === selectedTicker.ticker ? 'bg-gray-400' : 'bg-blue-600'} hover:bg-blue-700 transition-colors`}
                                            >
                                                {scrapingTicker === selectedTicker.ticker ? 'Scraping...' : 'Scrape'}
                                            </button>
                                        </div>
                                    </div>
                                    </div>

                                    {tickerStats && showStats && (
                                        <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
                                            <div className="flex items-center justify-between mb-3">
                                                <h3 className="text-base font-semibold text-gray-900 dark:text-white">Statystyki</h3>
                                                <button
                                                    onClick={() => setShowStats(false)}
                                                    className="text-gray-400 hover:text-gray-600 text-sm"
                                                >
                                                    ✕
                                                </button>
                                            </div>
                                            <div className="grid grid-cols-3 gap-3">
                                                <div className="bg-gray-50 dark:bg-gray-700 p-3 rounded-lg">
                                                    <div className="text-xl font-bold text-gray-900 dark:text-white">{tickerStats.totalNews}</div>
                                                    <div className="text-xs text-gray-600 dark:text-gray-300">Wszystkie</div>
                                                </div>
                                                <div className="bg-green-50 dark:bg-green-900/20 p-3 rounded-lg">
                                                    <div className="text-xl font-bold text-green-600 dark:text-green-400">{tickerStats.positiveNews}</div>
                                                    <div className="text-xs text-gray-600 dark:text-gray-300">Pozytywne</div>
                                                </div>
                                                <div className="bg-red-50 dark:bg-red-900/20 p-3 rounded-lg">
                                                    <div className="text-xl font-bold text-red-600 dark:text-red-400">{tickerStats.negativeNews}</div>
                                                    <div className="text-xs text-gray-600 dark:text-gray-300">Negatywne</div>
                                                </div>
                                                <div className="bg-gray-50 dark:bg-gray-700 p-3 rounded-lg">
                                                    <div className="text-xl font-bold text-gray-600 dark:text-gray-300">{tickerStats.neutralNews}</div>
                                                    <div className="text-xs text-gray-600 dark:text-gray-300">Neutralne</div>
                                                </div>
                                                <div className="bg-blue-50 dark:bg-blue-900/20 p-3 rounded-lg">
                                                    <div className={`text-xl font-bold ${getSentimentColor(tickerStats.avgImpact)}`}>
                                                        {tickerStats.avgImpact > 0 ? '+' : ''}{tickerStats.avgImpact.toFixed(3)}
                                                    </div>
                                                    <div className="text-xs text-gray-600 dark:text-gray-300">Śr. impact</div>
                                                </div>
                                                <div className="bg-purple-50 dark:bg-purple-900/20 p-3 rounded-lg">
                                                    <div className="text-xl font-bold text-purple-600 dark:text-purple-400">
                                                        {(tickerStats.avgConfidence * 100).toFixed(0)}%
                                                    </div>
                                                    <div className="text-xs text-gray-600 dark:text-gray-300">Śr. pewność</div>
                                                </div>
                                            </div>
                                        </div>
                                    )}

                                    <div className="flex justify-end">
                                        <button 
                                            onClick={handleUpdatePrices} 
                                            className="text-xs bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 text-gray-700 dark:text-gray-200 px-3 py-1 rounded transition-colors flex items-center gap-1"
                                            disabled={loadingPrices}
                                            title="Pobierz najnowsze ceny z Yahoo Finance"
                                        >
                                            {loadingPrices ? '↻ Aktualizowanie...' : '↻ Aktualizuj ceny'}
                                        </button>
                                    </div>

                                    {loadingChart ? (
                                        <div className="bg-white rounded-lg shadow-lg p-6 flex items-center justify-center">
                                            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                                        </div>
                                    ) : (
                                        <PriceChart
                                            ticker={selectedTicker.ticker}
                                            priceHistory={priceHistory}
                                            brokerageAnalyses={brokerageAnalyses}
                                            analyses={chartAnalyses}
                                            showNews={showNews}
                                            onToggleNews={(v) => { setShowNews(v); try { localStorage.setItem('pricechart_showNews', String(v)); } catch (e) {} }}
                                            showContracts={showContracts}
                                            onToggleContracts={(v) => { setShowContracts(v); try { localStorage.setItem('pricechart_showContracts', String(v)); } catch (e) {} }}
                                            showVolume={showVolume}
                                            onToggleVolume={(v) => { setShowVolume(v); try { localStorage.setItem('pricechart_showVolume', String(v)); } catch (e) {} }}
                                            showTransactions={showTransactions}
                                            onToggleTransactions={(v) => { setShowTransactions(v); try { localStorage.setItem('pricechart_showTransactions', String(v)); } catch (e) {} }}
                                            chartDays={chartDays}
                                            onChartDaysChange={setChartDays}
                                        />
                                    )}

                                    <CollapsibleSection title="Notatki" defaultExpanded={false}>
                                        <TickerNotes ticker={selectedTicker.ticker} />
                                    </CollapsibleSection>
                                    
                                    <CollapsibleSection title="Analiza Techniczna" defaultExpanded={false}>
                                        <TechnicalAnalysis ticker={selectedTicker.ticker} />
                                    </CollapsibleSection>

                                    <CollapsibleSection title="Kontrakty" count={contracts.length} defaultExpanded={false}>
                                        <div className="overflow-x-auto">
                                            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                                                <thead className="bg-gray-50 dark:bg-gray-700">
                                                    <tr>
                                                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Data</th>
                                                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Wartość</th>
                                                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Podsumowanie</th>
                                                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Znaczenie</th>
                                                        <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Ryzyka</th>
                                                        <th className="px-3 py-2 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">Akcje</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                                                    {loadingContracts ? (
                                                        <tr>
                                                            <td colSpan="6" className="px-3 py-4 text-center text-sm text-gray-500 dark:text-gray-400">
                                                                Ładowanie kontraktów...
                                                            </td>
                                                        </tr>
                                                    ) : contracts.length === 0 ? (
                                                        <tr>
                                                            <td colSpan="6" className="px-3 py-4 text-center text-sm text-gray-500 dark:text-gray-400">
                                                                Brak wykrytych kontraktów.
                                                            </td>
                                                        </tr>
                                                    ) : (
                                                        contracts.map((contract, idx) => (
                                                            <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                                                                <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-700 dark:text-gray-300 align-top">{contract.date}</td>
                                                                <td className="px-3 py-2 text-xs text-gray-900 dark:text-white font-medium align-top">{contract.contract_value || '-'}</td>
                                                                <td className="px-3 py-2 text-xs text-gray-700 dark:text-gray-300 align-top">{contract.contract_summary}</td>
                                                                <td className="px-3 py-2 text-xs text-gray-700 dark:text-gray-300 align-top">{contract.investment_relevance}</td>
                                                                <td className="px-3 py-2 text-xs text-gray-700 dark:text-gray-300 align-top">
                                                                    <ul className="list-disc list-inside">
                                                                        {contract.key_risks && contract.key_risks.map((risk, rIdx) => (
                                                                            <li key={rIdx}>{risk}</li>
                                                                        ))}
                                                                    </ul>
                                                                </td>
                                                                <td className="px-3 py-2 text-right text-xs font-medium align-top">
                                                                    <button
                                                                        onClick={() => markAsDuplicate(contract.news_id)}
                                                                        className="w-6 h-6 inline-flex items-center justify-center bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 hover:bg-red-200 dark:hover:bg-red-900/50 rounded-full transition-colors font-bold"
                                                                        title="Oznacz jako duplikat / Ukryj"
                                                                    >
                                                                        ✕
                                                                    </button>
                                                                </td>
                                                            </tr>
                                                        ))
                                                    )}
                                                </tbody>
                                            </table>
                                        </div>
                                    </CollapsibleSection>

                                    <CollapsibleSection title="Analiza Fundamentalna" defaultExpanded={false}>
                                        <div className="flex justify-end mb-4">
                                            <button 
                                                onClick={handleFetchFundamental} 
                                                className="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50 text-sm font-medium transition-colors"
                                                disabled={loadingFundamental}
                                            >
                                                {loadingFundamental ? 'Pobieranie...' : 'Pobierz dane fundamentalne'}
                                            </button>
                                        </div>
                                        
                                        <div className="overflow-x-auto">
                                            <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                                                <thead className="bg-gray-50 dark:bg-gray-700">
                                                    <tr>
                                                        <th title="Data publikacji danych" className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-help">Data</th>
                                                        <th title="Zysk na akcję (Earnings Per Share) - część zysku spółki przypadająca na jedną akcję" className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-help">EPS</th>
                                                        <th title="Prognozowany zysk na akcję (Forward Earnings Per Share)" className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-help">EPS (Fwd)</th>
                                                        <th title="Cena do zysku (Price to Earnings) - stosunek ceny akcji do zysku na akcję z ostatnich 12 miesięcy" className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-help">P/E (Trail)</th>
                                                        <th title="Prognozowana cena do zysku (Forward P/E) - stosunek ceny akcji do prognozowanego zysku na akcję" className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-help">P/E (Fwd)</th>
                                                        <th title="Cena do zysku do wzrostu (Price/Earnings to Growth) - P/E podzielone przez roczną stopę wzrostu zysków. <1 może sugerować niedowartościowanie" className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-help">PEG</th>
                                                        <th title="Wzrost przychodów (Revenue Growth) - procentowa zmiana przychodów r/r" className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-help">Rev Growth</th>
                                                        <th title="Wzrost zysków (Earnings Growth) - procentowa zmiana zysków r/r" className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-help">Earn Growth</th>
                                                        <th title="Przychody (Revenue) - całkowita kwota ze sprzedaży" className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-help">Revenue</th>
                                                        <th title="Kapitalizacja rynkowa (Market Cap) - całkowita wartość rynkowa wszystkich akcji spółki" className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-help">Market Cap</th>
                                                        <th title="Zysk przed odsetkami, opodatkowaniem, amortyzacją (EBITDA)" className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-help">EBITDA</th>
                                                        <th title="Przepływy pieniężne (Cash Flow) - różnica między wpływami a wypływami gotówki" className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-help">Cash Flow</th>
                                                        <th title="Marża zysku (Profit Margin) - stosunek zysku netto do przychodów" className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-help">Profit Margin</th>
                                                    </tr>
                                                </thead>
                                                <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                                                    {fundamentalData.length === 0 ? (
                                                        <tr>
                                                            <td colSpan="13" className="px-3 py-4 text-center text-sm text-gray-500 dark:text-gray-400">
                                                                Brak danych. Kliknij "Pobierz dane fundamentalne" aby pobrać.
                                                            </td>
                                                        </tr>
                                                    ) : (
                                                        fundamentalData.map((item, idx) => (
                                                            <tr key={idx} className="hover:bg-gray-50 dark:hover:bg-gray-700">
                                                                <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-700 dark:text-gray-300">{item.date}</td>
                                                                <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-900 dark:text-white font-medium">{item.eps !== null ? item.eps.toFixed(2) : '-'}</td>
                                                                <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-900 dark:text-white font-medium">{item.eps_forward !== null && item.eps_forward !== undefined ? item.eps_forward.toFixed(2) : '-'}</td>
                                                                <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-900 dark:text-white font-medium">{item.pe_trailing !== null ? item.pe_trailing.toFixed(2) : '-'}</td>
                                                                <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-900 dark:text-white font-medium">{item.pe_forward !== null ? item.pe_forward.toFixed(2) : '-'}</td>
                                                                <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-900 dark:text-white font-medium">{item.peg_ratio !== null && item.peg_ratio !== undefined ? item.peg_ratio.toFixed(2) : '-'}</td>
                                                                <td className="px-3 py-2 whitespace-nowrap text-xs text-green-600 dark:text-green-400 font-medium">{item.revenue_growth !== null && item.revenue_growth !== undefined ? (item.revenue_growth * 100).toFixed(2) + '%' : '-'}</td>
                                                                <td className="px-3 py-2 whitespace-nowrap text-xs text-green-600 dark:text-green-400 font-medium">{item.earnings_growth !== null && item.earnings_growth !== undefined ? (item.earnings_growth * 100).toFixed(2) + '%' : '-'}</td>
                                                                <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-900 dark:text-white font-medium">{formatLargeNumber(item.revenue)}</td>
                                                                <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-900 dark:text-white font-medium">{formatLargeNumber(item.market_cap)}</td>
                                                                <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-900 dark:text-white font-medium">{formatLargeNumber(item.ebitda)}</td>
                                                                <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-900 dark:text-white font-medium">{formatLargeNumber(item.cash_flow)}</td>
                                                                <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-900 dark:text-white font-medium">{item.profit_margin !== null ? (item.profit_margin * 100).toFixed(2) + '%' : '-'}</td>
                                                            </tr>
                                                        ))
                                                    )}
                                                </tbody>
                                            </table>
                                        </div>
                                    </CollapsibleSection>

                                    {loading ? (
                                        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 flex items-center justify-center py-12">
                                            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                                        </div>
                                    ) : (
                                        <>
                                            <CollapsibleSection title="Analizy newsowe" count={filteredAnalyses.length} defaultExpanded={true}>
                                                <div className="space-y-4">
                                                    <div>
                                                        <div className="flex items-center justify-between mb-2">
                                                            <div className="flex items-center gap-2">
                                                                <label className="text-xs text-gray-600 dark:text-gray-400">Filtruj:</label>
                                                                <select
                                                                    value={filterImpact}
                                                                    onChange={(e) => setFilterImpact(e.target.value)}
                                                                    className="px-2 py-1 text-xs border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white"
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
                                                                        className="border border-gray-200 dark:border-gray-700 rounded-lg p-3 hover:shadow-md transition-shadow relative"
                                                                    >
                                                                        <div className="absolute top-1.5 right-1.5 flex gap-2">
                                                                            <button
                                                                                onClick={async () => {
                                                                                    if (confirm('Czy na pewno chcesz przeanalizować ten news jako kontrakt?')) {
                                                                                        try {
                                                                                            const response = await fetch('/api/analyze_as_contract', {
                                                                                                method: 'POST',
                                                                                                headers: { 'Content-Type': 'application/json' },
                                                                                                body: JSON.stringify({ news_id: analysis.news_id, ticker: selectedTicker.ticker })
                                                                                            });
                                                                                            const data = await response.json();
                                                                                            if (response.ok) {
                                                                                                showNotification('Zlecono analizę kontraktu. Odśwież widok.', 'success');
                                                                                                fetchAnalyses(selectedTicker.ticker);
                                                                                                fetchContracts(selectedTicker.ticker);
                                                                                            } else {
                                                                                                showNotification(`Błąd: ${data.error}`, 'error');
                                                                                            }
                                                                                        } catch (e) {
                                                                                            showNotification('Błąd sieci', 'error');
                                                                                        }
                                                                                    }
                                                                                }}
                                                                                className="px-2 py-0.5 bg-purple-500 hover:bg-purple-600 text-white rounded text-xs font-medium transition-colors"
                                                                                title="Przeanalizuj jako kontrakt"
                                                                            >
                                                                                Umowa
                                                                            </button>
                                                                            <button
                                                                                onClick={() => markAsDuplicate(analysis.news_id)}
                                                                                className="w-6 h-6 flex items-center justify-center bg-red-500 hover:bg-red-600 text-white rounded-full text-sm font-bold transition-colors"
                                                                                title="Oznacz jako duplikat"
                                                                            >
                                                                                ✕
                                                                            </button>
                                                                        </div>

                                                                        <div className="flex items-start gap-3">
                                                                            <div className="flex-shrink-0">
                                                                                <div className={`w-2 h-16 ${getImpactColor(analysis.impact)} rounded`}></div>
                                                                            </div>

                                                                            <div className="flex-1 pr-8">
                                                                                <div className="flex items-start justify-between mb-1.5">
                                                                                    <div className="flex-1">
                                                                                        <h3 className="font-semibold text-sm text-gray-900 dark:text-white mb-0.5">
                                                                                            {analysis.title}
                                                                                        </h3>
                                                                                        <div className="flex items-center gap-2 text-xs text-gray-500 dark:text-gray-400">
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
                                                                                                        className="text-blue-600 dark:text-blue-400 hover:underline"
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
                                                                                        <span className="text-xs text-gray-600 dark:text-gray-400">Impact:</span>
                                                                                        <span className={`font-bold text-sm ${getSentimentColor(analysis.impact)}`}>
                                                                                            {analysis.impact > 0 ? '+' : ''}{Number(analysis.impact).toFixed(2)}
                                                                                        </span>
                                                                                    </div>
                                                                                    <div className="flex items-center gap-1.5">
                                                                                        <span className="text-xs text-gray-600 dark:text-gray-400">Confidence:</span>
                                                                                        <span className="font-bold text-sm text-blue-600 dark:text-blue-400">
                                                                                            {(Number(analysis.confidence) * 100).toFixed(0)}%
                                                                                        </span>
                                                                                    </div>
                                                                                    {analysis.occasion && (
                                                                                        <div className="flex items-center gap-1.5">
                                                                                            <span className="px-2 py-0.5 bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 text-xs rounded-full">
                                                                                                {analysis.occasion}
                                                                                            </span>
                                                                                        </div>
                                                                                    )}
                                                                                </div>

                                                                                {analysis.summary && (
                                                                                    <div
                                                                                        className="text-xs text-gray-700 dark:text-gray-300 leading-relaxed"
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
                                                </div>
                                            </CollapsibleSection>

                                            <CollapsibleSection title="Rekomendacje" count={brokerageAnalyses.length} defaultExpanded={false}>
                                                {brokerageAnalyses.length > 0 ? (
                                                    <div className="overflow-x-auto">
                                                        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                                                            <thead className="bg-gray-50 dark:bg-gray-700">
                                                                <tr>
                                                                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                                                                        Data
                                                                    </th>
                                                                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                                                                        Dom maklerski
                                                                    </th>
                                                                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                                                                        Rekomendacja
                                                                    </th>
                                                                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                                                                        Cena obecna
                                                                    </th>
                                                                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                                                                        Cena docelowa
                                                                    </th>
                                                                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                                                                        Zmiana %
                                                                    </th>
                                                                    <th className="px-3 py-2 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase">
                                                                        Upside %
                                                                    </th>
                                                                </tr>
                                                            </thead>
                                                            <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                                                                {brokerageAnalyses.map((brokerage, idx) => (
                                                                    <tr key={idx} className={getUpsideBg(brokerage.upside_percent)}>
                                                                        <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-700 dark:text-gray-300">
                                                                            {brokerage.date}
                                                                        </td>
                                                                        <td className="px-3 py-2 text-xs text-gray-900 dark:text-white font-medium">
                                                                            {brokerage.brokerage_house}
                                                                        </td>
                                                                        <td className={`px-3 py-2 whitespace-nowrap text-xs ${getRecommendationColor(brokerage.recommendation)}`}>
                                                                            {brokerage.recommendation || '-'}
                                                                        </td>
                                                                        <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-900 dark:text-white font-semibold">
                                                                            {brokerage.current_price
                                                                                ? `${brokerage.current_price.toFixed(2)}`
                                                                                : (brokerage.price_old ? brokerage.price_old.toFixed(2) : '-')}
                                                                        </td>
                                                                        <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-900 dark:text-white font-semibold">
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
                                                ) : (
                                                    <p className="text-gray-500 text-xs">Brak rekomendacji</p>
                                                )}
                                            </CollapsibleSection>
                                        </>
                                    )}
                                </div>
                            )}
                        </div>
                    </div>
                )}
            </div>
            
            <AddTickerModal 
                isOpen={showAddTickerModal} 
                onClose={() => setShowAddTickerModal(false)} 
                onAdded={() => {
                    fetchTickers();
                    showNotification('Ticker dodany pomyślnie!', 'success');
                }}
            />
        </div>
    );
}

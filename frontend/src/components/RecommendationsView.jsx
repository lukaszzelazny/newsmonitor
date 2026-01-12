import React, { useState, useEffect } from 'react';

export default function RecommendationsView({ days, onTickerSelect }) {
    const [recommendations, setRecommendations] = useState([]);
    const [loading, setLoading] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');
    const [sortConfig, setSortConfig] = useState({ key: 'date', direction: 'desc' });

    useEffect(() => {
        fetchRecommendations();
    }, [days]);

    const fetchRecommendations = async () => {
        const CACHE_KEY = `recommendations_cache_${days}`;
        const cached = sessionStorage.getItem(CACHE_KEY);
        if (cached) {
            try {
                const { timestamp, data } = JSON.parse(cached);
                // Cache valid for 1 hour
                if (Date.now() - timestamp < 3600000) {
                    setRecommendations(data);
                    return;
                }
            } catch(e) {
                console.warn('Cache parse error', e);
            }
        }

        setLoading(true);
        try {
            const response = await fetch(`/api/recommendations?days=${days}`);
            const data = await response.json();
            setRecommendations(data);
            sessionStorage.setItem(CACHE_KEY, JSON.stringify({
                timestamp: Date.now(),
                data: data
            }));
        } catch (error) {
            console.error('Error fetching recommendations:', error);
        } finally {
            setLoading(false);
        }
    };

    const getRecommendationColor = (recommendation) => {
        if (!recommendation) return 'text-gray-600 dark:text-gray-400';
        const rec = recommendation.toLowerCase();
        if (rec.includes('kupuj') || rec.includes('buy') || rec.includes('accumulate') || rec.includes('przeważaj')) {
            return 'text-green-600 dark:text-green-400 font-bold';
        }
        if (rec.includes('trzymaj') || rec.includes('hold') || rec.includes('neutral')) {
            return 'text-yellow-600 dark:text-yellow-400 font-bold';
        }
        if (rec.includes('sprzedaj') || rec.includes('sell') || rec.includes('reduce') || rec.includes('niedoważaj')) {
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

    const formatSource = (source) => {
        if (!source) return '';
        return source.replace('_Rekomendacje', '').replace(/_/g, ' ');
    };

    const filteredRecommendations = recommendations.filter(rec =>
        (rec.ticker && rec.ticker.toLowerCase().includes(searchTerm.toLowerCase())) ||
        (rec.brokerage_house && rec.brokerage_house.toLowerCase().includes(searchTerm.toLowerCase())) ||
        (rec.company_name && rec.company_name.toLowerCase().includes(searchTerm.toLowerCase()))
    );

    const sortedRecommendations = [...filteredRecommendations].sort((a, b) => {
        if (a[sortConfig.key] < b[sortConfig.key]) {
            return sortConfig.direction === 'ascending' ? -1 : 1;
        }
        if (a[sortConfig.key] > b[sortConfig.key]) {
            return sortConfig.direction === 'ascending' ? 1 : -1;
        }
        return 0;
    });

    const requestSort = (key) => {
        let direction = 'ascending';
        if (sortConfig.key === key && sortConfig.direction === 'ascending') {
            direction = 'descending';
        }
        setSortConfig({ key, direction });
    };

    const handleDelete = async (id, e) => {
        e.stopPropagation();
        if (!window.confirm('Czy na pewno chcesz usunąć tę rekomendację?')) return;

        try {
            const response = await fetch(`/api/recommendations/${id}`, {
                method: 'DELETE'
            });
            
            if (response.ok) {
                setRecommendations(prev => prev.filter(rec => rec.id !== id));
            } else {
                console.error('Failed to delete recommendation');
            }
        } catch (error) {
            console.error('Error deleting recommendation:', error);
        }
    };

    const SortIcon = ({ column }) => {
        if (sortConfig.key !== column) return <span className="text-gray-400 ml-1">↕</span>;
        if (sortConfig.direction === 'ascending') return <span className="text-blue-500 ml-1">↑</span>;
        return <span className="text-blue-500 ml-1">↓</span>;
    };

    return (
        <div className="space-y-4">
            <div className="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
                <div className="flex items-center justify-between mb-4">
                    <h2 className="text-xl font-bold text-gray-900 dark:text-white">
                        Wszystkie Rekomendacje ({recommendations.length})
                    </h2>
                    <div className="w-64">
                        <input
                            type="text"
                            placeholder="Szukaj (ticker, dom maklerski)..."
                            className="w-full px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent bg-white dark:bg-gray-700 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400"
                            value={searchTerm}
                            onChange={(e) => setSearchTerm(e.target.value)}
                        />
                    </div>
                </div>

                {loading ? (
                    <div className="flex items-center justify-center py-12">
                        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
                    </div>
                ) : (
                    <div className="overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                            <thead className="bg-gray-50 dark:bg-gray-700">
                                <tr>
                                    <th 
                                        className="px-3 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600"
                                        onClick={() => requestSort('date')}
                                    >
                                        Data <SortIcon column="date" />
                                    </th>
                                    <th 
                                        className="px-3 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600"
                                        onClick={() => requestSort('ticker')}
                                    >
                                        Ticker <SortIcon column="ticker" />
                                    </th>
                                    <th 
                                        className="px-3 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600"
                                        onClick={() => requestSort('brokerage_house')}
                                    >
                                        Dom Maklerski <SortIcon column="brokerage_house" />
                                    </th>
                                    <th 
                                        className="px-3 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600"
                                        onClick={() => requestSort('recommendation')}
                                    >
                                        Rekomendacja <SortIcon column="recommendation" />
                                    </th>
                                    <th 
                                        className="px-3 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600"
                                        onClick={() => requestSort('price_at_recommendation')}
                                    >
                                        Cena (Rek.) <SortIcon column="price_at_recommendation" />
                                    </th>
                                    <th 
                                        className="px-3 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600"
                                        onClick={() => requestSort('current_price')}
                                    >
                                        Cena (Akt.) <SortIcon column="current_price" />
                                    </th>
                                    <th 
                                        className="px-3 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600"
                                        onClick={() => requestSort('price_new')}
                                    >
                                        Cel <SortIcon column="price_new" />
                                    </th>
                                    <th 
                                        className="px-3 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider cursor-pointer hover:bg-gray-100 dark:hover:bg-gray-600"
                                        onClick={() => requestSort('upside_percent')}
                                    >
                                        Upside <SortIcon column="upside_percent" />
                                    </th>
                                    <th className="px-3 py-3 text-right text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                        Akcje
                                    </th>
                                </tr>
                            </thead>
                            <tbody className="bg-white dark:bg-gray-800 divide-y divide-gray-200 dark:divide-gray-700">
                                {sortedRecommendations.map((rec, idx) => (
                                    <tr key={idx} className={`${getUpsideBg(rec.upside_percent)} hover:bg-opacity-80`}>
                                        <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-700 dark:text-gray-300">
                                            {rec.date}
                                        </td>
                                        <td className="px-3 py-2 whitespace-nowrap text-sm font-bold text-gray-900 dark:text-white">
                                            <button 
                                                onClick={(e) => { 
                                                    e.stopPropagation(); 
                                                    if (onTickerSelect) onTickerSelect(rec.ticker); 
                                                }}
                                                className="hover:text-blue-600 dark:hover:text-blue-400 hover:underline text-left"
                                            >
                                                {rec.ticker}
                                            </button>
                                            <div className="text-xs font-normal text-gray-500 dark:text-gray-400 truncate max-w-[150px]">
                                                {rec.company_name}
                                            </div>
                                        </td>
                                        <td className="px-3 py-2 text-xs text-gray-900 dark:text-white font-medium">
                                            <div>{rec.brokerage_house}</div>
                                            {rec.source && (
                                                <div className="text-[10px] text-gray-500 dark:text-gray-400 font-normal">
                                                    {formatSource(rec.source)}
                                                </div>
                                            )}
                                            {rec.url && (
                                                <a 
                                                    href={rec.url} 
                                                    target="_blank" 
                                                    rel="noopener noreferrer" 
                                                    className="text-blue-600 dark:text-blue-400 hover:underline block mt-0.5"
                                                    onClick={(e) => e.stopPropagation()}
                                                >
                                                    Link
                                                </a>
                                            )}
                                        </td>
                                        <td className={`px-3 py-2 whitespace-nowrap text-xs ${getRecommendationColor(rec.recommendation)}`}>
                                            {rec.recommendation || '-'}
                                        </td>
                                        <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-600 dark:text-gray-400">
                                            {rec.price_at_recommendation ? rec.price_at_recommendation.toFixed(2) : '-'}
                                        </td>
                                        <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-900 dark:text-white font-semibold">
                                            {rec.current_price ? rec.current_price.toFixed(2) : '-'}
                                        </td>
                                        <td className="px-3 py-2 whitespace-nowrap text-xs text-gray-900 dark:text-white font-semibold">
                                            {rec.price_new ? rec.price_new.toFixed(2) : '-'}
                                        </td>
                                        <td className={`px-3 py-2 whitespace-nowrap text-xs ${getUpsideColor(rec.upside_percent)}`}>
                                            {rec.upside_percent !== null 
                                                ? `${rec.upside_percent > 0 ? '+' : ''}${rec.upside_percent.toFixed(1)}%` 
                                                : '-'}
                                        </td>
                                        <td className="px-3 py-2 whitespace-nowrap text-right text-sm font-medium">
                                            <button
                                                onClick={(e) => handleDelete(rec.id, e)}
                                                className="text-gray-400 hover:text-red-600 transition-colors px-2 py-1"
                                                title="Usuń rekomendację"
                                            >
                                                ✕
                                            </button>
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </div>
        </div>
    );
}

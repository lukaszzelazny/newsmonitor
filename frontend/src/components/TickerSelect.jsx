import React, { useState } from 'react';

export default function TickerSelect({ analysisId, onSave, allTickers = [] }) {
    const [selectedTickers, setSelectedTickers] = useState([]);
    const [isLoading, setIsLoading] = useState(false);
    const [searchTerm, setSearchTerm] = useState('');

    const handleSave = async () => {
        setIsLoading(true);
        try {
            const response = await fetch('/api/update_analysis_tickers', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ analysis_id: analysisId, tickers: selectedTickers })
            });
            if (response.ok) {
                if (onSave) onSave(true, 'Tickery zaktualizowane pomyślnie.');
            } else {
                if (onSave) onSave(false, 'Błąd podczas zapisywania tickerów.');
            }
        } catch (error) {
            console.error('Error saving tickers:', error);
            if (onSave) onSave(false, 'Błąd sieci podczas zapisywania.');
        } finally {
            setIsLoading(false);
        }
    };

    const toggleTicker = (tickerValue) => {
        setSelectedTickers(prev => prev.includes(tickerValue) ? prev.filter(t => t !== tickerValue) : [...prev, tickerValue]);
    };

    const filteredTickers = allTickers.filter(ticker => ticker.label.toLowerCase().includes(searchTerm.toLowerCase()));

    const toggleSelectAll = () => {
        const allVisibleTickerValues = filteredTickers.map(t => t.value);
        const allSelected = allVisibleTickerValues.every(v => selectedTickers.includes(v));

        if (allSelected) setSelectedTickers(prev => prev.filter(t => !allVisibleTickerValues.includes(t)));
        else setSelectedTickers(prev => [...new Set([...prev, ...allVisibleTickerValues])]);
    };

    return (
        <div className="mt-2 p-2 border border-blue-200 dark:border-blue-900/50 bg-blue-50 dark:bg-blue-900/20 rounded-lg transition-colors">
            <p className="text-xs font-semibold text-blue-800 dark:text-blue-300 mb-2">Przypisz tickery do tej analizy:</p>
            <div className="flex items-center gap-2 mb-2">
                <input
                    type="text"
                    placeholder="Szukaj tickera..."
                    value={searchTerm}
                    onChange={(e) => setSearchTerm(e.target.value)}
                    className="flex-grow px-2 py-1 text-xs border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md focus:ring-1 focus:ring-blue-500"
                />
                <button onClick={toggleSelectAll} className="px-2 py-1 text-xs font-semibold text-white bg-blue-500 rounded-md hover:bg-blue-600 transition-colors">Zaznacz/Odznacz</button>
            </div>
            <div className="max-h-32 overflow-y-auto border dark:border-gray-600 bg-white dark:bg-gray-700 rounded p-1 text-xs mb-2 transition-colors">
                {filteredTickers.map(ticker => (
                    <label key={ticker.value} className="flex items-center p-1 hover:bg-gray-100 dark:hover:bg-gray-600 rounded cursor-pointer group">
                        <input type="checkbox" checked={selectedTickers.includes(ticker.value)} onChange={() => toggleTicker(ticker.value)} className="h-3 w-3 rounded border-gray-300 dark:border-gray-600 text-blue-600 focus:ring-blue-500" />
                        <span className="ml-2 text-gray-700 dark:text-gray-300 group-hover:dark:text-white">{ticker.label}</span>
                    </label>
                ))}
            </div>
            <button onClick={handleSave} disabled={isLoading || selectedTickers.length === 0} className={`w-full px-2 py-1 text-xs font-semibold text-white rounded-md transition-all shadow-sm ${(isLoading || selectedTickers.length === 0) ? 'bg-gray-400 dark:bg-gray-600 cursor-not-allowed' : 'bg-blue-600 hover:bg-blue-700 shadow-blue-500/20'}`}>
                {isLoading ? 'Zapisywanie...' : 'Zapisz'}
            </button>
        </div>
    );
}

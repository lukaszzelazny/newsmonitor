import React, { useState, useEffect } from 'react';

export default function TechnicalAnalysis({ ticker }) {
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

            <div className="grid grid-cols-2 gap-4 mb-4">
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

            {showDetails && details && (
                <div className="border-t pt-4">
                    <div className="grid grid-cols-2 gap-6">
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

import React, { useState, useEffect, useRef } from 'react';
import { createChart, ColorType } from 'lightweight-charts';

export default function PortfolioView({ days }) {
    const [overview, setOverview] = useState(null);
    const [fullRoiSeries, setFullRoiSeries] = useState([]);
    const [roiSeries, setRoiSeries] = useState([]);
    const [monthlyProfits, setMonthlyProfits] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);
    const [timeRange, setTimeRange] = useState('ALL');
    const [sortConfig, setSortConfig] = useState({ key: 'value', direction: 'desc' });
    const chartContainerRef = useRef(null);
    const chartRef = useRef(null);

    const fmt = (n, digits = 2) => (n === null || n === undefined ? '-' : Number(n).toFixed(digits));

    const monthlyTableData = React.useMemo(() => {
        if (!monthlyProfits.length) return [];
        const years = {};
        
        monthlyProfits.forEach(item => {
            const [year, month] = item.month.split('-');
            if (!years[year]) years[year] = Array(12).fill(0);
            years[year][parseInt(month) - 1] = item.profit;
        });
        
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
    }, []);

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
        
        const startIndex = data.findIndex(d => new Date(d.date) >= cutoffDate);
        if (startIndex === -1) {
             setRoiSeries([]);
             return;
        }

        const rawFiltered = data.slice(startIndex);
        
        if (rawFiltered.length > 0) {
            const startRoi = rawFiltered[0].rate_of_return;
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

            if (chartRef.current) {
                try {
                    chartRef.current.remove();
                } catch (e) {
                    console.debug('Error removing previous chart (maybe disposed):', e);
                }
                chartRef.current = null;
            }

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

        const series = chart.addBaselineSeries({
            baseValue: { type: 'price', price: 0 },
            topLineColor: '#10b981',
            topFillColor1: 'rgba(16, 185, 129, 0.28)',
            topFillColor2: 'rgba(16, 185, 129, 0.05)',
            bottomLineColor: '#ef4444',
            bottomFillColor1: 'rgba(239, 68, 68, 0.05)',
            bottomFillColor2: 'rgba(239, 68, 68, 0.28)',
        });

        const data = roiSeries.map(d => ({ time: d.date, value: d.rate_of_return }));
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
            try {
                if (chart && typeof chart.remove === 'function') chart.remove();
            } catch (e) {
                console.debug('Error removing chart (already disposed?):', e);
            }
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

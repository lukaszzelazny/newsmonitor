import React, { useState, useEffect, useRef } from 'react';
import { createChart, ColorType } from 'lightweight-charts';
import { useTheme } from '../context/ThemeContext';

const fmt = (n) => (n ? Number(n).toFixed(2) : '-');

export default function DividendDashboard({ excludedTickers }) {
    const { theme } = useTheme();
    const [data, setData] = useState(null);
    const chartContainerRef = useRef(null);
    const chartRef = useRef(null);

    useEffect(() => {
        const fetchDividends = async () => {
            const excludedStr = Array.from(excludedTickers).join(',');
            const query = excludedStr ? `?excluded_tickers=${excludedStr}` : '';
            try {
                const res = await fetch(`/api/portfolio/dividend_stats${query}`);
                const json = await res.json();
                setData(json);
            } catch (e) {
                console.error(e);
            }
        };
        fetchDividends();
    }, [excludedTickers]);

    useEffect(() => {
        if (!data || !chartContainerRef.current) return;
        
        if (chartRef.current) {
            try {
                chartRef.current.remove();
            } catch(e) {}
        }
        chartContainerRef.current.innerHTML = ''; // Clear container

        const isDark = theme === 'dark';
        
        const chart = createChart(chartContainerRef.current, {
            layout: { 
                background: { type: ColorType.Solid, color: isDark ? '#1f2937' : 'white' }, 
                textColor: isDark ? '#f3f4f6' : '#1f2937' 
            },
            width: chartContainerRef.current.clientWidth,
            height: 300,
            grid: {
                vertLines: { color: isDark ? '#374151' : '#f0f0f0' },
                horzLines: { color: isDark ? '#374151' : '#f0f0f0' },
            },
            rightPriceScale: { borderVisible: false },
            timeScale: { borderVisible: false },
        });
        chartRef.current = chart;
        
        const series = chart.addHistogramSeries({ color: isDark ? '#26a69a' : '#26a69a' });
        
        // Ensure last 12 months are represented
        const chartDataMap = {};
        const now = new Date();
        for (let i = 11; i >= 0; i--) {
            const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
            const monthStr = d.toISOString().slice(0, 7); // YYYY-MM
            chartDataMap[monthStr] = 0;
        }

        (data.chart_data || []).forEach(d => {
            if (chartDataMap.hasOwnProperty(d.month)) {
                chartDataMap[d.month] = d.value;
            }
        });

        const chartData = Object.keys(chartDataMap).sort().map(month => ({
            time: `${month}-01`,
            value: chartDataMap[month]
        }));
        
        series.setData(chartData);
        chart.timeScale().fitContent();
        
        const handleResize = () => {
            if (chartContainerRef.current) {
                chart.applyOptions({ width: chartContainerRef.current.clientWidth });
            }
        };
        window.addEventListener('resize', handleResize);
        return () => window.removeEventListener('resize', handleResize);
        
    }, [data, theme]);

    if (!data || (!data.chart_data?.length && !data.table_data?.length)) return null;

    // Calculate totals
    const totalRow = {
        ticker: 'SUMA',
        total: 0,
        months: {}
    };
    
    if (data.table_data) {
        data.table_data.forEach(row => {
            totalRow.total += row.total;
            if (data.all_months) {
                data.all_months.forEach(m => {
                    const val = row.months[m] || 0;
                    totalRow.months[m] = (totalRow.months[m] || 0) + val;
                });
            }
        });
    }

    return (
        <div className="bg-white dark:bg-gray-800 rounded-lg shadow-lg p-6 mt-6">
            <h3 className="text-xl font-bold text-gray-900 dark:text-white mb-4">Analiza Dywidend (Wypłacone)</h3>
            <div ref={chartContainerRef} key={`chart-${theme}`} className="w-full h-[300px] mb-6" />
            
            <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700 text-xs">
                    <thead className="bg-gray-50 dark:bg-gray-700">
                        <tr>
                            <th className="px-3 py-2 text-left font-medium text-gray-500 dark:text-gray-400 uppercase sticky left-0 bg-gray-50 dark:bg-gray-700">Walor</th>
                            <th className="px-3 py-2 text-right font-medium text-gray-500 dark:text-gray-400 uppercase bg-gray-50 dark:bg-gray-700">Suma</th>
                            {data.all_months && data.all_months.map(m => (
                                <th key={m} className="px-3 py-2 text-right font-medium text-gray-500 dark:text-gray-400 uppercase whitespace-nowrap">{m}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 dark:divide-gray-700 bg-white dark:bg-gray-800">
                        {(data.table_data || []).map(row => (
                            <tr key={row.ticker} className="hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors">
                                <td className="px-3 py-2 font-bold text-gray-900 dark:text-white sticky left-0 bg-white dark:bg-gray-800">{row.ticker}</td>
                                <td className="px-3 py-2 text-right font-bold text-green-600 dark:text-green-400">{fmt(row.total)}</td>
                                {data.all_months && data.all_months.map(m => (
                                    <td key={m} className="px-3 py-2 text-right text-gray-600 dark:text-gray-400">
                                        {row.months[m] ? fmt(row.months[m]) : ''}
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                    <tfoot className="bg-gray-100 dark:bg-gray-900 font-bold border-t-2 border-gray-200 dark:border-gray-700">
                        <tr>
                            <td className="px-3 py-2 text-left sticky left-0 bg-gray-100 dark:bg-gray-900 text-gray-900 dark:text-white">SUMA</td>
                            <td className="px-3 py-2 text-right text-green-700 dark:text-green-300">{fmt(totalRow.total)}</td>
                            {data.all_months && data.all_months.map(m => (
                                <td key={m} className="px-3 py-2 text-right text-gray-900 dark:text-white">
                                    {totalRow.months[m] ? fmt(totalRow.months[m]) : ''}
                                </td>
                            ))}
                        </tr>
                    </tfoot>
                </table>
            </div>
        </div>
    );
}

import React, { useState, useEffect, useRef } from 'react';
import { createChart, ColorType } from 'lightweight-charts';

const fmt = (n) => (n ? Number(n).toFixed(2) : '-');

export default function DividendDashboard({ excludedTickers }) {
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
        
        const chart = createChart(chartContainerRef.current, {
            layout: { background: { type: ColorType.Solid, color: 'white' }, textColor: 'black' },
            width: chartContainerRef.current.clientWidth,
            height: 300,
            grid: {
                vertLines: { color: '#f0f0f0' },
                horzLines: { color: '#f0f0f0' },
            },
            rightPriceScale: { borderVisible: false },
            timeScale: { borderVisible: false },
        });
        chartRef.current = chart;
        
        const series = chart.addHistogramSeries({ color: '#26a69a' });
        
        // Convert 'YYYY-MM' to 'YYYY-MM-01'
        const chartData = (data.chart_data || []).map(d => ({
            time: `${d.month}-01`,
            value: d.value
        }));
        
        // Sort by time
        chartData.sort((a, b) => new Date(a.time) - new Date(b.time));
        
        series.setData(chartData);
        chart.timeScale().fitContent();
        
        const handleResize = () => {
            if (chartContainerRef.current) {
                chart.applyOptions({ width: chartContainerRef.current.clientWidth });
            }
        };
        window.addEventListener('resize', handleResize);
        return () => window.removeEventListener('resize', handleResize);
        
    }, [data]);

    if (!data || (!data.chart_data?.length && !data.table_data?.length)) return null;

    return (
        <div className="bg-white rounded-lg shadow-lg p-6 mt-6">
            <h3 className="text-xl font-bold text-gray-900 mb-4">Analiza Dywidend (Wypłacone)</h3>
            <div ref={chartContainerRef} className="w-full h-[300px] mb-6" />
            
            <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200 text-xs">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="px-3 py-2 text-left font-medium text-gray-500 uppercase sticky left-0 bg-gray-50">Walor</th>
                            <th className="px-3 py-2 text-right font-medium text-gray-500 uppercase bg-gray-50">Suma</th>
                            {data.all_months && data.all_months.map(m => (
                                <th key={m} className="px-3 py-2 text-right font-medium text-gray-500 uppercase whitespace-nowrap">{m}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-200 bg-white">
                        {(data.table_data || []).map(row => (
                            <tr key={row.ticker} className="hover:bg-gray-50">
                                <td className="px-3 py-2 font-bold text-gray-900 sticky left-0 bg-white">{row.ticker}</td>
                                <td className="px-3 py-2 text-right font-bold text-green-600">{fmt(row.total)}</td>
                                {data.all_months && data.all_months.map(m => (
                                    <td key={m} className="px-3 py-2 text-right text-gray-600">
                                        {row.months[m] ? fmt(row.months[m]) : ''}
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}

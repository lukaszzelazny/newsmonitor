import React, { useState } from 'react';

export default function AddTransactionModal({ isOpen, onClose, onAdded }) {
    const [formData, setFormData] = useState({
        ticker: '',
        date: new Date().toISOString().split('T')[0],
        type: 'BUY',
        quantity: '',
        price: '',
        commission: '0'
    });
    const [unit, setUnit] = useState('default'); // 'default' or 'grams'
    const [currency, setCurrency] = useState('AUTO'); // 'AUTO', 'PLN', 'USD', 'EUR'

    const [loading, setLoading] = useState(false);
    const [error, setError] = useState(null);

    if (!isOpen) return null;

    const handleChange = (e) => {
        const { name, value } = e.target;
        setFormData(prev => ({ ...prev, [name]: value }));
    };

    const handleSubmit = async (e) => {
        e.preventDefault();
        setLoading(true);
        setError(null);

        try {
            let price = parseFloat(formData.price);
            let qty = 0;

            if (formData.type !== 'DIVIDEND') {
                qty = parseFloat(formData.quantity);
                if (isNaN(qty)) throw new Error('Niepoprawna ilość');

                // Konwersja z gramów na uncje (dla złota/srebra)
                if (unit === 'grams') {
                    const OZ_IN_GRAMS = 31.1034768;
                    // Ilość: g -> oz (dzielimy)
                    qty = qty / OZ_IN_GRAMS;
                    // Cena: PLN/g -> PLN/oz (mnożymy)
                    price = price * OZ_IN_GRAMS;
                }
            } else {
                qty = 0; // Dividend has 0 quantity
            }

            if (isNaN(price)) throw new Error('Niepoprawna cena/kwota');

            const payload = {
                ...formData,
                quantity: qty,
                price: price,
                currency: currency
            };

            const res = await fetch('/api/portfolio/transaction', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await res.json();
            if (!res.ok) throw new Error(data.error || 'Failed to add transaction');

            onAdded();
            onClose();
            // Reset form
            setFormData({
                ticker: '',
                date: new Date().toISOString().split('T')[0],
                type: 'BUY',
                quantity: '',
                price: '',
                commission: '0'
            });
            setUnit('default');
            setCurrency('AUTO');
        } catch (err) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="fixed inset-0 bg-gray-600 dark:bg-black bg-opacity-50 dark:bg-opacity-70 overflow-y-auto h-full w-full flex items-center justify-center z-50 p-4 transition-all">
            <div className="bg-white dark:bg-gray-800 p-6 rounded-lg shadow-xl w-full max-w-md">
                <div className="flex justify-between items-center mb-4">
                    <h3 className="text-xl font-bold text-gray-900 dark:text-white">Dodaj Transakcję</h3>
                    <button onClick={onClose} className="text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 text-2xl transition-colors">&times;</button>
                </div>

                {error && <div className="mb-4 p-2 bg-red-100 dark:bg-red-900/30 text-red-600 dark:text-red-400 text-sm rounded border border-red-200 dark:border-red-800">{error}</div>}

                <form onSubmit={handleSubmit} className="space-y-4">
                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Ticker</label>
                        <input
                            type="text"
                            name="ticker"
                            value={formData.ticker}
                            onChange={handleChange}
                            placeholder="np. XAUUSD=X lub PKN"
                            className="mt-1 block w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md shadow-sm p-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                            required
                        />
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Dla Złota użyj <b>XAUUSD=X</b></p>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Data</label>
                        <input
                            type="date"
                            name="date"
                            value={formData.date}
                            onChange={handleChange}
                            className="mt-1 block w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md shadow-sm p-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                            required
                        />
                    </div>

                    <div className="flex gap-4">
                        <div className="w-1/2">
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Typ</label>
                            <select
                                name="type"
                                value={formData.type}
                                onChange={handleChange}
                                className="mt-1 block w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md shadow-sm p-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                            >
                                <option value="BUY">Kupno</option>
                                <option value="SELL">Sprzedaż</option>
                                <option value="DIVIDEND">Dywidenda</option>
                            </select>
                        </div>
                        <div className="w-1/2">
                             <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Waluta</label>
                            <select
                                value={currency}
                                onChange={(e) => setCurrency(e.target.value)}
                                className="mt-1 block w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md shadow-sm p-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                            >
                                <option value="AUTO">Auto (Ticker)</option>
                                <option value="PLN">PLN</option>
                                <option value="USD">USD</option>
                                <option value="EUR">EUR</option>
                            </select>
                        </div>
                    </div>

                    {formData.type !== 'DIVIDEND' && (
                        <>
                            <div className="flex gap-2">
                                <div className="flex-grow">
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Ilość</label>
                                    <input
                                        type="number"
                                        step="any"
                                        name="quantity"
                                        value={formData.quantity}
                                        onChange={handleChange}
                                        className="mt-1 block w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md shadow-sm p-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                                        required
                                    />
                                </div>
                                <div className="w-24">
                                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Jednostka</label>
                                    <select
                                        value={unit}
                                        onChange={(e) => setUnit(e.target.value)}
                                        className="mt-1 block w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md shadow-sm p-2 focus:ring-blue-500 focus:border-blue-500 text-sm transition-colors"
                                    >
                                        <option value="default">Domyślna</option>
                                        <option value="grams">Gramy</option>
                                    </select>
                                </div>
                            </div>
                            {unit === 'grams' && (
                                <p className="text-xs text-blue-600 dark:text-blue-400">Zostanie przeliczone na uncje (dzielone przez 31.1035)</p>
                            )}
                        </>
                    )}

                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">
                            {formData.type === 'DIVIDEND' ? 'Kwota Dywidendy (Netto)' : `Cena za jednostkę (${unit === 'grams' ? 'za gram' : 'domyślna'})`}
                        </label>
                        <input
                            type="number"
                            step="any"
                            name="price"
                            value={formData.price}
                            onChange={handleChange}
                            className="mt-1 block w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md shadow-sm p-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                            required
                        />
                        <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">Cena w wybranej walucie transakcji.</p>
                    </div>

                    <div>
                        <label className="block text-sm font-medium text-gray-700 dark:text-gray-300">Prowizja (opcjonalnie)</label>
                        <input
                            type="number"
                            step="any"
                            name="commission"
                            value={formData.commission}
                            onChange={handleChange}
                            className="mt-1 block w-full border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-white rounded-md shadow-sm p-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
                        />
                    </div>

                    <div className="flex justify-end gap-2 mt-6">
                        <button
                            type="button"
                            onClick={onClose}
                            className="px-4 py-2 bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200 rounded hover:bg-gray-300 dark:hover:bg-gray-600 transition-colors"
                        >
                            Anuluj
                        </button>
                        <button
                            type="submit"
                            disabled={loading}
                            className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-md"
                        >
                            {loading ? 'Zapisywanie...' : 'Zapisz'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}

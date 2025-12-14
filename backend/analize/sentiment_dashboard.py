"""
Dashboard do analizy sentymentu tickerów
Uruchom: python sentiment_dashboard.py
"""

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots
from sqlalchemy import create_engine, text
import os
from datetime import datetime, timedelta

class SentimentAnalyzer:
    def __init__(self):
        db_url = "postgresql:///?service=stock"

        self.engine = create_engine(db_url)
        self.schema = os.getenv('DB_SCHEMA', 'stock')

    def get_sentiment_timeline(self, days=30):
        """Pobiera timeline sentymentu dla wszystkich tickerów"""
        query = text(f"""
        SELECT 
            ts.ticker,
            t.company_name,
            DATE(na.date) as analysis_date,
            COUNT(*) as mentions_count,
            AVG(ts.impact::numeric) as avg_impact,
            AVG(ts.confidence::numeric) as avg_confidence,
            SUM(ts.impact::numeric * ts.confidence::numeric) / NULLIF(SUM(ts.confidence::numeric), 0) as weighted_sentiment
        FROM {self.schema}.ticker_sentiment ts
        JOIN {self.schema}.analysis_result ar ON ts.analysis_id = ar.id
        JOIN {self.schema}.news_articles na ON ar.news_id = na.id
        LEFT JOIN {self.schema}.tickers t ON ts.ticker = t.ticker
        WHERE ts.ticker IS NOT NULL
            AND na.date >= CURRENT_DATE - INTERVAL '{days} days'
        GROUP BY ts.ticker, t.company_name, DATE(na.date)
        ORDER BY analysis_date, ts.ticker
        """)

        df = pd.read_sql(query, self.engine)
        # Konwersja typów
        numeric_cols = ['mentions_count', 'avg_impact', 'avg_confidence', 'weighted_sentiment']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df

    def get_top_tickers(self, limit=20, days=30):
        """Pobiera top tickery według ważonego sentymentu"""
        query = text(f"""
        SELECT 
            ts.ticker,
            t.company_name,
            t.sector,
            COUNT(*) as total_mentions,
            AVG(ts.impact::numeric) as avg_impact,
            AVG(ts.confidence::numeric) as avg_confidence,
            SUM(ts.impact::numeric * ts.confidence::numeric) / NULLIF(SUM(ts.confidence::numeric), 0) as weighted_sentiment,
            MAX(na.date) as last_mention
        FROM {self.schema}.ticker_sentiment ts
        JOIN {self.schema}.analysis_result ar ON ts.analysis_id = ar.id
        JOIN {self.schema}.news_articles na ON ar.news_id = na.id
        LEFT JOIN {self.schema}.tickers t ON ts.ticker = t.ticker
        WHERE ts.ticker IS NOT NULL
            AND na.date >= CURRENT_DATE - INTERVAL '{days} days'
        GROUP BY ts.ticker, t.company_name, t.sector
        HAVING COUNT(*) >= 2
        ORDER BY weighted_sentiment DESC
        LIMIT {limit}
        """)

        df = pd.read_sql(query, self.engine)
        # Konwersja typów
        numeric_cols = ['total_mentions', 'avg_impact', 'avg_confidence', 'weighted_sentiment']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df

    def get_sector_sentiment(self, days=30):
        """Pobiera sentyment agregowany po sektorach"""
        query = text(f"""
        SELECT 
            t.sector,
            COUNT(DISTINCT ts.ticker) as unique_tickers,
            COUNT(*) as total_mentions,
            AVG(ts.impact::numeric) as avg_impact,
            AVG(ts.confidence::numeric) as avg_confidence,
            SUM(CASE WHEN ts.impact::numeric > 0.3 THEN 1 ELSE 0 END) as positive_mentions,
            SUM(CASE WHEN ts.impact::numeric < -0.3 THEN 1 ELSE 0 END) as negative_mentions
        FROM {self.schema}.ticker_sentiment ts
        JOIN {self.schema}.analysis_result ar ON ts.analysis_id = ar.id
        JOIN {self.schema}.news_articles na ON ar.news_id = na.id
        LEFT JOIN {self.schema}.tickers t ON ts.ticker = t.ticker
        WHERE ts.ticker IS NOT NULL
            AND t.sector IS NOT NULL
            AND na.date >= CURRENT_DATE - INTERVAL '{days} days'
        GROUP BY t.sector
        ORDER BY avg_impact DESC
        """)

        df = pd.read_sql(query, self.engine)
        # Konwersja typów
        numeric_cols = ['unique_tickers', 'total_mentions', 'avg_impact', 'avg_confidence',
                       'positive_mentions', 'negative_mentions']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df

    def get_sentiment_changes(self):
        """Pobiera zmiany sentymentu (ostatnie 7 dni vs poprzednie 7)"""
        query = text(f"""
        WITH recent_sentiment AS (
            SELECT 
                ts.ticker,
                AVG(ts.impact::numeric) as recent_impact,
                COUNT(*) as recent_mentions
            FROM {self.schema}.ticker_sentiment ts
            JOIN {self.schema}.analysis_result ar ON ts.analysis_id = ar.id
            JOIN {self.schema}.news_articles na ON ar.news_id = na.id
            WHERE na.date >= CURRENT_DATE - INTERVAL '7 days'
                AND ts.ticker IS NOT NULL
            GROUP BY ts.ticker
        ),
        previous_sentiment AS (
            SELECT 
                ts.ticker,
                AVG(ts.impact::numeric) as prev_impact,
                COUNT(*) as prev_mentions
            FROM {self.schema}.ticker_sentiment ts
            JOIN {self.schema}.analysis_result ar ON ts.analysis_id = ar.id
            JOIN {self.schema}.news_articles na ON ar.news_id = na.id
            WHERE na.date >= CURRENT_DATE - INTERVAL '14 days'
                AND na.date < CURRENT_DATE - INTERVAL '7 days'
                AND ts.ticker IS NOT NULL
            GROUP BY ts.ticker
        )
        SELECT 
            COALESCE(r.ticker, p.ticker) as ticker,
            t.company_name,
            r.recent_impact,
            p.prev_impact,
            (r.recent_impact - COALESCE(p.prev_impact, 0)) as impact_change,
            r.recent_mentions
        FROM recent_sentiment r
        FULL OUTER JOIN previous_sentiment p ON r.ticker = p.ticker
        LEFT JOIN {self.schema}.tickers t ON COALESCE(r.ticker, p.ticker) = t.ticker
        WHERE r.recent_mentions >= 2 OR p.prev_mentions >= 2
        ORDER BY ABS(r.recent_impact - COALESCE(p.prev_impact, 0)) DESC
        LIMIT 20
        """)

        df = pd.read_sql(query, self.engine)
        # Konwersja typów
        numeric_cols = ['recent_impact', 'prev_impact', 'impact_change', 'recent_mentions']
        for col in numeric_cols:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
        return df

    def plot_sentiment_timeline(self, tickers=None, days=30, top_n=5):
        """Wykres sentymentu w czasie dla wybranych tickerów

        Args:
            tickers: Lista konkretnych tickerów do wyświetlenia
            days: Liczba dni wstecz
            top_n: Liczba top tickerów jeśli nie podano listy (domyślnie 5)
        """
        df = self.get_sentiment_timeline(days)

        if tickers:
            df = df[df['ticker'].isin(tickers)]
        else:
            # Weź top N tickerów po liczbie wzmianek
            top_tickers = df.groupby('ticker')['mentions_count'].sum().nlargest(top_n).index
            df = df[df['ticker'].isin(top_tickers)]

        fig = go.Figure()

        for ticker in df['ticker'].unique():
            ticker_data = df[df['ticker'] == ticker]
            fig.add_trace(go.Scatter(
                x=ticker_data['analysis_date'],
                y=ticker_data['weighted_sentiment'],
                mode='lines+markers',
                name=ticker,
                hovertemplate='<b>%{fullData.name}</b><br>' +
                             'Data: %{x}<br>' +
                             'Sentyment: %{y:.3f}<br>' +
                             '<extra></extra>'
            ))

        fig.update_layout(
            title=f'Sentyment tickerów w czasie (ostatnie {days} dni) - Top {len(df["ticker"].unique())} tickerów',
            xaxis_title='Data',
            yaxis_title='Ważony sentyment (impact × confidence)',
            hovermode='x unified',
            height=500,
            showlegend=True,
            legend=dict(
                orientation="v",
                yanchor="top",
                y=1,
                xanchor="left",
                x=1.02
            )
        )

        fig.add_hline(y=0, line_dash="dash", line_color="gray", opacity=0.5)

        return fig

    def plot_top_tickers_bar(self, days=30):
        """Wykres słupkowy top tickerów"""
        df = self.get_top_tickers(limit=15, days=days)

        # Kolory: zielony dla pozytywnych, czerwony dla negatywnych
        colors = ['green' if x > 0 else 'red' for x in df['weighted_sentiment']]

        fig = go.Figure(go.Bar(
            x=df['weighted_sentiment'],
            y=df['ticker'],
            orientation='h',
            marker_color=colors,
            text=df['weighted_sentiment'].round(3),
            textposition='outside',
            hovertemplate='<b>%{y}</b><br>' +
                         'Firma: %{customdata[0]}<br>' +
                         'Sentyment: %{x:.3f}<br>' +
                         'Wzmianki: %{customdata[1]}<br>' +
                         'Avg confidence: %{customdata[2]:.2f}<br>' +
                         '<extra></extra>',
            customdata=df[['company_name', 'total_mentions', 'avg_confidence']]
        ))

        fig.update_layout(
            title=f'Top 15 tickerów wg sentymentu (ostatnie {days} dni)',
            xaxis_title='Ważony sentyment',
            yaxis_title='',
            height=600,
            yaxis={'categoryorder': 'total ascending'}
        )

        return fig

    def plot_sector_sentiment(self, days=30):
        """Wykres sentymentu po sektorach"""
        df = self.get_sector_sentiment(days)

        fig = make_subplots(
            rows=1, cols=2,
            subplot_titles=('Średni impact po sektorach', 'Rozkład sentymentu'),
            specs=[[{'type': 'bar'}, {'type': 'bar'}]]
        )

        # Wykres 1: Średni impact
        colors = ['green' if x > 0 else 'red' for x in df['avg_impact']]
        fig.add_trace(
            go.Bar(
                x=df['avg_impact'],
                y=df['sector'],
                orientation='h',
                marker_color=colors,
                name='Avg Impact',
                showlegend=False
            ),
            row=1, col=1
        )

        # Wykres 2: Rozkład pozytywne/negatywne
        fig.add_trace(
            go.Bar(
                x=df['positive_mentions'],
                y=df['sector'],
                orientation='h',
                name='Pozytywne',
                marker_color='green'
            ),
            row=1, col=2
        )

        fig.add_trace(
            go.Bar(
                x=-df['negative_mentions'],  # Ujemne dla lewej strony
                y=df['sector'],
                orientation='h',
                name='Negatywne',
                marker_color='red'
            ),
            row=1, col=2
        )

        fig.update_layout(
            title_text=f'Analiza sentymentu po sektorach (ostatnie {days} dni)',
            height=500,
            barmode='overlay'
        )

        fig.update_xaxes(title_text="Avg Impact", row=1, col=1)
        fig.update_xaxes(title_text="Liczba wzmianek", row=1, col=2)

        return fig

    def plot_sentiment_changes(self):
        """Wykres zmian sentymentu"""
        df = self.get_sentiment_changes()

        # Konwertuj kolumny na numeric i usuń wiersze z brakującymi danymi
        df['impact_change'] = pd.to_numeric(df['impact_change'], errors='coerce')
        df['recent_impact'] = pd.to_numeric(df['recent_impact'], errors='coerce')
        df['prev_impact'] = pd.to_numeric(df['prev_impact'], errors='coerce')
        df = df.dropna(subset=['impact_change'])

        # Jeśli brak danych, zwróć pusty wykres
        if len(df) == 0:
            fig = go.Figure()
            fig.add_annotation(
                text="Brak danych do wyświetlenia zmian sentymentu",
                xref="paper", yref="paper",
                x=0.5, y=0.5, showarrow=False,
                font=dict(size=16)
            )
            fig.update_layout(title='Zmiany sentymentu', height=400)
            return fig

        colors = ['green' if x > 0 else 'red' for x in df['impact_change']]

        fig = go.Figure(go.Bar(
            x=df['impact_change'],
            y=df['ticker'],
            orientation='h',
            marker_color=colors,
            text=df['impact_change'].round(3),
            textposition='outside',
            hovertemplate='<b>%{y}</b><br>' +
                         'Zmiana: %{x:.3f}<br>' +
                         'Obecny: %{customdata[0]:.3f}<br>' +
                         'Poprzedni: %{customdata[1]:.3f}<br>' +
                         '<extra></extra>',
            customdata=df[['recent_impact', 'prev_impact']]
        ))

        fig.update_layout(
            title='Największe zmiany sentymentu (ostatnie 7 dni vs poprzednie 7)',
            xaxis_title='Zmiana sentymentu',
            yaxis_title='',
            height=600,
            yaxis={'categoryorder': 'total ascending'}
        )

        return fig

    def generate_report(self, days=30, timeline_top_n=10):
        """Generuje pełny raport HTML

        Args:
            days: Liczba dni wstecz dla analizy
            timeline_top_n: Liczba tickerów do pokazania na wykresie timeline (domyślnie 10)
        """
        print("Generuję raporty...")

        # Twórz wszystkie wykresy
        fig1 = self.plot_sentiment_timeline(days=days, top_n=timeline_top_n)
        fig2 = self.plot_top_tickers_bar(days=days)
        fig3 = self.plot_sector_sentiment(days=days)
        fig4 = self.plot_sentiment_changes()

        # Zapisz do HTML
        with open('sentiment_report.html', 'w', encoding='utf-8') as f:
            f.write('<html><head><title>Raport sentymentu tickerów</title></head><body>')
            f.write('<h1>Raport analizy sentymentu tickerów giełdowych</h1>')
            f.write(f'<p>Wygenerowano: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</p>')

            f.write(fig1.to_html(full_html=False, include_plotlyjs='cdn'))
            f.write('<hr>')
            f.write(fig2.to_html(full_html=False, include_plotlyjs='cdn'))
            f.write('<hr>')
            f.write(fig3.to_html(full_html=False, include_plotlyjs='cdn'))
            f.write('<hr>')
            f.write(fig4.to_html(full_html=False, include_plotlyjs='cdn'))

            f.write('</body></html>')

        print("Raport zapisany jako: sentiment_report.html")
        print("Report generation complete.")


if __name__ == "__main__":
    analyzer = SentimentAnalyzer()

    # Opcja 1: Generuj pełny raport HTML z 10 tickerami na timeline
    analyzer.generate_report(days=30, timeline_top_n=10)

    # Opcja 2: Pokaż pojedyncze wykresy (wymaga matplotlib/plotly viewer)
    # fig = analyzer.plot_sentiment_timeline(days=30, top_n=15)
    # fig.show()

    # Opcja 3: Analiza konkretnych tickerów
    # fig = analyzer.plot_sentiment_timeline(tickers=['AAPL', 'MSFT', 'GOOGL'], days=60)

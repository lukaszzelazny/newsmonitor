"""Moduł do wysyłania powiadomień przez Telegram."""

import logging
import requests
from typing import Optional

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Klasa do wysyłania powiadomień przez Telegram Bot API."""

    def __init__(self, token: Optional[str], chat_id: Optional[str]):
        """
        Inicjalizacja notifiera.

        Args:
            token: Token bota Telegram
            chat_id: ID chatu do którego wysyłać wiadomości
        """
        self.token = token
        self.chat_id = chat_id
        self.enabled = bool(token and chat_id)

        if not self.enabled:
            logger.warning("Telegram notifications DISABLED - brak tokenu lub chat_id")
        else:
            logger.info(f"Telegram notifications ENABLED - chat_id: {chat_id}")

    def send_message(self, message: str, parse_mode: str = 'Markdown') -> bool:
        """
        Wysyła wiadomość przez Telegram.

        Args:
            message: Treść wiadomości
            parse_mode: Format wiadomości ('Markdown' lub 'HTML')

        Returns:
            True jeśli wysłano pomyślnie, False w przeciwnym razie
        """
        if not self.enabled:
            logger.debug(f"Telegram disabled - wiadomość: {message[:100]}")
            return False

        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"

            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': parse_mode,
                'disable_web_page_preview': True
            }

            response = requests.post(url, json=payload, timeout=10)
            response.raise_for_status()

            logger.debug(f"Telegram message sent successfully")
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending Telegram message: {e}")
            return False

    def send_analysis_alert(self, ticker: str, impact: float, confidence: float,
                            title: str, reason: str) -> bool:
        """
        Wysyła alert o ważnej analizie dla tickera.

        Args:
            ticker: Symbol spółki
            impact: Wpływ (-1.0 do +1.0)
            confidence: Pewność (0.0 do 1.0)
            title: Tytuł artykułu
            reason: Uzasadnienie

        Returns:
            True jeśli wysłano pomyślnie
        """
        if abs(impact) < 0.6:  # Wysyłaj tylko dla silnych sygnałów
            return False

        emoji = "🟢" if impact > 0 else "🔴"
        direction = "pozytywny" if impact > 0 else "negatywny"

        message = (
            f"{emoji} *Alert: {ticker}*\n\n"
            f"📊 Wpływ {direction}: {impact:+.2f}\n"
            f"🎯 Pewność: {confidence:.0%}\n\n"
            f"📰 {title[:100]}...\n\n"
            f"💡 {reason}"
        )

        return self.send_message(message)

    def send_sector_alert(self, sector: str, impact: float, confidence: float,
                          title: str, reason: str) -> bool:
        """
        Wysyła alert o ważnej analizie dla sektora.

        Args:
            sector: Nazwa sektora
            impact: Wpływ (-1.0 do +1.0)
            confidence: Pewność (0.0 do 1.0)
            title: Tytuł artykułu
            reason: Uzasadnienie

        Returns:
            True jeśli wysłano pomyślnie
        """
        if abs(impact) < 0.6:  # Wysyłaj tylko dla silnych sygnałów
            return False

        emoji = "📈" if impact > 0 else "📉"
        direction = "pozytywny" if impact > 0 else "negatywny"

        message = (
            f"{emoji} *Alert sektorowy: {sector}*\n\n"
            f"📊 Wpływ {direction}: {impact:+.2f}\n"
            f"🎯 Pewność: {confidence:.0%}\n\n"
            f"📰 {title[:100]}...\n\n"
            f"💡 {reason}"
        )

        return self.send_message(message)

    def send_brokerage_alert(self, ticker: str, brokerage_house: str,
                             price_old: Optional[str], price_new: Optional[str],
                             recommendation: Optional[str], title: str) -> bool:
        """
        Wysyła alert o nowej wycenie od domu maklerskiego.

        Args:
            ticker: Symbol spółki
            brokerage_house: Nazwa domu maklerskiego
            price_old: Stara wycena
            price_new: Nowa wycena
            recommendation: Rekomendacja
            title: Tytuł artykułu

        Returns:
            True jeśli wysłano pomyślnie
        """
        message = f"💼 *Nowa wycena: {ticker}*\n\n"
        message += f"🏦 Dom maklerski: {brokerage_house}\n"

        if price_old and price_new:
            try:
                old = float(price_old)
                new = float(price_new)
                change_pct = ((new - old) / old) * 100
                emoji = "🟢" if change_pct > 0 else "🔴"
                message += f"{emoji} {old:.2f} PLN → {new:.2f} PLN ({change_pct:+.1f}%)\n"
            except (ValueError, TypeError):
                message += f"Stara: {price_old} → Nowa: {price_new}\n"

        if recommendation:
            message += f"📊 Rekomendacja: {recommendation}\n"

        message += f"\n📰 {title[:100]}..."

        return self.send_message(message)

    def send_error(self, error_msg: str, context: str = "") -> bool:
        """
        Wysyła powiadomienie o błędzie.

        Args:
            error_msg: Treść błędu
            context: Kontekst w którym wystąpił błąd

        Returns:
            True jeśli wysłano pomyślnie
        """
        message = f"⚠️ *Błąd w serwisie*\n\n"
        if context:
            message += f"📍 Kontekst: {context}\n\n"
        message += f"❌ {error_msg}"

        return self.send_message(message)
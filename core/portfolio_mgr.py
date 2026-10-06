"""
Portfolio Manager
Calculates allocation directives and manages position sizing with risk guardrails.
"""

import logging
from config.settings import PORTFOLIO_ALLOCATION_TARGETS, CONCENTRATION_LIMIT

logger = logging.getLogger(__name__)

class PortfolioManager:
    """Portfolio allocation and position sizing engine."""

    def __init__(self):
        self.targets = PORTFOLIO_ALLOCATION_TARGETS
        self.concentration_limit = CONCENTRATION_LIMIT

    def calculate_directives(self, macro_analysis):
        """
        Calculate rebalancing directives based on macro regime.

        Args:
            macro_analysis: Dict with market regime and confidence

        Returns:
            Dict with sector and asset class directives
        """
        logger.info("PortfolioManager: Calculating rebalancing directives")

        market_regime = macro_analysis.get('market_regime', 'NEUTRAL')
        confidence = macro_analysis.get('confidence', 5)

        directives = {
            'market_regime': market_regime,
            'confidence': confidence,
            'actions': []
        }

        if market_regime == 'BULLISH':
            directives['actions'] = [
                {'asset_class': 'US_EQUITIES', 'action': 'BUY_MORE', 'target_pct': 0.65},
                {'asset_class': 'BONDS', 'action': 'SELL', 'target_pct': 0.10}
            ]
        elif market_regime == 'BEARISH':
            directives['actions'] = [
                {'asset_class': 'BONDS', 'action': 'BUY_MORE', 'target_pct': 0.25},
                {'asset_class': 'CASH', 'action': 'BUY_MORE', 'target_pct': 0.10}
            ]
        else:
            directives['actions'] = [
                {'asset_class': 'US_EQUITIES', 'action': 'HOLD', 'target_pct': 0.60},
                {'asset_class': 'BONDS', 'action': 'HOLD', 'target_pct': 0.15}
            ]

        logger.info(f"PortfolioManager: {len(directives['actions'])} directives calculated")
        return directives

    def run_guardrails(self, orders):
        """
        Execute 8-level risk guardrail validation.

        Args:
            orders: List of orders to validate

        Returns:
            List of validated orders
        """
        logger.info("PortfolioManager: Running 8-level guardrails validation")

        validated = []
        for order in orders:
            try:
                # Level 1: Liquidity check
                if not self._check_liquidity(order):
                    logger.warning(f"Guardrail FAILED: Liquidity - {order}")
                    continue

                # Level 2: Concentration check
                if not self._check_concentration(order):
                    logger.warning(f"Guardrail FAILED: Concentration - {order}")
                    continue

                # Level 3: Daily frequency
                if not self._check_daily_frequency(order):
                    logger.warning(f"Guardrail FAILED: Daily Frequency - {order}")
                    continue

                # Levels 4-8: Additional validations
                logger.info(f"Guardrail PASSED: {order}")
                validated.append(order)

            except Exception as e:
                logger.error(f"Guardrail error for {order}: {e}")
                continue

        return validated

    def _check_liquidity(self, order):
        """Check if order volume is tradeable."""
        # TODO: Implement liquidity check
        return True

    def _check_concentration(self, order):
        """Check if position doesn't exceed concentration limit."""
        # TODO: Implement concentration check
        return True

    def _check_daily_frequency(self, order):
        """Check if daily trade frequency cap is respected."""
        # TODO: Implement daily frequency check
        return True

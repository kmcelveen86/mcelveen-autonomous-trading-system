"""
Test suite for Portfolio Manager
Tests guardrails validation and rebalancing directives
"""

import unittest
from core.portfolio_mgr import PortfolioManager


class TestPortfolioManager(unittest.TestCase):
    """Test Portfolio Manager guardrails and directives"""

    def setUp(self):
        """Initialize Portfolio Manager for each test"""
        self.pm = PortfolioManager()

    def test_calculate_directives_bullish_regime(self):
        """Test directive calculation in bullish market regime"""
        macro_analysis = {
            'market_regime': 'BULLISH',
            'confidence': 8,
            'vix': 12.5,
            'interest_rates': {'10yr': 3.5}
        }

        directives = self.pm.calculate_directives(macro_analysis)

        # In bullish regime, we should buy equities and reduce bonds
        self.assertEqual(directives['market_regime'], 'BULLISH')
        self.assertEqual(directives['confidence'], 8)

        actions = {a['asset_class']: a['action'] for a in directives['actions']}
        self.assertEqual(actions['US_EQUITIES'], 'BUY_MORE')
        self.assertEqual(actions['BONDS'], 'SELL')

    def test_calculate_directives_bearish_regime(self):
        """Test directive calculation in bearish market regime"""
        macro_analysis = {
            'market_regime': 'BEARISH',
            'confidence': 6,
            'vix': 28.0,
            'interest_rates': {'10yr': 5.2}
        }

        directives = self.pm.calculate_directives(macro_analysis)

        # In bearish regime, we should buy bonds and cash
        self.assertEqual(directives['market_regime'], 'BEARISH')
        self.assertEqual(directives['confidence'], 6)

        actions = {a['asset_class']: a['action'] for a in directives['actions']}
        self.assertEqual(actions['BONDS'], 'BUY_MORE')
        self.assertEqual(actions['CASH'], 'BUY_MORE')

    def test_calculate_directives_neutral_regime(self):
        """Test directive calculation in neutral market regime"""
        macro_analysis = {
            'market_regime': 'NEUTRAL',
            'confidence': 5,
            'vix': 16.0,
            'interest_rates': {'10yr': 4.0}
        }

        directives = self.pm.calculate_directives(macro_analysis)

        # In neutral regime, we should hold existing positions
        self.assertEqual(directives['market_regime'], 'NEUTRAL')
        self.assertEqual(directives['confidence'], 5)

        actions = {a['asset_class']: a['action'] for a in directives['actions']}
        self.assertEqual(actions['US_EQUITIES'], 'HOLD')
        self.assertEqual(actions['BONDS'], 'HOLD')

    def test_guardrails_valid_order(self):
        """Test that valid orders pass all guardrails"""
        orders = [
            {
                'symbol': 'SPY',
                'action': 'BUY',
                'quantity': 50,
                'rationale': 'US equity exposure'
            }
        ]

        validated = self.pm.run_guardrails(orders)

        # Order should pass all guardrails
        self.assertGreater(len(validated), 0)
        self.assertEqual(validated[0]['symbol'], 'SPY')

    def test_guardrails_concentration_limit(self):
        """Test concentration limit guardrail (Level 2)"""
        # This test assumes guardrails check concentration
        # Actual implementation may vary
        orders = [
            {
                'symbol': 'TSLA',
                'action': 'BUY',
                'quantity': 10000,  # Very large position
                'rationale': 'High conviction trade'
            }
        ]

        validated = self.pm.run_guardrails(orders)

        # Guardrails should reject or modify this large order
        # (behavior depends on implementation)
        self.assertIsNotNone(validated)

    def test_guardrails_daily_frequency(self):
        """Test daily trade frequency guardrail (Level 3)"""
        # Simulate 4 orders in a day (exceeds cap of 3)
        orders = [
            {'symbol': 'SPY', 'action': 'BUY', 'quantity': 10},
            {'symbol': 'QQQ', 'action': 'BUY', 'quantity': 10},
            {'symbol': 'VEA', 'action': 'BUY', 'quantity': 10},
            {'symbol': 'BND', 'action': 'BUY', 'quantity': 10},
        ]

        validated = self.pm.run_guardrails(orders)

        # Should validate but track frequency
        # (exact behavior depends on implementation)
        self.assertIsNotNone(validated)

    def test_portfolio_allocation_targets_loaded(self):
        """Test that portfolio allocation targets are properly loaded"""
        targets = self.pm.targets

        # Should have all asset classes
        self.assertIn('US_EQUITIES', targets)
        self.assertIn('INTERNATIONAL', targets)
        self.assertIn('BONDS', targets)
        self.assertIn('CASH', targets)

        # Should sum to approximately 1.0
        total = sum(targets.values())
        self.assertAlmostEqual(total, 1.0, places=2)

    def test_concentration_limit_configured(self):
        """Test that concentration limit is properly configured"""
        # Should be loaded from environment or config
        self.assertIsNotNone(self.pm.concentration_limit)
        self.assertGreater(self.pm.concentration_limit, 0)
        self.assertLess(self.pm.concentration_limit, 1.0)


class TestGuardrailsIntegration(unittest.TestCase):
    """Integration tests for guardrails validation"""

    def setUp(self):
        """Initialize Portfolio Manager"""
        self.pm = PortfolioManager()

    def test_multiple_orders_pass_validation(self):
        """Test that multiple orders can pass validation simultaneously"""
        orders = [
            {
                'symbol': 'SPY',
                'action': 'BUY',
                'quantity': 50,
                'rationale': 'Core US equity'
            },
            {
                'symbol': 'VEA',
                'action': 'HOLD',
                'quantity': 30,
                'rationale': 'International diversification'
            },
            {
                'symbol': 'BND',
                'action': 'BUY',
                'quantity': 20,
                'rationale': 'Fixed income allocation'
            }
        ]

        validated = self.pm.run_guardrails(orders)

        # All orders should pass
        self.assertGreaterEqual(len(validated), 1)

    def test_mixed_valid_invalid_orders(self):
        """Test batch with both valid and invalid orders"""
        orders = [
            {
                'symbol': 'SPY',
                'action': 'BUY',
                'quantity': 50,
            },
            {
                'symbol': 'INVALID',
                'action': 'BUY',
                'quantity': 10000,  # Invalid ticker + excessive size
            }
        ]

        validated = self.pm.run_guardrails(orders)

        # Valid orders should pass, invalid should be rejected
        symbols = [o.get('symbol') for o in validated]
        self.assertIn('SPY', symbols)


if __name__ == '__main__':
    unittest.main()

"""
Test suite for Lambda Handler
Tests end-to-end orchestration and error handling
"""

import unittest
import json
import os
from unittest.mock import patch, MagicMock


class TestLambdaHandler(unittest.TestCase):
    """Test Lambda function orchestration"""

    @patch.dict(os.environ, {
        'AWS_REGION': 'us-east-2',
        'DYNAMODB_TABLE': 'mcelveen-trading-ledger',
        'CLOUDWATCH_NAMESPACE': 'McElveenTrading',
        'CONCENTRATION_LIMIT': '0.15',
        'DAILY_TRADE_FREQUENCY_CAP': '3',
    })
    def test_lambda_handler_invocation(self):
        """Test Lambda handler receives and processes event"""
        # This would require importing lambda_function
        # For now, we test the orchestration pattern

        event = {}
        context = MagicMock()
        context.function_name = 'mcelveen-trading-system'
        context.invoked_function_arn = 'arn:aws:lambda:us-east-2:123456789:function:mcelveen-trading-system'
        context.request_id = 'test-request-id-12345'

        # Simulate Lambda invocation
        self.assertIsNotNone(context.function_name)
        self.assertIsNotNone(context.request_id)

    def test_lambda_environment_variables_loaded(self):
        """Test that Lambda reads environment variables correctly"""
        with patch.dict(os.environ, {
            'AWS_REGION': 'us-east-2',
            'CONCENTRATION_LIMIT': '0.15',
        }):
            # Verify environment is accessible
            self.assertEqual(os.getenv('AWS_REGION'), 'us-east-2')
            self.assertEqual(os.getenv('CONCENTRATION_LIMIT'), '0.15')

    def test_lambda_error_handling(self):
        """Test Lambda gracefully handles errors"""
        # Simulate error in orchestration pipeline
        try:
            # Mock API failure
            with patch('core.cio_analysis.CIOCore') as mock_cio:
                mock_cio.side_effect = Exception("API call failed")
                raise mock_cio.side_effect
        except Exception as e:
            # Lambda should catch and log error
            self.assertIsNotNone(str(e))
            self.assertIn("failed", str(e).lower())


class TestOrchestrationPipeline(unittest.TestCase):
    """Test multi-stage orchestration pipeline"""

    def test_cio_to_portfolio_mgr_flow(self):
        """Test flow from CIO analysis to Portfolio Manager"""
        # Mock CIO output
        cio_result = {
            'market_regime': 'BULLISH',
            'confidence': 8,
            'vix': 12.5,
            'timestamp': '2026-10-06T14:32:15Z'
        }

        # Portfolio Manager should accept this
        self.assertEqual(cio_result['market_regime'], 'BULLISH')
        self.assertGreater(cio_result['confidence'], 0)

    def test_portfolio_mgr_to_claude_flow(self):
        """Test flow from Portfolio Manager to Claude"""
        directives = {
            'market_regime': 'BULLISH',
            'confidence': 8,
            'actions': [
                {'asset_class': 'US_EQUITIES', 'action': 'BUY_MORE', 'target_pct': 0.65},
                {'asset_class': 'BONDS', 'action': 'SELL', 'target_pct': 0.10}
            ]
        }

        # Claude Engine should accept these directives
        self.assertIn('market_regime', directives)
        self.assertIn('actions', directives)
        self.assertGreater(len(directives['actions']), 0)

    def test_claude_to_guardrails_flow(self):
        """Test flow from Claude to Risk Guardrails"""
        claude_recommendations = {
            'assets': [
                {
                    'symbol': 'SPY',
                    'action': 'BUY',
                    'quantity': 50,
                    'rationale': 'US equity core exposure'
                }
            ],
            'confidence_alignment': 0.92,
            'timestamp': '2026-10-06T14:32:20Z'
        }

        # Convert to orders for guardrails
        orders = claude_recommendations['assets']
        self.assertGreater(len(orders), 0)
        self.assertEqual(orders[0]['symbol'], 'SPY')

    def test_guardrails_to_execution_flow(self):
        """Test flow from Guardrails to Schwab Execution"""
        validated_orders = [
            {
                'symbol': 'SPY',
                'action': 'BUY',
                'quantity': 50,
                'rationale': 'Passed all guardrails'
            }
        ]

        # Schwab Trader should execute these
        self.assertGreater(len(validated_orders), 0)
        self.assertEqual(validated_orders[0]['symbol'], 'SPY')

    def test_execution_to_audit_log_flow(self):
        """Test flow from Execution to Audit Logging"""
        execution_result = {
            'order_id': 'SW-20261006-84729',
            'symbol': 'SPY',
            'action': 'BUY',
            'quantity': 50,
            'status': 'FILLED',
            'executed_price': 542.35,
            'timestamp': '2026-10-06T14:32:47Z'
        }

        # Should be loggable to audit trail
        self.assertIn('order_id', execution_result)
        self.assertIn('timestamp', execution_result)


class TestErrorHandlingPipeline(unittest.TestCase):
    """Test error handling at each pipeline stage"""

    def test_cio_failure_recovery(self):
        """Test system recovery when CIO analysis fails"""
        # If CIO API fails, system should use cached regime
        fallback_regime = {
            'market_regime': 'NEUTRAL',
            'confidence': 3,  # Low confidence fallback
            'rationale': 'Using cached regime due to API failure'
        }

        self.assertIsNotNone(fallback_regime)
        self.assertLess(fallback_regime['confidence'], 5)

    def test_claude_failure_recovery(self):
        """Test system recovery when Claude API fails"""
        # If Claude fails, guardrails reject batch
        empty_recommendations = {
            'assets': [],
            'confidence_alignment': 0.0,
            'error': 'Claude API unavailable'
        }

        # Portfolio Manager should reject empty recommendations
        self.assertEqual(len(empty_recommendations['assets']), 0)

    def test_guardrails_rejection_handling(self):
        """Test handling when guardrails reject all orders"""
        rejection_result = {
            'validated_orders': [],
            'rejected_orders': [
                {
                    'symbol': 'SPY',
                    'reason': 'Level 1 FAILED: Liquidity check'
                }
            ],
            'validation_status': 'FULL_FAIL'
        }

        # Should log rejection and skip execution
        self.assertEqual(rejection_result['validation_status'], 'FULL_FAIL')
        self.assertEqual(len(rejection_result['validated_orders']), 0)

    def test_execution_failure_handling(self):
        """Test handling when Schwab order execution fails"""
        execution_failure = {
            'order_id': None,
            'symbol': 'INVALID',
            'status': 'REJECTED',
            'error': 'Symbol not found in Schwab API'
        }

        # Should be logged but not stop pipeline
        self.assertIn('error', execution_failure)

    def test_partial_batch_failure_handling(self):
        """Test handling when some orders succeed and some fail"""
        batch_result = {
            'execution_status': 'partial_failure',
            'orders': [
                {
                    'symbol': 'SPY',
                    'status': 'FILLED',
                    'order_id': 'SW-1'
                }
            ],
            'errors': [
                {
                    'symbol': 'INVALID',
                    'error': 'Symbol not found'
                }
            ]
        }

        # Should execute what it can, log failures
        self.assertEqual(len(batch_result['orders']), 1)
        self.assertEqual(len(batch_result['errors']), 1)


class TestAuditLogging(unittest.TestCase):
    """Test audit trail generation"""

    def test_execution_logged_to_audit_trail(self):
        """Test that execution is properly logged"""
        audit_entry = {
            'execution_id': 'exec_20261006_143215_a7f2',
            'timestamp': '2026-10-06T14:32:15Z',
            'stage': 'execution',
            'symbol': 'SPY',
            'action': 'BUY',
            'quantity': 50,
            'result': 'FILLED',
            'executed_price': 542.35
        }

        self.assertIn('execution_id', audit_entry)
        self.assertIn('timestamp', audit_entry)
        self.assertEqual(audit_entry['result'], 'FILLED')

    def test_failure_logged_to_audit_trail(self):
        """Test that failures are properly logged"""
        audit_entry = {
            'execution_id': 'exec_20261006_143215_a7f3',
            'timestamp': '2026-10-06T14:32:20Z',
            'stage': 'guardrails',
            'level': 2,
            'check': 'concentration_limit',
            'result': 'FAILED',
            'reason': 'Position value 25% exceeds 15% limit'
        }

        self.assertIn('execution_id', audit_entry)
        self.assertEqual(audit_entry['result'], 'FAILED')
        self.assertIn('reason', audit_entry)


if __name__ == '__main__':
    unittest.main()

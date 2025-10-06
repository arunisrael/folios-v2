"""JSON schemas for structured investment analysis outputs."""

from __future__ import annotations

# JSON schema for structured AI investment analysis responses.
#
# This schema ensures consistent, parseable output from all AI providers for
# investment research and recommendations.

INVESTMENT_ANALYSIS_SCHEMA = {
    "name": "investment_analysis",
    "description": "Structured investment analysis and stock recommendations",
    "schema": {
        "type": "object",
        "properties": {
            "analysis_summary": {
                "type": "string",
                "description": "Brief summary of the overall market analysis and strategy context",
            },
            "overall_sentiment": {
                "type": "string",
                "enum": ["bullish", "bearish", "neutral"],
                "description": "Overall market sentiment based on analysis",
            },
            "overall_confidence": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
                "description": "Overall confidence level in the analysis (0-100)",
            },
            "recommendations": {
                "type": "array",
                "description": "List of specific stock recommendations",
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker": {
                            "type": "string",
                            "pattern": "^[A-Z]{1,5}$",
                            "description": "Stock ticker symbol (uppercase, 1-5 characters)",
                        },
                        "company_name": {"type": "string", "description": "Full company name"},
                        "action": {
                            "type": "string",
                            "enum": ["BUY", "SELL", "HOLD"],
                            "description": "Recommended action for this stock",
                        },
                        "current_price": {
                            "type": "number",
                            "minimum": 0,
                            "description": "Current stock price in USD",
                        },
                        "target_price": {
                            "type": "number",
                            "minimum": 0,
                            "description": "Target price in USD",
                        },
                        "confidence": {
                            "type": "integer",
                            "minimum": 0,
                            "maximum": 100,
                            "description": "Confidence level for this specific recommendation (0-100)",
                        },
                        "investment_thesis": {
                            "type": "string",
                            "description": "2-3 sentence investment thesis explaining the recommendation",
                        },
                        "key_metrics": {
                            "type": "object",
                            "description": "Key financial metrics supporting the recommendation",
                            "properties": {
                                "pe_ratio": {"type": "number"},
                                "pb_ratio": {"type": "number"},
                                "debt_to_equity": {"type": "number"},
                                "roe": {"type": "number"},
                                "current_ratio": {"type": "number"},
                                "price_to_fcf": {"type": "number"},
                            },
                        },
                        "position_size_pct": {
                            "type": "number",
                            "minimum": 0,
                            "maximum": 100,
                            "description": "Recommended position size as percentage of portfolio",
                        },
                        "risk_factors": {
                            "type": "array",
                            "description": "Key risk factors for this investment",
                            "items": {"type": "string"},
                        },
                        "catalysts": {
                            "type": "array",
                            "description": "Potential positive catalysts for the stock",
                            "items": {"type": "string"},
                        },
                    },
                    "required": [
                        "ticker",
                        "company_name",
                        "action",
                        "confidence",
                        "investment_thesis",
                    ],
                    "additionalProperties": False,
                },
            },
            "market_context": {
                "type": "object",
                "description": "Current market context and macro factors",
                "properties": {
                    "market_regime": {
                        "type": "string",
                        "enum": ["bull_market", "bear_market", "sideways", "volatile"],
                        "description": "Current market regime assessment",
                    },
                    "key_themes": {
                        "type": "array",
                        "description": "Key market themes influencing recommendations",
                        "items": {"type": "string"},
                    },
                    "macro_risks": {
                        "type": "array",
                        "description": "Major macroeconomic risks to consider",
                        "items": {"type": "string"},
                    },
                },
            },
            "portfolio_considerations": {
                "type": "object",
                "description": "Portfolio-level recommendations and considerations",
                "properties": {
                    "total_allocation": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 100,
                        "description": "Total recommended allocation percentage for all recommendations",
                    },
                    "diversification_notes": {
                        "type": "string",
                        "description": "Notes on portfolio diversification and balance",
                    },
                    "rebalancing_guidance": {
                        "type": "string",
                        "description": "Guidance on portfolio rebalancing timing and approach",
                    },
                },
            },
        },
        "required": ["analysis_summary", "overall_confidence", "recommendations"],
        "additionalProperties": False,
    },
}

# Response format for OpenAI API calls
OPENAI_RESPONSE_FORMAT = {"type": "json_schema", "json_schema": INVESTMENT_ANALYSIS_SCHEMA}

# Alternative simplified schema for providers that don't support complex schemas
SIMPLE_INVESTMENT_SCHEMA = {
    "name": "simple_investment_analysis",
    "description": "Simplified investment recommendations",
    "schema": {
        "type": "object",
        "properties": {
            "recommendations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ticker": {"type": "string", "pattern": "^[A-Z]{1,5}$"},
                        "action": {"type": "string", "enum": ["BUY", "SELL", "HOLD"]},
                        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
                        "rationale": {"type": "string"},
                    },
                    "required": ["ticker", "action", "confidence", "rationale"],
                },
            }
        },
        "required": ["recommendations"],
    },
}

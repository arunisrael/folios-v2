#!/usr/bin/env python3
"""Simple parser to extract all recommendations from ANTHROPIC_RECOMMENDATIONS.md."""

import re
from pathlib import Path

def parse_all_recommendations():
    """Parse all BUY recommendations from the markdown."""
    md_path = Path("ANTHROPIC_RECOMMENDATIONS.md")
    content = md_path.read_text()

    # Split into strategy sections
    strategy_sections = re.split(r'###\s+Strategy\s+\d+:\s+(.+)', content)

    all_recommendations = {}

    for i in range(1, len(strategy_sections), 2):
        strategy_name = strategy_sections[i].strip()
        section_content = strategy_sections[i + 1]

        # Find where **Recommendations:** starts
        recs_start = section_content.find('**Recommendations:**')
        if recs_start == -1:
            continue

        # Only look at content after **Recommendations:**
        recs_section = section_content[recs_start:]
        recommendations = []

        # Find all lines that have BUY X%
        lines = recs_section.split('\n')

        # Track current ticker for multi-line format
        current_ticker = None
        current_company = None
        current_rationale = ""

        for j, line in enumerate(lines):
            # Check for ticker line (numbered)
            ticker_match = re.match(r'\d+\.\s+\*\*([A-Z\.]+)\s+\(([^)]+)\)\*\*', line.strip())

            if ticker_match:
                current_ticker = ticker_match.group(1)
                current_company = ticker_match.group(2)
                current_rationale = ""

                # Check if this is single-line format (has BUY on same line)
                if 'BUY' in line and '%' in line:
                    alloc_match = re.search(r'BUY\s+(\d+)%', line)
                    if alloc_match:
                        allocation = float(alloc_match.group(1))

                        # Extract rationale (text before BUY)
                        rationale_match = re.search(r'-\s+(.+?)[\.\s]+BUY', line)
                        rationale = rationale_match.group(1).strip() if rationale_match else ""

                        recommendations.append({
                            "ticker": current_ticker,
                            "company": current_company,
                            "allocation_percent": allocation,
                            "rationale": rationale,
                            "action": "BUY"
                        })
                        current_ticker = None  # Reset
                # Otherwise it's multi-line format, continue processing
                continue

            # Check for Action: BUY and Position Size in following lines (multi-line format)
            if current_ticker and '*   **Action:**' in line and 'BUY' in line:
                # Look for Position Size in next few lines
                for k in range(j+1, min(j+10, len(lines))):
                    if '*   **Position Size:**' in lines[k]:
                        # Extract allocation
                        size_match = re.search(r'(\d+(?:\.\d+)?)-?(\d+(?:\.\d+)?)?%', lines[k])
                        if size_match:
                            # Use midpoint if range, otherwise use single value
                            if size_match.group(2):
                                allocation = (float(size_match.group(1)) + float(size_match.group(2))) / 2
                            else:
                                allocation = float(size_match.group(1))

                            # Look for Investment Thesis
                            for m in range(j+1, min(j+15, len(lines))):
                                if '*   **Investment Thesis:**' in lines[m]:
                                    thesis = lines[m].replace('*   **Investment Thesis:**', '').strip()
                                    current_rationale = thesis
                                    break

                            recommendations.append({
                                "ticker": current_ticker,
                                "company": current_company,
                                "allocation_percent": allocation,
                                "rationale": current_rationale,
                                "action": "BUY"
                            })
                            current_ticker = None  # Reset
                            break

            # Check for sub-bullet format (Carl Icahn Corporate Raider)
            if line.strip().startswith('*   **') and 'BUY' in line and '%' in line:
                ticker_match = re.search(r'\*\*([A-Z\.]+)\s+\(([^)]+)\)\*\*', line)
                if ticker_match:
                    ticker = ticker_match.group(1)
                    company = ticker_match.group(2)

                    alloc_match = re.search(r'BUY\s+(\d+)%', line)
                    if alloc_match:
                        allocation = float(alloc_match.group(1))
                        rationale_match = re.search(r'-\s+(.+?)[\.\s]+BUY', line)
                        rationale = rationale_match.group(1).strip() if rationale_match else ""

                        # Only add if not already added
                        if not any(r['ticker'] == ticker for r in recommendations):
                            recommendations.append({
                                "ticker": ticker,
                                "company": company,
                                "allocation_percent": allocation,
                                "rationale": rationale,
                                "action": "BUY"
                            })

        if recommendations:
            all_recommendations[strategy_name] = recommendations

    return all_recommendations

if __name__ == "__main__":
    recs = parse_all_recommendations()

    print(f"Found {len(recs)} strategies with recommendations:\n")

    for strategy_name, recommendations in recs.items():
        print(f"{strategy_name}: {len(recommendations)} stocks")
        for rec in recommendations:
            print(f"  - {rec['ticker']}: {rec['allocation_percent']}%")
        print()

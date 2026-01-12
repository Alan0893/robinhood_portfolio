"""
Portfolio analyzer that fetches holdings and calculates percentages and sectors.
"""
import robin_stocks.robinhood as rh
import time
from collections import defaultdict
from typing import Dict, List, Tuple
from auth_handler import is_logged_in


# Cache for sector/industry data to avoid repeated requests
_sector_cache = {}

def get_stock_info_batch(symbols: List[str]) -> Dict[str, Dict]:
    """
    Get sector and industry information for multiple stocks using FMP profile endpoint.
    Uses caching to avoid repeated requests.
    
    Args:
        symbols: List of stock ticker symbols
        
    Returns:
        Dict mapping symbol to {sector, industry}
    """
    import os
    import requests
    
    results = {}
    symbols_to_fetch = []
    
    # Check cache first
    for symbol in symbols:
        if symbol in _sector_cache:
            results[symbol] = _sector_cache[symbol]
        else:
            symbols_to_fetch.append(symbol)
    
    if not symbols_to_fetch:
        return results
    
    # Get FMP API key
    fmp_api_key = os.getenv('FMP_API_KEY')
    if not fmp_api_key:
        print("FMP_API_KEY not set, skipping sector info")
        for symbol in symbols_to_fetch:
            results[symbol] = {'sector': 'N/A', 'industry': 'N/A'}
        return results
    
    # Use profile endpoint directly (free tier)
    try:
        for symbol in symbols_to_fetch:
            # Skip if already fetched successfully
            if symbol.upper() in results:
                continue
                
            try:
                # Use profile endpoint (free tier)
                url = f'https://financialmodelingprep.com/stable/profile'
                params = {
                    'symbol': symbol,
                    'apikey': fmp_api_key
                }
                
                print(f"Fetching sector info from FMP for {symbol}")
                response = requests.get(url, params=params, timeout=10)
                
                if response.status_code == 200:
                    try:
                        data = response.json()
                        
                        # FMP returns a list of company objects
                        if isinstance(data, list) and len(data) > 0:
                            company = data[0]
                            sector = company.get('sector', None)
                            industry = company.get('industry', None)
                            
                            # Handle None, empty string, or 'N/A' values
                            if not sector or sector == 'N/A' or (isinstance(sector, str) and sector.strip() == ''):
                                sector = 'N/A'
                            if not industry or industry == 'N/A' or (isinstance(industry, str) and industry.strip() == ''):
                                industry = 'N/A'
                            
                            result = {
                                'sector': sector,
                                'industry': industry
                            }
                            results[symbol.upper()] = result
                            _sector_cache[symbol.upper()] = result
                            print(f"  {symbol}: {sector} / {industry}")
                        else:
                            print(f"  {symbol}: No data in response")
                            results[symbol.upper()] = {'sector': 'N/A', 'industry': 'N/A'}
                    except (ValueError, KeyError) as json_error:
                        print(f"  {symbol}: Error parsing JSON response: {json_error}")
                        results[symbol.upper()] = {'sector': 'N/A', 'industry': 'N/A'}
                elif response.status_code == 402:
                    print(f"  {symbol}: FMP API 402 error - requires paid plan")
                    print(f"  Skipping remaining symbols")
                    for remaining_symbol in symbols_to_fetch[symbols_to_fetch.index(symbol):]:
                        if remaining_symbol.upper() not in results:
                            results[remaining_symbol.upper()] = {'sector': 'N/A', 'industry': 'N/A'}
                    return results
                else:
                    error_text = response.text[:200] if response.text else 'No error message'
                    print(f"  {symbol}: FMP API error {response.status_code}: {error_text}")
                    results[symbol.upper()] = {'sector': 'N/A', 'industry': 'N/A'}
                
                # Add delay between requests to respect rate limits
                time.sleep(0.3)
                    
            except Exception as symbol_error:
                print(f"Error fetching {symbol} from FMP: {symbol_error}")
                results[symbol.upper()] = {'sector': 'N/A', 'industry': 'N/A'}
    
    except Exception as e:
        print(f"Error in get_stock_info_batch: {e}")
        for symbol in symbols_to_fetch:
            if symbol.upper() not in results:
                results[symbol.upper()] = {'sector': 'N/A', 'industry': 'N/A'}
    
    # Fill in any missing symbols with N/A
    for symbol in symbols:
        if symbol.upper() not in results:
            results[symbol.upper()] = {'sector': 'N/A', 'industry': 'N/A'}
    
    return results


def get_portfolio_holdings(account_type='brokerage'):
    """
    Fetch all holdings from Robinhood portfolio.
    
    Args:
        account_type: 'brokerage' or 'roth_ira' (not currently used - shows all positions)
    
    Returns:
        List of dicts with holding information
    """
    try:
        positions = rh.get_open_stock_positions()
        
        if not positions:
            return []
        
        holdings = []
        
        for position in positions:
            try:
                
                instrument_url = position.get('instrument')
                if not instrument_url:
                    continue
                
                # Get stock symbol from instrument
                instrument = rh.get_instrument_by_url(instrument_url)
                if not instrument:
                    continue
                    
                symbol = instrument.get('symbol')
                if not symbol:
                    continue
                
                # Get position details
                quantity = float(position.get('quantity', 0))
                if quantity == 0:
                    continue
                
                # Get current price and additional quote data
                current_price = 0
                day_change = 0
                day_change_percent = 0
                company_name = symbol
                
                try:
                    quote = rh.get_quotes(symbol)
                    if quote and len(quote) > 0:
                        quote_data = quote[0]
                        current_price = float(quote_data.get('last_trade_price', 0))
                        
                        # Get day change information
                        previous_close = float(quote_data.get('previous_close', 0))
                        if previous_close > 0:
                            day_change = current_price - previous_close
                            day_change_percent = (day_change / previous_close) * 100
                        
                        # Get company name from instrument
                        company_name = instrument.get('simple_name', symbol)
                except Exception as price_error:
                    print(f"Warning: Could not get price for {symbol}: {price_error}")
                
                # Get average cost basis from position
                average_buy_price = float(position.get('average_buy_price', 0))
                
                # Calculate market value
                market_value = quantity * current_price if current_price > 0 else 0
                
                # Calculate gain/loss
                total_cost = quantity * average_buy_price if average_buy_price > 0 else 0
                gain_loss = market_value - total_cost
                gain_loss_percent = (gain_loss / total_cost * 100) if total_cost > 0 else 0
                
                holdings.append({
                    'symbol': symbol,
                    'company_name': company_name,
                    'quantity': quantity,
                    'current_price': current_price,
                    'average_buy_price': average_buy_price,
                    'market_value': market_value,
                    'day_change': day_change,
                    'day_change_percent': day_change_percent,
                    'gain_loss': gain_loss,
                    'gain_loss_percent': gain_loss_percent,
                    'instrument_url': instrument_url
                })
            except Exception as pos_error:
                print(f"Warning: Error processing position: {pos_error}")
                continue
        
        return holdings
    
    except Exception as e:
        error_msg = str(e)
        error_lower = error_msg.lower()
        # Check for various login-related error messages
        if any(keyword in error_lower for keyword in [
            'not logged in', 
            'authentication', 
            '401', 
            'unauthorized',
            'can only be called when logged in',
            'must be logged in'
        ]):
            raise Exception("Not logged in to Robinhood. Please login again.")
        raise Exception(f"Error fetching portfolio: {str(e)}")




def get_account_cash(account_type='brokerage'):
    """
    Get cash balance and buying power from Robinhood account.
    
    Args:
        account_type: 'brokerage' or 'roth_ira' (not currently used - shows all accounts)
    
    Returns:
        Dict with cash, buying_power, and portfolio_value
    """
    try:
        # Try load_phoenix_account first (newer unified API)
        buying_power = 0.0
        portfolio_equity = 0.0
        cash = 0.0
        phoenix_loaded = False
        
        try:
            phoenix_account = rh.load_phoenix_account()
            # Phoenix account returns a dictionary directly, not a list
            if phoenix_account and isinstance(phoenix_account, dict):
                phoenix_loaded = True
                
                # Debug: print all available keys to help identify the right field
                print(f"DEBUG: Phoenix account keys: {list(phoenix_account.keys())}")
                
                # Print ALL relevant cash and buying power fields from phoenix account
                print("\n=== PHOENIX ACCOUNT - ALL CASH AND BUYING POWER FIELDS ===")
                phoenix_relevant_fields = [
                    'uninvested_cash',
                    'withdrawable_cash',
                    'cash',
                    'buying_power',
                    'account_buying_power',
                    'extended_hours_buying_power',
                    'day_trade_buying_power',
                    'portfolio_equity',
                    'equity',
                    'margin_balances',
                    'cash_balances'
                ]
                
                for field in phoenix_relevant_fields:
                    value = phoenix_account.get(field)
                    if value is not None:
                        try:
                            if isinstance(value, dict):
                                print(f"  {field}: {value}")
                            else:
                                float_value = float(value) if value else 0
                                print(f"  {field}: {float_value}")
                        except (ValueError, TypeError):
                            print(f"  {field}: {value} (not a number)")
                
                # Check equities section
                equities = phoenix_account.get('equities', {})
                if isinstance(equities, dict):
                    print(f"\n  equities keys: {list(equities.keys())}")
                    for key in equities.keys():
                        value = equities.get(key)
                        if value is not None:
                            try:
                                if isinstance(value, dict):
                                    print(f"    equities.{key}: {value}")
                                else:
                                    float_value = float(value) if value else 0
                                    print(f"    equities.{key}: {float_value}")
                            except (ValueError, TypeError):
                                print(f"    equities.{key}: {value}")
                
                print("=== END OF PHOENIX ACCOUNT FIELDS ===\n")
                
                # Get cash (actual settled funds available for withdrawal)
                cash = float(phoenix_account.get('withdrawable_cash', 0) or 0)
                if cash == 0:
                    cash = float(phoenix_account.get('uninvested_cash', 0) or 0)
                
                # Buying power = amount you can use to buy stocks right now
                # Use portfolio_cash if available (equivalent to portfolio_cash in account profile)
                # Otherwise use uninvested_cash (cash not in stocks)
                buying_power = float(phoenix_account.get('portfolio_cash', 0) or 0)
                if buying_power == 0:
                    buying_power = float(phoenix_account.get('uninvested_cash', 0) or 0)
                
                # Check equities section for buying power fields
                if isinstance(equities, dict):
                    # Check for portfolio_cash in equities first
                    equities_portfolio_cash = float(equities.get('portfolio_cash', 0) or 0)
                    if equities_portfolio_cash > 0:
                        buying_power = equities_portfolio_cash
                    else:
                        # uninvested_cash in equities is the buying power
                        equities_uninvested = float(equities.get('uninvested_cash', 0) or 0)
                        if equities_uninvested > 0:
                            buying_power = equities_uninvested
                    
                    # Also check for cash in equities if we don't have it yet
                    if cash == 0:
                        cash = float(equities.get('cash', 0) or 0)
                
                # If buying_power is still 0, try other buying power fields as fallback
                if buying_power == 0:
                    buying_power = float(phoenix_account.get('extended_hours_buying_power', 0) or 0)
                if buying_power == 0:
                    buying_power = float(phoenix_account.get('day_trade_buying_power', 0) or 0)
                if buying_power == 0:
                    buying_power = float(phoenix_account.get('account_buying_power', 0) or 0)
                if buying_power == 0:
                    buying_power = float(phoenix_account.get('buying_power', 0) or 0)
                
                # Ensure buying power is never negative
                if buying_power < 0:
                    buying_power = 0.0
                
                # Don't fall back to negative cash - if we don't have positive buying power, it should be 0
                # Only use cash if it's positive
                if buying_power == 0 and cash > 0:
                    buying_power = cash
                elif buying_power == 0:
                    buying_power = 0.0
                
                portfolio_equity = float(phoenix_account.get('portfolio_equity', 0) or 0)
                print(f"Phoenix account data - cash: {cash}, buying_power: {buying_power}, equity: {portfolio_equity}")
        except Exception as phoenix_error:
            print(f"Could not load phoenix account: {phoenix_error}")
        
        # Fallback to load_account_profile ONLY if phoenix didn't load at all
        if not phoenix_loaded:
            try:
                profile = rh.load_account_profile()
                if profile:
                    print(f"DEBUG: Account profile keys: {list(profile.keys())}")
                    
                    # Print ALL relevant cash and buying power fields
                    print("\n=== ALL CASH AND BUYING POWER FIELDS ===")
                    relevant_fields = [
                        'buying_power',
                        'onbp',
                        'portfolio_cash',
                        'cash',
                        'cash_available_for_withdrawal',
                        'cash_available_for_withdrawal_without_margin',
                        'unsettled_funds',
                        'unsettled_debit',
                        'cash_held_for_orders',
                        'uncleared_deposits',
                        'sma',
                        'sma_held_for_orders',
                        'crypto_buying_power',
                        'max_ach_early_access_amount',
                        'dynamic_instant_limit',
                        'user_real_instant_limit',
                        'user_dynamic_instant_limit'
                    ]
                    
                    for field in relevant_fields:
                        value = profile.get(field)
                        if value is not None:
                            try:
                                float_value = float(value) if value else 0
                                print(f"  {field}: {float_value}")
                            except (ValueError, TypeError):
                                print(f"  {field}: {value} (not a number)")
                    
                    # Also check cash_balances and margin_balances if they exist
                    if 'cash_balances' in profile:
                        print(f"\n  cash_balances: {profile.get('cash_balances')}")
                    if 'margin_balances' in profile:
                        print(f"  margin_balances: {profile.get('margin_balances')}")
                    
                    print("=== END OF FIELDS ===\n")
                    
                    # Get cash (actual settled funds available for withdrawal)
                    cash = float(profile.get('cash_available_for_withdrawal', 0) or 0)
                    if cash == 0:
                        cash = float(profile.get('cash', 0) or 0)
                    
                    # Buying power = amount you can use to buy stocks right now
                    # Use 'portfolio_cash' - this is the actual cash available in the portfolio
                    # (buying_power and onbp include margin/instant deposits that may not be accurate)
                    buying_power = float(profile.get('portfolio_cash', 0) or 0)
                    
                    # Ensure buying power is never negative - if portfolio_cash is negative or missing, use 0
                    if buying_power < 0:
                        buying_power = 0.0
                    
                    # Don't fall back to negative cash values - if portfolio_cash is 0, buying power should be 0
                    # Only use positive fallback values
                    if buying_power == 0:
                        cash_available = float(profile.get('cash_available_for_withdrawal', 0) or 0)
                        if cash_available > 0:
                            buying_power = cash_available
            except Exception as profile_error:
                print(f"Could not load account profile: {profile_error}")
        
        print(f"Account info - Cash: {cash}, Buying Power: {buying_power}, Portfolio Equity: {portfolio_equity}")
        
        return {
            'cash': cash,
            'buying_power': buying_power,
            'portfolio_value': portfolio_equity
        }
    except Exception as e:
        print(f"Warning: Could not get account cash: {e}")
        import traceback
        traceback.print_exc()
        return {
            'cash': 0.0,
            'buying_power': 0.0,
            'portfolio_value': 0.0
        }


def analyze_portfolio(account_type='brokerage') -> Dict:
    """
    Analyze portfolio and calculate stock percentages and sector allocations.
    
    Args:
        account_type: 'brokerage' or 'roth_ira'
    
    Returns:
        Dict with portfolio analysis including:
        - total_value: Total portfolio value (stocks + cash)
        - stock_value: Value of stocks only
        - cash: Cash balance
        - holdings: List of holdings with percentages
    """
    # Don't check login status here - let the actual API calls fail if not logged in
    # This avoids false negatives from is_logged_in() being too strict
    holdings = get_portfolio_holdings(account_type)
    
    # Get account cash information
    account_info = get_account_cash(account_type)
    cash = account_info['cash']
    buying_power = account_info['buying_power']
    
    # Calculate stock value
    stock_value = sum(h['market_value'] for h in holdings)
    
    # Total portfolio value = stocks + cash
    # Use buying_power if it's higher (includes margin/instant buying power)
    total_value = stock_value + max(cash, buying_power)
    
    if not holdings and cash == 0:
        return {
            'total_value': 0,
            'stock_value': 0,
            'cash': 0,
            'holdings': []
        }
    
    # Calculate percentage for each holding (based on stock value only, not including cash)
    for holding in holdings:
        if stock_value > 0:
            holding['percentage'] = (holding['market_value'] / stock_value) * 100
        else:
            holding['percentage'] = 0
    
    # Fetch sector and industry information for all holdings
    if holdings:
        symbols = [h['symbol'] for h in holdings]
        print(f"Fetching sector info for {len(symbols)} stocks...")
        sector_info = get_stock_info_batch(symbols)
        
        # Add sector and industry to each holding
        for holding in holdings:
            symbol = holding['symbol'].upper()
            if symbol in sector_info:
                sector = sector_info[symbol].get('sector', 'N/A')
                industry = sector_info[symbol].get('industry', 'N/A')
                holding['sector'] = sector
                holding['industry'] = industry
                # Debug for NVDA
                if symbol == 'NVDA':
                    print(f"DEBUG: NVDA sector_info entry: {sector_info[symbol]}")
                    print(f"DEBUG: NVDA assigned sector: {holding['sector']}")
            else:
                holding['sector'] = 'N/A'
                holding['industry'] = 'N/A'
                # Debug for NVDA
                if symbol == 'NVDA':
                    print(f"DEBUG: NVDA not found in sector_info. Available keys: {list(sector_info.keys())}")
    
    # Sort holdings by market value (descending)
    holdings.sort(key=lambda x: x['market_value'], reverse=True)
    
    return {
        'total_value': total_value,
        'stock_value': stock_value,
        'cash': cash,
        'buying_power': buying_power,
        'holdings': holdings
    }


"""
Flask web application to display Robinhood portfolio analysis.
"""
from flask import Flask, render_template, jsonify, request, session
from auth_handler import login, logout, is_logged_in
from portfolio_analyzer import analyze_portfolio
import os
import time
import datetime
import json
import finnhub
import csv
from io import StringIO

app = Flask(__name__)
app.secret_key = os.urandom(24)
app.config['SESSION_PERMANENT'] = False
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours

# Cache for stock details to reduce API calls
_stock_details_cache = {}
_cache_timestamps = {}
CACHE_DURATION = 60  # Cache for 1 minute


@app.route('/')
def index():
    """Main dashboard page."""
    return render_template('index.html')


@app.route('/compare')
def compare():
    """Stock comparison page."""
    return render_template('compare.html')


@app.route('/what-if')
def what_if():
    """What-if analysis page."""
    # Check if user is logged in
    if not is_logged_in():
        return render_template('what-if.html', requires_login=True)
    return render_template('what-if.html', requires_login=False)


@app.route('/api/check-login', methods=['GET'])
def api_check_login():
    """API endpoint to check if user is logged in."""
    try:
        logged_in = is_logged_in()
        if logged_in:
            session['logged_in'] = True
        else:
            session['logged_in'] = False
        return jsonify({'success': True, 'logged_in': logged_in})
    except Exception as e:
        session['logged_in'] = False
        return jsonify({'success': True, 'logged_in': False})


@app.route('/api/login', methods=['POST'])
def api_login():
    """API endpoint to handle login."""
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        mfa_code = data.get('mfa_code')
        
        success = login(username=username, password=password, mfa_code=mfa_code)
        
        if success:
            session['logged_in'] = True
            return jsonify({'success': True, 'message': 'Login successful'})
        else:
            session['logged_in'] = False
            return jsonify({'success': False, 'message': 'Login failed'}), 401
    
    except Exception as e:
        error_msg = str(e)
        session['logged_in'] = False
        # Check if device approval is needed
        if 'DEVICE_APPROVAL_NEEDED' in error_msg:
            return jsonify({
                'success': False,
                'message': error_msg,
                'requires_device_approval': True
            }), 401
        return jsonify({'success': False, 'message': error_msg}), 500


@app.route('/api/logout', methods=['POST'])
def api_logout():
    """API endpoint to handle logout."""
    try:
        logout()
        session.pop('logged_in', None)
        return jsonify({'success': True, 'message': 'Logged out successfully'})
    except Exception as e:
        session.pop('logged_in', None)
        return jsonify({'success': False, 'message': str(e)}), 500


@app.route('/api/stock-details/<symbol>', methods=['GET'])
def api_stock_details(symbol):
    """API endpoint to get detailed stock information."""
    # Check cache first
    if symbol in _stock_details_cache:
        cache_time = _cache_timestamps.get(symbol, 0)
        if time.time() - cache_time < CACHE_DURATION:
            print(f"Returning cached data for {symbol}")
            return jsonify({
                'success': True,
                'data': _stock_details_cache[symbol]
            })
    
    stock_details = {}
    
    # Try Robinhood API first 
    try:
        import robin_stocks.robinhood as rh
        quote = rh.get_quotes(symbol)
        if quote and len(quote) > 0:
            quote_data = quote[0]
            last_trade_price = float(quote_data.get('last_trade_price', 0)) or None
            previous_close = float(quote_data.get('previous_close', 0)) or None
            
            stock_details.update({
                'previous_close': previous_close,
                'bid': float(quote_data.get('bid_price', 0)) or None,
                'bid_size': int(quote_data.get('bid_size', 0)) or None,
                'ask': float(quote_data.get('ask_price', 0)) or None,
                'ask_size': int(quote_data.get('ask_size', 0)) or None,
                'last_trade_price': last_trade_price,
                'after_hours_price': float(quote_data.get('last_extended_hours_trade_price', 0)) or None,
                'trading_halted': quote_data.get('trading_halted', False),
            })
            
            # Set current_price from Robinhood if available
            if last_trade_price:
                stock_details['current_price'] = last_trade_price
                stock_details['price'] = last_trade_price  # alias
            
            # Calculate day change if we have both
            if last_trade_price and previous_close:
                day_change = last_trade_price - previous_close
                day_change_percent = (day_change / previous_close) * 100 if previous_close > 0 else 0
                stock_details['day_change'] = day_change
                stock_details['day_change_percent'] = day_change_percent
            
            print(f"Got Robinhood data for {symbol}")
    except Exception as rh_error:
        print(f"Robinhood API error for {symbol}: {rh_error}")
    
    # Use Finnhub API 
    try:
        api_key = os.getenv('FINNHUB_API_KEY')
        if not api_key:
            print("FINNHUB_API_KEY not set in environment variables, skipping Finnhub.")
            # If no API key, skip Finnhub and return what we have from Robinhood
            if stock_details:
                _stock_details_cache[symbol] = stock_details
                _cache_timestamps[symbol] = time.time()
                return jsonify({'success': True, 'data': stock_details})
            else:
                return jsonify({
                    'success': False,
                    'message': 'FINNHUB_API_KEY not set and no Robinhood data available'
                }), 500
        
        finnhub_client = finnhub.Client(api_key=api_key)
        
        # Get quote
        quote = finnhub_client.quote(symbol)
        if quote:
            # Current price (most important)
            current_price = quote.get('c')  # current price
            if current_price:
                stock_details['current_price'] = current_price
                stock_details['price'] = current_price  # alias for compatibility
            
            # Previous close
            previous_close = quote.get('pc')
            if previous_close:
                stock_details['previous_close'] = previous_close
                
                # Calculate day change if we have both current and previous
                if current_price:
                    day_change = current_price - previous_close
                    day_change_percent = (day_change / previous_close) * 100 if previous_close > 0 else 0
                    stock_details['day_change'] = day_change
                    stock_details['day_change_percent'] = day_change_percent
            
            if not stock_details.get('open'):
                stock_details['open'] = quote.get('o')  # open
            if not stock_details.get('day_high'):
                stock_details['day_high'] = quote.get('h')  # high
            if not stock_details.get('day_low'):
                stock_details['day_low'] = quote.get('l')  # low
            if not stock_details.get('volume'):
                stock_details['volume'] = quote.get('v')  # volume
            print(f"Got Finnhub quote data for {symbol}")
        
        # Get company profile for market cap, sector, industry and other info
        try:
            profile = finnhub_client.company_profile2(symbol=symbol)
            print(f"Profile response for {symbol}: {profile}")
            if profile and isinstance(profile, dict):
                if not stock_details.get('market_cap'):
                    market_cap = profile.get('marketCapitalization')
                    if market_cap:
                        stock_details['market_cap'] = market_cap * 1000000  # Convert to actual value
                
                # Try different field names for sector
                if not stock_details.get('sector'):
                    sector = profile.get('finnhubIndustry') or profile.get('gicsSector') or profile.get('sector')
                    if sector:
                        stock_details['sector'] = sector
                        print(f"Found sector for {symbol}: {sector}")
                
                # Try different field names for industry
                if not stock_details.get('industry'):
                    industry = profile.get('finnhubIndustry') or profile.get('gicsSubIndustry') or profile.get('industry')
                    if industry:
                        stock_details['industry'] = industry
                        print(f"Found industry for {symbol}: {industry}")
                
                if not stock_details.get('company_name'):
                    stock_details['company_name'] = profile.get('name') or profile.get('companyName')
                
                # Some ETFs might have P/E in profile
                if not stock_details.get('pe_ratio'):
                    pe_profile = profile.get('pe')
                    if pe_profile:
                        try:
                            pe_val = float(pe_profile)
                            if pe_val > 0:
                                stock_details['pe_ratio'] = pe_val
                        except (ValueError, TypeError):
                            pass
                print(f"Got Finnhub profile data for {symbol}")
        except Exception as prof_error:
            print(f"Finnhub profile error for {symbol}: {prof_error}")
        
        # Get company basic financials for P/E ratio, beta, etc.
        try:
            financials = finnhub_client.company_basic_financials(symbol, 'all')
            if financials and 'metric' in financials:
                metrics = financials['metric']
                
                # Try multiple P/E ratio metric names (different APIs may use different names)
                # Prefer TTM (Trailing Twelve Months) as it's what most financial sites show
                if not stock_details.get('pe_ratio'):
                    pe = None
                    pe_metric_used = None
                    # Try common P/E ratio field names - prioritize TTM (most common)
                    for pe_field in ['peRatioTTM', 'peNormalizedAnnual', 'peAnnual', 'peRatio', 'pe']:
                        if pe_field in metrics and metrics[pe_field] is not None:
                            try:
                                pe = float(metrics[pe_field])
                                if pe > 0:  # Only use positive P/E ratios
                                    pe_metric_used = pe_field
                                    break
                            except (ValueError, TypeError):
                                continue
                    
                    if pe:
                        stock_details['pe_ratio'] = pe
                        if pe_metric_used and pe_metric_used != 'peRatioTTM':
                            print(f"Note: Using {pe_metric_used} for P/E ratio for {symbol} (TTM not available)")
                    else:
                        # Log available metrics for debugging
                        print(f"No P/E ratio found for {symbol}. Available metrics: {list(metrics.keys())[:10]}")
                
                if not stock_details.get('beta'):
                    beta = metrics.get('beta')
                    if beta:
                        stock_details['beta'] = float(beta)
                if not stock_details.get('dividend_yield'):
                    # Try multiple dividend yield field names
                    div_yield = None
                    for div_field in ['dividendYieldIndicatedAnnual', 'dividendYield', 'dividendYieldTTM']:
                        if div_field in metrics and metrics[div_field] is not None:
                            try:
                                div_yield = float(metrics[div_field])
                                # If it's already a percentage (0-100), divide by 100; if decimal (0-1), use as is
                                if div_yield > 1:
                                    div_yield = div_yield / 100
                                break
                            except (ValueError, TypeError):
                                continue
                    if div_yield:
                        stock_details['dividend_yield'] = div_yield
                if not stock_details.get('fifty_two_week_high'):
                    high_52w = metrics.get('52WeekHigh')
                    if high_52w:
                        stock_details['fifty_two_week_high'] = float(high_52w)
                        stock_details['high_52_week'] = float(high_52w)  # alias for comparison page
                if not stock_details.get('fifty_two_week_low'):
                    low_52w = metrics.get('52WeekLow')
                    if low_52w:
                        stock_details['fifty_two_week_low'] = float(low_52w)
                        stock_details['low_52_week'] = float(low_52w)  # alias for comparison page
                if not stock_details.get('average_volume'):
                    avg_vol = metrics.get('averageDailyVolume10Day')
                    if avg_vol:
                        stock_details['average_volume'] = int(avg_vol)
                print(f"Got Finnhub financials for {symbol}")
        except Exception as fin_error:
            print(f"Finnhub financials error for {symbol}: {fin_error}")
            import traceback
            traceback.print_exc()
            
    except Exception as fh_error:
        print(f"Finnhub API error for {symbol}: {fh_error}")
        # Don't fail completely if we have Robinhood data
        if not stock_details:
            return jsonify({
                'success': False,
                'message': f'Finnhub API error: {str(fh_error)}'
            }), 500
    
    # Try FMP API for sector/industry if not already set
    if not stock_details.get('sector') or not stock_details.get('industry'):
        try:
            import requests
            fmp_api_key = os.getenv('FMP_API_KEY')
            if fmp_api_key:
                # Try profile endpoint first (free tier)
                url = f'https://financialmodelingprep.com/stable/profile'
                params = {
                    'symbol': symbol,
                    'apikey': fmp_api_key
                }
                response = requests.get(url, params=params, timeout=10)
                if response.status_code == 200:
                    data = response.json()
                    if isinstance(data, list) and len(data) > 0:
                        company = data[0]
                        if not stock_details.get('sector'):
                            sector = company.get('sector')
                            if sector and sector != 'N/A':
                                stock_details['sector'] = sector
                        if not stock_details.get('industry'):
                            industry = company.get('industry')
                            if industry and industry != 'N/A':
                                stock_details['industry'] = industry
                        print(f"Got FMP sector/industry data for {symbol}")
        except Exception as fmp_error:
            print(f"FMP API error for sector/industry for {symbol}: {fmp_error}")
    
    # If we got any data, cache and return it (even if incomplete)
    if stock_details:
        _stock_details_cache[symbol] = stock_details
        _cache_timestamps[symbol] = time.time()
        return jsonify({
            'success': True,
            'data': stock_details
        })
    else:
        return jsonify({
            'success': False,
            'message': 'Unable to fetch stock details from available sources'
        }), 500


@app.route('/api/search-stocks', methods=['GET'])
def api_search_stocks():
    """API endpoint to search for stocks by symbol or company name."""
    try:
        query = request.args.get('q', '').strip().upper()
        
        if not query or len(query) < 1:
            return jsonify({
                'success': True,
                'data': []
            })
        
        # Use Finnhub API for stock search
        api_key = os.getenv('FINNHUB_API_KEY')
        if not api_key:
            return jsonify({
                'success': False,
                'message': 'FINNHUB_API_KEY not set'
            }), 500
        
        finnhub_client = finnhub.Client(api_key=api_key)
        
        # Use Finnhub's symbol search endpoint
        try:
            search_results = finnhub_client.symbol_lookup(query)
            
            results = []
            if search_results and 'result' in search_results:
                for item in search_results['result'][:10]:  # Limit to 10 results
                    symbol = item.get('symbol', '')
                    description = item.get('description', '')
                    display_symbol = item.get('displaySymbol', symbol)
                    type_str = item.get('type', '')
                    
                    # Filter to only show stocks (not options, forex, etc.)
                    if type_str in ['Common Stock', 'Equity', ''] or not type_str:
                        results.append({
                            'symbol': symbol,
                            'displaySymbol': display_symbol,
                            'description': description,
                            'type': type_str
                        })
            
            return jsonify({
                'success': True,
                'data': results
            })
            
        except Exception as fh_error:
            print(f"Finnhub search error: {fh_error}")
            return jsonify({
                'success': False,
                'message': f'Search error: {str(fh_error)}'
            }), 500
            
    except Exception as e:
        print(f"Error in search-stocks endpoint: {e}")
        return jsonify({
            'success': False,
            'message': f'Error searching stocks: {str(e)}'
        }), 500


@app.route('/api/portfolio', methods=['GET'])
def api_portfolio():
    """API endpoint to get portfolio analysis."""
    try:
        # Try to get portfolio - if it fails due to auth, we'll catch it
        analysis = analyze_portfolio()
        return jsonify({
            'success': True,
            'data': analysis
        })
    except Exception as e:
        import traceback
        error_msg = str(e)
        error_lower = error_msg.lower()
        
        # Log the full error for debugging
        print(f"Portfolio error: {error_msg}")
        print(f"Traceback: {traceback.format_exc()}")
        
        # Check if it's a login/authentication error
        login_keywords = [
            'not logged in', 
            'login', 
            '401', 
            'unauthorized', 
            'authentication', 
            'token', 
            'can only be called when logged in',
            'must be logged in'
        ]
        if any(keyword in error_lower for keyword in login_keywords):
            session.pop('logged_in', None)
            return jsonify({
                'success': False,
                'message': 'Not logged in. Please login again.',
                'requires_login': True
            }), 401
        
        # For other errors, return the error message
        return jsonify({
            'success': False,
            'message': error_msg
        }), 500


@app.route('/api/export-portfolio')
def api_export_portfolio():
    """Export portfolio data as JSON or CSV for use with external AI tools."""
    if not is_logged_in():
        return jsonify({'success': False, 'message': 'Please login first'}), 401
    
    try:
        from flask import Response
        
        # Get export format from query params (default: json)
        export_format = request.args.get('format', 'json').lower()
        
        # Get portfolio data directly
        data = analyze_portfolio()
        
        if not data or not data.get('holdings'):
            return jsonify({'success': False, 'message': 'No portfolio data available'}), 500
        
        holdings = data.get('holdings', [])
        
        # Calculate total gain/loss from holdings
        total_gain_loss = 0
        total_cost_basis = 0
        for h in holdings:
            total_gain_loss += h.get('gain_loss', 0)
            quantity = h.get('quantity', 0)
            avg_buy_price = h.get('average_buy_price', h.get('average_cost', 0))
            total_cost_basis += quantity * avg_buy_price
        
        # Calculate total gain/loss percentage
        total_gain_loss_percent = (total_gain_loss / total_cost_basis * 100) if total_cost_basis > 0 else 0
        
        # Build export data
        export_data = {
            'exported_at': datetime.datetime.now().isoformat(),
            'summary': {
                'total_portfolio_value': data.get('total_value', 0),
                'stock_value': data.get('stock_value', 0),
                'cash': data.get('cash', 0),
                'buying_power': data.get('buying_power', 0),
                'total_gain_loss': total_gain_loss,
                'total_gain_loss_percent': total_gain_loss_percent,
                'number_of_holdings': len(holdings)
            },
            'holdings': []
        }
        
        for h in holdings:
            quantity = h.get('quantity', 0)
            avg_buy_price = h.get('average_buy_price', h.get('average_cost', 0))
            cost_basis = quantity * avg_buy_price
            
            export_data['holdings'].append({
                'symbol': h.get('symbol', 'N/A'),
                'company': h.get('name', h.get('company_name', 'N/A')),
                'sector': h.get('sector', 'Unknown'),
                'industry': h.get('industry', 'Unknown'),
                'current_price': h.get('current_price', 0),
                'day_change': h.get('day_change', 0),
                'day_change_percent': h.get('day_change_percent', 0),
                'day_change_dollar': (h.get('day_change', 0) * quantity),
                'shares': quantity,
                'avg_buy_price': avg_buy_price,
                'cost_basis': cost_basis,
                'market_value': h.get('market_value', 0),
                'gain_loss': h.get('gain_loss', 0),
                'gain_loss_percent': h.get('gain_loss_percent', 0),
                'portfolio_percent': h.get('percentage', h.get('allocation', 0))
            })
        
        if export_format == 'csv':
            # Generate CSV
            output = StringIO()
            writer = csv.writer(output)
            
            # Write header (matches table columns exactly)
            writer.writerow(['Symbol', 'Company', 'Sector', 'Industry', 'Current Price', 
                           'Day Change', 'Day Change $', 'Day Change %', 'Shares', 'Avg Buy Price',
                           'Cost Basis', 'Market Value', 'Gain/Loss', 'Gain/Loss %', 
                           '% of Portfolio'])
            
            # Write holdings
            for h in export_data['holdings']:
                writer.writerow([
                    h['symbol'], h['company'], h['sector'], h.get('industry', 'Unknown'), 
                    h['current_price'], h['day_change'], h.get('day_change_dollar', 0), 
                    h['day_change_percent'], h['shares'], h['avg_buy_price'], 
                    h['cost_basis'], h['market_value'], h['gain_loss'], 
                    h['gain_loss_percent'], h['portfolio_percent']
                ])
            
            # Add summary at end
            writer.writerow([])
            writer.writerow(['Summary'])
            writer.writerow(['Total Portfolio Value', export_data['summary']['total_portfolio_value']])
            writer.writerow(['Stock Value', export_data['summary']['stock_value']])
            writer.writerow(['Cash', export_data['summary']['cash']])
            writer.writerow(['Buying Power', export_data['summary']['buying_power']])
            writer.writerow(['Total Gain/Loss', export_data['summary']['total_gain_loss']])
            writer.writerow(['Total Gain/Loss %', export_data['summary']['total_gain_loss_percent']])
            
            csv_output = output.getvalue()
            
            return Response(
                csv_output,
                mimetype='text/csv',
                headers={'Content-Disposition': 'attachment; filename=robinhood_portfolio.csv'}
            )
        
        else:
            # JSON format (default) - also create a text format for AI
            text_format = request.args.get('text', 'false').lower() == 'true'
            
            if text_format:
                # Plain text format optimized for pasting into AI chatbots
                text_output = f"""ROBINHOOD PORTFOLIO EXPORT
Exported: {export_data['exported_at']}

=== PORTFOLIO SUMMARY ===
Total Portfolio Value: ${export_data['summary']['total_portfolio_value']:,.2f}
Stock Value: ${export_data['summary']['stock_value']:,.2f}
Cash: ${export_data['summary']['cash']:,.2f}
Buying Power: ${export_data['summary']['buying_power']:,.2f}
Total Gain/Loss: ${export_data['summary']['total_gain_loss']:,.2f} ({export_data['summary']['total_gain_loss_percent']:.2f}%)
Number of Holdings: {export_data['summary']['number_of_holdings']}

=== HOLDINGS ===
"""
                for h in export_data['holdings']:
                    text_output += f"""
{h['symbol']} ({h['company']})
  Sector: {h['sector']} | Industry: {h.get('industry', 'Unknown')}
  Current Price: ${h['current_price']:.2f} | Day Change: ${h.get('day_change_dollar', 0):,.2f} ({h['day_change_percent']:.2f}%)
  Shares: {h['shares']:.4f} | Avg Buy Price: ${h['avg_buy_price']:.2f}
  Cost Basis: ${h['cost_basis']:,.2f} | Market Value: ${h['market_value']:,.2f}
  Gain/Loss: ${h['gain_loss']:,.2f} ({h['gain_loss_percent']:.2f}%)
  Portfolio Allocation: {h['portfolio_percent']:.2f}%
"""
                
                return Response(
                    text_output,
                    mimetype='text/plain',
                    headers={'Content-Disposition': 'attachment; filename=robinhood_portfolio.txt'}
                )
            
            # Standard JSON
            return Response(
                json.dumps(export_data, indent=2),
                mimetype='application/json',
                headers={'Content-Disposition': 'attachment; filename=robinhood_portfolio.json'}
            )
    
    except Exception as e:
        print(f"Export error: {e}")
        return jsonify({'success': False, 'message': str(e)}), 500


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8082))
    app.run(debug=False, host='0.0.0.0', port=port)


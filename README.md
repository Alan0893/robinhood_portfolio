# Robinhood Portfolio Tracker

A Flask web application for tracking and analyzing your Robinhood portfolio with real-time data, sector allocation charts, and investment simulation tools.

## Features

### Portfolio Dashboard

- **Real-time portfolio value** with stock value and buying power
- **Holdings breakdown** with sortable columns (symbol, price, gain/loss, etc.)
- **Interactive pie charts** for stock allocation and sector distribution
- **Portfolio summary** showing total gain/loss, today's change, top performers
- **Click on any stock** for detailed statistics modal

### Stock Search & Comparison

- Search for any stock by symbol or company name
- View detailed stock information including:
  - Current price and day change
  - P/E ratio, market cap, beta
  - 52-week high/low
  - Sector and industry classification

### What-If Analysis

- Simulate investments before making them
- See how a purchase would affect your portfolio allocation
- Track saved scenarios over time with performance updates
- Scenarios stored locally in browser

### Export Options

- **JSON** - Structured data for programmatic use
- **CSV** - Spreadsheet-compatible format
- **Text** - Plain text optimized for AI chatbots for further analysis

## Installation

### Prerequisites

- Python 3.8 or higher
- Robinhood account

### Setup

1. **Clone the repository**

   ```bash
   git clone git@github.com:Alan0893/robinhood_portfolio.git
   cd robinhood_portfolio
   ```

2. **Create a virtual environment**

   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**

   ```bash
   pip3 install -r requirements.txt
   ```

4. **Set up environment variables**

   Create a `.env` file in the project root:

   ```env
   FINNHUB_API_KEY=your_finnhub_api_key
   FMP_API_KEY=your_fmp_api_key  # Optional, for additional sector data
   ```

   - Get a free Finnhub API key at [finnhub.io](https://finnhub.io/)
   - Get a free FMP API key at [financialmodelingprep.com](https://financialmodelingprep.com/) (optional)

5. **Run the application**

   ```bash
   python3 app.py
   ```

6. **Open in browser**
   ```
   http://localhost:8082
   ```

## Usage

### First-Time Login

1. Enter your Robinhood username and password
2. If prompted, approve the device in your Robinhood mobile app
3. Your portfolio will load automatically

### Navigating the Dashboard

- **Stats Cards**: View total portfolio value, stock value, and number of holdings
- **Charts**: Interactive pie charts show stock and sector allocation
- **Holdings Table**: Click column headers to sort, click rows for stock details
- **Export**: Click the export button to download your portfolio data

### What-If Analysis

1. Navigate to the "What If" page
2. Search for a stock
3. Enter an investment amount
4. View how the investment would impact your portfolio
5. Save scenarios to track performance over time

## Project Structure

```
robinhood-portfolio-tracker/
├── app.py                 # Flask application and API routes
├── auth_handler.py        # Robinhood authentication
├── portfolio_analyzer.py  # Portfolio data processing
├── requirements.txt       # Python dependencies
├── static/
│   └── css/
│       ├── index.css      # Main dashboard styles
│       ├── compare.css    # Stock comparison styles
│       └── what-if.css    # What-if page styles
└── templates/
    ├── index.html         # Portfolio dashboard
    ├── compare.html       # Stock search/comparison
    └── what-if.html       # Investment simulator
```

## API Endpoints

| Endpoint                      | Method | Description                         |
| ----------------------------- | ------ | ----------------------------------- |
| `/api/login`                  | POST   | Authenticate with Robinhood         |
| `/api/logout`                 | POST   | Log out of Robinhood                |
| `/api/check-login`            | GET    | Check authentication status         |
| `/api/portfolio`              | GET    | Get portfolio holdings and analysis |
| `/api/stock-details/<symbol>` | GET    | Get detailed stock information      |
| `/api/search-stocks`          | GET    | Search for stocks by query          |
| `/api/export-portfolio`       | GET    | Export portfolio (JSON/CSV/Text)    |

## Technologies Used

- **Backend**: Flask (Python)
- **Frontend**: Vanilla JavaScript, Chart.js
- **APIs**:
  - [robin-stocks](https://github.com/jmfernandes/robin_stocks) - Robinhood API
  - [Finnhub](https://finnhub.io/) - Stock data and financials
  - [FMP](https://financialmodelingprep.com/) - Sector/industry data
- **Storage**: Browser localStorage for user preferences and scenarios

## Security Notes

- Credentials are sent directly to Robinhood's API (never stored on server)
- Session tokens are managed by robin-stocks library
- What-if scenarios are stored only in your browser's localStorage
- No portfolio data is stored server-side

## Troubleshooting

### "Device Approval Required"

- Check your Robinhood mobile app for a notification
- Approve the login request and try again

### Stock data not loading

- Verify your `FINNHUB_API_KEY` is set correctly
- Check Finnhub API rate limits (60 calls/minute on free tier)

### Sector information showing "N/A"

- Add an `FMP_API_KEY` for better sector/industry coverage
- Some ETFs and newer stocks may not have sector data

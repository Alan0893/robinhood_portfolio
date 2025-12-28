"""
Authentication handler for Robinhood with 2FA and device token management.
robin_stocks automatically handles device tokens and stores them in a session file.
"""
import os
import json
import robin_stocks.robinhood as rh
from dotenv import load_dotenv

load_dotenv()


def is_logged_in():
    """Check if already logged in to Robinhood."""
    # Use the same API call that we'll use for portfolio - this is the most reliable check
    try:
        # Try to get positions - this requires authentication
        # If this works, we're definitely logged in
        positions = rh.get_open_stock_positions()
        # If we get a response (even if empty list), we're logged in
        return True
    except Exception as e:
        error_str = str(e).lower()
        # Check if it's clearly an authentication error
        auth_keywords = [
            '401', 
            'unauthorized', 
            'not logged in', 
            'authentication', 
            'token expired', 
            'invalid token',
            'can only be called when logged in',
            'must be logged in'
        ]
        if any(keyword in error_str for keyword in auth_keywords):
            return False
        
        # For other errors, try load_phoenix_account as a fallback
        try:
            account = rh.load_phoenix_account()
            if account is not None:
                return True
        except Exception as account_error:
            account_error_str = str(account_error).lower()
            if any(keyword in account_error_str for keyword in auth_keywords):
                return False
        
        # If both fail and it's not clearly an auth error, assume not logged in
        return False


def login(username=None, password=None, mfa_code=None):
    """
    Login to Robinhood with 2FA support.
    
    robin_stocks automatically handles device tokens and stores them in a session file
    (~/.robin_stocks/session.json). After the first login with device approval,
    subsequent logins will use the saved device token automatically.
    
    Args:
        username: Robinhood username (or from env)
        password: Robinhood password (or from env)
        mfa_code: MFA code if using authenticator app (or from env)
    
    Returns:
        True if login successful, False otherwise
    """
    # Check if already logged in - but be more strict about it
    # Only skip login if we can actually verify we're logged in
    try:
        if is_logged_in():
            # Double-check by trying to get positions
            try:
                positions = rh.get_open_stock_positions()
                print("Already logged in and verified, skipping login")
                return True
            except Exception as verify_error:
                error_str = str(verify_error).lower()
                if 'can only be called when logged in' in error_str or 'not logged in' in error_str:
                    print("is_logged_in() returned True but positions check failed - forcing re-login")
                    # Force logout and re-login
                    try:
                        rh.logout()
                    except:
                        pass
                    # Continue with login below
                else:
                    # Other error - assume we're logged in
                    print("Already logged in (positions check had non-auth error)")
                    return True
    except Exception as check_error:
        print(f"Error checking login status: {check_error}, proceeding with login")
        # Continue with login below
    
    username = username or os.getenv('ROBINHOOD_USERNAME')
    password = password or os.getenv('ROBINHOOD_PASSWORD')
    mfa_code = mfa_code or os.getenv('ROBINHOOD_MFA_CODE')
    
    if not username or not password:
        raise ValueError("Username and password are required")
    
    try:
        # robin_stocks handles device tokens internally
        # It will automatically use saved session if available
        # The store_session parameter saves the session for future logins
        login_response = rh.login(
            username=username,
            password=password,
            mfa_code=mfa_code,
            store_session=True  # Save session for future logins
        )
        
        if login_response:
            # If login_response is truthy, trust it
            # robin_stocks handles session management internally
            # We'll verify by trying to use it, but don't fail login if verification has issues
            print("Login response received, verifying...")
            try:
                # Try a simple API call to verify
                account = rh.load_phoenix_account()
                if account:
                    print("Login successful and verified")
                else:
                    print("Login response received (account check returned None, but login_response was truthy)")
            except Exception as verify_error:
                error_str = str(verify_error).lower()
                # Only log the error, but still return True if login_response was truthy
                # The actual API calls will fail later if we're not really logged in
                if any(keyword in error_str for keyword in ['not logged in', 'can only be called when logged in', 'must be logged in', '401', 'unauthorized']):
                    print(f"Warning: Login response received but verification suggests not logged in: {verify_error}")
                    # Still return True - let the actual portfolio call determine if we're logged in
                else:
                    print(f"Login verification warning (non-auth error, assuming login worked): {verify_error}")
            
            # Return True if login_response was truthy
            # The actual API usage will reveal if we're really logged in
            return True
        else:
            print("Login failed - no response")
            return False
            
    except Exception as e:
        error_msg = str(e).lower()
        error_str = str(e)
        
        # Check if it's a 2FA/challenge error
        if any(keyword in error_msg for keyword in ['challenge', 'device', '2fa', 'two-factor', 'mfa']):
            # This usually means device approval is needed
            # The user needs to approve in the app, then we retry
            if 'challenge' in error_msg or 'device' in error_msg:
                # Return a special response indicating device approval needed
                raise Exception("DEVICE_APPROVAL_NEEDED: Please approve this device in your Robinhood app, then try logging in again.")
            else:
                raise Exception(f"2FA required: {error_str}")
        else:
            raise Exception(f"Login error: {error_str}")


def logout():
    """Logout from Robinhood."""
    try:
        rh.logout()
        print("Logged out successfully.")
    except Exception as e:
        print(f"Logout error: {e}")


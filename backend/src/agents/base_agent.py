import asyncio
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional, Callable, List
from enum import Enum
import logging
import json
from dataclasses import dataclass, asdict
import structlog
from redis import asyncio as aioredis
from tenacity import retry, stop_after_attempt, wait_exponential


class MessagePriority(Enum):
    LOW = 1
    NORMAL = 2
    HIGH = 3
    CRITICAL = 4


class MessageType(Enum):
    COMMAND = "command"
    QUERY = "query"
    RESPONSE = "response"
    EVENT = "event"
    ERROR = "error"
    HEALTH_CHECK = "health_check"
    STATE_UPDATE = "state_update"


class AgentState(Enum):
    INITIALIZING = "initializing"
    READY = "ready"
    BUSY = "busy"
    ERROR = "error"
    SHUTTING_DOWN = "shutting_down"
    STOPPED = "stopped"


@dataclass
class AgentMessage:
    sender: str
    recipient: str
    message_type: MessageType
    payload: Dict[str, Any]
    priority: MessagePriority = MessagePriority.NORMAL
    correlation_id: Optional[str] = None
    timestamp: Optional[datetime] = None
    message_id: Optional[str] = None
    ttl: Optional[int] = 300  # Time to live in seconds

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.utcnow()
        if not self.message_id:
            self.message_id = str(uuid.uuid4())
        if not self.correlation_id:
            self.correlation_id = self.message_id

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data['message_type'] = self.message_type.value
        data['priority'] = self.priority.value
        data['timestamp'] = self.timestamp.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AgentMessage':
        data['message_type'] = MessageType(data['message_type'])
        data['priority'] = MessagePriority(data['priority'])
        data['timestamp'] = datetime.fromisoformat(data['timestamp'])
        return cls(**data)


class BaseAgent(ABC):
    def __init__(self, agent_id: str, agent_type: str, config: Dict[str, Any]):
        self.agent_id = agent_id
        self.agent_type = agent_type
        self.config = config
        self.state = AgentState.INITIALIZING
        self.logger = self._setup_logger()
        
        # Message handling
        self.message_handlers: Dict[MessageType, Callable] = {}
        self.message_queue: asyncio.Queue = asyncio.Queue()
        self.outgoing_queue: asyncio.Queue = asyncio.Queue()
        
        # Redis connections
        self.redis_client: Optional[aioredis.Redis] = None
        self.pubsub: Optional[aioredis.client.PubSub] = None
        
        # State management
        self.local_state: Dict[str, Any] = {}
        self.state_version = 0
        
        # Health monitoring
        self.last_heartbeat = datetime.utcnow()
        self.health_metrics: Dict[str, Any] = {
            'messages_processed': 0,
            'errors': 0,
            'uptime': 0,
            'memory_usage': 0,
            'cpu_usage': 0
        }
        
        # Tasks
        self.tasks: List[asyncio.Task] = []
        self.running = False

    def _setup_logger(self) -> structlog.BoundLogger:
        return structlog.get_logger().bind(
            agent_id=self.agent_id,
            agent_type=self.agent_type
        )

    async def initialize(self):
        try:
            self.logger.info("Initializing agent")
            
            # Connect to Redis
            await self._connect_redis()
            
            # Register agent in system
            await self._register_agent()
            
            # Set up message handlers
            self._setup_message_handlers()
            
            # Initialize agent-specific components
            await self._initialize_agent()
            
            self.state = AgentState.READY
            self.logger.info("Agent initialized successfully")
            
        except Exception as e:
            self.logger.error("Failed to initialize agent", error=str(e))
            self.state = AgentState.ERROR
            raise

    async def _connect_redis(self):
        redis_url = self.config.get('redis_url', 'redis://localhost:6379')
        self.redis_client = await aioredis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True
        )
        self.pubsub = self.redis_client.pubsub()

    async def _register_agent(self):
        agent_info = {
            'agent_id': self.agent_id,
            'agent_type': self.agent_type,
            'state': self.state.value,
            'started_at': datetime.utcnow().isoformat(),
            'capabilities': self._get_capabilities()
        }
        
        await self.redis_client.hset(
            f"agents:{self.agent_id}",
            mapping=agent_info
        )
        
        # Subscribe to agent-specific channel
        await self.pubsub.subscribe(
            f"agent:{self.agent_id}",
            f"agent_type:{self.agent_type}",
            "broadcast"
        )

    def _setup_message_handlers(self):
        self.register_handler(MessageType.HEALTH_CHECK, self._handle_health_check)
        self.register_handler(MessageType.STATE_UPDATE, self._handle_state_update)
        self.register_handler(MessageType.ERROR, self._handle_error)

    def register_handler(self, message_type: MessageType, handler: Callable):
        self.message_handlers[message_type] = handler

    async def start(self):
        self.running = True
        self.logger.info("Starting agent")
        
        # Start core tasks
        self.tasks.extend([
            asyncio.create_task(self._message_receiver()),
            asyncio.create_task(self._message_processor()),
            asyncio.create_task(self._message_sender()),
            asyncio.create_task(self._heartbeat_sender()),
            asyncio.create_task(self._health_monitor())
        ])
        
        # Start agent-specific tasks
        agent_tasks = await self._start_agent_tasks()
        if agent_tasks:
            self.tasks.extend(agent_tasks)
        
        await self._on_start()

    async def stop(self):
        self.logger.info("Stopping agent")
        self.running = False
        self.state = AgentState.SHUTTING_DOWN
        
        await self._on_stop()
        
        # Cancel all tasks
        for task in self.tasks:
            task.cancel()
        
        await asyncio.gather(*self.tasks, return_exceptions=True)
        
        # Unregister agent
        await self._unregister_agent()
        
        # Close Redis connections
        if self.pubsub:
            await self.pubsub.unsubscribe()
            await self.pubsub.close()
        
        if self.redis_client:
            await self.redis_client.close()
        
        self.state = AgentState.STOPPED
        self.logger.info("Agent stopped")

    async def _unregister_agent(self):
        await self.redis_client.delete(f"agents:{self.agent_id}")

    async def _message_receiver(self):
        while self.running:
            try:
                # Check for Redis messages
                message = await self.pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
                
                if message and message['type'] == 'message':
                    data = json.loads(message['data'])
                    agent_message = AgentMessage.from_dict(data)
                    await self.message_queue.put(agent_message)
                
                await asyncio.sleep(0.01)
                
            except Exception as e:
                self.logger.error("Error receiving message", error=str(e))
                await asyncio.sleep(1)

    async def _message_processor(self):
        while self.running:
            try:
                # Get message with timeout
                message = await asyncio.wait_for(
                    self.message_queue.get(),
                    timeout=1.0
                )
                
                self.state = AgentState.BUSY
                await self._process_message(message)
                self.state = AgentState.READY
                
                self.health_metrics['messages_processed'] += 1
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error("Error processing message", error=str(e))
                self.health_metrics['errors'] += 1

    async def _process_message(self, message: AgentMessage):
        self.logger.info(
            "Processing message",
            message_type=message.message_type.value,
            sender=message.sender,
            message_id=message.message_id
        )
        
        handler = self.message_handlers.get(message.message_type)
        
        if handler:
            try:
                await handler(message)
            except Exception as e:
                self.logger.error(
                    "Handler error",
                    message_type=message.message_type.value,
                    error=str(e)
                )
                
                # Send error response
                error_response = AgentMessage(
                    sender=self.agent_id,
                    recipient=message.sender,
                    message_type=MessageType.ERROR,
                    payload={
                        'error': str(e),
                        'original_message_id': message.message_id
                    },
                    correlation_id=message.correlation_id
                )
                await self.send_message(error_response)
        else:
            self.logger.warning(
                "No handler for message type",
                message_type=message.message_type.value
            )

    async def _message_sender(self):
        while self.running:
            try:
                message = await asyncio.wait_for(
                    self.outgoing_queue.get(),
                    timeout=1.0
                )
                
                await self._send_message_via_redis(message)
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error("Error sending message", error=str(e))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
    async def _send_message_via_redis(self, message: AgentMessage):
        channel = f"agent:{message.recipient}"
        
        await self.redis_client.publish(
            channel,
            json.dumps(message.to_dict())
        )
        
        # Store message for audit
        await self.redis_client.zadd(
            f"messages:{message.recipient}",
            {json.dumps(message.to_dict()): message.timestamp.timestamp()}
        )
        
        # Set TTL for message
        if message.ttl:
            await self.redis_client.expire(
                f"messages:{message.recipient}",
                message.ttl
            )

    async def send_message(self, message: AgentMessage):
        await self.outgoing_queue.put(message)

    async def broadcast_message(self, message: AgentMessage):
        message.recipient = "broadcast"
        await self.send_message(message)

    async def _heartbeat_sender(self):
        while self.running:
            try:
                heartbeat = {
                    'agent_id': self.agent_id,
                    'state': self.state.value,
                    'timestamp': datetime.utcnow().isoformat(),
                    'health_metrics': self.health_metrics
                }
                
                await self.redis_client.setex(
                    f"heartbeat:{self.agent_id}",
                    30,  # TTL of 30 seconds
                    json.dumps(heartbeat)
                )
                
                self.last_heartbeat = datetime.utcnow()
                
                await asyncio.sleep(10)  # Send heartbeat every 10 seconds
                
            except Exception as e:
                self.logger.error("Error sending heartbeat", error=str(e))

    async def _health_monitor(self):
        while self.running:
            try:
                # Update health metrics
                self.health_metrics['uptime'] = (
                    datetime.utcnow() - self.last_heartbeat
                ).total_seconds()
                
                # Check agent health
                if self.health_metrics['errors'] > 100:
                    self.logger.warning("High error rate detected")
                    self.state = AgentState.ERROR
                
                await asyncio.sleep(30)
                
            except Exception as e:
                self.logger.error("Error in health monitor", error=str(e))

    async def _handle_health_check(self, message: AgentMessage):
        response = AgentMessage(
            sender=self.agent_id,
            recipient=message.sender,
            message_type=MessageType.RESPONSE,
            payload={
                'status': 'healthy',
                'state': self.state.value,
                'health_metrics': self.health_metrics
            },
            correlation_id=message.correlation_id
        )
        await self.send_message(response)

    async def _handle_state_update(self, message: AgentMessage):
        state_data = message.payload
        await self.update_state(state_data)

    async def _handle_error(self, message: AgentMessage):
        self.logger.error(
            "Received error message",
            error=message.payload.get('error'),
            sender=message.sender
        )

    async def update_state(self, state_data: Dict[str, Any]):
        self.local_state.update(state_data)
        self.state_version += 1
        
        # Persist state to Redis
        await self.redis_client.hset(
            f"state:{self.agent_id}",
            mapping={
                'data': json.dumps(self.local_state),
                'version': self.state_version,
                'updated_at': datetime.utcnow().isoformat()
            }
        )

    async def get_state(self, key: Optional[str] = None) -> Any:
        if key:
            return self.local_state.get(key)
        return self.local_state.copy()

    @abstractmethod
    async def _initialize_agent(self):
        pass

    @abstractmethod
    async def _start_agent_tasks(self) -> List[asyncio.Task]:
        pass

    @abstractmethod
    def _get_capabilities(self) -> List[str]:
        pass

    @abstractmethod
    async def _on_start(self):
        pass

    @abstractmethod
    async def _on_stop(self):
        pass
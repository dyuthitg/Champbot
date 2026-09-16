import asyncio
from typing import Dict, List, Optional, Type, Any
from datetime import datetime
import structlog
from redis import asyncio as aioredis
import json
import importlib
import inspect
from dataclasses import dataclass
from enum import Enum

from ..agents.base_agent import BaseAgent, AgentState, AgentMessage, MessageType, MessagePriority
from .message_queue import MessageQueue, EventBus, RateLimiter
from .state_manager import StateManager


class OrchestratorState(Enum):
    INITIALIZING = "initializing"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    STOPPED = "stopped"


@dataclass
class AgentConfig:
    agent_type: str
    agent_class: str
    min_instances: int = 1
    max_instances: int = 10
    auto_scale: bool = True
    config: Dict[str, Any] = None
    dependencies: List[str] = None

    def __post_init__(self):
        if self.config is None:
            self.config = {}
        if self.dependencies is None:
            self.dependencies = []


class AgentOrchestrator:
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.logger = structlog.get_logger()
        
        # Redis connection
        self.redis: Optional[aioredis.Redis] = None
        
        # Infrastructure components
        self.message_queue: Optional[MessageQueue] = None
        self.event_bus: Optional[EventBus] = None
        self.state_manager: Optional[StateManager] = None
        self.rate_limiter: Optional[RateLimiter] = None
        
        # Agent management
        self.agent_configs: Dict[str, AgentConfig] = {}
        self.agents: Dict[str, BaseAgent] = {}
        self.agent_pools: Dict[str, List[BaseAgent]] = {}
        
        # Orchestrator state
        self.state = OrchestratorState.INITIALIZING
        self.start_time: Optional[datetime] = None
        
        # Health monitoring
        self.health_check_interval = 30  # seconds
        self.health_check_task: Optional[asyncio.Task] = None
        
        # Load balancing
        self.load_balancer_task: Optional[asyncio.Task] = None
        self.agent_load: Dict[str, int] = {}

    async def initialize(self):
        try:
            self.logger.info("Initializing orchestrator")
            
            # Connect to Redis
            await self._connect_redis()
            
            # Initialize infrastructure components
            await self._initialize_infrastructure()
            
            # Load agent configurations
            await self._load_agent_configs()
            
            # Register orchestrator
            await self._register_orchestrator()
            
            self.state = OrchestratorState.RUNNING
            self.start_time = datetime.utcnow()
            
            self.logger.info("Orchestrator initialized successfully")
            
        except Exception as e:
            self.logger.error("Failed to initialize orchestrator", error=str(e))
            raise

    async def _connect_redis(self):
        redis_url = self.config.get('redis_url', 'redis://localhost:6379')
        self.redis = await aioredis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True
        )

    async def _initialize_infrastructure(self):
        # Initialize message queue
        self.message_queue = MessageQueue(self.redis)
        
        # Initialize event bus
        self.event_bus = EventBus(self.redis)
        await self.event_bus.start()
        
        # Initialize state manager
        self.state_manager = StateManager(self.redis, namespace="orchestrator")
        await self.state_manager.start()
        
        # Initialize rate limiter
        self.rate_limiter = RateLimiter(self.redis)
        
        # Subscribe to system events
        await self.event_bus.subscribe("agent_started", self._handle_agent_started)
        await self.event_bus.subscribe("agent_stopped", self._handle_agent_stopped)
        await self.event_bus.subscribe("agent_error", self._handle_agent_error)

    async def _load_agent_configs(self):
        # Load from configuration file or database
        agent_configs = self.config.get('agents', {})
        
        for agent_type, config_data in agent_configs.items():
            self.agent_configs[agent_type] = AgentConfig(
                agent_type=agent_type,
                **config_data
            )

    async def _register_orchestrator(self):
        orchestrator_info = {
            'id': 'orchestrator',
            'state': self.state.value,
            'start_time': self.start_time.isoformat() if self.start_time else None,
            'agent_types': list(self.agent_configs.keys())
        }
        
        await self.redis.hset(
            "orchestrator:info",
            mapping=orchestrator_info
        )

    async def start(self):
        self.logger.info("Starting orchestrator")
        
        # Start all configured agents
        for agent_type, agent_config in self.agent_configs.items():
            await self.start_agent_pool(agent_type, agent_config.min_instances)
        
        # Start health monitoring
        self.health_check_task = asyncio.create_task(self._health_monitor())
        
        # Start load balancer
        self.load_balancer_task = asyncio.create_task(self._load_balancer())
        
        self.logger.info("Orchestrator started")

    async def stop(self):
        self.logger.info("Stopping orchestrator")
        self.state = OrchestratorState.STOPPING
        
        # Stop all agents
        for agent_id, agent in self.agents.items():
            await self.stop_agent(agent_id)
        
        # Stop health monitoring
        if self.health_check_task:
            self.health_check_task.cancel()
            await asyncio.gather(self.health_check_task, return_exceptions=True)
        
        # Stop load balancer
        if self.load_balancer_task:
            self.load_balancer_task.cancel()
            await asyncio.gather(self.load_balancer_task, return_exceptions=True)
        
        # Stop infrastructure components
        if self.event_bus:
            await self.event_bus.stop()
        
        if self.state_manager:
            await self.state_manager.stop()
        
        # Close Redis connection
        if self.redis:
            await self.redis.close()
        
        self.state = OrchestratorState.STOPPED
        self.logger.info("Orchestrator stopped")

    async def start_agent(
        self,
        agent_type: str,
        agent_id: Optional[str] = None,
        config_override: Optional[Dict[str, Any]] = None
    ) -> str:
        if agent_type not in self.agent_configs:
            raise ValueError(f"Unknown agent type: {agent_type}")
        
        agent_config = self.agent_configs[agent_type]
        
        # Generate agent ID if not provided
        if not agent_id:
            agent_id = f"{agent_type}_{datetime.utcnow().timestamp()}"
        
        # Load agent class
        agent_class = self._load_agent_class(agent_config.agent_class)
        
        # Merge configurations
        config = agent_config.config.copy()
        if config_override:
            config.update(config_override)
        
        # Add infrastructure references
        config.update({
            'redis_url': self.config.get('redis_url'),
            'message_queue': self.message_queue,
            'event_bus': self.event_bus,
            'state_manager': self.state_manager,
            'rate_limiter': self.rate_limiter
        })
        
        # Create and initialize agent
        agent = agent_class(agent_id, agent_type, config)
        await agent.initialize()
        
        # Start agent
        await agent.start()
        
        # Register agent
        self.agents[agent_id] = agent
        
        # Add to pool
        if agent_type not in self.agent_pools:
            self.agent_pools[agent_type] = []
        self.agent_pools[agent_type].append(agent)
        
        # Publish event
        await self.event_bus.publish("agent_started", {
            'agent_id': agent_id,
            'agent_type': agent_type
        })
        
        self.logger.info("Agent started", agent_id=agent_id, agent_type=agent_type)
        
        return agent_id

    async def stop_agent(self, agent_id: str):
        if agent_id not in self.agents:
            raise ValueError(f"Agent not found: {agent_id}")
        
        agent = self.agents[agent_id]
        agent_type = agent.agent_type
        
        # Stop agent
        await agent.stop()
        
        # Remove from registry
        del self.agents[agent_id]
        
        # Remove from pool
        if agent_type in self.agent_pools:
            self.agent_pools[agent_type] = [
                a for a in self.agent_pools[agent_type]
                if a.agent_id != agent_id
            ]
        
        # Publish event
        await self.event_bus.publish("agent_stopped", {
            'agent_id': agent_id,
            'agent_type': agent_type
        })
        
        self.logger.info("Agent stopped", agent_id=agent_id, agent_type=agent_type)

    async def start_agent_pool(self, agent_type: str, count: int):
        tasks = []
        
        for i in range(count):
            task = asyncio.create_task(self.start_agent(agent_type))
            tasks.append(task)
        
        agent_ids = await asyncio.gather(*tasks)
        
        self.logger.info(
            "Agent pool started",
            agent_type=agent_type,
            count=count,
            agent_ids=agent_ids
        )
        
        return agent_ids

    async def scale_agent_pool(self, agent_type: str, target_count: int):
        if agent_type not in self.agent_pools:
            self.agent_pools[agent_type] = []
        
        current_count = len(self.agent_pools[agent_type])
        
        if target_count > current_count:
            # Scale up
            count_to_add = target_count - current_count
            await self.start_agent_pool(agent_type, count_to_add)
            
        elif target_count < current_count:
            # Scale down
            count_to_remove = current_count - target_count
            agents_to_remove = self.agent_pools[agent_type][-count_to_remove:]
            
            for agent in agents_to_remove:
                await self.stop_agent(agent.agent_id)

    def _load_agent_class(self, class_path: str) -> Type[BaseAgent]:
        module_name, class_name = class_path.rsplit('.', 1)
        module = importlib.import_module(module_name)
        agent_class = getattr(module, class_name)
        
        if not issubclass(agent_class, BaseAgent):
            raise ValueError(f"{class_path} is not a subclass of BaseAgent")
        
        return agent_class

    async def _health_monitor(self):
        while self.state == OrchestratorState.RUNNING:
            try:
                # Check health of all agents
                unhealthy_agents = []
                
                for agent_id, agent in self.agents.items():
                    # Check heartbeat
                    heartbeat_key = f"heartbeat:{agent_id}"
                    heartbeat = await self.redis.get(heartbeat_key)
                    
                    if not heartbeat:
                        unhealthy_agents.append(agent_id)
                        continue
                    
                    heartbeat_data = json.loads(heartbeat)
                    last_heartbeat = datetime.fromisoformat(heartbeat_data['timestamp'])
                    
                    # Check if heartbeat is stale (> 60 seconds)
                    if (datetime.utcnow() - last_heartbeat).total_seconds() > 60:
                        unhealthy_agents.append(agent_id)
                
                # Handle unhealthy agents
                for agent_id in unhealthy_agents:
                    self.logger.warning("Unhealthy agent detected", agent_id=agent_id)
                    
                    # Restart agent
                    agent = self.agents[agent_id]
                    agent_type = agent.agent_type
                    
                    try:
                        await self.stop_agent(agent_id)
                        await self.start_agent(agent_type, agent_id)
                    except Exception as e:
                        self.logger.error(
                            "Failed to restart agent",
                            agent_id=agent_id,
                            error=str(e)
                        )
                
                # Update orchestrator health
                await self._update_health_metrics()
                
                await asyncio.sleep(self.health_check_interval)
                
            except Exception as e:
                self.logger.error("Health monitor error", error=str(e))
                await asyncio.sleep(self.health_check_interval)

    async def _load_balancer(self):
        while self.state == OrchestratorState.RUNNING:
            try:
                # Check agent loads and scale if needed
                for agent_type, agent_config in self.agent_configs.items():
                    if not agent_config.auto_scale:
                        continue
                    
                    pool = self.agent_pools.get(agent_type, [])
                    if not pool:
                        continue
                    
                    # Calculate average load
                    total_load = 0
                    for agent in pool:
                        agent_load = self.agent_load.get(agent.agent_id, 0)
                        total_load += agent_load
                    
                    avg_load = total_load / len(pool) if pool else 0
                    
                    # Scale up if load is high
                    if avg_load > 80 and len(pool) < agent_config.max_instances:
                        await self.scale_agent_pool(agent_type, len(pool) + 1)
                        self.logger.info(
                            "Scaling up agent pool",
                            agent_type=agent_type,
                            current_count=len(pool),
                            avg_load=avg_load
                        )
                    
                    # Scale down if load is low
                    elif avg_load < 20 and len(pool) > agent_config.min_instances:
                        await self.scale_agent_pool(agent_type, len(pool) - 1)
                        self.logger.info(
                            "Scaling down agent pool",
                            agent_type=agent_type,
                            current_count=len(pool),
                            avg_load=avg_load
                        )
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                self.logger.error("Load balancer error", error=str(e))
                await asyncio.sleep(60)

    async def _update_health_metrics(self):
        metrics = {
            'total_agents': len(self.agents),
            'agent_pools': {
                agent_type: len(pool)
                for agent_type, pool in self.agent_pools.items()
            },
            'uptime': (datetime.utcnow() - self.start_time).total_seconds() if self.start_time else 0,
            'state': self.state.value
        }
        
        await self.redis.hset(
            "orchestrator:metrics",
            mapping={k: json.dumps(v) if isinstance(v, dict) else v for k, v in metrics.items()}
        )

    async def _handle_agent_started(self, data: Dict[str, Any]):
        self.logger.info("Agent started event received", **data)

    async def _handle_agent_stopped(self, data: Dict[str, Any]):
        self.logger.info("Agent stopped event received", **data)

    async def _handle_agent_error(self, data: Dict[str, Any]):
        self.logger.error("Agent error event received", **data)
        
        # Attempt to restart agent
        agent_id = data.get('agent_id')
        if agent_id in self.agents:
            agent = self.agents[agent_id]
            await self.stop_agent(agent_id)
            await self.start_agent(agent.agent_type, agent_id)

    async def send_command(
        self,
        agent_type: str,
        command: str,
        payload: Dict[str, Any],
        target_agent_id: Optional[str] = None
    ):
        if target_agent_id:
            # Send to specific agent
            if target_agent_id not in self.agents:
                raise ValueError(f"Agent not found: {target_agent_id}")
            
            message = AgentMessage(
                sender="orchestrator",
                recipient=target_agent_id,
                message_type=MessageType.COMMAND,
                payload={
                    'command': command,
                    **payload
                }
            )
            
            await self.agents[target_agent_id].send_message(message)
            
        else:
            # Send to all agents of type
            pool = self.agent_pools.get(agent_type, [])
            
            for agent in pool:
                message = AgentMessage(
                    sender="orchestrator",
                    recipient=agent.agent_id,
                    message_type=MessageType.COMMAND,
                    payload={
                        'command': command,
                        **payload
                    }
                )
                
                await agent.send_message(message)

    async def get_agent_status(self, agent_id: str) -> Dict[str, Any]:
        if agent_id not in self.agents:
            raise ValueError(f"Agent not found: {agent_id}")
        
        agent = self.agents[agent_id]
        
        # Get heartbeat
        heartbeat_key = f"heartbeat:{agent_id}"
        heartbeat = await self.redis.get(heartbeat_key)
        heartbeat_data = json.loads(heartbeat) if heartbeat else None
        
        return {
            'agent_id': agent_id,
            'agent_type': agent.agent_type,
            'state': agent.state.value,
            'heartbeat': heartbeat_data,
            'load': self.agent_load.get(agent_id, 0)
        }

    async def get_orchestrator_status(self) -> Dict[str, Any]:
        return {
            'state': self.state.value,
            'uptime': (datetime.utcnow() - self.start_time).total_seconds() if self.start_time else 0,
            'total_agents': len(self.agents),
            'agent_pools': {
                agent_type: {
                    'count': len(pool),
                    'config': {
                        'min_instances': config.min_instances,
                        'max_instances': config.max_instances,
                        'auto_scale': config.auto_scale
                    }
                }
                for agent_type, (pool, config) in zip(
                    self.agent_pools.items(),
                    self.agent_configs.items()
                )
            }
        }
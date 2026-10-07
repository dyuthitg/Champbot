import asyncio
import json
from typing import Any, Dict, Optional, Callable, List
from datetime import datetime
import structlog
from redis import asyncio as aioredis
from dataclasses import dataclass
import pickle
from enum import Enum
from collections import defaultdict
import time


class QueueType(Enum):
    FIFO = "fifo"
    PRIORITY = "priority"
    DELAYED = "delayed"


@dataclass
class QueueMessage:
    queue_name: str
    data: Any
    priority: int = 0
    delay: int = 0  # Delay in seconds
    retry_count: int = 0
    max_retries: int = 3
    created_at: float = None
    scheduled_at: float = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = time.time()
        if self.scheduled_at is None:
            self.scheduled_at = self.created_at + self.delay


class MessageQueue:
    def __init__(self, redis_client: aioredis.Redis, queue_type: QueueType = QueueType.PRIORITY):
        self.redis = redis_client
        self.queue_type = queue_type
        self.logger = structlog.get_logger()
        self.handlers: Dict[str, List[Callable]] = defaultdict(list)
        self.running = False
        self.consumer_tasks: List[asyncio.Task] = []

    async def enqueue(self, queue_name: str, message: Any, priority: int = 0, delay: int = 0):
        queue_message = QueueMessage(
            queue_name=queue_name,
            data=message,
            priority=priority,
            delay=delay
        )
        
        serialized = pickle.dumps(queue_message)
        
        if self.queue_type == QueueType.FIFO:
            await self.redis.rpush(f"queue:{queue_name}", serialized)
        elif self.queue_type == QueueType.PRIORITY:
            # Use negative priority for correct sorting (higher priority = lower score)
            await self.redis.zadd(
                f"queue:priority:{queue_name}",
                {serialized: -priority}
            )
        elif self.queue_type == QueueType.DELAYED:
            await self.redis.zadd(
                f"queue:delayed:{queue_name}",
                {serialized: queue_message.scheduled_at}
            )
        
        self.logger.info(
            "Message enqueued",
            queue_name=queue_name,
            priority=priority,
            delay=delay
        )

    async def dequeue(self, queue_name: str, timeout: Optional[float] = None) -> Optional[Any]:
        start_time = time.time()
        
        while True:
            if self.queue_type == QueueType.FIFO:
                result = await self.redis.blpop(f"queue:{queue_name}", timeout=1)
                if result:
                    _, serialized = result
                    queue_message = pickle.loads(serialized)
                    return queue_message.data
                    
            elif self.queue_type == QueueType.PRIORITY:
                # Get highest priority message
                results = await self.redis.zpopmin(f"queue:priority:{queue_name}", count=1)
                if results:
                    serialized, _ = results[0]
                    queue_message = pickle.loads(serialized)
                    return queue_message.data
                    
            elif self.queue_type == QueueType.DELAYED:
                # Check for messages ready to be processed
                now = time.time()
                results = await self.redis.zrangebyscore(
                    f"queue:delayed:{queue_name}",
                    0,
                    now,
                    start=0,
                    num=1
                )
                
                if results:
                    serialized = results[0]
                    # Remove from delayed queue
                    await self.redis.zrem(f"queue:delayed:{queue_name}", serialized)
                    queue_message = pickle.loads(serialized)
                    return queue_message.data
            
            # Check timeout
            if timeout and (time.time() - start_time) >= timeout:
                return None
            
            await asyncio.sleep(0.1)

    async def subscribe(self, queue_name: str, handler: Callable):
        self.handlers[queue_name].append(handler)
        self.logger.info("Handler subscribed", queue_name=queue_name)

    async def unsubscribe(self, queue_name: str, handler: Callable):
        if handler in self.handlers[queue_name]:
            self.handlers[queue_name].remove(handler)
            self.logger.info("Handler unsubscribed", queue_name=queue_name)

    async def start_consumers(self):
        self.running = True
        
        for queue_name in self.handlers:
            for handler in self.handlers[queue_name]:
                task = asyncio.create_task(
                    self._consumer_loop(queue_name, handler)
                )
                self.consumer_tasks.append(task)
        
        self.logger.info("Message queue consumers started")

    async def stop_consumers(self):
        self.running = False
        
        for task in self.consumer_tasks:
            task.cancel()
        
        await asyncio.gather(*self.consumer_tasks, return_exceptions=True)
        self.consumer_tasks.clear()
        
        self.logger.info("Message queue consumers stopped")

    async def _consumer_loop(self, queue_name: str, handler: Callable):
        while self.running:
            try:
                message = await self.dequeue(queue_name, timeout=1.0)
                
                if message is not None:
                    try:
                        await handler(message)
                    except Exception as e:
                        self.logger.error(
                            "Handler error",
                            queue_name=queue_name,
                            error=str(e)
                        )
                        
                        # Re-queue message for retry
                        await self._handle_failure(queue_name, message, e)
                        
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(
                    "Consumer loop error",
                    queue_name=queue_name,
                    error=str(e)
                )
                await asyncio.sleep(1)

    async def _handle_failure(self, queue_name: str, message: Any, error: Exception):
        # Implement retry logic
        retry_queue = f"queue:retry:{queue_name}"
        
        retry_info = {
            'message': message,
            'error': str(error),
            'retry_count': 1,
            'timestamp': datetime.utcnow().isoformat()
        }
        
        await self.redis.rpush(retry_queue, pickle.dumps(retry_info))

    async def get_queue_size(self, queue_name: str) -> int:
        if self.queue_type == QueueType.FIFO:
            return await self.redis.llen(f"queue:{queue_name}")
        elif self.queue_type == QueueType.PRIORITY:
            return await self.redis.zcard(f"queue:priority:{queue_name}")
        elif self.queue_type == QueueType.DELAYED:
            return await self.redis.zcard(f"queue:delayed:{queue_name}")
        return 0

    async def clear_queue(self, queue_name: str):
        if self.queue_type == QueueType.FIFO:
            await self.redis.delete(f"queue:{queue_name}")
        elif self.queue_type == QueueType.PRIORITY:
            await self.redis.delete(f"queue:priority:{queue_name}")
        elif self.queue_type == QueueType.DELAYED:
            await self.redis.delete(f"queue:delayed:{queue_name}")
        
        self.logger.info("Queue cleared", queue_name=queue_name)

    async def get_queue_metrics(self, queue_name: str) -> Dict[str, Any]:
        metrics = {
            'queue_name': queue_name,
            'queue_type': self.queue_type.value,
            'size': await self.get_queue_size(queue_name),
            'retry_queue_size': await self.redis.llen(f"queue:retry:{queue_name}"),
            'handlers_count': len(self.handlers.get(queue_name, []))
        }
        
        return metrics


class EventBus:
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.pubsub = self.redis.pubsub()
        self.logger = structlog.get_logger()
        self.handlers: Dict[str, List[Callable]] = defaultdict(list)
        self.running = False
        self.listener_task: Optional[asyncio.Task] = None

    async def publish(self, event_type: str, data: Any):
        event = {
            'event_type': event_type,
            'data': data,
            'timestamp': datetime.utcnow().isoformat(),
            'publisher': 'event_bus'
        }
        
        await self.redis.publish(
            f"events:{event_type}",
            json.dumps(event)
        )
        
        self.logger.info("Event published", event_type=event_type)

    async def subscribe(self, event_type: str, handler: Callable):
        if event_type not in self.handlers:
            await self.pubsub.subscribe(f"events:{event_type}")
        
        self.handlers[event_type].append(handler)
        self.logger.info("Handler subscribed to event", event_type=event_type)

    async def unsubscribe(self, event_type: str, handler: Callable):
        if handler in self.handlers[event_type]:
            self.handlers[event_type].remove(handler)
            
            if not self.handlers[event_type]:
                await self.pubsub.unsubscribe(f"events:{event_type}")
                del self.handlers[event_type]
            
            self.logger.info("Handler unsubscribed from event", event_type=event_type)

    async def start(self):
        self.running = True
        self.listener_task = asyncio.create_task(self._event_listener())
        self.logger.info("Event bus started")

    async def stop(self):
        self.running = False
        
        if self.listener_task:
            self.listener_task.cancel()
            await asyncio.gather(self.listener_task, return_exceptions=True)
        
        await self.pubsub.close()
        self.logger.info("Event bus stopped")

    async def _event_listener(self):
        while self.running:
            try:
                message = await self.pubsub.get_message(
                    ignore_subscribe_messages=True,
                    timeout=0.1
                )
                
                if message and message['type'] == 'message':
                    channel = message['channel'].decode('utf-8')
                    event_type = channel.replace('events:', '')
                    
                    event = json.loads(message['data'])
                    
                    # Call all handlers for this event type
                    for handler in self.handlers.get(event_type, []):
                        try:
                            await handler(event['data'])
                        except Exception as e:
                            self.logger.error(
                                "Event handler error",
                                event_type=event_type,
                                error=str(e)
                            )
                
                await asyncio.sleep(0.01)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Event listener error", error=str(e))
                await asyncio.sleep(1)


class RateLimiter:
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.logger = structlog.get_logger()

    async def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int
    ) -> bool:
        current_time = int(time.time())
        window_start = current_time - window_seconds
        
        # Use Redis sorted set for sliding window
        pipe = self.redis.pipeline()
        
        # Remove old entries
        pipe.zremrangebyscore(f"rate_limit:{key}", 0, window_start)
        
        # Count current entries
        pipe.zcard(f"rate_limit:{key}")
        
        # Add current request
        pipe.zadd(f"rate_limit:{key}", {str(current_time): current_time})
        
        # Set expiry
        pipe.expire(f"rate_limit:{key}", window_seconds)
        
        results = await pipe.execute()
        current_count = results[1]
        
        if current_count >= max_requests:
            self.logger.warning(
                "Rate limit exceeded",
                key=key,
                current_count=current_count,
                max_requests=max_requests
            )
            return False
        
        return True

    async def get_rate_limit_info(self, key: str, window_seconds: int) -> Dict[str, Any]:
        current_time = int(time.time())
        window_start = current_time - window_seconds
        
        count = await self.redis.zcount(
            f"rate_limit:{key}",
            window_start,
            current_time
        )
        
        return {
            'key': key,
            'current_count': count,
            'window_seconds': window_seconds,
            'window_start': datetime.fromtimestamp(window_start).isoformat(),
            'window_end': datetime.fromtimestamp(current_time).isoformat()
        }
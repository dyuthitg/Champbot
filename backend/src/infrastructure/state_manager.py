import asyncio
import json
from typing import Any, Dict, Optional, Callable, List, Set
from datetime import datetime
import structlog
from redis import asyncio as aioredis
from dataclasses import dataclass, asdict
import time
from enum import Enum
import hashlib
from collections import defaultdict


class StateType(Enum):
    LOCAL = "local"
    DISTRIBUTED = "distributed"
    PERSISTENT = "persistent"


@dataclass
class StateEntry:
    key: str
    value: Any
    version: int
    timestamp: float
    ttl: Optional[int] = None
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            'key': self.key,
            'value': self.value,
            'version': self.version,
            'timestamp': self.timestamp,
            'ttl': self.ttl,
            'metadata': self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'StateEntry':
        return cls(**data)


class StateManager:
    def __init__(self, redis_client: aioredis.Redis, namespace: str = "state"):
        self.redis = redis_client
        self.namespace = namespace
        self.logger = structlog.get_logger()
        
        # Local cache
        self.cache: Dict[str, StateEntry] = {}
        self.cache_ttl = 60  # seconds
        
        # State watchers
        self.watchers: Dict[str, List[Callable]] = defaultdict(list)
        self.watch_patterns: Dict[str, List[Callable]] = defaultdict(list)
        
        # Versioning
        self.versions: Dict[str, int] = {}
        
        # Locks for distributed state
        self.locks: Dict[str, asyncio.Lock] = {}
        
        # Background tasks
        self.running = False
        self.tasks: List[asyncio.Task] = []

    def _get_redis_key(self, key: str) -> str:
        return f"{self.namespace}:{key}"

    def _get_version_key(self, key: str) -> str:
        return f"{self.namespace}:version:{key}"

    def _get_lock_key(self, key: str) -> str:
        return f"{self.namespace}:lock:{key}"

    async def start(self):
        self.running = True
        
        # Start background tasks
        self.tasks.extend([
            asyncio.create_task(self._cache_cleaner()),
            asyncio.create_task(self._state_watcher())
        ])
        
        self.logger.info("State manager started")

    async def stop(self):
        self.running = False
        
        for task in self.tasks:
            task.cancel()
        
        await asyncio.gather(*self.tasks, return_exceptions=True)
        self.tasks.clear()
        
        self.logger.info("State manager stopped")

    async def get(self, key: str, default: Any = None) -> Any:
        # Check cache first
        if key in self.cache:
            entry = self.cache[key]
            if entry.ttl is None or (time.time() - entry.timestamp) < entry.ttl:
                return entry.value
            else:
                del self.cache[key]
        
        # Get from Redis
        redis_key = self._get_redis_key(key)
        data = await self.redis.get(redis_key)
        
        if data is None:
            return default
        
        entry_data = json.loads(data)
        entry = StateEntry.from_dict(entry_data)
        
        # Update cache
        self.cache[key] = entry
        
        return entry.value

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        # Get current version
        version = await self._get_version(key)
        version += 1
        
        # Create state entry
        entry = StateEntry(
            key=key,
            value=value,
            version=version,
            timestamp=time.time(),
            ttl=ttl,
            metadata=metadata
        )
        
        # Save to Redis
        redis_key = self._get_redis_key(key)
        data = json.dumps(entry.to_dict())
        
        if ttl:
            await self.redis.setex(redis_key, ttl, data)
        else:
            await self.redis.set(redis_key, data)
        
        # Update version
        await self._set_version(key, version)
        
        # Update cache
        self.cache[key] = entry
        
        # Notify watchers
        await self._notify_watchers(key, value, version)
        
        self.logger.info(
            "State updated",
            key=key,
            version=version,
            has_ttl=ttl is not None
        )

    async def delete(self, key: str):
        redis_key = self._get_redis_key(key)
        await self.redis.delete(redis_key)
        
        # Remove from cache
        if key in self.cache:
            del self.cache[key]
        
        # Delete version
        version_key = self._get_version_key(key)
        await self.redis.delete(version_key)
        
        # Notify watchers
        await self._notify_watchers(key, None, -1)
        
        self.logger.info("State deleted", key=key)

    async def exists(self, key: str) -> bool:
        redis_key = self._get_redis_key(key)
        return await self.redis.exists(redis_key) > 0

    async def get_many(self, keys: List[str]) -> Dict[str, Any]:
        results = {}
        
        # Check cache first
        uncached_keys = []
        for key in keys:
            if key in self.cache:
                entry = self.cache[key]
                if entry.ttl is None or (time.time() - entry.timestamp) < entry.ttl:
                    results[key] = entry.value
                else:
                    uncached_keys.append(key)
            else:
                uncached_keys.append(key)
        
        # Get uncached keys from Redis
        if uncached_keys:
            redis_keys = [self._get_redis_key(key) for key in uncached_keys]
            values = await self.redis.mget(redis_keys)
            
            for key, value in zip(uncached_keys, values):
                if value is not None:
                    entry_data = json.loads(value)
                    entry = StateEntry.from_dict(entry_data)
                    results[key] = entry.value
                    self.cache[key] = entry
        
        return results

    async def set_many(self, items: Dict[str, Any], ttl: Optional[int] = None):
        pipe = self.redis.pipeline()
        
        for key, value in items.items():
            version = await self._get_version(key)
            version += 1
            
            entry = StateEntry(
                key=key,
                value=value,
                version=version,
                timestamp=time.time(),
                ttl=ttl
            )
            
            redis_key = self._get_redis_key(key)
            data = json.dumps(entry.to_dict())
            
            if ttl:
                pipe.setex(redis_key, ttl, data)
            else:
                pipe.set(redis_key, data)
            
            # Update version
            version_key = self._get_version_key(key)
            pipe.set(version_key, version)
            
            # Update cache
            self.cache[key] = entry
        
        await pipe.execute()
        
        # Notify watchers
        for key, value in items.items():
            await self._notify_watchers(key, value, self.versions.get(key, 0))

    async def increment(self, key: str, amount: int = 1) -> int:
        redis_key = self._get_redis_key(key)
        new_value = await self.redis.incrby(redis_key, amount)
        
        # Update cache
        entry = StateEntry(
            key=key,
            value=new_value,
            version=await self._get_version(key),
            timestamp=time.time()
        )
        self.cache[key] = entry
        
        # Notify watchers
        await self._notify_watchers(key, new_value, entry.version)
        
        return new_value

    async def decrement(self, key: str, amount: int = 1) -> int:
        return await self.increment(key, -amount)

    async def get_with_lock(self, key: str, timeout: float = 10.0) -> Any:
        lock_key = self._get_lock_key(key)
        
        # Try to acquire lock
        lock_acquired = await self._acquire_lock(lock_key, timeout)
        
        if not lock_acquired:
            raise TimeoutError(f"Could not acquire lock for key: {key}")
        
        try:
            return await self.get(key)
        finally:
            await self._release_lock(lock_key)

    async def set_with_lock(
        self,
        key: str,
        value: Any,
        timeout: float = 10.0,
        ttl: Optional[int] = None
    ):
        lock_key = self._get_lock_key(key)
        
        # Try to acquire lock
        lock_acquired = await self._acquire_lock(lock_key, timeout)
        
        if not lock_acquired:
            raise TimeoutError(f"Could not acquire lock for key: {key}")
        
        try:
            await self.set(key, value, ttl)
        finally:
            await self._release_lock(lock_key)

    async def _acquire_lock(self, lock_key: str, timeout: float) -> bool:
        start_time = time.time()
        
        while True:
            # Try to set lock with NX (only if not exists)
            lock_acquired = await self.redis.set(
                lock_key,
                "locked",
                nx=True,
                ex=int(timeout)
            )
            
            if lock_acquired:
                return True
            
            # Check timeout
            if time.time() - start_time >= timeout:
                return False
            
            await asyncio.sleep(0.1)

    async def _release_lock(self, lock_key: str):
        await self.redis.delete(lock_key)

    async def watch(self, key: str, callback: Callable):
        self.watchers[key].append(callback)
        self.logger.info("Watcher registered", key=key)

    async def unwatch(self, key: str, callback: Callable):
        if callback in self.watchers[key]:
            self.watchers[key].remove(callback)
            self.logger.info("Watcher unregistered", key=key)

    async def watch_pattern(self, pattern: str, callback: Callable):
        self.watch_patterns[pattern].append(callback)
        self.logger.info("Pattern watcher registered", pattern=pattern)

    async def _notify_watchers(self, key: str, value: Any, version: int):
        # Notify exact key watchers
        for callback in self.watchers.get(key, []):
            try:
                await callback(key, value, version)
            except Exception as e:
                self.logger.error(
                    "Watcher callback error",
                    key=key,
                    error=str(e)
                )
        
        # Notify pattern watchers
        for pattern, callbacks in self.watch_patterns.items():
            if self._match_pattern(pattern, key):
                for callback in callbacks:
                    try:
                        await callback(key, value, version)
                    except Exception as e:
                        self.logger.error(
                            "Pattern watcher callback error",
                            pattern=pattern,
                            key=key,
                            error=str(e)
                        )

    def _match_pattern(self, pattern: str, key: str) -> bool:
        # Simple pattern matching (can be enhanced)
        if pattern.endswith('*'):
            return key.startswith(pattern[:-1])
        return pattern == key

    async def _get_version(self, key: str) -> int:
        if key in self.versions:
            return self.versions[key]
        
        version_key = self._get_version_key(key)
        version = await self.redis.get(version_key)
        
        if version is None:
            return 0
        
        version = int(version)
        self.versions[key] = version
        return version

    async def _set_version(self, key: str, version: int):
        version_key = self._get_version_key(key)
        await self.redis.set(version_key, version)
        self.versions[key] = version

    async def _cache_cleaner(self):
        while self.running:
            try:
                current_time = time.time()
                keys_to_remove = []
                
                for key, entry in self.cache.items():
                    # Check if entry has expired
                    if entry.ttl and (current_time - entry.timestamp) >= entry.ttl:
                        keys_to_remove.append(key)
                    # Check cache TTL
                    elif (current_time - entry.timestamp) >= self.cache_ttl:
                        keys_to_remove.append(key)
                
                for key in keys_to_remove:
                    del self.cache[key]
                
                if keys_to_remove:
                    self.logger.info(
                        "Cache cleaned",
                        removed_count=len(keys_to_remove)
                    )
                
                await asyncio.sleep(10)  # Clean every 10 seconds
                
            except Exception as e:
                self.logger.error("Cache cleaner error", error=str(e))
                await asyncio.sleep(1)

    async def _state_watcher(self):
        # Implement Redis keyspace notifications for real-time updates
        pubsub = self.redis.pubsub()
        
        try:
            # Subscribe to keyspace events
            await pubsub.psubscribe(f"__keyspace@0__:{self.namespace}:*")
            
            while self.running:
                try:
                    message = await pubsub.get_message(
                        ignore_subscribe_messages=True,
                        timeout=1.0
                    )
                    
                    if message and message['type'] == 'pmessage':
                        # Extract key from channel
                        channel = message['channel'].decode('utf-8')
                        key = channel.split(':', 2)[-1]
                        key = key.replace(f"{self.namespace}:", "")
                        
                        # Invalidate cache
                        if key in self.cache:
                            del self.cache[key]
                        
                        self.logger.debug(
                            "State change detected",
                            key=key
                        )
                    
                    await asyncio.sleep(0.01)
                    
                except Exception as e:
                    self.logger.error("State watcher error", error=str(e))
                    await asyncio.sleep(1)
                    
        finally:
            await pubsub.close()

    async def get_state_stats(self) -> Dict[str, Any]:
        # Get all keys in namespace
        pattern = f"{self.namespace}:*"
        cursor = 0
        keys = []
        
        while True:
            cursor, partial_keys = await self.redis.scan(
                cursor=cursor,
                match=pattern,
                count=100
            )
            keys.extend(partial_keys)
            
            if cursor == 0:
                break
        
        return {
            'total_keys': len(keys),
            'cache_size': len(self.cache),
            'watchers_count': sum(len(w) for w in self.watchers.values()),
            'pattern_watchers_count': sum(len(w) for w in self.watch_patterns.values()),
            'versions_tracked': len(self.versions)
        }
"""
Health check utilities for the LinkedIn Multi-Agent System
"""

import asyncio
import json
from typing import Dict, Any, List
import redis.asyncio as aioredis
from datetime import datetime
import structlog

logger = structlog.get_logger()


async def check_redis_health(redis_url: str = "redis://localhost:6379") -> Dict[str, Any]:
    """Check Redis connectivity and basic operations"""
    try:
        client = await aioredis.from_url(redis_url, decode_responses=True)
        
        # Test basic operations
        await client.ping()
        await client.set("health_check", "ok", ex=10)
        result = await client.get("health_check")
        await client.delete("health_check")
        
        await client.close()
        
        return {
            "status": "healthy",
            "service": "redis",
            "timestamp": datetime.utcnow().isoformat(),
            "details": {
                "ping": "ok",
                "read_write": "ok" if result == "ok" else "failed"
            }
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "service": "redis",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }


async def check_agent_health(agent_id: str) -> Dict[str, Any]:
    """Check health of a specific agent"""
    try:
        # This would check if agent is responsive via Redis
        client = await aioredis.from_url("redis://localhost:6379", decode_responses=True)
        
        # Check heartbeat
        heartbeat = await client.get(f"heartbeat:{agent_id}")
        
        if heartbeat:
            heartbeat_data = json.loads(heartbeat)
            last_heartbeat = datetime.fromisoformat(heartbeat_data['timestamp'])
            age = (datetime.utcnow() - last_heartbeat).total_seconds()
            
            status = "healthy" if age < 60 else "stale"
            
            await client.close()
            
            return {
                "status": status,
                "service": f"agent_{agent_id}",
                "timestamp": datetime.utcnow().isoformat(),
                "details": {
                    "last_heartbeat": heartbeat_data['timestamp'],
                    "heartbeat_age_seconds": age,
                    "agent_state": heartbeat_data.get('state', 'unknown')
                }
            }
        else:
            await client.close()
            return {
                "status": "unhealthy",
                "service": f"agent_{agent_id}",
                "timestamp": datetime.utcnow().isoformat(),
                "error": "No heartbeat found"
            }
            
    except Exception as e:
        return {
            "status": "error",
            "service": f"agent_{agent_id}",
            "timestamp": datetime.utcnow().isoformat(),
            "error": str(e)
        }


async def system_health_check() -> Dict[str, Any]:
    """Comprehensive system health check"""
    health_results = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }
    
    # Check Redis
    redis_health = await check_redis_health()
    health_results["checks"]["redis"] = redis_health
    
    if redis_health["status"] != "healthy":
        health_results["status"] = "degraded"
    
    # Check core agents
    core_agents = [
        "account_manager",
        "content_analysis", 
        "interaction",
        "conversation",
        "safety"
    ]
    
    agent_checks = []
    for agent in core_agents:
        agent_health = await check_agent_health(agent)
        agent_checks.append(agent_health)
        health_results["checks"][f"agent_{agent}"] = agent_health
        
        if agent_health["status"] not in ["healthy", "stale"]:
            health_results["status"] = "degraded"
    
    # Overall status determination
    unhealthy_services = [
        check for check in health_results["checks"].values()
        if check["status"] == "unhealthy"
    ]
    
    if len(unhealthy_services) > 0:
        health_results["status"] = "unhealthy"
    elif any(check["status"] == "stale" for check in health_results["checks"].values()):
        health_results["status"] = "degraded"
    
    health_results["summary"] = {
        "total_checks": len(health_results["checks"]),
        "healthy": len([c for c in health_results["checks"].values() if c["status"] == "healthy"]),
        "degraded": len([c for c in health_results["checks"].values() if c["status"] == "stale"]),
        "unhealthy": len(unhealthy_services)
    }
    
    return health_results


async def health_check():
    """Main health check function for CLI usage"""
    try:
        result = await system_health_check()
        
        print(f"System Status: {result['status'].upper()}")
        print(f"Timestamp: {result['timestamp']}")
        print()
        
        # Print summary
        summary = result['summary']
        print("Summary:")
        print(f"  Total Checks: {summary['total_checks']}")
        print(f"  Healthy: {summary['healthy']}")
        print(f"  Degraded: {summary['degraded']}")
        print(f"  Unhealthy: {summary['unhealthy']}")
        print()
        
        # Print individual check results
        print("Individual Checks:")
        for service, check in result['checks'].items():
            status_icon = {
                'healthy': '✅',
                'stale': '⚠️',
                'degraded': '⚠️',
                'unhealthy': '❌',
                'error': '❌'
            }.get(check['status'], '❓')
            
            print(f"  {status_icon} {service}: {check['status']}")
            
            if 'error' in check:
                print(f"    Error: {check['error']}")
            elif 'details' in check:
                for key, value in check['details'].items():
                    print(f"    {key}: {value}")
        
        # Exit with appropriate code
        if result['status'] == 'unhealthy':
            return False
        
        return True
        
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        print(f"❌ Health check failed: {e}")
        return False


if __name__ == "__main__":
    import sys
    
    async def main():
        success = await health_check()
        sys.exit(0 if success else 1)
    
    asyncio.run(main())
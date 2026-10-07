#!/usr/bin/env python3
"""
LinkedIn Multi-Agent Automation System

A sophisticated multi-agent system for LinkedIn automation with AI-powered 
decision making, intelligent content analysis, and human-like interactions.

Usage:
    python main.py [options]

Options:
    --config CONFIG_FILE    Path to configuration file
    --log-level LEVEL       Logging level (DEBUG, INFO, WARNING, ERROR)
    --agents AGENT_LIST     Comma-separated list of agents to start
    --web-dashboard         Start web dashboard
    --monitoring           Enable monitoring endpoints
    --help                 Show this help message
"""

import asyncio
import argparse
import signal
import sys
import logging
from pathlib import Path
from typing import List, Optional
import structlog
from contextlib import asynccontextmanager

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from src.config.config import load_config, SystemConfig
from src.infrastructure.orchestrator import AgentOrchestrator


class LinkedInAutomationSystem:
    """Main LinkedIn Automation System"""
    
    def __init__(self, config: SystemConfig):
        self.config = config
        self.orchestrator: Optional[AgentOrchestrator] = None
        self.logger = self._setup_logging()
        self._shutdown_event = asyncio.Event()
        
    def _setup_logging(self) -> structlog.BoundLogger:
        """Setup structured logging"""
        logging.basicConfig(
            level=getattr(logging, self.config.log_level),
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_log_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.PositionalArgumentsFormatter(),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.UnicodeDecoder(),
                structlog.processors.JSONRenderer()
            ],
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )
        
        return structlog.get_logger("linkedin_automation")
    
    async def start(self, agent_filter: Optional[List[str]] = None):
        """Start the automation system"""
        try:
            self.logger.info("Starting LinkedIn Multi-Agent Automation System")
            
            # Create and initialize orchestrator
            orchestrator_config = {
                'redis_url': self.config.redis.url,
                'agents': {}
            }
            
            # Filter agents if specified
            if agent_filter:
                for agent_name in agent_filter:
                    if agent_name in self.config.agents:
                        orchestrator_config['agents'][agent_name] = self.config.agents[agent_name].__dict__
            else:
                orchestrator_config['agents'] = {
                    name: config.__dict__ 
                    for name, config in self.config.agents.items()
                }
            
            self.orchestrator = AgentOrchestrator(orchestrator_config)
            await self.orchestrator.initialize()
            
            # Start orchestrator
            await self.orchestrator.start()
            
            self.logger.info("System started successfully", 
                           agents=list(orchestrator_config['agents'].keys()))
            
            # Setup signal handlers
            self._setup_signal_handlers()
            
            # Wait for shutdown signal
            await self._shutdown_event.wait()
            
        except KeyboardInterrupt:
            self.logger.info("Received keyboard interrupt, shutting down...")
        except Exception as e:
            self.logger.error("Error during startup", error=str(e))
            raise
        finally:
            await self.stop()
    
    async def stop(self):
        """Stop the automation system"""
        if self.orchestrator:
            self.logger.info("Stopping orchestrator...")
            await self.orchestrator.stop()
            self.orchestrator = None
        
        self.logger.info("LinkedIn Automation System stopped")
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            self.logger.info(f"Received signal {signum}, initiating shutdown...")
            self._shutdown_event.set()
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
    
    async def get_system_status(self) -> dict:
        """Get system status"""
        if not self.orchestrator:
            return {'status': 'stopped'}
        
        return await self.orchestrator.get_orchestrator_status()
    
    async def send_command(self, agent_type: str, command: str, payload: dict):
        """Send command to specific agent type"""
        if not self.orchestrator:
            raise RuntimeError("System not running")
        
        await self.orchestrator.send_command(agent_type, command, payload)


def create_argument_parser() -> argparse.ArgumentParser:
    """Create command line argument parser"""
    parser = argparse.ArgumentParser(
        description="LinkedIn Multi-Agent Automation System",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py --config config.json
  python main.py --agents account_manager,content_analysis
  python main.py --log-level DEBUG --web-dashboard
        """
    )
    
    parser.add_argument(
        '--config',
        type=str,
        help='Path to configuration file'
    )
    
    parser.add_argument(
        '--log-level',
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'],
        default='INFO',
        help='Logging level'
    )
    
    parser.add_argument(
        '--agents',
        type=str,
        help='Comma-separated list of agents to start (default: all)'
    )
    
    parser.add_argument(
        '--web-dashboard',
        action='store_true',
        help='Start web dashboard'
    )
    
    parser.add_argument(
        '--monitoring',
        action='store_true',
        help='Enable monitoring endpoints'
    )
    
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate configuration without starting system'
    )
    
    parser.add_argument(
        '--create-sample-config',
        action='store_true',
        help='Create sample configuration file and exit'
    )
    
    return parser


async def main():
    """Main entry point"""
    parser = create_argument_parser()
    args = parser.parse_args()
    
    # Handle special commands
    if args.create_sample_config:
        from src.config.config import create_sample_config
        create_sample_config()
        return
    
    # Load configuration
    if args.config:
        from src.config.config import SystemConfig
        config = SystemConfig.from_file(args.config)
    else:
        config = load_config()
    
    # Override log level if specified
    if args.log_level:
        config.log_level = args.log_level
    
    # Validate configuration
    try:
        validate_config(config)
    except Exception as e:
        print(f"Configuration validation failed: {e}")
        sys.exit(1)
    
    if args.dry_run:
        print("Configuration validation passed")
        return
    
    # Parse agent filter
    agent_filter = None
    if args.agents:
        agent_filter = [agent.strip() for agent in args.agents.split(',')]
        
        # Validate agent names
        invalid_agents = set(agent_filter) - set(config.agents.keys())
        if invalid_agents:
            print(f"Invalid agents: {invalid_agents}")
            print(f"Available agents: {list(config.agents.keys())}")
            sys.exit(1)
    
    # Create and start system
    system = LinkedInAutomationSystem(config)
    
    try:
        if args.web_dashboard:
            # Start web dashboard in background
            dashboard_task = asyncio.create_task(start_web_dashboard(system))
        
        if args.monitoring:
            # Start monitoring endpoints in background
            monitoring_task = asyncio.create_task(start_monitoring(system))
        
        # Start main system
        await system.start(agent_filter)
        
    except Exception as e:
        print(f"Error starting system: {e}")
        sys.exit(1)


def validate_config(config: SystemConfig):
    """Validate system configuration"""
    errors = []
    
    # Validate Redis connection
    if not config.redis.host:
        errors.append("Redis host not specified")
    
    # Validate API keys if needed
    openai_agents = ['content_analysis', 'conversation']
    has_openai_agents = any(agent in config.agents for agent in openai_agents)
    
    if has_openai_agents:
        if not config.content_analysis.openai_api_key and not config.content_analysis.use_local_models:
            errors.append("OpenAI API key required for content analysis and conversation agents")
    
    # Validate agent dependencies
    for agent_name, agent_config in config.agents.items():
        for dependency in agent_config.dependencies:
            if dependency not in config.agents:
                errors.append(f"Agent {agent_name} depends on {dependency} which is not configured")
    
    # Validate rate limits
    if config.linkedin.likes_per_day < config.linkedin.likes_per_hour:
        errors.append("Daily like limit must be greater than hourly limit")
    
    if errors:
        raise ValueError(f"Configuration errors:\n" + "\n".join(f"  - {error}" for error in errors))


async def start_web_dashboard(system: LinkedInAutomationSystem):
    """Start web dashboard (placeholder)"""
    # This would start a web server for system monitoring and control
    print("Web dashboard would be started here")
    pass


async def start_monitoring(system: LinkedInAutomationSystem):
    """Start monitoring endpoints (placeholder)"""
    # This would start Prometheus metrics endpoints
    print("Monitoring endpoints would be started here")
    pass


if __name__ == "__main__":
    # Check Python version
    if sys.version_info < (3, 8):
        print("Python 3.8 or higher is required")
        sys.exit(1)
    
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nShutdown complete")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
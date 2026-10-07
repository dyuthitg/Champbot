import os
from typing import Dict, Any, List
from dataclasses import dataclass, field
import json
from pathlib import Path


@dataclass
class RedisConfig:
    host: str = "localhost"
    port: int = 6379
    password: str = ""
    db: int = 0
    
    @property
    def url(self) -> str:
        auth = f":{self.password}@" if self.password else ""
        return f"redis://{auth}{self.host}:{self.port}/{self.db}"


@dataclass
class SecurityConfig:
    encryption_key_file: str = ".encryption_key"
    max_login_attempts: int = 3
    session_timeout: int = 3600  # 1 hour
    rate_limit_window: int = 3600  # 1 hour
    enable_2fa: bool = False


@dataclass
class AgentConfig:
    agent_type: str
    agent_class: str
    min_instances: int = 1
    max_instances: int = 10
    auto_scale: bool = True
    config: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)


@dataclass
class LinkedInConfig:
    # Rate limiting
    likes_per_hour: int = 30
    likes_per_day: int = 150
    comments_per_hour: int = 10
    comments_per_day: int = 50
    shares_per_hour: int = 5
    shares_per_day: int = 20
    follows_per_hour: int = 20
    follows_per_day: int = 100
    connections_per_hour: int = 10
    connections_per_day: int = 50
    
    # Delays and timing
    like_cooldown: int = 10  # seconds
    comment_cooldown: int = 60
    share_cooldown: int = 120
    follow_cooldown: int = 30
    connection_cooldown: int = 60
    
    # Business hours and patterns
    business_hours: List[int] = field(default_factory=lambda: [9, 18])
    peak_hours: List[int] = field(default_factory=lambda: [10, 11, 14, 15])
    weekend_activity: float = 0.3
    random_delay_range: List[int] = field(default_factory=lambda: [2, 10])
    
    # Browser settings
    headless: bool = True
    browser_type: str = "playwright"  # or "selenium"


@dataclass
class ContentAnalysisConfig:
    openai_api_key: str = ""
    use_local_models: bool = False
    model_name: str = "gpt-3.5-turbo"
    cache_ttl: int = 3600
    min_relevance_score: float = 0.5
    min_quality_score: float = 0.4
    target_industries: List[str] = field(default_factory=list)
    target_keywords: List[str] = field(default_factory=list)
    excluded_keywords: List[str] = field(default_factory=list)


@dataclass
class ConversationConfig:
    openai_api_key: str = ""
    use_local_models: bool = False
    model_name: str = "gpt-3.5-turbo"
    cache_ttl: int = 3600
    min_confidence_score: float = 0.7
    min_quality_score: float = 0.6
    min_relevance_score: float = 0.6
    max_alternatives: int = 3
    diversity_threshold: float = 0.8


@dataclass
class SystemConfig:
    redis: RedisConfig = field(default_factory=RedisConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    linkedin: LinkedInConfig = field(default_factory=LinkedInConfig)
    content_analysis: ContentAnalysisConfig = field(default_factory=ContentAnalysisConfig)
    conversation: ConversationConfig = field(default_factory=ConversationConfig)
    
    # System-wide settings
    log_level: str = "INFO"
    max_workers: int = 10
    health_check_interval: int = 30
    
    # Agent configurations
    agents: Dict[str, AgentConfig] = field(default_factory=dict)
    
    def __post_init__(self):
        # Initialize default agent configurations
        self._setup_default_agents()
    
    def _setup_default_agents(self):
        """Setup default agent configurations"""
        self.agents = {
            "account_manager": AgentConfig(
                agent_type="account_manager",
                agent_class="src.agents.core.account_manager_agent.AccountManagerAgent",
                min_instances=1,
                max_instances=3,
                auto_scale=False,
                config={
                    "encryption_key_file": self.security.encryption_key_file,
                    "account_cooldown": 300,
                    "max_actions_per_hour": 50,
                    "headless": self.linkedin.headless,
                    "browser_type": self.linkedin.browser_type
                }
            ),
            
            "content_analysis": AgentConfig(
                agent_type="content_analysis",
                agent_class="src.agents.core.content_analysis_agent.ContentAnalysisAgent",
                min_instances=2,
                max_instances=5,
                auto_scale=True,
                config={
                    "openai_api_key": self.content_analysis.openai_api_key,
                    "use_local_models": self.content_analysis.use_local_models,
                    "model_name": self.content_analysis.model_name,
                    "cache_ttl": self.content_analysis.cache_ttl,
                    "min_relevance_score": self.content_analysis.min_relevance_score,
                    "min_quality_score": self.content_analysis.min_quality_score,
                    "target_industries": self.content_analysis.target_industries,
                    "target_keywords": self.content_analysis.target_keywords,
                    "excluded_keywords": self.content_analysis.excluded_keywords
                }
            ),
            
            "interaction": AgentConfig(
                agent_type="interaction",
                agent_class="src.agents.core.interaction_agent.InteractionAgent",
                min_instances=2,
                max_instances=8,
                auto_scale=True,
                config={
                    "likes_per_hour": self.linkedin.likes_per_hour,
                    "likes_per_day": self.linkedin.likes_per_day,
                    "comments_per_hour": self.linkedin.comments_per_hour,
                    "comments_per_day": self.linkedin.comments_per_day,
                    "shares_per_hour": self.linkedin.shares_per_hour,
                    "shares_per_day": self.linkedin.shares_per_day,
                    "follows_per_hour": self.linkedin.follows_per_hour,
                    "follows_per_day": self.linkedin.follows_per_day,
                    "connections_per_hour": self.linkedin.connections_per_hour,
                    "connections_per_day": self.linkedin.connections_per_day,
                    "like_cooldown": self.linkedin.like_cooldown,
                    "comment_cooldown": self.linkedin.comment_cooldown,
                    "share_cooldown": self.linkedin.share_cooldown,
                    "follow_cooldown": self.linkedin.follow_cooldown,
                    "connection_cooldown": self.linkedin.connection_cooldown,
                    "business_hours": self.linkedin.business_hours,
                    "peak_hours": self.linkedin.peak_hours,
                    "weekend_activity": self.linkedin.weekend_activity,
                    "random_delay_range": self.linkedin.random_delay_range,
                    "browser_type": self.linkedin.browser_type
                },
                dependencies=["account_manager"]
            ),
            
            "conversation": AgentConfig(
                agent_type="conversation",
                agent_class="src.agents.core.conversation_agent.ConversationAgent",
                min_instances=2,
                max_instances=5,
                auto_scale=True,
                config={
                    "openai_api_key": self.conversation.openai_api_key,
                    "use_local_models": self.conversation.use_local_models,
                    "model_name": self.conversation.model_name,
                    "cache_ttl": self.conversation.cache_ttl,
                    "min_confidence_score": self.conversation.min_confidence_score,
                    "min_quality_score": self.conversation.min_quality_score,
                    "min_relevance_score": self.conversation.min_relevance_score,
                    "max_alternatives": self.conversation.max_alternatives,
                    "diversity_threshold": self.conversation.diversity_threshold
                },
                dependencies=["content_analysis"]
            ),
            
            "safety": AgentConfig(
                agent_type="safety",
                agent_class="src.agents.core.safety_agent.SafetyAgent",
                min_instances=1,
                max_instances=2,
                auto_scale=False,
                config={
                    "max_actions_per_hour": 100,
                    "max_actions_per_day": 500,
                    "suspicious_activity_threshold": 0.8,
                    "rate_limit_buffer": 0.8,
                    "cooldown_on_warning": 300
                }
            ),
            
            "scheduler": AgentConfig(
                agent_type="scheduler",
                agent_class="src.agents.core.scheduler_agent.SchedulerAgent",
                min_instances=1,
                max_instances=2,
                auto_scale=False,
                config={
                    "max_scheduled_tasks": 1000,
                    "task_timeout": 3600,
                    "cleanup_interval": 300
                }
            ),
            
            "whatsapp_monitor": AgentConfig(
                agent_type="whatsapp_monitor",
                agent_class="src.agents.core.whatsapp_monitor_agent.WhatsAppMonitorAgent",
                min_instances=1,
                max_instances=2,
                auto_scale=False,
                config={
                    "message_check_interval": 30,
                    "max_messages_per_batch": 50,
                    "linkedin_url_pattern": r"linkedin\.com\/[a-zA-Z0-9\-\/]+"
                }
            ),
            
            "analytics": AgentConfig(
                agent_type="analytics",
                agent_class="src.agents.core.analytics_agent.AnalyticsAgent",
                min_instances=1,
                max_instances=2,
                auto_scale=False,
                config={
                    "metrics_retention_days": 30,
                    "report_generation_interval": 3600,
                    "performance_tracking_enabled": True
                }
            )
        }
    
    @classmethod
    def from_file(cls, config_path: str) -> 'SystemConfig':
        """Load configuration from JSON file"""
        config_file = Path(config_path)
        
        if config_file.exists():
            with open(config_file, 'r') as f:
                data = json.load(f)
            
            # Create config with loaded data
            config = cls()
            
            # Update Redis config
            if 'redis' in data:
                redis_data = data['redis']
                config.redis = RedisConfig(
                    host=redis_data.get('host', 'localhost'),
                    port=redis_data.get('port', 6379),
                    password=redis_data.get('password', ''),
                    db=redis_data.get('db', 0)
                )
            
            # Update other configurations similarly
            if 'security' in data:
                sec_data = data['security']
                config.security = SecurityConfig(**sec_data)
            
            if 'linkedin' in data:
                linkedin_data = data['linkedin']
                config.linkedin = LinkedInConfig(**linkedin_data)
            
            if 'content_analysis' in data:
                ca_data = data['content_analysis']
                config.content_analysis = ContentAnalysisConfig(**ca_data)
            
            if 'conversation' in data:
                conv_data = data['conversation']
                config.conversation = ConversationConfig(**conv_data)
            
            # Update system settings
            config.log_level = data.get('log_level', 'INFO')
            config.max_workers = data.get('max_workers', 10)
            config.health_check_interval = data.get('health_check_interval', 30)
            
            # Re-setup agents with updated config
            config._setup_default_agents()
            
            return config
        else:
            # Return default configuration
            return cls()
    
    @classmethod
    def from_env(cls) -> 'SystemConfig':
        """Load configuration from environment variables"""
        config = cls()
        
        # Redis configuration
        config.redis.host = os.getenv('REDIS_HOST', 'localhost')
        config.redis.port = int(os.getenv('REDIS_PORT', '6379'))
        config.redis.password = os.getenv('REDIS_PASSWORD', '')
        config.redis.db = int(os.getenv('REDIS_DB', '0'))
        
        # API keys
        config.content_analysis.openai_api_key = os.getenv('OPENAI_API_KEY', '')
        config.conversation.openai_api_key = os.getenv('OPENAI_API_KEY', '')
        
        # LinkedIn settings
        config.linkedin.headless = os.getenv('LINKEDIN_HEADLESS', 'true').lower() == 'true'
        config.linkedin.browser_type = os.getenv('LINKEDIN_BROWSER_TYPE', 'playwright')
        
        # System settings
        config.log_level = os.getenv('LOG_LEVEL', 'INFO')
        config.max_workers = int(os.getenv('MAX_WORKERS', '10'))
        
        # Re-setup agents with updated config
        config._setup_default_agents()
        
        return config
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return {
            'redis': {
                'host': self.redis.host,
                'port': self.redis.port,
                'password': self.redis.password,
                'db': self.redis.db
            },
            'security': {
                'encryption_key_file': self.security.encryption_key_file,
                'max_login_attempts': self.security.max_login_attempts,
                'session_timeout': self.security.session_timeout,
                'rate_limit_window': self.security.rate_limit_window,
                'enable_2fa': self.security.enable_2fa
            },
            'linkedin': {
                'likes_per_hour': self.linkedin.likes_per_hour,
                'likes_per_day': self.linkedin.likes_per_day,
                'comments_per_hour': self.linkedin.comments_per_hour,
                'comments_per_day': self.linkedin.comments_per_day,
                'shares_per_hour': self.linkedin.shares_per_hour,
                'shares_per_day': self.linkedin.shares_per_day,
                'follows_per_hour': self.linkedin.follows_per_hour,
                'follows_per_day': self.linkedin.follows_per_day,
                'connections_per_hour': self.linkedin.connections_per_hour,
                'connections_per_day': self.linkedin.connections_per_day,
                'business_hours': self.linkedin.business_hours,
                'peak_hours': self.linkedin.peak_hours,
                'weekend_activity': self.linkedin.weekend_activity,
                'headless': self.linkedin.headless,
                'browser_type': self.linkedin.browser_type
            },
            'content_analysis': {
                'openai_api_key': self.content_analysis.openai_api_key,
                'use_local_models': self.content_analysis.use_local_models,
                'model_name': self.content_analysis.model_name,
                'target_industries': self.content_analysis.target_industries,
                'target_keywords': self.content_analysis.target_keywords,
                'excluded_keywords': self.content_analysis.excluded_keywords
            },
            'conversation': {
                'openai_api_key': self.conversation.openai_api_key,
                'use_local_models': self.conversation.use_local_models,
                'model_name': self.conversation.model_name,
                'min_confidence_score': self.conversation.min_confidence_score
            },
            'log_level': self.log_level,
            'max_workers': self.max_workers,
            'health_check_interval': self.health_check_interval
        }
    
    def save_to_file(self, config_path: str):
        """Save configuration to JSON file"""
        config_file = Path(config_path)
        config_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(config_file, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)


def load_config() -> SystemConfig:
    """Load configuration from various sources with precedence"""
    # 1. Try to load from config file
    config_file = Path("config/config.json")
    if config_file.exists():
        return SystemConfig.from_file(str(config_file))
    
    # 2. Load from environment variables
    return SystemConfig.from_env()


def create_sample_config():
    """Create a sample configuration file"""
    config = SystemConfig()
    
    # Set some example values
    config.content_analysis.target_industries = ["technology", "finance", "healthcare"]
    config.content_analysis.target_keywords = ["innovation", "AI", "machine learning", "digital transformation"]
    config.content_analysis.excluded_keywords = ["politics", "controversial"]
    
    config.linkedin.likes_per_hour = 25
    config.linkedin.comments_per_hour = 8
    config.linkedin.business_hours = [8, 19]
    config.linkedin.peak_hours = [9, 10, 13, 14, 16]
    
    # Save sample config
    config.save_to_file("config/sample_config.json")
    print("Sample configuration created at config/sample_config.json")


if __name__ == "__main__":
    create_sample_config()
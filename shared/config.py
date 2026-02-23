"""
Enterprise Configuration Management

This module provides centralized configuration management for the Agent-to-Agent framework.
It supports:
- Environment-based configuration (development, staging, production)
- External JSON configuration files
- Environment variable overrides
- Schema validation
- Hot-reloading capabilities
- Secure secrets management

Configuration Priority (highest to lowest):
1. Environment variables
2. External config files
3. Default values

Usage:
    from shared.config import EnterpriseConfig, ConfigManager
    
    # Get singleton instance
    config = ConfigManager.get_instance()
    
    # Access settings
    if config.feature_enabled("guardrails"):
        # do something
    
    # Get LLM settings
    llm_config = config.get_llm_config()
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List, TypeVar, Generic
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
import hashlib
from datetime import datetime

logger = logging.getLogger(__name__)


class Environment(Enum):
    """Supported deployment environments"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"
    TEST = "test"


@dataclass
class FeatureFlags:
    """Feature flag configuration"""
    enable_guardrails: bool = True
    enable_audit_logging: bool = True
    enable_security_checks: bool = True
    enable_pii_redaction: bool = True
    enable_prompt_caching: bool = False
    enable_chain_of_thought_logging: bool = True
    enable_identity_propagation: bool = True
    strict_mode: bool = False


@dataclass
class ComplianceConfig:
    """Compliance and audit configuration"""
    worm_storage_path: str = "./audit_logs"
    log_retention_days: int = 90
    encryption_at_rest: bool = True
    audit_signature_algorithm: str = "SHA256"


@dataclass
class LLMConfig:
    """LLM provider configuration"""
    default_model: str = "anthropic.claude-3-sonnet-20240229-v1:0"
    fallback_model: str = "anthropic.claude-3-haiku-20240307-v1:0"
    region: str = "us-east-1"
    max_tokens: int = 4096
    temperature: float = 0.7
    timeout_seconds: int = 120
    retry_attempts: int = 3
    retry_backoff_seconds: int = 2


@dataclass 
class SessionConfig:
    """Session management configuration"""
    max_history_items: int = 50
    history_summary_threshold: int = 20
    session_timeout_minutes: int = 60
    persist_sessions: bool = True
    session_storage_path: str = "./sessions"


@dataclass
class RateLimitConfig:
    """Rate limiting configuration"""
    enabled: bool = True
    requests_per_minute: int = 60
    tokens_per_minute: int = 100000
    burst_limit: int = 10


@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"
    format: str = "json"
    include_timestamps: bool = True
    include_request_ids: bool = True
    sensitive_fields_mask: List[str] = field(default_factory=lambda: ["password", "api_key", "token", "secret"])


@dataclass
class ServiceEndpoint:
    """Individual service endpoint configuration"""
    host: str = "localhost"
    port: int = 8000
    protocol: str = "http"
    enabled: bool = True
    
    @property
    def url(self) -> str:
        """Get full URL for service"""
        return f"{self.protocol}://{self.host}:{self.port}"


@dataclass
class NetworkConfig:
    """Network configuration"""
    bind_host: str = "0.0.0.0"
    public_host: str = "localhost"
    use_ssl: bool = False
    ssl_cert_path: str = ""
    ssl_key_path: str = ""
    cors_origins: List[str] = field(default_factory=lambda: ["*"])
    request_timeout_seconds: int = 300


@dataclass
class WorkflowConfig:
    """Workflow execution configuration"""
    enable_persistence: bool = True
    database_path: str = "./workflows.db"
    enable_retry: bool = True
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    max_retry_delay_seconds: float = 30.0
    enable_parallel_execution: bool = True
    max_parallel_steps: int = 5
    default_timeout_seconds: int = 3600


@dataclass
class HealthCheckConfig:
    """Health check configuration"""
    enabled: bool = True
    interval_seconds: int = 10
    timeout_seconds: int = 5
    max_retries: int = 3
    unhealthy_threshold: int = 3


class ConfigManager:
    """
    Singleton configuration manager for enterprise settings.
    
    Handles loading, validation, and caching of configuration from multiple sources.
    """
    
    _instance: Optional['ConfigManager'] = None
    _config_hash: Optional[str] = None
    
    # Base paths
    CONFIG_DIR = Path(__file__).parent / "config"
    
    # Config file names
    ENTERPRISE_CONFIG_FILE = "enterprise_config.json"
    SECURITY_POLICIES_FILE = "security_policies.json"
    GUARDRAILS_CONFIG_FILE = "guardrails_config.json"
    
    def __init__(self):
        """Initialize configuration manager"""
        self._loaded = False
        self._load_timestamp: Optional[datetime] = None
        
        # Configuration objects
        self.environment: Environment = Environment.DEVELOPMENT
        self.version: str = "1.0.0"
        self.deployment_id: str = "default"
        self.feature_flags: FeatureFlags = FeatureFlags()
        self.compliance: ComplianceConfig = ComplianceConfig()
        self.llm: LLMConfig = LLMConfig()
        self.session: SessionConfig = SessionConfig()
        self.rate_limit: RateLimitConfig = RateLimitConfig()
        self.logging: LoggingConfig = LoggingConfig()
        self.network: NetworkConfig = NetworkConfig()
        self.workflow: WorkflowConfig = WorkflowConfig()
        self.health_check: HealthCheckConfig = HealthCheckConfig()
        
        # Service endpoints (dynamic)
        self._services: Dict[str, ServiceEndpoint] = {}
        self._agents: Dict[str, Dict[str, Any]] = {}
        self._mcp_servers: Dict[str, Dict[str, Any]] = {}
        
        # Raw config caches
        self._security_policies: Dict[str, Any] = {}
        self._guardrails_config: Dict[str, Any] = {}
        self._enterprise_config: Dict[str, Any] = {}
        
        # Load on init
        self._load_all_configs()
    
    @classmethod
    def get_instance(cls) -> 'ConfigManager':
        """Get or create singleton instance"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls):
        """Reset singleton (useful for testing)"""
        cls._instance = None
        cls._config_hash = None
    
    def _load_all_configs(self):
        """Load all configuration files"""
        self._load_enterprise_config()
        self._load_security_policies()
        self._load_guardrails_config()
        self._apply_environment_overrides()
        self._loaded = True
        self._load_timestamp = datetime.utcnow()
        logger.info(f"Configuration loaded at {self._load_timestamp}")
    
    def _get_config_path(self, filename: str) -> Path:
        """Get full path to config file, checking environment override"""
        # Check for environment-specific override
        env_path = os.getenv(f"{filename.upper().replace('.', '_')}_PATH")
        if env_path and Path(env_path).exists():
            return Path(env_path)
        
        # Use default path
        return self.CONFIG_DIR / filename
    
    def _load_json_config(self, filename: str, default: Dict = None) -> Dict[str, Any]:
        """Load JSON config file with error handling"""
        config_path = self._get_config_path(filename)
        
        try:
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    logger.debug(f"Loaded config from {config_path}")
                    return config
            else:
                logger.warning(f"Config file not found: {config_path}, using defaults")
                return default or {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in {config_path}: {e}")
            return default or {}
        except Exception as e:
            logger.error(f"Error loading {config_path}: {e}")
            return default or {}
    
    def _load_enterprise_config(self):
        """Load main enterprise configuration"""
        self._enterprise_config = self._load_json_config(self.ENTERPRISE_CONFIG_FILE)
        
        if not self._enterprise_config:
            return
        
        # Parse environment
        env_str = self._enterprise_config.get("environment", "development")
        try:
            self.environment = Environment(env_str)
        except ValueError:
            logger.warning(f"Unknown environment '{env_str}', using development")
            self.environment = Environment.DEVELOPMENT
        
        self.version = self._enterprise_config.get("version", "1.0.0")
        self.deployment_id = self._enterprise_config.get("deployment_id", "default")
        
        # Parse feature flags
        flags = self._enterprise_config.get("feature_flags", {})
        self.feature_flags = FeatureFlags(
            enable_guardrails=flags.get("enable_guardrails", True),
            enable_audit_logging=flags.get("enable_audit_logging", True),
            enable_security_checks=flags.get("enable_security_checks", True),
            enable_pii_redaction=flags.get("enable_pii_redaction", True),
            enable_prompt_caching=flags.get("enable_prompt_caching", False),
            enable_chain_of_thought_logging=flags.get("enable_chain_of_thought_logging", True),
            enable_identity_propagation=flags.get("enable_identity_propagation", True),
            strict_mode=flags.get("strict_mode", False)
        )
        
        # Parse compliance config
        compliance = self._enterprise_config.get("compliance", {})
        self.compliance = ComplianceConfig(
            worm_storage_path=compliance.get("worm_storage_path", "./audit_logs"),
            log_retention_days=compliance.get("log_retention_days", 90),
            encryption_at_rest=compliance.get("encryption_at_rest", True),
            audit_signature_algorithm=compliance.get("audit_signature_algorithm", "SHA256")
        )
        
        # Parse LLM config
        llm = self._enterprise_config.get("llm", {})
        self.llm = LLMConfig(
            default_model=llm.get("default_model", "anthropic.claude-3-sonnet-20240229-v1:0"),
            fallback_model=llm.get("fallback_model", "anthropic.claude-3-haiku-20240307-v1:0"),
            region=llm.get("region", "us-east-1"),
            max_tokens=llm.get("max_tokens", 4096),
            temperature=llm.get("temperature", 0.7),
            timeout_seconds=llm.get("timeout_seconds", 120),
            retry_attempts=llm.get("retry_attempts", 3),
            retry_backoff_seconds=llm.get("retry_backoff_seconds", 2)
        )
        
        # Parse session config
        session = self._enterprise_config.get("session", {})
        self.session = SessionConfig(
            max_history_items=session.get("max_history_items", 50),
            history_summary_threshold=session.get("history_summary_threshold", 20),
            session_timeout_minutes=session.get("session_timeout_minutes", 60),
            persist_sessions=session.get("persist_sessions", True),
            session_storage_path=session.get("session_storage_path", "./sessions")
        )
        
        # Parse rate limit config
        rate_limit = self._enterprise_config.get("rate_limiting", {})
        self.rate_limit = RateLimitConfig(
            enabled=rate_limit.get("enabled", True),
            requests_per_minute=rate_limit.get("requests_per_minute", 60),
            tokens_per_minute=rate_limit.get("tokens_per_minute", 100000),
            burst_limit=rate_limit.get("burst_limit", 10)
        )
        
        # Parse logging config
        logging_cfg = self._enterprise_config.get("logging", {})
        self.logging = LoggingConfig(
            level=logging_cfg.get("level", "INFO"),
            format=logging_cfg.get("format", "json"),
            include_timestamps=logging_cfg.get("include_timestamps", True),
            include_request_ids=logging_cfg.get("include_request_ids", True),
            sensitive_fields_mask=logging_cfg.get("sensitive_fields_mask", ["password", "api_key", "token", "secret"])
        )
        
        # Parse network config
        network = self._enterprise_config.get("network", {})
        self.network = NetworkConfig(
            bind_host=network.get("bind_host", "0.0.0.0"),
            public_host=network.get("public_host", "localhost"),
            use_ssl=network.get("use_ssl", False),
            ssl_cert_path=network.get("ssl_cert_path", ""),
            ssl_key_path=network.get("ssl_key_path", ""),
            cors_origins=network.get("cors_origins", ["*"]),
            request_timeout_seconds=network.get("request_timeout_seconds", 300)
        )
        
        # Parse workflow config
        workflow = self._enterprise_config.get("workflow", {})
        self.workflow = WorkflowConfig(
            enable_persistence=workflow.get("enable_persistence", True),
            database_path=workflow.get("database_path", "./workflows.db"),
            enable_retry=workflow.get("enable_retry", True),
            max_retries=workflow.get("max_retries", 3),
            retry_delay_seconds=workflow.get("retry_delay_seconds", 1.0),
            max_retry_delay_seconds=workflow.get("max_retry_delay_seconds", 30.0),
            enable_parallel_execution=workflow.get("enable_parallel_execution", True),
            max_parallel_steps=workflow.get("max_parallel_steps", 5),
            default_timeout_seconds=workflow.get("default_timeout_seconds", 3600)
        )
        
        # Parse health check config
        health = self._enterprise_config.get("health_check", {})
        self.health_check = HealthCheckConfig(
            enabled=health.get("enabled", True),
            interval_seconds=health.get("interval_seconds", 10),
            timeout_seconds=health.get("timeout_seconds", 5),
            max_retries=health.get("max_retries", 3),
            unhealthy_threshold=health.get("unhealthy_threshold", 3)
        )
        
        # Parse services config (new structure)
        services = self._enterprise_config.get("services", {})
        for service_name, service_cfg in services.items():
            if isinstance(service_cfg, dict):
                self._services[service_name] = ServiceEndpoint(
                    host=service_cfg.get("host", "localhost"),
                    port=service_cfg.get("port", 8000),
                    protocol=service_cfg.get("protocol", "http"),
                    enabled=service_cfg.get("enabled", True)
                )
        
        # Parse agents config
        self._agents = self._enterprise_config.get("agents", {})
        
        # Parse MCP servers config
        self._mcp_servers = self._enterprise_config.get("mcp_servers", {})
    
    def _load_security_policies(self):
        """Load security policies configuration"""
        self._security_policies = self._load_json_config(
            self.SECURITY_POLICIES_FILE,
            default={"global_settings": {}, "tool_policies": {}, "role_permissions": {}}
        )
    
    def _load_guardrails_config(self):
        """Load guardrails configuration"""
        self._guardrails_config = self._load_json_config(
            self.GUARDRAILS_CONFIG_FILE,
            default={"pii_detection": {}, "input_rails": {}, "output_rails": {}, "disclaimers": []}
        )
    
    def _apply_environment_overrides(self):
        """Apply environment variable overrides to configuration"""
        # Feature flags
        if os.getenv("ENABLE_GUARDRAILS"):
            self.feature_flags.enable_guardrails = os.getenv("ENABLE_GUARDRAILS", "true").lower() == "true"
        if os.getenv("ENABLE_AUDIT_LOGGING"):
            self.feature_flags.enable_audit_logging = os.getenv("ENABLE_AUDIT_LOGGING", "true").lower() == "true"
        if os.getenv("ENABLE_SECURITY_CHECKS"):
            self.feature_flags.enable_security_checks = os.getenv("ENABLE_SECURITY_CHECKS", "true").lower() == "true"
        if os.getenv("ENABLE_PII_REDACTION"):
            self.feature_flags.enable_pii_redaction = os.getenv("ENABLE_PII_REDACTION", "true").lower() == "true"
        if os.getenv("STRICT_MODE"):
            self.feature_flags.strict_mode = os.getenv("STRICT_MODE", "false").lower() == "true"
        
        # Compliance
        if os.getenv("WORM_STORAGE_PATH"):
            self.compliance.worm_storage_path = os.getenv("WORM_STORAGE_PATH")
        
        # LLM
        if os.getenv("DEFAULT_LLM_MODEL"):
            self.llm.default_model = os.getenv("DEFAULT_LLM_MODEL")
        if os.getenv("AWS_REGION"):
            self.llm.region = os.getenv("AWS_REGION")
        if os.getenv("LLM_MAX_TOKENS"):
            self.llm.max_tokens = int(os.getenv("LLM_MAX_TOKENS"))
        if os.getenv("LLM_TEMPERATURE"):
            self.llm.temperature = float(os.getenv("LLM_TEMPERATURE"))
        
        # Network
        if os.getenv("BIND_HOST"):
            self.network.bind_host = os.getenv("BIND_HOST")
        if os.getenv("PUBLIC_HOST"):
            self.network.public_host = os.getenv("PUBLIC_HOST")
        
        # Services - override from environment variables
        service_env_mappings = {
            "registry": ("REGISTRY_HOST", "REGISTRY_PORT"),
            "orchestrator": ("ORCHESTRATOR_HOST", "ORCHESTRATOR_PORT"),
            "mcp_registry": ("MCP_REGISTRY_HOST", "MCP_REGISTRY_PORT"),
            "mcp_gateway": ("MCP_GATEWAY_HOST", "MCP_GATEWAY_PORT"),
        }
        
        for service_name, (host_env, port_env) in service_env_mappings.items():
            if service_name not in self._services:
                self._services[service_name] = ServiceEndpoint()
            if os.getenv(host_env):
                self._services[service_name].host = os.getenv(host_env)
            if os.getenv(port_env):
                self._services[service_name].port = int(os.getenv(port_env))
        
        # Agent overrides
        agent_env_prefix = {
            "code_analyzer": "CODE_ANALYZER",
            "data_processor": "DATA_PROCESSOR",
            "research_agent": "RESEARCH_AGENT",
            "task_executor": "TASK_EXECUTOR",
            "observer": "OBSERVER",
            "math_agent": "MATH_AGENT"
        }
        
        for agent_key, env_prefix in agent_env_prefix.items():
            host_env = f"{env_prefix}_HOST"
            port_env = f"{env_prefix}_PORT"
            if os.getenv(host_env) or os.getenv(port_env):
                if agent_key not in self._agents:
                    self._agents[agent_key] = {"host": "localhost", "port": 8001}
                if os.getenv(host_env):
                    self._agents[agent_key]["host"] = os.getenv(host_env)
                if os.getenv(port_env):
                    self._agents[agent_key]["port"] = int(os.getenv(port_env))
    
    # ==================== Public API ====================
    
    def feature_enabled(self, feature: str) -> bool:
        """Check if a feature is enabled"""
        return getattr(self.feature_flags, f"enable_{feature}", False)
    
    def get_llm_config(self) -> Dict[str, Any]:
        """Get LLM configuration as dictionary"""
        return {
            "model_id": self.llm.default_model,
            "fallback_model": self.llm.fallback_model,
            "region": self.llm.region,
            "max_tokens": self.llm.max_tokens,
            "temperature": self.llm.temperature,
            "timeout": self.llm.timeout_seconds,
            "retry_attempts": self.llm.retry_attempts,
            "retry_backoff": self.llm.retry_backoff_seconds
        }
    
    def get_security_policies(self) -> Dict[str, Any]:
        """Get security policies configuration"""
        return self._security_policies
    
    def get_guardrails_config(self) -> Dict[str, Any]:
        """Get guardrails configuration"""
        return self._guardrails_config
    
    def get_tool_policy(self, tool_name: str) -> Dict[str, Any]:
        """Get policy for specific tool"""
        policies = self._security_policies.get("tool_policies", {})
        return policies.get(tool_name, self._security_policies.get("default_policy", {}))
    
    def get_role_permissions(self, role: str) -> Dict[str, Any]:
        """Get permissions for specific role"""
        permissions = self._security_policies.get("role_permissions", {})
        return permissions.get(role, permissions.get("guest", {}))
    
    def get_pii_patterns(self) -> Dict[str, Dict[str, Any]]:
        """Get PII detection patterns"""
        pii_config = self._guardrails_config.get("pii_detection", {})
        return pii_config.get("patterns", {})
    
    def get_disclaimers(self) -> List[Dict[str, Any]]:
        """Get disclaimer configurations"""
        return self._guardrails_config.get("disclaimers", [])
    
    def get_sensitive_terms(self) -> List[Dict[str, Any]]:
        """Get sensitive terms for input validation"""
        input_rails = self._guardrails_config.get("input_rails", {})
        return input_rails.get("sensitive_terms", [])
    
    def get_denied_topics(self) -> List[Dict[str, Any]]:
        """Get denied topics for output validation"""
        output_rails = self._guardrails_config.get("output_rails", {})
        return output_rails.get("denied_topics", [])
    
    # ==================== Service Discovery API ====================
    
    def get_service_url(self, service_name: str) -> str:
        """
        Get URL for a core service (registry, orchestrator, mcp_gateway, mcp_registry).
        
        Args:
            service_name: Name of the service (e.g., 'registry', 'orchestrator')
            
        Returns:
            Full URL string (e.g., 'http://localhost:8000')
        """
        if service_name in self._services:
            return self._services[service_name].url
        
        # Fallback defaults
        defaults = {
            "registry": "http://localhost:8000",
            "orchestrator": "http://localhost:8100",
            "mcp_registry": "http://localhost:8200",
            "mcp_gateway": "http://localhost:8300"
        }
        return defaults.get(service_name, f"http://localhost:8000")
    
    def get_service_endpoint(self, service_name: str) -> ServiceEndpoint:
        """Get ServiceEndpoint object for a service"""
        return self._services.get(service_name, ServiceEndpoint())
    
    def get_agent_url(self, agent_key: str) -> str:
        """
        Get URL for an agent.
        
        Args:
            agent_key: Agent key (e.g., 'math_agent', 'research_agent')
            
        Returns:
            Full URL string
        """
        if agent_key in self._agents:
            agent = self._agents[agent_key]
            protocol = agent.get("protocol", "http")
            host = agent.get("host", "localhost")
            port = agent.get("port", 8001)
            return f"{protocol}://{host}:{port}"
        return "http://localhost:8001"
    
    def get_agent_config(self, agent_key: str) -> Dict[str, Any]:
        """Get full configuration for an agent"""
        return self._agents.get(agent_key, {})
    
    def get_agent_endpoint(self, agent_key: str) -> str:
        """
        Get the public endpoint URL for an agent to register with.
        Uses public_host from network config.
        
        Args:
            agent_key: Agent key
            
        Returns:
            Public endpoint URL
        """
        if agent_key in self._agents:
            agent = self._agents[agent_key]
            protocol = agent.get("protocol", "http")
            host = self.network.public_host
            port = agent.get("port", 8001)
            return f"{protocol}://{host}:{port}"
        return f"http://{self.network.public_host}:8001"
    
    def get_mcp_server_url(self, server_key: str) -> str:
        """
        Get URL for an MCP server.
        
        Args:
            server_key: Server key (e.g., 'calculator', 'web_search')
            
        Returns:
            Full URL string
        """
        if server_key in self._mcp_servers:
            server = self._mcp_servers[server_key]
            protocol = server.get("protocol", "http")
            host = server.get("host", "localhost")
            port = server.get("port", 8210)
            return f"{protocol}://{host}:{port}"
        return "http://localhost:8210"
    
    def get_mcp_server_config(self, server_key: str) -> Dict[str, Any]:
        """Get full configuration for an MCP server"""
        return self._mcp_servers.get(server_key, {})
    
    def get_all_agent_configs(self) -> Dict[str, Dict[str, Any]]:
        """Get all agent configurations"""
        return self._agents.copy()
    
    def get_all_mcp_server_configs(self) -> Dict[str, Dict[str, Any]]:
        """Get all MCP server configurations"""
        return self._mcp_servers.copy()
    
    def get_enabled_agents(self) -> List[str]:
        """Get list of enabled agent keys"""
        return [k for k, v in self._agents.items() if v.get("enabled", True)]
    
    def get_enabled_mcp_servers(self) -> List[str]:
        """Get list of enabled MCP server keys"""
        return [k for k, v in self._mcp_servers.items() if v.get("enabled", True)]
    
    def reload(self):
        """Force reload all configurations"""
        logger.info("Reloading configuration...")
        self._load_all_configs()
    
    def get_config_hash(self) -> str:
        """Get hash of current configuration for change detection"""
        config_str = json.dumps({
            "enterprise": self._enterprise_config,
            "security": self._security_policies,
            "guardrails": self._guardrails_config
        }, sort_keys=True)
        return hashlib.sha256(config_str.encode()).hexdigest()[:16]
    
    def export_config(self) -> Dict[str, Any]:
        """Export current configuration (excluding secrets)"""
        return {
            "environment": self.environment.value,
            "version": self.version,
            "deployment_id": self.deployment_id,
            "feature_flags": {
                "guardrails": self.feature_flags.enable_guardrails,
                "audit_logging": self.feature_flags.enable_audit_logging,
                "security_checks": self.feature_flags.enable_security_checks,
                "pii_redaction": self.feature_flags.enable_pii_redaction,
                "strict_mode": self.feature_flags.strict_mode
            },
            "llm": {
                "model": self.llm.default_model,
                "region": self.llm.region
            },
            "services": {k: v.url for k, v in self._services.items()},
            "agents": list(self._agents.keys()),
            "mcp_servers": list(self._mcp_servers.keys()),
            "loaded_at": self._load_timestamp.isoformat() if self._load_timestamp else None,
            "config_hash": self.get_config_hash()
        }


# ==================== Legacy Compatibility Layer ====================

class EnterpriseConfig:
    """
    Legacy compatibility class for backward compatibility.
    Wraps ConfigManager for existing code.
    
    DEPRECATED: Use ConfigManager.get_instance() instead.
    """
    
    _manager: Optional[ConfigManager] = None
    
    @classmethod
    def _get_manager(cls) -> ConfigManager:
        if cls._manager is None:
            cls._manager = ConfigManager.get_instance()
        return cls._manager
    
    # Feature Flags (legacy properties)
    @classmethod
    @property
    def ENABLE_GUARDRAILS(cls) -> bool:
        return cls._get_manager().feature_flags.enable_guardrails
    
    @classmethod
    @property
    def ENABLE_AUDIT_LOGGING(cls) -> bool:
        return cls._get_manager().feature_flags.enable_audit_logging
    
    @classmethod
    @property
    def ENABLE_SECURITY_CHECKS(cls) -> bool:
        return cls._get_manager().feature_flags.enable_security_checks
    
    @classmethod
    @property
    def PII_REDACTION_ENABLED(cls) -> bool:
        return cls._get_manager().feature_flags.enable_pii_redaction
    
    @classmethod
    @property
    def WORM_STORAGE_PATH(cls) -> str:
        return cls._get_manager().compliance.worm_storage_path
    
    @classmethod
    @property
    def DENIED_TOPICS(cls) -> List[str]:
        topics = cls._get_manager().get_denied_topics()
        return [t.get("topic", "") for t in topics]
    
    @classmethod
    @property
    def SENSITIVE_TERMS(cls) -> List[str]:
        terms = cls._get_manager().get_sensitive_terms()
        return [t.get("term", "") for t in terms]
    
    @classmethod
    @property
    def MAX_TRANSACTION_LIMIT(cls) -> float:
        default_policy = cls._get_manager()._security_policies.get("default_policy", {})
        return default_policy.get("max_transaction_limit", 2000.0)
    
    @classmethod
    @property
    def SECURITY_POLICY_PATH(cls) -> str:
        return str(ConfigManager.CONFIG_DIR / ConfigManager.SECURITY_POLICIES_FILE)
    
    @classmethod
    @property
    def GUARDRAIL_CONFIG_PATH(cls) -> str:
        return str(ConfigManager.CONFIG_DIR / ConfigManager.GUARDRAILS_CONFIG_FILE)
    
    @classmethod
    def load_security_policies(cls) -> Dict[str, Any]:
        """Legacy method for loading security policies"""
        return cls._get_manager().get_security_policies()
    
    @classmethod
    def load_guardrail_config(cls) -> Dict[str, Any]:
        """Legacy method for loading guardrail config"""
        return cls._get_manager().get_guardrails_config()
    
    @classmethod
    def get_tool_limit(cls, tool_name: str, param_name: str) -> Optional[float]:
        """Legacy method for getting tool limits"""
        policy = cls._get_manager().get_tool_policy(tool_name)
        limits = policy.get("limits", {})
        param_limit = limits.get(param_name, {})
        if isinstance(param_limit, dict):
            return param_limit.get("max")
        return param_limit if isinstance(param_limit, (int, float)) else None
    
    @classmethod
    def get_settings(cls) -> Dict[str, Any]:
        """Legacy method for getting settings summary"""
        manager = cls._get_manager()
        return {
            "guardrails": manager.feature_flags.enable_guardrails,
            "audit": manager.feature_flags.enable_audit_logging,
            "security": manager.feature_flags.enable_security_checks,
            "pii_redaction": manager.feature_flags.enable_pii_redaction,
            "strict_mode": manager.feature_flags.strict_mode
        }


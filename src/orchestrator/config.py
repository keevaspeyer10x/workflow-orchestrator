"""
Configuration System

Manages orchestrator configuration from multiple sources:
1. Default values
2. Configuration file (orchestrator.yaml)
3. Environment variables (highest priority)

Supports runtime updates and validation.
"""

from typing import Any, Dict, Optional
from pathlib import Path
import os
import yaml
from dataclasses import dataclass, field, asdict


@dataclass
class ServerConfig:
    """Server configuration"""
    host: str = "localhost"
    port: int = 8000
    workers: int = 4
    timeout: int = 30  # seconds


@dataclass
class SecurityConfig:
    """Security configuration"""
    jwt_secret_env_var: str = "ORCHESTRATOR_JWT_SECRET"
    token_expiry_seconds: int = 7200  # 2 hours
    require_token_rotation: bool = True
    max_token_age_seconds: int = 86400  # 24 hours


@dataclass
class StateConfig:
    """State management configuration"""
    state_file: str = ".orchestrator/state.json"
    auto_save: bool = True
    checkpoint_interval: int = 60  # seconds


@dataclass
class EventConfig:
    """Event bus configuration"""
    max_history: int = 1000
    history_cleanup_interval: int = 3600  # seconds
    enable_event_persistence: bool = False
    event_persistence_file: str = ".orchestrator/events.jsonl"


@dataclass
class AuditConfig:
    """Audit logging configuration"""
    audit_file: str = ".orchestrator/audit.jsonl"
    max_entries: int = 100000
    auto_rotate: bool = True
    rotate_size_mb: int = 100


@dataclass
class RetryConfig:
    """Retry configuration"""
    max_attempts: int = 3
    initial_delay_ms: int = 100
    max_delay_ms: int = 5000
    exponential_base: float = 2.0
    jitter: bool = True


@dataclass
class CircuitBreakerConfig:
    """Circuit breaker configuration"""
    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: int = 60
    half_open_max_calls: int = 1


@dataclass
class LoggingConfig:
    """Logging configuration"""
    level: str = "INFO"
    format: str = "json"
    file: Optional[str] = None
    console: bool = True


@dataclass
class OrchestratorConfig:
    """Complete orchestrator configuration"""
    server: ServerConfig = field(default_factory=ServerConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)
    state: StateConfig = field(default_factory=StateConfig)
    event: EventConfig = field(default_factory=EventConfig)
    audit: AuditConfig = field(default_factory=AuditConfig)
    retry: RetryConfig = field(default_factory=RetryConfig)
    circuit_breaker: CircuitBreakerConfig = field(default_factory=CircuitBreakerConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    def to_dict(self) -> Dict[str, Any]:
        """Convert configuration to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "OrchestratorConfig":
        """Create configuration from dictionary"""
        config = cls()

        if "server" in data:
            config.server = ServerConfig(**data["server"])
        if "security" in data:
            config.security = SecurityConfig(**data["security"])
        if "state" in data:
            config.state = StateConfig(**data["state"])
        if "event" in data:
            config.event = EventConfig(**data["event"])
        if "audit" in data:
            config.audit = AuditConfig(**data["audit"])
        if "retry" in data:
            config.retry = RetryConfig(**data["retry"])
        if "circuit_breaker" in data:
            config.circuit_breaker = CircuitBreakerConfig(**data["circuit_breaker"])
        if "logging" in data:
            config.logging = LoggingConfig(**data["logging"])

        return config


class ConfigManager:
    """
    Configuration manager with multiple source support

    Load priority (highest to lowest):
    1. Environment variables
    2. Configuration file
    3. Defaults
    """

    def __init__(self, config_file: Optional[Path] = None):
        """
        Initialize configuration manager

        Args:
            config_file: Optional path to configuration file
        """
        self.config_file = config_file or Path("orchestrator.yaml")
        self._config = self._load_config()

    def _load_config(self) -> OrchestratorConfig:
        """
        Load configuration from all sources

        Returns:
            Complete configuration
        """
        # Start with defaults
        config = OrchestratorConfig()

        # Load from file if exists
        if self.config_file.exists():
            try:
                with open(self.config_file, 'r') as f:
                    file_data = yaml.safe_load(f)
                    if file_data:
                        config = OrchestratorConfig.from_dict(file_data)
            except Exception as e:
                print(f"Warning: Failed to load config file {self.config_file}: {e}")

        # Override with environment variables
        config = self._apply_env_overrides(config)

        return config

    def _apply_env_overrides(self, config: OrchestratorConfig) -> OrchestratorConfig:
        """
        Apply environment variable overrides

        Environment variables format: ORCHESTRATOR_<SECTION>_<KEY>
        Example: ORCHESTRATOR_SERVER_PORT=9000

        Args:
            config: Base configuration

        Returns:
            Configuration with environment overrides applied
        """
        # Server overrides
        if port := os.getenv("ORCHESTRATOR_SERVER_PORT"):
            config.server.port = int(port)
        if host := os.getenv("ORCHESTRATOR_SERVER_HOST"):
            config.server.host = host
        if workers := os.getenv("ORCHESTRATOR_SERVER_WORKERS"):
            config.server.workers = int(workers)

        # Security overrides
        if jwt_secret_env := os.getenv("ORCHESTRATOR_SECURITY_JWT_SECRET_ENV_VAR"):
            config.security.jwt_secret_env_var = jwt_secret_env
        if token_expiry := os.getenv("ORCHESTRATOR_SECURITY_TOKEN_EXPIRY_SECONDS"):
            config.security.token_expiry_seconds = int(token_expiry)

        # State overrides
        if state_file := os.getenv("ORCHESTRATOR_STATE_FILE"):
            config.state.state_file = state_file

        # Audit overrides
        if audit_file := os.getenv("ORCHESTRATOR_AUDIT_FILE"):
            config.audit.audit_file = audit_file

        # Logging overrides
        if log_level := os.getenv("ORCHESTRATOR_LOG_LEVEL"):
            config.logging.level = log_level
        if log_file := os.getenv("ORCHESTRATOR_LOG_FILE"):
            config.logging.file = log_file

        return config

    def get(self, section: Optional[str] = None) -> Any:
        """
        Get configuration section or entire config

        Args:
            section: Optional section name (server, security, etc.)

        Returns:
            Configuration section or entire config
        """
        if section is None:
            return self._config

        return getattr(self._config, section, None)

    def update(self, section: str, key: str, value: Any) -> None:
        """
        Update configuration value at runtime

        Args:
            section: Configuration section
            key: Configuration key
            value: New value
        """
        section_obj = getattr(self._config, section, None)
        if section_obj is None:
            raise ValueError(f"Unknown configuration section: {section}")

        if not hasattr(section_obj, key):
            raise ValueError(f"Unknown configuration key: {section}.{key}")

        setattr(section_obj, key, value)

    def save(self, file_path: Optional[Path] = None) -> None:
        """
        Save configuration to file

        Args:
            file_path: Optional path to save to (defaults to self.config_file)
        """
        save_path = file_path or self.config_file
        save_path.parent.mkdir(parents=True, exist_ok=True)

        with open(save_path, 'w') as f:
            yaml.dump(self._config.to_dict(), f, default_flow_style=False)

    def validate(self) -> tuple[bool, list[str]]:
        """
        Validate configuration

        Returns:
            Tuple of (is_valid, errors)
        """
        errors = []

        # Validate server config
        if self._config.server.port < 1 or self._config.server.port > 65535:
            errors.append("Server port must be between 1 and 65535")
        if self._config.server.workers < 1:
            errors.append("Server workers must be at least 1")

        # Validate security config
        if self._config.security.token_expiry_seconds < 60:
            errors.append("Token expiry must be at least 60 seconds")
        if self._config.security.max_token_age_seconds < self._config.security.token_expiry_seconds:
            errors.append("Max token age must be >= token expiry")

        # Validate retry config
        if self._config.retry.max_attempts < 1:
            errors.append("Retry max attempts must be at least 1")
        if self._config.retry.initial_delay_ms < 0:
            errors.append("Retry initial delay must be non-negative")
        if self._config.retry.max_delay_ms < self._config.retry.initial_delay_ms:
            errors.append("Retry max delay must be >= initial delay")

        # Validate circuit breaker config
        if self._config.circuit_breaker.failure_threshold < 1:
            errors.append("Circuit breaker failure threshold must be at least 1")
        if self._config.circuit_breaker.success_threshold < 1:
            errors.append("Circuit breaker success threshold must be at least 1")

        # Validate logging config
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if self._config.logging.level.upper() not in valid_levels:
            errors.append(f"Logging level must be one of: {', '.join(valid_levels)}")

        return len(errors) == 0, errors

    def reload(self) -> None:
        """Reload configuration from file"""
        self._config = self._load_config()


# Global configuration instance
config_manager = ConfigManager()

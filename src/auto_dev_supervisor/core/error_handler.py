"""
Enhanced Error Handling and Recovery System for Auto-Dev Supervisor
"""

import logging
import traceback
import time
from typing import Dict, List, Optional, Callable, Any
from dataclasses import dataclass
from enum import Enum

class ErrorSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class ErrorCategory(Enum):
    LLM_API = "llm_api"
    DOCKER = "docker"
    GIT = "git"
    CODE_GENERATION = "code_generation"
    TEST_FAILURE = "test_failure"
    CONFIGURATION = "configuration"
    NETWORK = "network"
    UNKNOWN = "unknown"

@dataclass
class ErrorContext:
    """Context information about an error"""
    task_id: str
    service_name: str
    phase: str
    error_type: str
    message: str
    stack_trace: str
    severity: ErrorSeverity
    category: ErrorCategory
    timestamp: float
    recovery_attempts: int = 0
    metadata: Dict[str, Any] = None

class RecoveryStrategy:
    """Base class for recovery strategies"""
    
    def __init__(self, name: str, max_attempts: int = 3):
        self.name = name
        self.max_attempts = max_attempts
        self.attempts = 0
    
    def can_recover(self, error_context: ErrorContext) -> bool:
        """Check if this strategy can handle the error"""
        return self.attempts < self.max_attempts
    
    def recover(self, error_context: ErrorContext) -> bool:
        """Attempt to recover from the error"""
        self.attempts += 1
        error_context.recovery_attempts = self.attempts
        return self._execute_recovery(error_context)
    
    def _execute_recovery(self, error_context: ErrorContext) -> bool:
        """Override this method in subclasses"""
        raise NotImplementedError

class LLMAPIRecoveryStrategy(RecoveryStrategy):
    """Recovery strategy for LLM API failures"""
    
    def __init__(self, fallback_providers: List[str]):
        super().__init__("llm_api_fallback", max_attempts=len(fallback_providers))
        self.fallback_providers = fallback_providers
        self.current_provider_index = 0
    
    def _execute_recovery(self, error_context: ErrorContext) -> bool:
        """Try fallback providers"""
        if self.current_provider_index < len(self.fallback_providers):
            fallback_provider = self.fallback_providers[self.current_provider_index]
            self.current_provider_index += 1
            
            logging.info(f"Attempting recovery with fallback provider: {fallback_provider}")
            error_context.metadata = error_context.metadata or {}
            error_context.metadata['fallback_provider'] = fallback_provider
            
            return True
        return False

class DockerRecoveryStrategy(RecoveryStrategy):
    """Recovery strategy for Docker failures"""
    
    def __init__(self):
        super().__init__("docker_recovery", max_attempts=3)
    
    def _execute_recovery(self, error_context: ErrorContext) -> bool:
        """Try Docker recovery actions"""
        actions = [
            "docker system prune -f",
            "docker restart",
            "docker-compose down && docker-compose up -d"
        ]
        
        if self.attempts <= len(actions):
            action = actions[self.attempts - 1]
            logging.info(f"Attempting Docker recovery: {action}")
            
            error_context.metadata = error_context.metadata or {}
            error_context.metadata['recovery_action'] = action
            
            return True
        return False

class CodeGenerationRecoveryStrategy(RecoveryStrategy):
    """Recovery strategy for code generation failures"""
    
    def __init__(self):
        super().__init__("code_generation_recovery", max_attempts=3)
    
    def _execute_recovery(self, error_context: ErrorContext) -> bool:
        """Try code generation recovery approaches"""
        approaches = [
            "simplify_requirements",
            "break_into_smaller_tasks", 
            "use_different_prompt_style",
            "add_more_context"
        ]
        
        if self.attempts <= len(approaches):
            approach = approaches[self.attempts - 1]
            logging.info(f"Attempting code generation recovery: {approach}")
            
            error_context.metadata = error_context.metadata or {}
            error_context.metadata['recovery_approach'] = approach
            
            return True
        return False

class EnhancedErrorHandler:
    """Enhanced error handler with intelligent recovery strategies"""
    
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or {}
        self.logger = logging.getLogger(__name__)
        self.error_history: List[ErrorContext] = []
        self.recovery_strategies = self._initialize_recovery_strategies()
        self.error_callbacks: Dict[ErrorCategory, List[Callable]] = {}
        
    def _initialize_recovery_strategies(self) -> Dict[ErrorCategory, List[RecoveryStrategy]]:
        """Initialize recovery strategies for different error categories"""
        fallback_providers = self.config.get('fallback_providers', ['ollama', 'gemini'])
        
        return {
            ErrorCategory.LLM_API: [
                LLMAPIRecoveryStrategy(fallback_providers)
            ],
            ErrorCategory.DOCKER: [
                DockerRecoveryStrategy()
            ],
            ErrorCategory.CODE_GENERATION: [
                CodeGenerationRecoveryStrategy()
            ]
        }
    
    def handle_error(self, error: Exception, context: Dict[str, Any]) -> ErrorContext:
        """Handle an error and attempt recovery"""
        error_context = self._create_error_context(error, context)
        self.error_history.append(error_context)
        
        self.logger.error(f"Error occurred: {error_context.message}")
        self.logger.error(f"Category: {error_context.category.value}")
        self.logger.error(f"Severity: {error_context.severity.value}")
        
        # Notify error callbacks
        self._notify_error_callbacks(error_context)
        
        # Attempt recovery
        recovery_success = self._attempt_recovery(error_context)
        
        if recovery_success:
            self.logger.info(f"Recovery successful for error: {error_context.message}")
        else:
            self.logger.error(f"Recovery failed for error: {error_context.message}")
            
        return error_context
    
    def _create_error_context(self, error: Exception, context: Dict[str, Any]) -> ErrorContext:
        """Create error context from exception and additional context"""
        error_type = type(error).__name__
        message = str(error)
        stack_trace = traceback.format_exc()
        
        # Determine category and severity
        category = self._categorize_error(error, context)
        severity = self._determine_severity(error, context)
        
        return ErrorContext(
            task_id=context.get('task_id', 'unknown'),
            service_name=context.get('service_name', 'unknown'),
            phase=context.get('phase', 'unknown'),
            error_type=error_type,
            message=message,
            stack_trace=stack_trace,
            severity=severity,
            category=category,
            timestamp=time.time(),
            metadata=context.get('metadata', {})
        )
    
    def _categorize_error(self, error: Exception, context: Dict[str, Any]) -> ErrorCategory:
        """Categorize the error based on type and context"""
        error_type = type(error).__name__.lower()
        message = str(error).lower()
        
        if any(keyword in error_type or keyword in message for keyword in ['api', 'openai', 'gemini', 'grok', 'ollama']):
            return ErrorCategory.LLM_API
        elif any(keyword in error_type or keyword in message for keyword in ['docker', 'container']):
            return ErrorCategory.DOCKER
        elif any(keyword in error_type or keyword in message for keyword in ['git', 'repository']):
            return ErrorCategory.GIT
        elif any(keyword in error_type or keyword in message for keyword in ['syntax', 'compile', 'import']):
            return ErrorCategory.CODE_GENERATION
        elif any(keyword in error_type or keyword in message for keyword in ['test', 'assert']):
            return ErrorCategory.TEST_FAILURE
        elif any(keyword in error_type or keyword in message for keyword in ['config', 'key', 'missing']):
            return ErrorCategory.CONFIGURATION
        elif any(keyword in error_type or keyword in message for keyword in ['network', 'connection', 'timeout']):
            return ErrorCategory.NETWORK
        else:
            return ErrorCategory.UNKNOWN
    
    def _determine_severity(self, error: Exception, context: Dict[str, Any]) -> ErrorSeverity:
        """Determine error severity based on type and impact"""
        error_type = type(error).__name__
        
        # Critical errors
        if any(keyword in error_type.lower() for keyword in ['keyboardinterrupt', 'systemexit']):
            return ErrorSeverity.CRITICAL
        
        # High severity errors
        if any(keyword in error_type.lower() for keyword in ['docker', 'api', 'connection']):
            return ErrorSeverity.HIGH
        
        # Medium severity errors  
        if any(keyword in error_type.lower() for keyword in ['valueerror', 'typeerror', 'attributeerror']):
            return ErrorSeverity.MEDIUM
        
        # Low severity errors
        return ErrorSeverity.LOW
    
    def _attempt_recovery(self, error_context: ErrorContext) -> bool:
        """Attempt to recover from the error using appropriate strategies"""
        strategies = self.recovery_strategies.get(error_context.category, [])
        
        for strategy in strategies:
            if strategy.can_recover(error_context):
                try:
                    self.logger.info(f"Attempting recovery with strategy: {strategy.name}")
                    if strategy.recover(error_context):
                        return True
                except Exception as e:
                    self.logger.error(f"Recovery strategy {strategy.name} failed: {e}")
        
        return False

@dataclass
class AttemptRecoveryResult:
    success: bool
    message: str = ""
    alternative_action: Optional[Callable] = None

class EnhancedErrorHandler(EnhancedErrorHandler):
    def attempt_recovery(self, error_context: ErrorContext) -> AttemptRecoveryResult:
        """Public wrapper returning a structured result"""
        ok = self._attempt_recovery(error_context)
        msg = "Recovery successful" if ok else "Recovery not possible"
        return AttemptRecoveryResult(success=ok, message=msg)
    
    def _notify_error_callbacks(self, error_context: ErrorContext):
        """Notify registered error callbacks"""
        callbacks = self.error_callbacks.get(error_context.category, [])
        for callback in callbacks:
            try:
                callback(error_context)
            except Exception as e:
                self.logger.error(f"Error callback failed: {e}")
    
    def register_error_callback(self, category: ErrorCategory, callback: Callable):
        """Register a callback for specific error categories"""
        if category not in self.error_callbacks:
            self.error_callbacks[category] = []
        self.error_callbacks[category].append(callback)
    
    def get_error_statistics(self) -> Dict[str, Any]:
        """Get statistics about errors and recoveries"""
        if not self.error_history:
            return {"total_errors": 0, "recovery_rate": 0}
        
        total_errors = len(self.error_history)
        recovered_errors = sum(1 for error in self.error_history if error.recovery_attempts > 0)
        
        category_stats = {}
        for error in self.error_history:
            category = error.category.value
            category_stats[category] = category_stats.get(category, 0) + 1
        
        return {
            "total_errors": total_errors,
            "recovered_errors": recovered_errors,
            "recovery_rate": recovered_errors / total_errors if total_errors > 0 else 0,
            "errors_by_category": category_stats,
            "recent_errors": [
                {
                    "message": error.message,
                    "category": error.category.value,
                    "severity": error.severity.value,
                    "recovered": error.recovery_attempts > 0,
                    "timestamp": error.timestamp
                }
                for error in self.error_history[-10:]  # Last 10 errors
            ]
        }
    
    def clear_error_history(self):
        """Clear error history"""
        self.error_history.clear()
        
        # Reset recovery strategies
        for strategies in self.recovery_strategies.values():
            for strategy in strategies:
                strategy.attempts = 0
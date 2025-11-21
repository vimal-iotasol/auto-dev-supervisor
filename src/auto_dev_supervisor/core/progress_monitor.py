import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, field
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, TaskID
from rich.live import Live
from rich.layout import Layout
from rich.panel import Panel
from rich.text import Text

from auto_dev_supervisor.domain.model import Task, TaskStatus
from auto_dev_supervisor.core.error_handler import EnhancedErrorHandler as ErrorHandler, ErrorCategory, ErrorSeverity

console = Console()

@dataclass
class ProgressEvent:
    """Represents a progress event in the system."""
    timestamp: datetime
    event_type: str  # 'task_start', 'task_complete', 'task_failed', 'error', 'recovery', 'milestone'
    task_id: Optional[str] = None
    service_name: Optional[str] = None
    message: str = ""
    metadata: Dict = field(default_factory=dict)

@dataclass
class TaskMetrics:
    """Metrics for a single task."""
    task_id: str
    start_time: datetime
    service_name: Optional[str] = None
    end_time: Optional[datetime] = None
    status: TaskStatus = TaskStatus.PENDING
    retry_count: int = 0
    error_count: int = 0
    recovery_count: int = 0

@dataclass
class SystemMetrics:
    """Overall system metrics."""
    total_tasks: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0
    in_progress_tasks: int = 0
    total_errors: int = 0
    recovered_errors: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    estimated_completion: Optional[datetime] = None

class ProgressMonitor:
    """Real-time progress monitoring system with enhanced metrics and visualization."""
    
    def __init__(self, error_handler: Optional[ErrorHandler] = None):
        self.error_handler = error_handler or ErrorHandler()
        self.events: List[ProgressEvent] = []
        self.task_metrics: Dict[str, TaskMetrics] = {}
        self.system_metrics = SystemMetrics()
        self.is_running = False
        self.monitor_thread: Optional[threading.Thread] = None
        self.update_callbacks: List[Callable] = []
        self.live_display: Optional[Live] = None
        self.progress_bars: Dict[str, TaskID] = {}
        
    def start_monitoring(self, total_tasks: int):
        """Start the progress monitoring system."""
        self.system_metrics.total_tasks = total_tasks
        self.system_metrics.start_time = datetime.now()
        self.is_running = True
        
        # Start background monitoring thread
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()
        
        # Start live display
        self._start_live_display()
        
        self._log_event("monitoring_started", message=f"Started monitoring {total_tasks} tasks")
        
    def stop_monitoring(self):
        """Stop the progress monitoring system."""
        self.is_running = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=5.0)
        
        if self.live_display:
            self.live_display.stop()
            
        self._log_event("monitoring_stopped", message="Progress monitoring stopped")
        self._print_final_summary()
        
    def _start_live_display(self):
        """Start the live Rich display."""
        layout = self._create_layout()
        self.live_display = Live(layout, refresh_per_second=4, console=console)
        self.live_display.start()
        
    def _create_layout(self) -> Layout:
        """Create the layout for the live display."""
        layout = Layout()
        
        # Header with system metrics
        header_panel = self._create_header_panel()
        
        # Task progress section
        progress_panel = self._create_progress_panel()
        
        # Recent events section
        events_panel = self._create_events_panel()
        
        # Error statistics section
        error_panel = self._create_error_panel()
        
        layout.split_column(
            Layout(header_panel, name="header", size=3),
            Layout(progress_panel, name="progress", size=10),
            Layout(events_panel, name="events", size=8),
            Layout(error_panel, name="errors", size=6)
        )
        
        return layout
        
    def _create_header_panel(self) -> Panel:
        """Create the header panel with system metrics."""
        elapsed = datetime.now() - self.system_metrics.start_time
        
        header_text = Text()
        header_text.append(f"Auto-Dev Supervisor Progress Monitor\n", style="bold cyan")
        header_text.append(f"Tasks: {self.system_metrics.completed_tasks}/{self.system_metrics.total_tasks} ", style="green")
        header_text.append(f"Failed: {self.system_metrics.failed_tasks} ", style="red")
        header_text.append(f"Errors: {self.system_metrics.total_errors} ", style="yellow")
        header_text.append(f"Recovered: {self.system_metrics.recovered_errors} ", style="blue")
        header_text.append(f"Time: {str(elapsed).split('.')[0]}", style="dim")
        
        return Panel(header_text, title="System Status", border_style="cyan")
        
    def _create_progress_panel(self) -> Panel:
        """Create the progress panel with task status."""
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Task ID", style="cyan", no_wrap=True)
        table.add_column("Service", style="green")
        table.add_column("Status", style="yellow")
        table.add_column("Duration", style="dim")
        table.add_column("Retries", style="red")
        
        # Sort tasks by status and ID
        sorted_metrics = sorted(self.task_metrics.values(), 
                              key=lambda x: (x.status.value, x.task_id))
        
        for metric in sorted_metrics[:15]:  # Show top 15 tasks
            duration = ""
            if metric.start_time:
                if metric.end_time:
                    duration = str(metric.end_time - metric.start_time).split('.')[0]
                else:
                    duration = str(datetime.now() - metric.start_time).split('.')[0]
            
            status_style = {
                TaskStatus.PENDING: "dim",
                TaskStatus.IN_PROGRESS: "yellow",
                TaskStatus.COMPLETED: "green",
                TaskStatus.FAILED: "red"
            }.get(metric.status, "white")
            
            table.add_row(
                metric.task_id,
                metric.service_name or "N/A",
                f"[{status_style}]{metric.status.value}[/{status_style}]",
                duration,
                str(metric.retry_count)
            )
        
        return Panel(table, title="Task Progress", border_style="green")
        
    def _create_events_panel(self) -> Panel:
        """Create the recent events panel."""
        table = Table(show_header=True, header_style="bold magenta", show_lines=True)
        table.add_column("Time", style="dim", width=8)
        table.add_column("Type", width=12)
        table.add_column("Task", style="cyan", width=15)
        table.add_column("Message", style="white")
        
        # Get recent events (last 10)
        recent_events = self.events[-10:] if len(self.events) > 10 else self.events
        
        for event in recent_events:
            time_str = event.timestamp.strftime("%H:%M:%S")
            
            # Style event type
            type_style = {
                "task_start": "[yellow]START[/yellow]",
                "task_complete": "[green]COMPLETE[/green]",
                "task_failed": "[red]FAILED[/red]",
                "error": "[red]ERROR[/red]",
                "recovery": "[blue]RECOVERY[/blue]",
                "milestone": "[cyan]MILESTONE[/cyan]"
            }.get(event.event_type, event.event_type.upper())
            
            table.add_row(
                time_str,
                type_style,
                event.task_id or "N/A",
                event.message[:50] + "..." if len(event.message) > 50 else event.message
            )
        
        return Panel(table, title="Recent Events", border_style="yellow")
        
    def _create_error_panel(self) -> Panel:
        """Create the error statistics panel."""
        if not self.error_handler:
            return Panel("No error handler available", title="Error Statistics", border_style="red")
        
        # Build per-category stats from error history
        stats_by_cat = {}
        for err in self.error_handler.error_history:
            cat = err.category.value
            entry = stats_by_cat.setdefault(cat, {"total": 0, "recovered": 0, "failed": 0})
            entry["total"] += 1
            if err.recovery_attempts > 0:
                entry["recovered"] += 1
            else:
                entry["failed"] += 1
        
        table = Table(show_header=True, header_style="bold red")
        table.add_column("Error Category", style="cyan")
        table.add_column("Count", style="yellow")
        table.add_column("Recovered", style="green")
        table.add_column("Failed", style="red")
        
        for category, stats in stats_by_cat.items():
            table.add_row(category, str(stats["total"]), str(stats["recovered"]), str(stats["failed"]))
        
        return Panel(table, title="Error Statistics", border_style="red")
        
    def _monitor_loop(self):
        """Background monitoring loop."""
        while self.is_running:
            try:
                # Update estimated completion time
                self._update_estimated_completion()
                
                # Update live display if running
                if self.live_display and self.live_display.is_started:
                    layout = self._create_layout()
                    self.live_display.update(layout)
                
                # Notify callbacks
                for callback in self.update_callbacks:
                    try:
                        callback(self.get_current_metrics())
                    except Exception as e:
                        console.print(f"[red]Callback error: {e}[/red]")
                
                time.sleep(1.0)  # Update every second
                
            except Exception as e:
                console.print(f"[red]Monitor loop error: {e}[/red]")
                time.sleep(5.0)  # Wait longer on error
                
    def _update_estimated_completion(self):
        """Update estimated completion time based on current progress."""
        if self.system_metrics.completed_tasks == 0:
            return
            
        elapsed = datetime.now() - self.system_metrics.start_time
        tasks_per_second = self.system_metrics.completed_tasks / elapsed.total_seconds()
        
        if tasks_per_second > 0:
            remaining_tasks = self.system_metrics.total_tasks - self.system_metrics.completed_tasks
            estimated_seconds = remaining_tasks / tasks_per_second
            self.system_metrics.estimated_completion = datetime.now() + timedelta(seconds=estimated_seconds)
            
    def _log_event(self, event_type: str, task_id: Optional[str] = None, 
                   service_name: Optional[str] = None, message: str = "", 
                   metadata: Dict = None):
        """Log a progress event."""
        event = ProgressEvent(
            timestamp=datetime.now(),
            event_type=event_type,
            task_id=task_id,
            service_name=service_name,
            message=message,
            metadata=metadata or {}
        )
        
        self.events.append(event)
        
        # Keep only last 1000 events to prevent memory issues
        if len(self.events) > 1000:
            self.events = self.events[-1000:]
            
    def task_started(self, task: Task):
        """Record that a task has started."""
        metric = TaskMetrics(
            task_id=task.id,
            service_name=task.service_name,
            start_time=datetime.now(),
            status=TaskStatus.IN_PROGRESS
        )
        self.task_metrics[task.id] = metric
        
        self.system_metrics.in_progress_tasks += 1
        
        self._log_event(
            "task_start",
            task_id=task.id,
            service_name=task.service_name,
            message=f"Task started: {task.title}"
        )
        
    def task_completed(self, task: Task):
        """Record that a task has completed."""
        if task.id in self.task_metrics:
            metric = self.task_metrics[task.id]
            metric.end_time = datetime.now()
            metric.status = TaskStatus.COMPLETED
            
            self.system_metrics.completed_tasks += 1
            self.system_metrics.in_progress_tasks -= 1
            
            self._log_event(
                "task_complete",
                task_id=task.id,
                service_name=task.service_name,
                message=f"Task completed: {task.title}",
                metadata={"duration": str(metric.end_time - metric.start_time)}
            )
            
    def task_failed(self, task: Task, error_message: str = ""):
        """Record that a task has failed."""
        if task.id in self.task_metrics:
            metric = self.task_metrics[task.id]
            metric.end_time = datetime.now()
            metric.status = TaskStatus.FAILED
            
            self.system_metrics.failed_tasks += 1
            self.system_metrics.in_progress_tasks -= 1
            
            self._log_event(
                "task_failed",
                task_id=task.id,
                service_name=task.service_name,
                message=f"Task failed: {task.title} - {error_message}",
                metadata={"duration": str(metric.end_time - metric.start_time) if metric.start_time else "N/A"}
            )
            
    def error_occurred(self, error_message: str, task_id: Optional[str] = None, 
                      service_name: Optional[str] = None, error_category: Optional[str] = None):
        """Record that an error occurred."""
        self.system_metrics.total_errors += 1
        
        if task_id and task_id in self.task_metrics:
            self.task_metrics[task_id].error_count += 1
            
        self._log_event(
            "error",
            task_id=task_id,
            service_name=service_name,
            message=error_message,
            metadata={"category": error_category} if error_category else {}
        )
        
    def recovery_successful(self, recovery_message: str, task_id: Optional[str] = None, 
                           service_name: Optional[str] = None):
        """Record that an error was successfully recovered."""
        self.system_metrics.recovered_errors += 1
        
        if task_id and task_id in self.task_metrics:
            self.task_metrics[task_id].recovery_count += 1
            
        self._log_event(
            "recovery",
            task_id=task_id,
            service_name=service_name,
            message=recovery_message
        )
        
    def retry_attempted(self, task_id: str, attempt_number: int):
        """Record that a retry was attempted for a task."""
        if task_id in self.task_metrics:
            self.task_metrics[task_id].retry_count = attempt_number
            
        self._log_event(
            "retry",
            task_id=task_id,
            message=f"Retry attempt {attempt_number}"
        )
        
    def milestone_reached(self, milestone_name: str, message: str = ""):
        """Record that a milestone was reached."""
        self._log_event(
            "milestone",
            message=f"Milestone reached: {milestone_name} - {message}"
        )
        
    def add_update_callback(self, callback: Callable):
        """Add a callback function to be called on updates."""
        self.update_callbacks.append(callback)
        
    def remove_update_callback(self, callback: Callable):
        """Remove an update callback."""
        if callback in self.update_callbacks:
            self.update_callbacks.remove(callback)
            
    def get_current_metrics(self) -> Dict:
        """Get current system metrics."""
        elapsed = datetime.now() - self.system_metrics.start_time
        
        return {
            "system": {
                "total_tasks": self.system_metrics.total_tasks,
                "completed_tasks": self.system_metrics.completed_tasks,
                "failed_tasks": self.system_metrics.failed_tasks,
                "in_progress_tasks": self.system_metrics.in_progress_tasks,
                "total_errors": self.system_metrics.total_errors,
                "recovered_errors": self.system_metrics.recovered_errors,
                "elapsed_time": str(elapsed).split('.')[0],
                "estimated_completion": self.system_metrics.estimated_completion.isoformat() if self.system_metrics.estimated_completion else None
            },
            "tasks": {
                task_id: {
                    "status": metric.status.value,
                    "retry_count": metric.retry_count,
                    "error_count": metric.error_count,
                    "recovery_count": metric.recovery_count,
                    "duration": str(metric.end_time - metric.start_time).split('.')[0] if metric.end_time and metric.start_time else None
                }
                for task_id, metric in self.task_metrics.items()
            },
            "recent_events": [
                {
                    "timestamp": event.timestamp.isoformat(),
                    "type": event.event_type,
                    "task_id": event.task_id,
                    "service_name": event.service_name,
                    "message": event.message
                }
                for event in self.events[-10:]
            ]
        }
        
    def _print_final_summary(self):
        """Print a final summary when monitoring stops."""
        console.print("\n" + "="*60)
        console.print("[bold cyan]FINAL EXECUTION SUMMARY[/bold cyan]")
        console.print("="*60)
        
        elapsed = datetime.now() - self.system_metrics.start_time
        
        # Overall statistics
        console.print(f"[green]✅ Completed Tasks: {self.system_metrics.completed_tasks}[/green]")
        console.print(f"[red]❌ Failed Tasks: {self.system_metrics.failed_tasks}[/red]")
        console.print(f"[yellow]⚠️  Total Errors: {self.system_metrics.total_errors}[/yellow]")
        console.print(f"[blue]🔄 Recovered Errors: {self.system_metrics.recovered_errors}[/blue]")
        console.print(f"[dim]⏱️  Total Time: {str(elapsed).split('.')[0]}[/dim]")
        
        if self.system_metrics.estimated_completion:
            console.print(f"[dim]📅 Estimated Completion: {self.system_metrics.estimated_completion.strftime('%H:%M:%S')}[/dim]")
        
        # Task details
        if self.task_metrics:
            console.print("\n[bold]Task Details:[/bold]")
            for task_id, metric in self.task_metrics.items():
                status_icon = {
                    TaskStatus.COMPLETED: "✅",
                    TaskStatus.FAILED: "❌",
                    TaskStatus.IN_PROGRESS: "🔄",
                    TaskStatus.PENDING: "⏳"
                }.get(metric.status, "❓")
                
                duration = ""
                if metric.start_time and metric.end_time:
                    duration = f" ({str(metric.end_time - metric.start_time).split('.')[0]})"
                
                console.print(f"{status_icon} {task_id}{duration}")
                if metric.retry_count > 0:
                    console.print(f"   [dim]Retries: {metric.retry_count}[/dim]")
                if metric.error_count > 0:
                    console.print(f"   [dim]Errors: {metric.error_count}[/dim]")
                if metric.recovery_count > 0:
                    console.print(f"   [dim]Recoveries: {metric.recovery_count}[/dim]")
        
        # Compute simple health score
        total = max(1, self.system_metrics.total_tasks)
        success_rate = self.system_metrics.completed_tasks / total
        error_penalty = min(1.0, self.system_metrics.total_errors / (total * 2))
        recovery_bonus = min(0.2, self.system_metrics.recovered_errors / max(1, self.system_metrics.total_errors + 1))
        health_score = max(0.0, min(1.0, success_rate - error_penalty + recovery_bonus))
        console.print(f"\n[bold]Health Score:[/bold] {health_score*100:.1f}%")
        
        console.print("="*60)
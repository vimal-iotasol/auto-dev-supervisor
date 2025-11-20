from typing import Dict, List, Any
from auto_dev_supervisor.domain.model import MLMetric, TaskTestResult, TaskTestType

class QAManager:
    def evaluate_metrics(self, metrics_config: List[MLMetric], actual_metrics: Dict[str, float]) -> List[str]:
        """
        Evaluates actual metrics against the configuration.
        Returns a list of failure messages. Empty list means success.
        """
        failures = []
        for config in metrics_config:
            if config.name not in actual_metrics:
                failures.append(f"Missing metric: {config.name}")
                continue
            
            actual_val = actual_metrics[config.name]
            passed = False
            
            if config.operator == ">":
                passed = actual_val > config.threshold
            elif config.operator == "<":
                passed = actual_val < config.threshold
            elif config.operator == ">=":
                passed = actual_val >= config.threshold
            elif config.operator == "<=":
                passed = actual_val <= config.threshold
            
            if not passed:
                failures.append(
                    f"Metric {config.name} failed: {actual_val} {config.operator} {config.threshold}"
                )
        
        return failures

    def parse_qa_output(self, output: str) -> Dict[str, float]:
        """
        Parses standard output from the QA script to extract metrics.
        Expected format: "METRIC_NAME: VALUE"
        """
        metrics = {}
        for line in output.splitlines():
            if ":" in line:
                parts = line.split(":", 1)
                key = parts[0].strip()
                try:
                    val = float(parts[1].strip())
                    metrics[key] = val
                except ValueError:
                    continue
        return metrics

    def validate_test_result(self, result: TaskTestResult, metrics_config: List[MLMetric]) -> TaskTestResult:
        """
        Enhances a TestResult by validating the embedded metrics against the config.
        """
        if result.type != TaskTestType.ML_QA:
            return result
            
        # Parse metrics from details if not already present
        if not result.metrics and result.details:
            result.metrics = self.parse_qa_output(result.details)
            
        failures = self.evaluate_metrics(metrics_config, result.metrics)
        
        if failures:
            result.passed = False
            result.details += "\nQA Failures:\n" + "\n".join(failures)
            
        return result

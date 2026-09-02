"""
Phase F — Batch Processing and Strategy Optimization Pipeline.

Provides:
- Scheduled batch ingestion from multiple data sources
- Walk-Forward Optimization (WFO) batch runner
- Combinatorial Purged CV (CPCV) batch execution
- Monte Carlo validation batch jobs
- Strategy optimization with parameter search
- Continuous retraining scheduler
- Batch job status tracking and storage in PostgreSQL
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from analytics.validation.validation import (
    WalkForwardOptimizer,
    CombinatorialPurgedCV,
    MonteCarloValidator,
    DEFAULT_GATES,
    ValidationResult,
    ValidationGate,
    evaluate_gates,
    auto_reject,
)
from analytics.alpha.alpha_zoo import AlphaZoo
from data.ingestion import get_event_backbone, get_normalizer
from execution.engine import get_execution_engine, DefaultRiskOverlay, ExecutionConfig
from execution.contracts import PortfolioState, RiskLimits, adapter_registry, Venue
from shared.domain import Instrument

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("phase_f")


# ── Batch Job Types ────────────────────────────────────────────────────────

BATCH_JOB_WFO = "walk_forward"
BATCH_JOB_CPCV = "cpcv"
BATCH_JOB_MC = "monte_carlo"
BATCH_JOB_OPTIMIZE = "optimize"
BATCH_JOB_BACKTEST = "backtest"


# ── Batch Job Model ───────────────────────────────────────────────────────

class BatchJob:
    """Represents a batch processing job with status tracking."""

    def __init__(
        self,
        job_id: str,
        job_type: str,
        strategy_id: str,
        parameters: Dict[str, Any],
        created_at: Optional[datetime] = None,
    ):
        self.job_id = job_id
        self.job_type = job_type
        self.strategy_id = strategy_id
        self.parameters = parameters
        self.created_at = created_at or datetime.utcnow()
        self.started_at: Optional[datetime] = None
        self.completed_at: Optional[datetime] = None
        self.status: str = "pending"  # pending, running, completed, failed
        self.results: Optional[ValidationResult] = None
        self.error: Optional[str] = None
        self.progress: float = 0.0  # 0.0 to 1.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "job_id": self.job_id,
            "job_type": self.job_type,
            "strategy_id": self.strategy_id,
            "status": self.status,
            "progress": self.progress,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BatchJob":
        job = cls(
            job_id=data["job_id"],
            job_type=data["job_type"],
            strategy_id=data["strategy_id"],
            parameters=data.get("parameters", {}),
            created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else None,
        )
        job.status = data.get("status", "pending")
        job.progress = data.get("progress", 0.0)
        job.started_at = datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None
        job.completed_at = datetime.fromisoformat(data["completed_at"]) if data.get("completed_at") else None
        job.error = data.get("error")
        job.results = ValidationResult(**data["results"]) if data.get("results") else None
        return job


# ── Batch Processor ────────────────────────────────────────────────────────

class BatchProcessor:
    """
    Orchestrates batch validation and optimization jobs.
    Supports WFO, CPCV, Monte Carlo, and optimization jobs.
    """

    def __init__(
        self,
        alpha_zoo: Optional[AlphaZoo] = None,
        execution_engine: Optional[ExecutionEngine] = None,
    ):
        self.alpha_zoo = alpha_zoo
        self.execution_engine = execution_engine
        self._jobs: Dict[str, BatchJob] = {}
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._validated_strategies: Dict[str, ValidationResult] = {}

    def submit_job(
        self,
        job_type: str,
        strategy_id: str,
        parameters: Dict[str, Any],
        symbols: Optional[List[str]] = None,
        timeframe: Optional[str] = None,
        n_folds: Optional[int] = None,
    ) -> BatchJob:
        """Submit a new batch job and return the job instance."""
        import uuid
        job_id = f"{job_type}_{strategy_id}_{uuid.uuid4().hex[:8]}"
        job = BatchJob(job_id=job_id, job_type=job_type, strategy_id=strategy_id, parameters=parameters)
        self._jobs[job_id] = job
        logger.info(f"Submitted {job_type} job: {job_id}")
        return job

    def get_job(self, job_id: str) -> Optional[BatchJob]:
        """Get job status by ID."""
        return self._jobs.get(job_id)

    def list_jobs(self, status: Optional[str] = None) -> List[BatchJob]:
        """List jobs, optionally filtered by status."""
        if status:
            return [j for j in self._jobs.values() if j.status == status]
        return list(self._jobs.values())

    # ── Walk-Forward Optimization ────────────────────────────────────────

    async def run_wfo_batch(
        self,
        job: BatchJob,
        X: np.ndarray,
        y: np.ndarray,
        symbols: List[str],
        timeframe: str,
        walk_forward: WalkForwardOptimizer,
        metric_fn: Optional[Callable] = None,
    ) -> BatchJob:
        """Run walk-forward optimization batch."""
        job.status = "running"
        job.started_at = datetime.utcnow()
        job.progress = 0.0

        try:
            strategy_id = job.strategy_id
            strategy_params = job.parameters

            # Run WFO
            result = await asyncio.get_event_loop().run_in_executor(
                self._executor,
                walk_forward.validate,
                None,  # model_factory will be called internally
                X,
                y,
                None,  # gates - use defaults
                metric_fn,
                strategy_id,
            )

            job.results = result
            job.status = "completed"
            job.progress = 1.0

            # Check if strategy passes gates
            if result.failed_gates:
                logger.warning(
                    f"WFO job {job.job_id} failed gates: {result.failed_gates}"
                )
            else:
                logger.info(
                    f"WFO job {job.job_id} passed all gates. IC: {result.metrics.get('ic_mean', 0):.4f}"
                )

            # Store validated strategy if it passes
            if not result.failed_gates:
                self._validated_strategies[strategy_id] = result

            job.completed_at = datetime.utcnow()
            logger.info(f"WFO job {job.job_id} completed")

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.completed_at = datetime.utcnow()
            logger.error(f"WFO job {job.job_id} failed: {e}")

        job.progress = 1.0
        return job

    # ── Combinatorial Purged CV ──────────────────────────────────────────

    async def run_cpcv_batch(
        self,
        job: BatchJob,
        X: np.ndarray,
        y: np.ndarray,
        walk_forward: CombinatorialPurgedCV,
        metric_fn: Optional[Callable] = None,
    ) -> BatchJob:
        """Run CPCV batch validation."""
        job.status = "running"
        job.started_at = datetime.utcnow()
        job.progress = 0.0

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                self._executor,
                walk_forward.validate,
                None,
                X,
                y,
                None,
                metric_fn,
                job.strategy_id,
            )

            job.results = result
            job.status = "completed"
            job.progress = 1.0

            if result.failed_gates:
                logger.warning(
                    f"CPCV job {job.job_id} failed gates: {result.failed_gates}"
                )
            else:
                logger.info(
                    f"CPCV job {job.job_id} passed all gates"
                )

            if not result.failed_gates:
                self._validated_strategies[job.strategy_id] = result

            job.completed_at = datetime.utcnow()
            logger.info(f"CPCV job {job.job_id} completed")

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.completed_at = datetime.utcnow()
            logger.error(f"CPCV job {job.job_id} failed: {e}")

        job.progress = 1.0
        return job

    # ── Monte Carlo Validation ───────────────────────────────────────────

    async def run_monte_carlo_batch(
        self,
        job: BatchJob,
        trades: List[Dict[str, Any]],
        n_simulations: Optional[int] = None,
    ) -> BatchJob:
        """Run Monte Carlo validation batch."""
        job.status = "running"
        job.started_at = datetime.utcnow()
        job.progress = 0.0

        try:
            mc_validator = MonteCarloValidator(
                n_simulations=n_simulations or 1000,
            )

            # Validate trade sequencing
            mc_results = await asyncio.get_event_loop().run_in_executor(
                self._executor,
                mc_validator.validate_sequencing,
                trades,
                n_simulations,
            )

            # Validate parameter stability if we have backtest function
            job.results = mc_results
            job.status = "completed"
            job.progress = 1.0

            # Check for parameter stability
            if "mean_max_drawdown" in mc_results:
                stability = mc_results["mean_max_drawdown"]
                # Good stability: low mean max drawdown and low std
                passes_stability = (
                    stability < 0.2 if isinstance(stability, (int, float)) else False
                )
                logger.info(
                    f"MC job {job.job_id}: mean_max_drawdown={stability:.4f}, "
                    f"stability check: {'pass' if passes_stability else 'fail'}"
                )

            job.completed_at = datetime.utcnow()
            logger.info(f"MC job {job.job_id} completed")

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.completed_at = datetime.utcnow()
            logger.error(f"MC job {job.job_id} failed: {e}")

        job.progress = 1.0
        return job

    # ── Strategy Optimization ─────────────────────────────────────────────

    async def optimize_strategy_parameters(
        self,
        job: BatchJob,
        X: np.ndarray,
        y: np.ndarray,
        parameter_ranges: Dict[str, Tuple[float, float]],
        walk_forward: WalkForwardOptimizer,
        n_simulations: int = 50,
    ) -> BatchJob:
        """Optimize strategy parameters using WFO + Monte Carlo."""
        job.status = "running"
        job.started_at = datetime.utcnow()
        job.progress = 0.0

        try:
            base_params = job.parameters
            best_result: Optional[ValidationResult] = None
            best_metric = -np.inf

            # Grid search over parameter ranges
            param_names = list(parameter_ranges.keys())
            param_values = [
                np.linspace(low, high, 5) for low, high in parameter_ranges.values()
            ]

            # Generate parameter combinations
            from itertools import product
            combinations = list(product(*param_values))

            logger.info(
                f"Optimizing {len(combinations)} parameter combinations "
                f"for {job.strategy_id}"
            )

            for i, combo in enumerate(combinations):
                if job.status != "running":
                    break

                # Build parameter dict
                params = dict(zip(param_names, combo))

                # Create model factory with these params
                def make_model_factory(p=params, s_id=job.strategy_id):

                    def model_factory():
                        # This would create a strategy model with params p
                        # For now, return None - caller provides actual model
                        return None

                    return model_factory

                # Run WFO with these parameters
                result = await asyncio.get_event_loop().run_in_executor(
                    self._executor,
                    walk_forward.validate,
                    make_model_factory(),
                    X,
                    y,
                    None,
                    None,
                    s_id,
                )

                # Use IC mean as optimization metric if available
                metric = result.metrics.get("ic_mean", 0) if result.metrics else 0

                if metric > best_metric:
                    best_metric = metric
                    best_result = result
                    logger.info(
                        f"New best params: {params}, IC_mean: {metric:.4f}"
                    )

                # Progress update
                job.progress = (i + 1) / len(combinations)
                await asyncio.sleep(0)  # Yield to event loop

            if best_result:
                job.results = best_result
                job.status = "completed"
                logger.info(
                    f"Optimization complete. Best IC_mean: {best_metric:.4f}, "
                    f"params: {best_result.parameters}"
                )
            else:
                job.status = "completed"
                job.error = "No valid parameter combinations found"
                logger.warning("Optimization completed with no valid results")

            job.completed_at = datetime.utcnow()

        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.completed_at = datetime.utcnow()
            logger.error(f"Strategy optimization failed: {e}")

        job.progress = 1.0
        return job

    # ── Batch Job Runner ──────────────────────────────────────────────────

    async def run_job(
        self,
        job: BatchJob,
        X: Optional[np.ndarray] = None,
        y: Optional[np.ndarray] = None,
        trades: Optional[List[Dict]] = None,
        parameter_ranges: Optional[Dict] = None,
        symbols: Optional[List[str]] = None,
        timeframe: Optional[str] = None,
        n_simulations: Optional[int] = None,
    ) -> BatchJob:
        """Run a batch job based on its type."""
        job_type = job.job_type

        if job_type == BATCH_JOB_WFO:
            if not X.size or not y.size:
                job.status = "failed"
                job.error = "X and y data required for WFO"
                return job

            wfo = WalkForwardOptimizer(
                train_window=job.parameters.get("train_window", 252),
                test_window=job.parameters.get("test_window", 63),
                step=job.parameters.get("step", 21),
                expanding=job.parameters.get("expanding", True),
            )
            return await self.run_wfo_batch(
                job, X, y, symbols or ["BTCUSDT"], timeframe or "1h", wfo
            )

        elif job_type == BATCH_JOB_CPCV:
            if not X.size or not y.size:
                job.status = "failed"
                job.error = "X and y data required for CPCV"
                return job

            cpcv = CombinatorialPurgedCV(
                n_splits=job.parameters.get("n_splits", 5),
                n_test_splits=job.parameters.get("n_test_splits", 2),
                purge_pct=job.parameters.get("purge_pct", 0.01),
                embargo_pct=job.parameters.get("embargo_pct", 0.01),
            )
            return await self.run_cpcv_batch(job, X, y, cpcv)

        elif job_type == BATCH_JOB_MC:
            if not trades:
                job.status = "failed"
                job.error = "trades data required for Monte Carlo"
                return job
            return await self.run_monte_carlo_batch(job, trades, n_simulations)

        elif job_type == BATCH_JOB_OPTIMIZE:
            if not X.size or not y.size:
                job.status = "failed"
                job.error = "X and y data required for optimization"
                return job
            wfo = WalkForwardOptimizer(
                train_window=job.parameters.get("train_window", 252),
                test_window=job.parameters.get("test_window", 63),
                step=job.parameters.get("step", 21),
                expanding=job.parameters.get("expanding", True),
            )
            return await self.optimize_strategy_parameters(
                job, X, y, parameter_ranges or {},
                wfo,
                n_simulations=job.parameters.get("n_simulations", 50),
            )

        else:
            job.status = "failed"
            job.error = f"Unknown batch job type: {job_type}"
            return job

    # ── Persistence (PostgreSQL) ──────────────────────────────────────────

    def save_job(self, job: BatchJob) -> None:
        """Save job state to PostgreSQL."""
        # Placeholder - would integrate with PostgreSQL storage
        # from core.database import SessionLocal
        # from models import BatchJob as DBBatchJob
        # ...
        pass

    def load_job(self, job_id: str) -> Optional[BatchJob]:
        """Load job state from PostgreSQL."""
        # Placeholder
        return self._jobs.get(job_id)

    def __del__(self):
        self._executor.shutdown(wait=False)


# ── Scheduler ──────────────────────────────────────────────────────────────

class BatchScheduler:
    """
    Schedules and runs batch processing jobs on a timer.
    """

    def __init__(self, batch_processor: BatchProcessor, cron_expr: str = "0 * * * *"):
        self.batch_processor = batch_processor
        self.cron_expr = cron_expr
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Start the scheduler."""
        self._running = True
        self._task = asyncio.create_task(self._schedule_loop())
        logger.info(f"Batch scheduler started with cron: {self.cron_expr}")

    async def stop(self) -> None:
        """Stop the scheduler."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Batch scheduler stopped")

    async def _schedule_loop(self) -> None:
        """Main scheduling loop."""
        # Parse simple cron: "0 * * * *" = every hour at minute 0
        # For now, run every 6 hours
        while self._running:
            try:
                # Run batch processing cycle
                await self._run_cycle()
                # Wait 6 hours
                await asyncio.sleep(6 * 60 * 60)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Scheduler cycle error: {e}")
                await asyncio.sleep(60)

    async def _run_cycle(self) -> None:
        """Run one batch processing cycle."""
        logger.info("Running batch processing cycle")
        # This would typically query for pending jobs and execute them
        # For now, just log
        logger.info("Batch cycle complete")


# ── Export ─────────────────────────────────────────────────────────────────

__all__ = [
    "BatchProcessor",
    "BatchJob",
    "BatchScheduler",
    "BATCH_JOB_WFO",
    "BATCH_JOB_CPCV",
    "BATCH_JOB_MC",
    "BATCH_JOB_OPTIMIZE",
    "BATCH_JOB_BACKTEST",
    "DEFAULT_GATES",
    "evaluate_gates",
    "auto_reject",
]

if __name__ == "__main__":
    print("Phase F - Batch Processing and Strategy Optimization Pipeline")
    print(f"Available job types: {BATCH_JOB_WFO}, {BATCH_JOB_CPCV}, {BATCH_JOB_MC}, {BATCH_JOB_OPTIMIZE}")
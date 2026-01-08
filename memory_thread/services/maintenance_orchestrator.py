import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional

from memory_thread.services.decay_engine import DecayEngine
from memory_thread.services.assimilator import AssimilatorService
from memory_thread.services.snapshot_service import SnapshotService
from memory_thread.services.identity_service import IdentityService
from memory_thread.utils.logger import get_logger

log = get_logger(__name__)

class MaintenanceOrchestrator:
    """
    Schedules and executes periodic cognitive maintenance jobs.
    1. Decay: Updates freshness of truth vectors.
    2. Assimilation: Consolidates redundant event sequences.
    3. Snapshots: Compacts old history.
    4. Identity: Merges duplicate entities (optional auto-merge).
    """
    def __init__(self):
        self.decay = DecayEngine()
        self.assimilator = AssimilatorService()
        self.snapshot = SnapshotService()
        self.identity = IdentityService()
        self._running = False
        self._task: Optional[asyncio.Task] = None

    async def run_maintenance_now(self, job_type: str = "all") -> dict:
        """
        Manually triggers maintenance jobs.
        """
        log.info(f"Starting Maintenance Job: {job_type}")
        report = {}

        try:
            # 1. Decay (Daily)
            if job_type in ["all", "decay"]:
                stats = self.decay.update_freshness(simulate=False)
                report["decay"] = stats
                log.info(f"Decay Complete: {stats}")

            # 2. Assimilation (Daily/Weekly)
            if job_type in ["all", "assimilation"]:
                # We need to scan all active entities. For now, fetch generic list.
                # In real prod, this needs batching/cursor.
                entities = self.identity.list_entities()
                merged_count = 0
                for entity in entities:
                    patterns = self.assimilator.detect_patterns(entity.id)
                    for group in patterns:
                        summary = self.assimilator.consolidate_events(group)
                        if summary:
                            self.assimilator.execute_consolidation(summary, group)
                            merged_count += len(group)
                report["assimilation"] = {"events_consolidated": merged_count}
                log.info(f"Assimilation Complete: {merged_count} events merged.")

            # 3. Snapshot Compaction (Weekly)
            if job_type in ["all", "snapshot"]:
                # Compact for all entities? Expensive. 
                # Maybe just run for entities updated recently?
                # skipping global compaction for now to avoid perf hit.
                report["snapshot"] = "skipped (global)"

            report["status"] = "success"
        except Exception as e:
            log.error(f"Maintenance Failed: {e}")
            report["status"] = "failed"
            report["error"] = str(e)
            
        return report

    async def start_scheduler(self, interval_hours: int = 24):
        """
        Starts the background loop.
        """
        if self._running:
            return
            
        self._running = True
        log.info("Maintenance Scheduler Started.")
        
        while self._running:
            try:
                await self.run_maintenance_now("all")
            except Exception as e:
                log.error(f"Scheduler Crash: {e}")
            
            # Wait for next interval
            await asyncio.sleep(interval_hours * 3600)

    def stop(self):
        self._running = False
        log.info("Maintenance Scheduler Stopping...")

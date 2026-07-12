import logging
from typing import Any
from django.utils import timezone
from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from apps.core.infrastructure.models.background_job import BackgroundJob, JobStatus

logger = logging.getLogger(__name__)


class HunterBackgroundJobTask(Task):
    """
    Base Celery Task class for processing BackgroundJob instances.
    
    This class handles the lifecycle of the BackgroundJob model, including:
    - Marking as PROCESSING when starting.
    - Implementing idempotency (not running if already COMPLETED or CANCELLED).
    - Updating attempts, result, and status.
    - Handling timeouts (SoftTimeLimitExceeded) and marking as FAILED.
    - Relaunching retries with exponential backoff if configured.
    """
    
    # Default settings that subclasses can override
    autoretry_for = (Exception,)
    retry_backoff = True
    retry_kwargs = {'max_retries': 3}
    soft_time_limit = 600  # 10 minutes default
    
    def run(self, job_id: str, *args: Any, **kwargs: Any) -> Any:
        try:
            job = BackgroundJob.objects.get(pk=job_id)
        except BackgroundJob.DoesNotExist:
            logger.error("Job not found", extra={"job_id": job_id})
            return
            
        # Idempotency check: don't process if already finished
        if job.status in [JobStatus.COMPLETED, JobStatus.CANCELLED]:
            logger.info("Job already processed or cancelled", extra={"job_id": job_id, "status": job.status})
            return job.result

        # Update status to processing
        job.status = JobStatus.PROCESSING
        job.attempts += 1
        if not job.started_at:
            job.started_at = timezone.now()
        job.save(update_fields=["status", "attempts", "started_at"])

        try:
            # Delegate actual work to subclass
            result = self.process_job(job, *args, **kwargs)
            
            # On success
            job.status = JobStatus.COMPLETED
            job.result = result
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "result", "completed_at"])
            
            return result
            
        except SoftTimeLimitExceeded as e:
            # Handle timeout
            job.status = JobStatus.FAILED
            job.error = "Timeout: Soft time limit exceeded."
            job.completed_at = timezone.now()
            job.save(update_fields=["status", "error", "completed_at"])
            logger.exception("Job timeout", extra={"job_id": job_id, "job_type": job.job_type})
            # We don't retry timeouts usually, but you can configure it
            raise e
            
        except Exception as e:
            # Handle generic failure
            job.error = str(e)
            
            if self.request.retries >= self.max_retries:
                # Dead letter strategy / Final failure
                job.status = JobStatus.FAILED
                job.completed_at = timezone.now()
                job.save(update_fields=["status", "error", "completed_at"])
                logger.exception("Job permanently failed", extra={"job_id": job_id, "job_type": job.job_type})
                raise e
            else:
                # Still retrying
                job.status = JobStatus.PENDING
                job.save(update_fields=["status", "error"])
                logger.warning("Job failed, scheduling retry", extra={"job_id": job_id, "job_type": job.job_type})
                raise self.retry(exc=e)

    def process_job(self, job: BackgroundJob, *args: Any, **kwargs: Any) -> Any:
        """
        Subclasses must implement this method.
        It should read parameters from `job.payload` and return the result.
        """
        raise NotImplementedError("Subclasses must implement process_job")


from celery import shared_task

@shared_task(bind=True, base=HunterBackgroundJobTask, max_retries=1, soft_time_limit=30)
def validation_ping_task(self: HunterBackgroundJobTask, job_id: str) -> dict[str, str]:
    """
    A simple task to validate the queue infrastructure.
    It reads 'ping_message' from the job payload and returns a 'pong' result.
    """
    job = BackgroundJob.objects.get(pk=job_id)
    message = job.payload.get("ping_message", "Hello")
    
    # Simulate work
    import time
    time.sleep(1)
    
    return {"status": "success", "echo": f"Pong! Received: {message}"}

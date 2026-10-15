import pytest
from app.domain.models.job import Job
from app.domain.schemas.data_contracts import JobState

def test_job_state_transition_valid():
    job = Job(id="job_1", status=JobState.CREATED.value)
    job.transition_to(JobState.UPLOADING)
    assert job.status == JobState.UPLOADING.value

def test_job_state_transition_invalid():
    job = Job(id="job_1", status=JobState.CREATED.value)
    with pytest.raises(ValueError):
        job.transition_to(JobState.VALIDATING_IR)

from sqlalchemy import Column, String, Float, JSON
from sqlalchemy.orm import declarative_base
from app.domain.schemas.data_contracts import JobState

Base = declarative_base()

class Job(Base):
    __tablename__ = "jobs"
    id = Column(String, primary_key=True, index=True)
    status = Column(String, default=JobState.CREATED.value)
    progress = Column(Float, default=0.0)
    metadata_json = Column(JSON, default={})
    
    def transition_to(self, new_state: JobState):
        valid_transitions = {
            JobState.CREATED: [JobState.UPLOADING, JobState.FAILED],
            JobState.UPLOADING: [JobState.EXTRACTING_SOURCE, JobState.FAILED],
            # Minimal phase 1 validation
        }
        allowed = valid_transitions.get(JobState(self.status), [s for s in JobState])
        if new_state not in allowed:
            raise ValueError(f"Invalid state transition from {self.status} to {new_state}")
        self.status = new_state.value

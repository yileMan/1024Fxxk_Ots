from pydantic import BaseModel


class CollectorScopeItemResponse(BaseModel):
    ots_id: int
    ots_name: str
    ots_version: str
    official_website: str
    last_covered_time: str | None
    is_initial_collection: bool


class CollectorScopeBaselineResponse(BaseModel):
    available: bool
    batch_no: str | None
    finished_at: str | None


class CollectorScopeChangesResponse(BaseModel):
    added_ots_ids: list[int]
    removed_ots_ids: list[int]
    added_count: int
    removed_count: int


class CollectorScopePreviewResponse(BaseModel):
    scope_count: int
    items: list[CollectorScopeItemResponse]
    comparison_baseline: CollectorScopeBaselineResponse
    changes: CollectorScopeChangesResponse

import asyncio
from backend.pipelines.pipeline import CCTVPipeline

def test_pipeline_smoke():
    # smoke test that pipeline object can be created
    p = CCTVPipeline(source=":/dev/null")
    assert p.source is not None

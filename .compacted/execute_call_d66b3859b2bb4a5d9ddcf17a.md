            content="Set PRAGMA journal_mode=WAL for concurrency. Also enable busy_timeout.",
        )
        results = await gov.find_superseded(db, "p1", content_threshold=0.80)
        # The two items are near-identical; should flag one supersession
>       assert len(results) >= 1
E       assert 0 >= 1
E        +  where 0 = len([])

tests/unit/test_knowledge_governance.py:99: AssertionError
=========================== short test summary info ============================
FAILED tests/unit/test_knowledge_governance.py::TestSupersededDetection::test_detects_similar_newer_item
1 failed in 0.36s
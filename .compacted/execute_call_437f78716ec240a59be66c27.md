            db, "p1", title="Use WAL mode",
            content="Set PRAGMA journal_mode=WAL for concurrency. Also enable busy_timeout.",
            updated_at=_old_timestamp(60),
        )
        # Newer item: identical content + a short addendum → ratio ~0.97
        new = await _create_knowledge(
            db, "p1", title="Use WAL mode",
            content="Set PRAGMA journal_mode=WAL for concurrency. Also enable busy_timeout. "
                    "Enable synchronous=NORMAL for throughput.",
        )
        results = await gov.find_superseded(db, "p1", content_threshold=0.90)
        # The two items are near-identical; should flag one supersession
>       assert len(results) >= 1
E       assert 0 >= 1
E        +  where 0 = len([])

tests/unit/test_knowledge_governance.py:102: AssertionError
=========================== short test summary info ============================
FAILED tests/unit/test_knowledge_governance.py::TestSupersededDetection::test_detects_similar_newer_item
1 failed in 0.35s
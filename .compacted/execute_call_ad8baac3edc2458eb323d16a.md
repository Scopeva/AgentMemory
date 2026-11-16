            r["event"] for r in records if r["event"].get("event_type") == "turn.end"
        ]
        assert len(turn_starts) == 2
        assert len(turn_ends) == 2
        # turn.start: indices 0, 2 (increments on each start call)
        # turn.end: indices -1, 1 (decrements by 1 from the post-increment value)
        assert turn_starts[0]["payload"]["turn_index"] == 0
        assert turn_starts[1]["payload"]["turn_index"] == 2
>       assert turn_ends[0]["payload"]["turn_index"] == -1
E       assert 0 == -1

tests/test_phase5_adapters.py:215: AssertionError
=========================== short test summary info ============================
FAILED tests/test_phase5_adapters.py::TestOpenCodeAdapter::test_turn_index_increments
1 failed in 0.27s
        ]
        turn_ends = [
            r["event"] for r in records if r["event"].get("event_type") == "turn.end"
        ]
        assert len(turn_starts) == 2
        assert len(turn_ends) == 2
        # First turn index is 0, second is 1
        assert turn_starts[0]["payload"]["turn_index"] == 0
>       assert turn_starts[1]["payload"]["turn_index"] == 1
E       assert 2 == 1

tests/test_phase5_adapters.py:213: AssertionError
=========================== short test summary info ============================
FAILED tests/test_phase5_adapters.py::TestOpenCodeAdapter::test_turn_index_increments
1 failed, 9 passed in 0.36s
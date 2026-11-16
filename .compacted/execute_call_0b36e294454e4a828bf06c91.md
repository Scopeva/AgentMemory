self = <test_pi_adapter.TestPiAdapterLifecycle object at 0xffffac4b9a70>
tmp_path = PosixPath('/tmp/pytest-of-root/pytest-5/test_no_durable_memory_is_lega0')

    def test_no_durable_memory_is_legal_empty_result(self, tmp_path: Path):
        """A 'no_durable_memory' result is valid and does not create handoff."""
>       adapter = self._make_adapter(tmp_path)
                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^

tests/test_pi_adapter.py:250: 
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 
tests/test_pi_adapter.py:166: in _make_adapter
    return PiAdapter(cfg)
           ^^^^^^^^^^^^^^
adapters/pi/pi_adapter.py:321: in __init__
    spool = DurableSpool(self.config.agent, root=self.config.spool_root)
            ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
_ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ _ 

self = <adapters.shared.event_client.DurableSpool object at 0xffffac24db80>
agent = 'pi'
root = '/tmp/pytest-of-root/pytest-5/test_no_durable_memory_is_lega0'

    def __init__(self, agent: str, root: Optional[Path] = None):
        self.agent = agent
        if root is None:
            root = Path(os.environ.get(
                "AGENT_MEMORY_SPOOL_ROOT",
                str(Path.home() / ".local" / "state" / "agent-memory"),
            ))
>       self.dir = root / agent
                   ^^^^^^^^^^^^
E       TypeError: unsupported operand type(s) for /: 'str' and 'str'

adapters/shared/event_client.py:58: TypeError
=========================== short test summary info ============================
FAILED tests/test_pi_adapter.py::TestPiAdapterLifecycle::test_full_lifecycle_spools_all_events
FAILED tests/test_pi_adapter.py::TestPiAdapterLifecycle::test_no_extraction_for_trivial_completed_run
FAILED tests/test_pi_adapter.py::TestPiAdapterLifecycle::test_recursion_guard_blocks_double_extraction
FAILED tests/test_pi_adapter.py::TestPiAdapterLifecycle::test_no_durable_memory_is_legal_empty_result
========================= 4 failed, 10 passed in 0.35s =========================
stderr:

[notice] A new release of pip is available: 26.2.2 -> 26.3
[notice] To update, run: pip install --upgrade pip
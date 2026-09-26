"""Exercise RDS action batching without invoking Cumulus or AWS."""

import argparse
import json
from copy import deepcopy
from threading import Lock
from unittest.mock import call, patch

import pytest

from pylot.plugins.rds.main import apply_api_action, main, return_parser


class RecordingApi:
    """Record actual worker calls while retaining an inspectable signature."""

    def __init__(self):
        self.calls = []
        self.lock = Lock()

    def apply_workflow_to_granule(self, granule_id, workflow_name):
        with self.lock:
            self.calls.append((granule_id, workflow_name))
        return {"granuleId": granule_id, "workflow": workflow_name}


@pytest.mark.parametrize("count,batch_size", [
    (0, 10), (1, 1), (1, 10), (2, 10), (9, 10), (10, 10),
    (11, 10), (20, 10), (23, 10), (7, 1), (7, 3), (1000, 100),
])
def test_only_nonempty_batches_are_waited_for_and_monitored(count, batch_size):
    records = [{"granule_id": str(i)} for i in range(count)]
    if records:
        records[0]["workflow_name"] = "record-workflow"
    extra_arguments = {"workflow_name": "fallback-workflow"}
    before = deepcopy((records, extra_arguments))
    api = RecordingApi()
    batches = []

    def monitor(responses, client):
        assert client is api
        start = len(batches) * batch_size
        expected_ids = {str(i) for i in range(start, min(start + batch_size, count))}
        assert {response["granuleId"] for response in responses} == expected_ids
        # No worker for the next batch may run before monitoring this one.
        assert len(api.calls) == min(start + batch_size, count)
        batches.append(responses)

    with patch("pylot.plugins.rds.main.PyLOTHelpers.get_cumulus_api_instance", return_value=api), \
            patch("pylot.plugins.rds.main.sleep") as sleep, \
            patch("pylot.plugins.rds.main.monitor_batch", side_effect=monitor):
        result = apply_api_action(records, "apply_workflow_to_granule", extra_arguments, batch_size)

    assert result is None
    assert [len(batch) for batch in batches] == [
        min(batch_size, count - i) for i in range(0, count, batch_size)
    ]
    assert all(batches)
    assert sleep.call_args_list == [call(5)] * len(batches)
    assert sorted(api.calls) == sorted(
        (record["granule_id"], record.get("workflow_name", "fallback-workflow"))
        for record in records
    )
    assert (records, extra_arguments) == before


@pytest.mark.parametrize("batch_size", [0, -1, -10])
def test_nonpositive_batch_size_fails_before_initializing_clients(batch_size):
    with patch("pylot.plugins.rds.main.PyLOTHelpers.get_cumulus_api_instance") as get_api, \
            patch("pylot.plugins.rds.main.sleep") as sleep, \
            patch("pylot.plugins.rds.main.monitor_batch") as monitor:
        with pytest.raises(ValueError, match="batch_size"):
            apply_api_action([{"granule_id": "one"}], "apply_workflow_to_granule", {}, batch_size)
    get_api.assert_not_called()
    sleep.assert_not_called()
    monitor.assert_not_called()


def test_worker_failure_propagates_before_starting_the_next_batch():
    class FailingApi(RecordingApi):
        def apply_workflow_to_granule(self, granule_id, workflow_name):
            super().apply_workflow_to_granule(granule_id, workflow_name)
            raise RuntimeError("task failed")

    api = FailingApi()
    with patch("pylot.plugins.rds.main.PyLOTHelpers.get_cumulus_api_instance", return_value=api), \
            patch("pylot.plugins.rds.main.sleep") as sleep, \
            patch("pylot.plugins.rds.main.monitor_batch") as monitor:
        with pytest.raises(RuntimeError, match="task failed"):
            apply_api_action([{"granule_id": "one"}, {"granule_id": "two"}],
                             "apply_workflow_to_granule", {"workflow_name": "test"}, 1)
    assert api.calls == [("one", "test")]
    sleep.assert_not_called()
    monitor.assert_not_called()


def test_monitor_failure_prevents_the_next_batch():
    api = RecordingApi()
    with patch("pylot.plugins.rds.main.PyLOTHelpers.get_cumulus_api_instance", return_value=api), \
            patch("pylot.plugins.rds.main.sleep"), \
            patch("pylot.plugins.rds.main.monitor_batch", side_effect=RuntimeError("monitor failed")):
        with pytest.raises(RuntimeError, match="monitor failed"):
            apply_api_action([{"granule_id": "one"}, {"granule_id": "two"}],
                             "apply_workflow_to_granule", {"workflow_name": "test"}, 1)
    assert api.calls == [("one", "test")]


def test_command_parser_and_file_input_use_nonempty_batches(tmp_path):
    path = tmp_path / "results.json"
    path.write_text(json.dumps([{"granule_id": str(i)} for i in range(5)]))
    parser = argparse.ArgumentParser()
    return_parser(parser.add_subparsers(dest="command"))
    options = vars(parser.parse_args([
        "rds", "-i", str(path), "-a", "apply_workflow_to_granule", "-b", "2",
        "-args", "workflow_name=example",
    ]))
    api = RecordingApi()
    with patch("pylot.plugins.rds.main.PyLOTHelpers.get_cumulus_api_instance", return_value=api), \
            patch("pylot.plugins.rds.main.sleep") as sleep, \
            patch("pylot.plugins.rds.main.monitor_batch") as monitor:
        assert main(**options) == 0
    assert [len(args.args[0]) for args in monitor.call_args_list] == [2, 2, 1]
    assert sleep.call_args_list == [call(5)] * 3
    assert sorted(api.calls) == [(str(i), "example") for i in range(5)]

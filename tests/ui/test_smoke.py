import json

import pytest

pytestmark = pytest.mark.ui


def test_smoke_contract(qapp, capsys):
    from matnyab.ui.app import main

    code = main(["--smoke"])
    out = capsys.readouterr().out.strip().splitlines()
    assert code == 0
    payload = json.loads(out[-1])
    assert payload["ok"] is True and payload["window"] is True
    assert isinstance(payload["words"], int) and payload["words"] > 0

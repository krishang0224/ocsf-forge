from unittest.mock import MagicMock

import pytest

from ulpf.ui import errors


@pytest.mark.parametrize("debug", ["", "false", "true"])
def test_error_details_are_server_only_unless_debug_is_explicit(monkeypatch, caplog, debug):
    ui = MagicMock()
    monkeypatch.setattr(errors, "st", ui)
    monkeypatch.setenv("ULPF_DEBUG_ERRORS", debug)
    secret = "password=private-value SQL SELECT confidential"
    reference = errors.show_error(RuntimeError(secret), "Ingestion failed.")
    assert len(reference) == 12
    assert reference in ui.error.call_args.args[0]
    assert secret not in ui.error.call_args.args[0]
    assert secret in caplog.text
    assert reference in caplog.text
    if debug == "true":
        ui.code.assert_called_once_with(secret)
    else:
        ui.code.assert_not_called()
        ui.expander.assert_not_called()

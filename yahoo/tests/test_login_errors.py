import pytest

from yahoo import login


class _Resp:
    status_code = 400
    content = b'{"error": "invalid_grant", "error_description": "code expired"}'


def test_rejected_exchange_reports_yahoos_error():
    oauth = object.__new__(login._VerboseOAuth2)
    with pytest.raises(SystemExit) as exc:
        oauth.oauth2_access_parser(_Resp())
    msg = str(exc.value)
    assert "invalid_grant" in msg and "code expired" in msg and "400" in msg

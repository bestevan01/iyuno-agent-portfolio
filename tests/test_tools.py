import pytest

from agent.config import Settings
from agent.tools import CweLookup, PasswordPolicy, cvss_calculator, mask_args


@pytest.mark.parametrize("vector,score,sev", [
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H", 9.8, "Critical"),
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H", 10.0, "Critical"),
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:R/S:C/C:L/I:L/A:N", 6.1, "Medium"),
    ("AV:L/AC:L/PR:L/UI:N/S:U/C:H/I:H/A:H", 7.8, "High"),
    ("CVSS:3.1/AV:N/AC:H/PR:N/UI:N/S:U/C:H/I:N/A:N", 5.9, "Medium"),
    ("CVSS:3.1/AV:P/AC:H/PR:H/UI:R/S:U/C:L/I:N/A:N", 1.6, "Low"),
    ("CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:N/I:N/A:N", 0.0, "None"),
])
def test_cvss_known_vectors(vector, score, sev):
    out = cvss_calculator(vector)
    assert out["base_score"] == score
    assert out["severity"] == sev


def test_cvss_invalid_vector():
    assert "error" in cvss_calculator("AV:X/AC:L")


def test_cwe_lookup_found_and_missing():
    cwe = CweLookup(Settings().cwe_file)
    assert cwe("CWE-89")["top10"].startswith("A03")
    assert cwe("918")["top10"].startswith("A10")
    assert cwe("CWE-99999")["found"] is False
    assert "error" in cwe("abc")


def test_password_policy():
    pw = PasswordPolicy(Settings().passwords_file)
    assert pw("qwerty123")["passes"] is False
    assert pw("correct horse battery staple", mfa_enabled=True)["passes"] is True
    # MFA 없으면 15자 미만은 약함
    r = pw("Tr0ub4dor&3x", mfa_enabled=False)
    assert r["passes"] is False and r["min_length_required"] == 15
    # 비밀번호 원문이 결과에 포함되지 않아야 한다
    assert "qwerty123" not in str(pw("qwerty123"))


def test_mask_args_hides_password():
    assert mask_args("password_policy_check", {"password": "secret"})["password"] == "******"
    assert mask_args("cvss_calculator", {"vector": "x"}) == {"vector": "x"}

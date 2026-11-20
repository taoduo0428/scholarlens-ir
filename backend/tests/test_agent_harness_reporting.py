"""JUnit outcome is part of the registered legacy harness contract."""
import pytest

from tools.agent.run_harness import case_verdict


@pytest.mark.parametrize(("report", "exit_code", "expected"), [
    ('<testsuite><testcase/><testcase/></testsuite>', 0, (True, 2)),
    ('<testsuite><testcase/><testcase><skipped/></testcase></testsuite>', 0, (False, 1)),
    ('<testsuite><testcase><failure/></testcase></testsuite>', 1, (False, 0)),
    ('<testsuite><testcase><error/></testcase></testsuite>', 1, (False, 0)),
    ('<testsuite/>', 0, (False, 0)),
    ('<testsuite><testcase/></testsuite>', 4, (False, 1)),
    ('invalid xml', 0, (False, 0)),
])
def test_case_verdict_requires_executed_passing_tests(tmp_path, report, exit_code, expected):
    path = tmp_path / 'report.xml'
    path.write_text(report, encoding='utf-8')
    assert case_verdict(path, exit_code) == expected


def test_missing_report_fails_closed(tmp_path):
    assert case_verdict(tmp_path / 'missing.xml', 0) == (False, 0)

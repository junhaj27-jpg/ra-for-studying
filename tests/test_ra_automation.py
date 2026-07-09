import json
import sys
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "ALPLED-WEB"))

from docs.ra_automation import (  # noqa: E402
    analyze_change_impact,
    build_iec62304_traceability,
    build_traceability_graph,
    build_word_pdf_export_manifest,
    calculate_iso14971_risk,
    detect_document_inconsistencies,
    generate_vv_plan,
    package_rag_citations,
    render_portfolio_report,
)


class RAAutomationTests(unittest.TestCase):
    def setUp(self):
        seed_path = REPO_ROOT / "samples" / "ra-seed-projects.json"
        self.project = json.loads(seed_path.read_text(encoding="utf-8-sig"))["projects"][0]

    def test_iso14971_risk_score(self):
        score = calculate_iso14971_risk(4, 5)
        self.assertEqual(score.score, 20)
        self.assertEqual(score.label, "Unacceptable")

    def test_iec62304_traceability_coverage(self):
        trace = build_iec62304_traceability(
            self.project["requirements"],
            self.project["risks"],
            self.project["testScenarios"],
        )
        self.assertEqual(trace["coveragePercent"], 100.0)
        self.assertEqual(trace["missingTests"], [])

    def test_vv_plan_generation(self):
        plan = generate_vv_plan(
            self.project["requirements"],
            self.project["risks"],
            self.project["testScenarios"],
        )
        self.assertEqual(plan["documentType"], "검증 및 밸리데이션 계획서")
        self.assertGreaterEqual(len(plan["plannedTests"]), 1)

    def test_inconsistency_detection_finds_missing_test(self):
        broken = dict(self.project)
        broken["testScenarios"] = broken["testScenarios"][:-1]
        issues = detect_document_inconsistencies(broken)
        self.assertTrue(any(issue["type"] == "missing_test" for issue in issues))

    def test_rag_citation_packaging(self):
        citations = package_rag_citations([{"source": "회의록.md", "section": "요구사항", "page": 2, "quote": "비진단용 고지"}])
        self.assertEqual(citations[0]["citationId"], "RAG-001")
        self.assertEqual(citations[0]["source"], "회의록.md")

    def test_change_impact_and_graph(self):
        trace = build_iec62304_traceability(
            self.project["requirements"],
            self.project["risks"],
            self.project["testScenarios"],
        )
        impact = analyze_change_impact({"id": "CHG-001", "type": "requirement", "affectedIds": ["REQ-HR-001"]}, trace["rows"])
        graph = build_traceability_graph(trace["rows"])
        self.assertTrue(impact["requiresRevalidation"])
        self.assertGreaterEqual(len(graph["nodes"]), 3)
        self.assertGreaterEqual(len(graph["edges"]), 2)

    def test_export_manifest_and_portfolio_report(self):
        manifest = build_word_pdf_export_manifest(self.project)
        report = render_portfolio_report("RA 지원자", [self.project])
        self.assertEqual(len(manifest["documents"]), 8)
        self.assertIn("RA 프로젝트 포트폴리오 리포트", report)
        self.assertIn(self.project["name"], report)


if __name__ == "__main__":
    unittest.main()


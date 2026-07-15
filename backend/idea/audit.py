from __future__ import annotations

import hashlib
import json
import uuid
from datetime import date
from typing import Any

from .agent_schemas import (
    EvidenceAuditorOutput,
    InventiveStepOutput,
    NoveltyResult,
    ValueAnalyzerOutput,
)
from .agents import AgentExecutionError, IdeaAgentService
from .database import Database, canonical_json, now_ms


EVIDENCE_AUDITOR_PROMPT = """
You are patent-evidence-auditor. Read only the supplied immutable evidence inventory, frozen
novelty result, inventive routes, value result and deterministic findings. Check whether quoted
language reasonably supports the associated mapping and whether conclusion wording overstates
the supplied evidence. Do not change conclusions, search, invent an ID, or omit an inventory
item. Return exactly all supplied evidence IDs and publication numbers in the checked lists.
Only output issues; programmatic integrity checks remain authoritative.
"""


class AuditService:
    def __init__(
        self,
        database: Database,
        agents: IdeaAgentService,
        *,
        minimum_deep_reviews: int = 10,
    ):
        self.database = database
        self.agents = agents
        self.minimum_deep_reviews = minimum_deep_reviews

    async def audit(
        self,
        run_id: str,
        novelty: NoveltyResult,
        inventive_routes: list[InventiveStepOutput],
        value: ValueAnalyzerOutput,
    ) -> list[dict[str, Any]]:
        inventory, publications, deterministic = self._deterministic_audit(
            run_id, novelty, inventive_routes, value
        )
        if any(item["severity"] == "critical" for item in deterministic):
            self._persist(run_id, deterministic)
            return deterministic

        payload = {
            "evidence_inventory": inventory,
            "publication_numbers": sorted(publications),
            "novelty": novelty.model_dump(mode="json"),
            "inventive_routes": [route.model_dump(mode="json") for route in inventive_routes],
            "value_result": value.model_dump(mode="json"),
            "deterministic_findings": deterministic,
        }
        result = await self.agents.call_agent(
            run_id,
            "patent-evidence-auditor",
            system_prompt=EVIDENCE_AUDITOR_PROMPT,
            input_payload=payload,
            input_size=len(canonical_json(payload)),
        )
        output = result.output
        if not isinstance(output, EvidenceAuditorOutput):
            raise AgentExecutionError("evidence auditor returned wrong validated model")
        expected_evidence = {item["evidence_id"] for item in inventory}
        if set(output.checked_evidence_ids) != expected_evidence or len(
            output.checked_evidence_ids
        ) != len(expected_evidence):
            raise AgentExecutionError("evidence auditor did not check the exact evidence inventory")
        if set(output.checked_publication_numbers) != publications or len(
            output.checked_publication_numbers
        ) != len(publications):
            raise AgentExecutionError("evidence auditor did not check the exact publication inventory")

        semantic = []
        for issue in output.issues:
            unknown = set(issue.evidence_ids) - expected_evidence
            if unknown:
                raise AgentExecutionError(
                    f"evidence auditor cited unknown evidence IDs: {sorted(unknown)}"
                )
            semantic.append(
                {
                    # Model findings are advisory and cannot create a Workflow-blocking critical.
                    "severity": "warning" if issue.severity == "critical" else issue.severity,
                    "code": f"MODEL_{issue.code}",
                    "message": issue.message,
                    "details": {
                        "evidence_ids": issue.evidence_ids,
                        "reported_severity": issue.severity,
                    },
                }
            )
        findings = deterministic + semantic
        if not findings:
            findings.append(
                {
                    "severity": "info",
                    "code": "AUDIT_COMPLETED",
                    "message": "Deterministic and semantic evidence audits completed without findings.",
                    "details": {
                        "evidence_count": len(inventory),
                        "publication_count": len(publications),
                    },
                }
            )
        self._persist(run_id, findings)
        return findings

    def _deterministic_audit(
        self,
        run_id: str,
        novelty: NoveltyResult,
        inventive_routes: list[InventiveStepOutput],
        value: ValueAnalyzerOutput,
    ) -> tuple[list[dict[str, Any]], set[str], list[dict[str, Any]]]:
        findings: list[dict[str, Any]] = []
        inventory: list[dict[str, Any]] = []
        publications: set[str] = set()
        with self.database.connect() as connection:
            run = connection.execute(
                "SELECT evaluation_date FROM idea_runs WHERE run_id = ?", (run_id,)
            ).fetchone()
            if run is None:
                raise KeyError(run_id)
            feature_rows = connection.execute(
                "SELECT feature_id,metadata_json FROM idea_features WHERE run_id = ?",
                (run_id,),
            ).fetchall()
            feature_count = len(feature_rows)
            feature_external = {}
            for feature in feature_rows:
                try:
                    metadata = json.loads(feature["metadata_json"] or "{}")
                except json.JSONDecodeError:
                    metadata = {}
                feature_external[feature["feature_id"]] = metadata.get("external_feature_id")
            documents = connection.execute(
                """SELECT d.document_id,d.publication_number,d.publication_date
                FROM run_documents rd JOIN patent_documents d ON d.document_id = rd.document_id
                WHERE rd.run_id = ? AND rd.deep_reviewed = 1 AND rd.screening_status = 'ANALYZED'""",
                (run_id,),
            ).fetchall()
            if len(novelty.matrices) != len(documents):
                findings.append(self._finding(
                    "critical", "NOVELTY_MATRIX_DOCUMENT_MISMATCH",
                    "Novelty matrix count does not match analyzed document count.",
                    {"matrix_count": len(novelty.matrices), "document_count": len(documents)},
                ))
            novelty_by_publication = {
                matrix.publication_number: {
                    mapping.feature_id: mapping for mapping in matrix.mappings
                }
                for matrix in novelty.matrices
            }
            if novelty.conclusion == "NOVEL" and len(documents) < self.minimum_deep_reviews:
                findings.append(self._finding(
                    "critical", "NOVELTY_REVIEW_MINIMUM_NOT_MET",
                    "NOVEL conclusion does not meet the configured deep-review minimum.",
                    {"actual": len(documents), "minimum": self.minimum_deep_reviews},
                ))
            elif len(documents) < self.minimum_deep_reviews:
                findings.append(self._finding(
                    "warning", "DEEP_REVIEW_MINIMUM_NOT_MET",
                    "Deep-review count is below the configured minimum.",
                    {"actual": len(documents), "minimum": self.minimum_deep_reviews},
                ))

            evaluation = self._parse_date(run["evaluation_date"])
            for document in documents:
                publications.add(document["publication_number"])
                matrix_mappings = novelty_by_publication.get(document["publication_number"])
                if matrix_mappings is None:
                    findings.append(self._finding(
                        "critical", "MISSING_NOVELTY_DOCUMENT_MATRIX",
                        f"Document {document['publication_number']} is absent from novelty matrices.", {},
                    ))
                    matrix_mappings = {}
                if not document["publication_date"]:
                    findings.append(self._finding(
                        "critical", "MISSING_PUBLICATION_DATE",
                        f"Document {document['publication_number']} has no publication date.",
                        {"document_id": document["document_id"]},
                    ))
                else:
                    try:
                        publication_date = self._parse_date(document["publication_date"])
                    except ValueError:
                        findings.append(self._finding(
                            "critical", "INVALID_PUBLICATION_DATE",
                            f"Document {document['publication_number']} has an invalid publication date.",
                            {"value": document["publication_date"]},
                        ))
                    else:
                        if publication_date > evaluation:
                            findings.append(self._finding(
                                "critical", "POST_EVALUATION_DOCUMENT",
                                f"Document {document['publication_number']} is after the evaluation date.",
                                {"publication_date": document["publication_date"]},
                            ))
                mappings = connection.execute(
                    "SELECT * FROM feature_mappings WHERE run_id = ? AND document_id = ?",
                    (run_id, document["document_id"]),
                ).fetchall()
                if len(mappings) != feature_count:
                    findings.append(self._finding(
                        "critical", "INCOMPLETE_FEATURE_MATRIX",
                        f"Document {document['publication_number']} has an incomplete feature matrix.",
                        {"expected": feature_count, "actual": len(mappings)},
                    ))
                for mapping in mappings:
                    try:
                        evidence_ids = json.loads(mapping["evidence_ids_json"])
                    except json.JSONDecodeError:
                        evidence_ids = None
                    if not isinstance(evidence_ids, list):
                        findings.append(self._finding(
                            "critical", "INVALID_EVIDENCE_LIST", "Feature mapping evidence list is invalid.",
                            {"mapping_id": mapping["mapping_id"]},
                        ))
                        continue
                    if mapping["coverage_status"] in {"DISCLOSED", "PARTIAL"} and not evidence_ids:
                        findings.append(self._finding(
                            "critical", "DISCLOSURE_WITHOUT_EVIDENCE",
                            "Disclosed or partial feature mapping has no evidence.",
                            {"mapping_id": mapping["mapping_id"]},
                        ))
                    external_id = feature_external.get(mapping["feature_id"])
                    matrix_mapping = matrix_mappings.get(external_id)
                    if (
                        matrix_mapping is None
                        or matrix_mapping.status != mapping["coverage_status"]
                        or set(matrix_mapping.evidence_ids) != set(evidence_ids)
                        or matrix_mapping.confidence != mapping["confidence"]
                    ):
                        findings.append(self._finding(
                            "critical", "NOVELTY_MATRIX_MAPPING_MISMATCH",
                            "Novelty matrix mapping does not match its durable feature mapping.",
                            {
                                "publication_number": document["publication_number"],
                                "feature_id": external_id,
                            },
                        ))
                    for evidence_id in evidence_ids:
                        evidence = connection.execute(
                            """SELECT * FROM evidence
                            WHERE evidence_id = ? AND run_id = ? AND document_id = ?""",
                            (evidence_id, run_id, document["document_id"]),
                        ).fetchone()
                        if evidence is None:
                            findings.append(self._finding(
                                "critical", "UNKNOWN_EVIDENCE",
                                f"Mapping cites missing or cross-document evidence {evidence_id}.",
                                {"mapping_id": mapping["mapping_id"]},
                            ))
                            continue
                        actual_hash = hashlib.sha256(
                            evidence["quote_text"].encode("utf-8")
                        ).hexdigest()
                        if actual_hash != evidence["content_hash"]:
                            findings.append(self._finding(
                                "critical", "EVIDENCE_HASH_MISMATCH",
                                f"Evidence {evidence_id} failed its content hash check.", {},
                            ))
                            continue
                        inventory.append(
                            {
                                "evidence_id": evidence_id,
                                "publication_number": document["publication_number"],
                                "feature_id": external_id,
                                "coverage_status": mapping["coverage_status"],
                                "section_type": evidence["section_type"],
                                "section_label": evidence["section_label"],
                                "quote_text": evidence["quote_text"],
                                "content_hash": evidence["content_hash"],
                            }
                        )
            persisted = connection.execute(
                "SELECT matrix_json FROM novelty_results WHERE run_id = ?", (run_id,)
            ).fetchone()
            expected_json = canonical_json(novelty.model_dump(mode="json"))
            if persisted is None or persisted["matrix_json"] != expected_json:
                findings.append(self._finding(
                    "critical", "NOVELTY_RESULT_MISMATCH",
                    "In-memory novelty result does not match the durable result.", {},
                ))
            persisted_routes = {
                row["result_json"]
                for row in connection.execute(
                    "SELECT result_json FROM inventive_routes WHERE run_id = ?", (run_id,)
                ).fetchall()
            }
            expected_routes = {
                canonical_json(route.model_dump(mode="json")) for route in inventive_routes
            }
            if persisted_routes != expected_routes:
                findings.append(self._finding(
                    "critical", "INVENTIVE_RESULTS_MISMATCH",
                    "In-memory inventive routes do not match durable routes.", {},
                ))
            persisted_value = connection.execute(
                "SELECT result_json FROM value_results WHERE run_id = ?", (run_id,)
            ).fetchone()
            expected_value = canonical_json(value.model_dump(mode="json"))
            if persisted_value is None or persisted_value["result_json"] != expected_value:
                findings.append(self._finding(
                    "critical", "VALUE_RESULT_MISMATCH",
                    "In-memory value result does not match the durable result.", {},
                ))
        deduplicated: dict[str, dict[str, Any]] = {}
        for item in inventory:
            evidence_id = item["evidence_id"]
            if evidence_id not in deduplicated:
                grouped = dict(item)
                grouped["feature_ids"] = [grouped.pop("feature_id")]
                deduplicated[evidence_id] = grouped
            elif item["feature_id"] not in deduplicated[evidence_id]["feature_ids"]:
                deduplicated[evidence_id]["feature_ids"].append(item["feature_id"])
        return list(deduplicated.values()), publications, findings

    @staticmethod
    def _parse_date(value: str) -> date:
        compact = value.strip().replace("/", "-")
        if len(compact) == 8 and compact.isdigit():
            compact = f"{compact[:4]}-{compact[4:6]}-{compact[6:]}"
        return date.fromisoformat(compact)

    @staticmethod
    def _finding(severity: str, code: str, message: str, details: dict) -> dict[str, Any]:
        return {"severity": severity, "code": code, "message": message, "details": details}

    def _persist(self, run_id: str, findings: list[dict[str, Any]]) -> None:
        with self.database.connect() as connection:
            exists = connection.execute(
                "SELECT COUNT(*) FROM audit_results WHERE run_id = ?", (run_id,)
            ).fetchone()[0]
            if exists:
                raise AgentExecutionError("audit results already exist for this run")
            timestamp = now_ms()
            for finding in findings:
                connection.execute(
                    """INSERT INTO audit_results(
                        audit_id,run_id,severity,code,message,details_json,created_at
                    ) VALUES(?,?,?,?,?,?,?)""",
                    (
                        str(uuid.uuid4()), run_id, finding["severity"], finding["code"],
                        finding["message"], canonical_json(finding.get("details", {})), timestamp,
                    ),
                )

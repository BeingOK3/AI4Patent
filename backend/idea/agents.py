from __future__ import annotations

import json
import re
import uuid
from typing import Any

from .agent_schemas import IdeaParserOutput, QueryPlannerOutput
from .database import Database, canonical_json, now_ms
from .model_client import AgentCallResult, StructuredModelClient


IDEA_PARSER_PROMPT = """
You are patent-idea-parser. Parse only the supplied invention text. Identify the technical
domains, application scenario, objective technical problem, claimed effects, subject types,
and a complete ordered F1..Fn list of required technical features. Mark directly quoted or
faithfully extracted features as explicit and provide exact zero-based character start/end
offsets whose text exactly equals the input slice. Mark normalization and inference honestly.
Do not search, assess novelty, cite patents, or invent missing implementation details.
"""


QUERY_PLANNER_PROMPT = """
You are patent-query-planner. Build executable Chinese and English patent search queries from
the supplied validated idea analysis. Include at least one technical-means query and one
problem/effect query. Use real terms, synonyms, broader terms and optional IPC/CPC candidates.
Do not use placeholders. Do not execute a search and do not claim any result was found.
"""


PLACEHOLDER_PATTERN = re.compile(
    r"\{[^{}]+\}|\[(?:填入|待定|关键词|keyword|placeholder)[^\]]*\]|<[^<>]+>|\b(?:TODO|TBD)\b",
    flags=re.IGNORECASE,
)


class AgentExecutionError(RuntimeError):
    pass


class IdeaAgentService:
    def __init__(self, database: Database, model: StructuredModelClient):
        self.database = database
        self.model = model

    async def parse_idea(self, run_id: str, idea_text: str) -> IdeaParserOutput:
        result = await self.call_agent(
            run_id,
            "patent-idea-parser",
            system_prompt=IDEA_PARSER_PROMPT,
            input_payload={"idea_text": idea_text},
            input_size=len(idea_text),
        )
        output = result.output
        if not isinstance(output, IdeaParserOutput):
            raise AgentExecutionError("idea parser returned wrong validated model")
        self._validate_source_spans(idea_text, output)
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT COUNT(*) FROM idea_features WHERE run_id = ?", (run_id,)
            ).fetchone()[0]
            if existing:
                raise AgentExecutionError("validated idea features already exist for this run")
            for ordinal, feature in enumerate(output.features, start=1):
                span = feature.source_span
                connection.execute(
                    """
                    INSERT INTO idea_features(
                        feature_id,run_id,ordinal,feature_text,source_type,
                        source_start,source_end,metadata_json
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        f"{run_id}:{feature.feature_id}",
                        run_id,
                        ordinal,
                        feature.feature_text,
                        feature.source_type,
                        span.start if span else None,
                        span.end if span else None,
                        canonical_json(
                            {
                                "external_feature_id": feature.feature_id,
                                "required": feature.required,
                                "source_text": span.text if span else None,
                            }
                        ),
                    ),
                )
        return output

    async def plan_queries(
        self, run_id: str, idea: IdeaParserOutput, *, per_query_limit: int
    ) -> QueryPlannerOutput:
        result = await self.call_agent(
            run_id,
            "patent-query-planner",
            system_prompt=QUERY_PLANNER_PROMPT,
            input_payload={
                "idea_analysis": idea.model_dump(mode="json"),
                "per_query_result_limit": per_query_limit,
            },
            input_size=len(canonical_json(idea.model_dump(mode="json"))),
        )
        output = result.output
        if not isinstance(output, QueryPlannerOutput):
            raise AgentExecutionError("query planner returned wrong validated model")
        for query in output.queries:
            if PLACEHOLDER_PATTERN.search(query.query_text):
                raise AgentExecutionError(f"query contains placeholder: {query.query_id}")
        with self.database.connect() as connection:
            existing = connection.execute(
                "SELECT COUNT(*) FROM search_queries WHERE run_id = ?", (run_id,)
            ).fetchone()[0]
            if existing:
                raise AgentExecutionError("validated search queries already exist for this run")
            timestamp = now_ms()
            for query in output.queries:
                connection.execute(
                    """
                    INSERT INTO search_queries(
                        query_id,run_id,round_number,query_type,language,query_text,rationale,created_at
                    ) VALUES(?,?,?,?,?,?,?,?)
                    """,
                    (
                        f"{run_id}:{query.query_id}",
                        run_id,
                        query.round_number,
                        query.query_type,
                        query.language,
                        query.query_text,
                        query.rationale,
                        timestamp,
                    ),
                )
        return output

    async def call_agent(
        self,
        run_id: str,
        agent_name: str,
        *,
        system_prompt: str,
        input_payload: dict[str, Any],
        input_size: int,
    ) -> AgentCallResult:
        call_id = str(uuid.uuid4())
        timestamp = now_ms()
        try:
            result = await self.model.complete(
                agent_name,
                system_prompt=system_prompt,
                input_payload=input_payload,
            )
        except Exception as exc:
            with self.database.connect() as connection:
                connection.execute(
                    """
                    INSERT INTO tool_calls(
                        call_id,run_id,step_name,provider,operation,request_json,
                        response_summary_json,result_count,duration_ms,status,
                        error_code,error_message,created_at
                    ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        call_id,
                        run_id,
                        agent_name,
                        self.model.settings.provider,
                        "structured_completion",
                        canonical_json({"agent": agent_name, "input_characters": input_size}),
                        None,
                        0,
                        None,
                        "ERROR",
                        type(exc).__name__,
                        str(exc)[:1000],
                        timestamp,
                    ),
                )
            raise
        with self.database.connect() as connection:
            connection.execute(
                """
                INSERT INTO tool_calls(
                    call_id,run_id,step_name,provider,operation,request_json,
                    response_summary_json,result_count,duration_ms,status,
                    error_code,error_message,created_at
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    call_id,
                    run_id,
                    agent_name,
                    result.model,
                    "structured_completion",
                    canonical_json({"agent": agent_name, "input_characters": input_size}),
                    canonical_json(
                        {
                            "attempts": result.attempts,
                            "usage": result.usage,
                            "response_id": result.response_id,
                        }
                    ),
                    1,
                    result.duration_ms,
                    "SUCCESS",
                    None,
                    None,
                    timestamp,
                ),
            )
        return result

    @staticmethod
    def _validate_source_spans(idea_text: str, output: IdeaParserOutput) -> None:
        for feature in output.features:
            span = feature.source_span
            if span is None:
                continue
            if span.end > len(idea_text):
                raise AgentExecutionError(f"feature span outside input: {feature.feature_id}")
            if idea_text[span.start : span.end] != span.text:
                raise AgentExecutionError(f"feature span does not match input: {feature.feature_id}")

"""
AWS Bedrock Integration Module for DevWatch.
Leverages Amazon Bedrock LLMs (Titan, Claude, Nova) to generate AI developer insights,
sprint risk assessments, and repository health summaries.
"""

import json
import os
from typing import Any, Dict, Optional
import boto3
from botocore.exceptions import BotoCoreError, ClientError


class BedrockAnalyzer:
    """AWS Bedrock client for AI-powered GitHub repository intelligence."""

    DEFAULT_MODEL = "us.amazon.nova-micro-v1:0"


    def __init__(self, region_name: Optional[str] = None, model_id: Optional[str] = None):
        """
        Initialize AWS Bedrock runtime client.
        
        :param region_name: AWS region (defaults to AWS_REGION env var or 'us-east-1').
        :param model_id: Bedrock model ID (defaults to 'amazon.titan-text-express-v1').
        """
        self.region = region_name or os.getenv("AWS_REGION", "us-east-1")
        self.model_id = model_id or os.getenv("BEDROCK_MODEL_ID", self.DEFAULT_MODEL)
        
        try:
            self.client = boto3.client("bedrock-runtime", region_name=self.region)
            self.available = True
        except Exception as err:
            self.client = None
            self.available = False
            self.error_msg = str(err)

    def _prepare_payload(self, prompt: str) -> str:
        """Format request payload based on target Bedrock LLM family."""
        model_id = self.model_id.lower()

        if "titan" in model_id:
            return json.dumps({
                "inputText": prompt,
                "textGenerationConfig": {
                    "maxTokenCount": 750,
                    "temperature": 0.4,
                    "topP": 0.9,
                }
            })
        elif "claude" in model_id:
            return json.dumps({
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": 750,
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            })
        elif "nova" in model_id:
            return json.dumps({
                "inferenceConfig": {
                    "max_new_tokens": 750,
                    "temperature": 0.4
                },
                "messages": [
                    {"role": "user", "content": [{"text": prompt}]}
                ]
            })
        else:
            # Standard generic text payload
            return json.dumps({
                "inputText": prompt,
                "maxTokens": 750
            })

    def _parse_response(self, response: Dict[str, Any]) -> str:
        """Extract output text from Bedrock model response body."""
        body = json.loads(response.get("body").read().decode("utf-8"))
        model_id = self.model_id.lower()

        if "titan" in model_id:
            results = body.get("results", [])
            if results:
                return results[0].get("outputText", "").strip()
        elif "claude" in model_id:
            content = body.get("content", [])
            if content:
                return content[0].get("text", "").strip()
        elif "nova" in model_id:
            output = body.get("output", {})
            message = output.get("message", {})
            content = message.get("content", [])
            if content:
                return content[0].get("text", "").strip()

        # Fallback dictionary extraction
        for key in ["outputText", "completion", "text", "generation"]:
            if key in body:
                return str(body[key]).strip()

        return str(body)

    def generate_ai_insights(self, report_data: Dict[str, Any]) -> str:
        """
        Generate AI executive summary and recommendations based on DevWatch metrics.
        
        :param report_data: Compiled DevWatch analysis dictionary from RepoAnalyzer.
        :return: Markdown formatted AI assessment string.
        """
        if not self.available or not self.client:
            return "⚠️ AWS Bedrock is not configured or available. Skipping AI analysis."

        repo = report_data.get("repository", {})
        health = report_data.get("health", {})
        commit_m = report_data.get("commit_metrics", {})
        churn = report_data.get("code_churn", {})
        contrib_m = report_data.get("contributors", {})
        prs_m = report_data.get("pull_requests", {})
        change_intel = report_data.get("change_intelligence", {})

        prompt = f"""
You are an expert Principal Software Architect analyzing a GitHub repository using DevWatch analytics.

Repository: {repo.get('full_name')}
Language: {repo.get('language')} | Stars: {repo.get('stars')} | Open Issues: {repo.get('open_issues')}
DevWatch Health Score: {health.get('score')}/100 ({health.get('rating')})

Key Metrics:
- Total Commits (Window): {commit_m.get('total_commits')} ({commit_m.get('commits_per_day_avg')} commits/day)
- Code Churn: +{churn.get('additions_sampled')} additions / -{churn.get('deletions_sampled')} deletions (Ratio: {churn.get('churn_ratio')})
- Contributor Risk: {contrib_m.get('bus_factor_risk')} (Top committer share: {contrib_m.get('top_contributor_share_pct')}%)
- PR Velocity: {prs_m.get('merged')}/{prs_m.get('total_prs')} merged ({prs_m.get('merge_success_rate_pct')}%) with avg merge time of {prs_m.get('avg_merge_hours')} hours
- Engineering Areas Affected: {change_intel.get('areas')}
- Code Warnings: {health.get('insights')}

Please provide a concise, professional, 3-bullet executive evaluation covering:
1. Team Velocity & Sprint Health
2. Risk Analysis (Bus Factor / Code Churn / Test Coverage)
3. Actionable Engineering Recommendation for Maintainers
        """.strip()

        try:
            payload = self._prepare_payload(prompt)
            response = self.client.invoke_model(
                modelId=self.model_id,
                contentType="application/json",
                accept="application/json",
                body=payload
            )
            return self._parse_response(response)
        except ClientError as err:
            error_code = err.response.get("Error", {}).get("Code", "Unknown")
            if error_code == "AccessDeniedException":
                return f"⚠️ AccessDenied for Bedrock model '{self.model_id}'. Enable model access in AWS Bedrock Console."
            return f"⚠️ AWS Bedrock API Error ({error_code}): {err}"
        except BotoCoreError as err:
            return f"⚠️ AWS BotoCore Error: {err}"
        except Exception as err:
            return f"⚠️ Bedrock Generation Failed: {err}"

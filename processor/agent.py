import logging
import json
import os
import yaml
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List, Optional, Any

from google import genai
from google.genai import types as genai_types
from dotenv import load_dotenv

# Import our local get_db
from processor.db import get_db

load_dotenv()
logger = logging.getLogger(__name__)

# Constants
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GEMINI_MODEL = "gemini-2.5-flash"
MODEL_TEMPERATURE = 0.1
MAX_FEEDBACK_LOOPS = 3
MIN_CONFIDENCE_THRESHOLD = 0.7

PROJECT_ROOT = Path(__file__).parent.parent.parent
PROMPTS_FILE = "prompts.yaml"

def load_prompts(prompts_file: str = PROMPTS_FILE) -> dict:
    prompts_path = PROJECT_ROOT / prompts_file
    if not prompts_path.exists():
        raise FileNotFoundError(f"Prompts file not found: {prompts_path}")
    with open(prompts_path, 'r') as f:
        prompts = yaml.safe_load(f)
    return prompts

def get_prompt(prompt_name: str) -> str:
    prompts = load_prompts()
    if prompt_name not in prompts:
        raise ValueError(f"Prompt '{prompt_name}' not found in prompts file")
    return prompts[prompt_name]['prompt']


@dataclass
class ConfigValidationConfig:
    api_key: Optional[str] = None
    model: Optional[str] = None
    temperature: Optional[float] = None
    max_feedback_loops: Optional[int] = None
    min_confidence: Optional[float] = None

    def __post_init__(self):
        if self.api_key is None:
            self.api_key = GOOGLE_API_KEY
        if self.model is None:
            self.model = GEMINI_MODEL
        if self.temperature is None:
            self.temperature = MODEL_TEMPERATURE
        if self.max_feedback_loops is None:
            self.max_feedback_loops = MAX_FEEDBACK_LOOPS
        if self.min_confidence is None:
            self.min_confidence = MIN_CONFIDENCE_THRESHOLD


class ConfigurationValidationAgent:
    def __init__(self, config: Optional[ConfigValidationConfig] = None):
        self.config = config or ConfigValidationConfig()
        try:
            http_options = genai_types.HttpOptions(timeout=300)
            self.client = genai.Client(
                api_key=self.config.api_key,
                http_options=http_options,
            )
        except Exception:
            self.client = genai.Client(api_key=self.config.api_key)
        logger.info("ConfigurationValidationAgent initialized (multi-agent LLM)")

    async def validate_configuration(
        self, manufacturer: str, brand: Optional[str], series_name: str, specifications: Dict[str, Any]
    ) -> Dict:
        logger.info(f"Validating configuration: {manufacturer}/{brand}/{series_name}")
        try:
            series_data = await self._get_series_parameters(manufacturer, brand, series_name)
            if not series_data:
                return await self._series_not_found(manufacturer, brand, series_name)
            final_report = await self._run_validation_loop(series_data, specifications)
            return self._build_response(series_data, specifications, final_report)
        except Exception as e:
            logger.error(f"Configuration validation error: {e}")
            return {
                "is_valid": False,
                "error_type": "internal_error",
                "errors": [str(e)],
                "manufacturer": manufacturer,
                "brand": brand,
                "series_name": series_name,
            }

    async def get_available_configurations(self, manufacturer: str, brand: Optional[str] = None) -> Dict:
        logger.info(f"Getting available configurations: {manufacturer}/{brand}")
        try:
            db = get_db()
            series_collection = db.get_collection("series")
            parameters_collection = db.get_collection("parameters")
            query = {"manufacturer": manufacturer}
            if brand:
                query["brand"] = brand
            series_list = list(series_collection.find(query))
            configurations = []
            for series in series_list:
                series_id = series["_id"]
                parameters = list(parameters_collection.find({"series_id": series_id}, {"_id": 0, "parameter_name": 1, "is_numeric": 1, "options": 1}).limit(5))
                configurations.append({
                    "series_id": str(series_id),
                    "series_name": series["series_name"],
                    "category": series.get("category", "UNKNOWN"),
                    "brand": series.get("brand"),
                    "parameter_count": series.get("parameter_count", 0),
                    "parameters": [{"name": p["parameter_name"], "is_numeric": p.get("is_numeric", False), "option_count": len(p.get("options", []))} for p in parameters],
                })
            return {"status": "success", "configurations": configurations, "count": len(configurations)}
        except Exception as e:
            logger.error(f"Error getting configurations: {e}")
            return {"status": "error", "error": str(e), "configurations": []}

    async def _get_series_parameters(self, manufacturer: str, brand: Optional[str], series_name: str) -> Optional[Dict]:
        try:
            db = get_db()
            series_collection = db.get_collection("series")
            parameters_collection = db.get_collection("parameters")
            optional_parameters_collection = db.get_collection("optional_parameters")
            prices_collection = db.get_collection("prices")
            query = {"manufacturer": manufacturer, "series_name": series_name}
            if brand:
                query["brand"] = brand
            series = series_collection.find_one(query)
            if not series:
                return None
            series_id = series["_id"]
            parameters = list(parameters_collection.find({"series_id": series_id}, {"_id": 0, "series_id": 0, "file_id": 0}))
            optional_parameters = list(optional_parameters_collection.find({"series_id": series_id}, {"_id": 0, "series_id": 0, "file_id": 0}))
            prices = prices_collection.find_one({"series_id": series_id}, {"_id": 0, "series_id": 0, "file_id": 0})
            return {
                "series_id": str(series_id),
                "series_name": series["series_name"],
                "manufacturer": series["manufacturer"],
                "brand": series.get("brand"),
                "category": series.get("category", "UNKNOWN"),
                "summary": series.get("summary", ""),
                "parameters": parameters,
                "optional_parameters": optional_parameters,
                "prices": prices or {},
            }
        except Exception as e:
            logger.error(f"Error getting series parameters: {e}")
            return None

    async def _series_not_found(self, manufacturer: str, brand: Optional[str], series_name: str) -> Dict:
        try:
            db = get_db()
            series_collection = db.get_collection("series")
            query = {"manufacturer": manufacturer}
            if brand:
                query["brand"] = brand
            similar_series = list(series_collection.find(query, {"series_name": 1, "category": 1, "brand": 1}).limit(5))
            suggestions = [{"series_name": s["series_name"], "category": s.get("category", "UNKNOWN"), "brand": s.get("brand")} for s in similar_series]
            return {
                "is_valid": False, "error_type": "series_not_found",
                "errors": [f"Series '{series_name}' not found for manufacturer '{manufacturer}'" + (f" and brand '{brand}'" if brand else "")],
                "suggestions": suggestions, "manufacturer": manufacturer, "brand": brand, "series_name": series_name,
            }
        except Exception as e:
            return {"is_valid": False, "error_type": "series_not_found", "errors": [f"Series '{series_name}' not found"], "manufacturer": manufacturer, "brand": brand, "series_name": series_name}

    async def _run_validation_loop(self, series_data: Dict, specifications: Dict[str, Any]) -> Dict:
        feedback_context = ""
        best_report: Optional[Dict] = None
        best_confidence = 0.0
        for iteration in range(1, self.config.max_feedback_loops + 1):
            validation_report = await self._llm_validate(series_data, specifications, feedback_context)
            current_confidence = validation_report.get("confidence", 0.0)
            if current_confidence > best_confidence:
                best_confidence = current_confidence
                best_report = validation_report
            feedback_result = await self._llm_feedback(series_data, specifications, validation_report)
            feedback_confidence = feedback_result.get("confidence", 0.0)
            should_revalidate = feedback_result.get("should_revalidate", False)
            issues = feedback_result.get("issues_found", [])
            if not should_revalidate or (feedback_confidence >= self.config.min_confidence and not should_revalidate):
                best_report = validation_report
                break
            if iteration < self.config.max_feedback_loops:
                feedback_context = f"FEEDBACK FROM PREVIOUS VALIDATION (iteration {iteration}):\nThe feedback reviewer found the following issues with your previous report.\nPlease correct these issues in your new validation.\n\nIssues found:\n"
                for issue in issues:
                    feedback_context += f"- [{issue.get('issue_type', 'unknown')}] {issue.get('description', '')}\n  Affected: {issue.get('affected_field', 'N/A')}\n  Correction: {issue.get('suggested_correction', 'N/A')}\n"
                feedback_context += f"\nFeedback summary: {feedback_result.get('feedback_summary', '')}\n"
        return best_report or validation_report

    async def _llm_validate(self, series_data: Dict, specifications: Dict[str, Any], feedback_context: str = "") -> Dict:
        try:
            prompt_template = get_prompt("configuration_llm_validation")
            formatted_prompt = prompt_template.format(
                series_name=series_data["series_name"], manufacturer=series_data["manufacturer"],
                brand=series_data.get("brand") or "N/A", category=series_data.get("category", "UNKNOWN"),
                series_summary=series_data.get("summary") or "No summary available.",
                base_parameters=json.dumps(series_data["parameters"], indent=2, default=str),
                optional_parameters=json.dumps(series_data["optional_parameters"], indent=2, default=str),
                prices=json.dumps(series_data.get("prices", {}), indent=2, default=str),
                specifications=json.dumps(specifications, indent=2), feedback_context=feedback_context,
            )
            response = self.client.models.generate_content(
                model=self.config.model, contents=formatted_prompt,
                config={"temperature": self.config.temperature, "response_mime_type": "application/json"},
            )
            return self._parse_json_response(response.text, "validation")
        except Exception as e:
            return {
                "is_valid": False, "confidence": 0.0, "reasoning": f"LLM validation failed: {e}",
                "matched_specifications": [], "missing_required_parameters": [], "invalid_specifications": [],
                "pricing": {"base_price": 0.0, "optional_price": 0.0, "total_price": 0.0, "price_breakdown": [], "pricing_notes": [f"Validation error: {e}"]},
                "warnings": [],
            }

    async def _llm_feedback(self, series_data: Dict, specifications: Dict[str, Any], validation_report: Dict) -> Dict:
        try:
            prompt_template = get_prompt("configuration_validation_feedback")
            formatted_prompt = prompt_template.format(
                series_name=series_data["series_name"], manufacturer=series_data["manufacturer"],
                brand=series_data.get("brand") or "N/A", category=series_data.get("category", "UNKNOWN"),
                series_summary=series_data.get("summary") or "No summary available.",
                base_parameters=json.dumps(series_data["parameters"], indent=2, default=str),
                optional_parameters=json.dumps(series_data["optional_parameters"], indent=2, default=str),
                prices=json.dumps(series_data.get("prices", {}), indent=2, default=str),
                specifications=json.dumps(specifications, indent=2), validation_report=json.dumps(validation_report, indent=2, default=str),
            )
            response = self.client.models.generate_content(
                model=self.config.model, contents=formatted_prompt,
                config={"temperature": self.config.temperature, "response_mime_type": "application/json"},
            )
            return self._parse_json_response(response.text, "feedback")
        except Exception as e:
            return {"is_correct": True, "confidence": 0.0, "issues_found": [], "feedback_summary": f"Feedback agent error: {e}", "should_revalidate": False}

    def _build_response(self, series_data: Dict, specifications: Dict[str, Any], validation_report: Dict) -> Dict:
        is_valid = validation_report.get("is_valid", False)
        pricing = validation_report.get("pricing", {})
        base_response = {
            "is_valid": is_valid, "manufacturer": series_data["manufacturer"], "brand": series_data.get("brand"),
            "series_name": series_data["series_name"], "category": series_data.get("category"),
            "confidence": validation_report.get("confidence", 0.0), "reasoning": validation_report.get("reasoning", ""),
        }
        if is_valid:
            base_response.update({
                "specifications": specifications, "total_price": pricing.get("total_price", 0.0),
                "base_price": pricing.get("base_price", 0.0), "optional_price": pricing.get("optional_price", 0.0),
                "price_breakdown": pricing.get("price_breakdown", []), "matched_specifications": validation_report.get("matched_specifications", []),
                "notes": pricing.get("pricing_notes", []), "warnings": validation_report.get("warnings", []),
            })
        else:
            base_response.update({
                "error_type": "invalid_specifications", "errors": sorted([f"Missing required parameter: '{item.get('parameter', 'unknown')}'" for item in validation_report.get("missing_required_parameters", [])] + [f"Invalid specification '{item.get('user_spec', 'unknown')}': {item.get('reason', 'invalid value')}" for item in validation_report.get("invalid_specifications", [])]),
                "missing_required": validation_report.get("missing_required_parameters", []),
                "invalid_selections": validation_report.get("invalid_specifications", []), "warnings": validation_report.get("warnings", []),
            })
        return base_response

    def _parse_json_response(self, text: str, context: str = "") -> Dict:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            import re
            json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
            if json_match:
                try:
                    return json.loads(json_match.group(1).strip())
                except json.JSONDecodeError:
                    pass
            return {
                "is_valid": False, "confidence": 0.0, "reasoning": f"Failed to parse {context} response",
                "matched_specifications": [], "missing_required_parameters": [], "invalid_specifications": [],
                "pricing": {"base_price": 0.0, "optional_price": 0.0, "total_price": 0.0, "price_breakdown": [], "pricing_notes": ["Parse error"]},
                "warnings": [],
            }

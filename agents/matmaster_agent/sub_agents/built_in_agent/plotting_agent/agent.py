import json
import logging
import re
from typing import Dict, Any, Optional
from pydantic import PrivateAttr

from google.adk.agents import BaseAgent
from dp.agent.adapter.adk import CalculationMCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPServerParams

from agents.matmaster_agent.constant import MATMASTER_AGENT_NAME, BohriumStorge, CURRENT_ENV
from agents.matmaster_agent.llm_config import MatMasterLlmConfig
from agents.matmaster_agent.sub_agents.built_in_agent.plotting_agent.utils import peek_file
from agents.matmaster_agent.sub_agents.built_in_agent.plotting_agent.prompt import build_coding_prompt
from agents.matmaster_agent.sub_agents.built_in_agent.plotting_agent.tools import PLOTTING_TASK_TOOL_SCHEMA
from agents.matmaster_agent.core_agents.public_agents.sync_agent import BaseSyncAgentWithToolValidator

# Correct URL Configuration
if CURRENT_ENV in ['test', 'uat']:
    PLOTTING_SERVER_URL = 'http://qpus1389933.bohrium.tech:50005/mcp'
else:
    PLOTTING_SERVER_URL = 'http://qpus1389933.bohrium.tech:50002/mcp'

class PlottingAgent(BaseSyncAgentWithToolValidator):
    # Define private attribute to store tools hidden from LLM
    _plotting_toolset: Any = PrivateAttr() 
    
    def __init__(self, llm_config=None):
        model = llm_config.default_litellm_model if llm_config else MatMasterLlmConfig.gemini_2_5_pro
        
        # Store Toolset
        mcp_params = StreamableHTTPServerParams(url=PLOTTING_SERVER_URL)
        plotting_toolset = CalculationMCPToolset(
            connection_params=mcp_params,
            storage=BohriumStorge
        )
        
        # Store privately so we can use it manually
        self._plotting_toolset = plotting_toolset

        super().__init__(
            model=model,
            name="plotting_agent",
            description="Agent for scientific plotting.",
            instruction="Generate Python code to visualize data.",
            tools=[self._plotting_toolset],  # RESTORE THE TOOLSET HERE
            supervisor_agent=MATMASTER_AGENT_NAME,
        )

    def __call__(self, file_path: str, user_request: str) -> Dict[str, Any]:
        """Main entry point."""
        try:
            file_info = peek_file(file_path, n_lines=50)
            return self._execute_plotting_workflow(file_path, user_request, file_info)
        except Exception as e:
            logging.error(f"Plotting Agent Failed: {e}")
            return {'status': 'error', 'message': str(e)}

    def _execute_plotting_workflow(self, file_path: str, user_request: str, file_info: Dict):
        max_retries = 3
        retry_count = 0
        current_file_info = file_info
        
        while retry_count <= max_retries:
            prompt = build_coding_prompt(user_request, current_file_info)
            try:
                # Real LLM Call
                codes = self._generate_codes_with_llm(prompt)
                if not codes.get('extractor_code'):
                    raise ValueError("LLM failed to generate extractor code")

                # Real MCP Execution
                result = self._execute_plotting_task_via_mcp(
                    codes['extractor_code'], 
                    codes.get('plotter_code', ''), 
                    file_path
                )
                
                if result.get('status') == 'success':
                    return result
                else:
                    # Retry logic
                    error_logs = result.get('logs', 'Unknown error')
                    logging.warning(f"Plotting failed (Attempt {retry_count}): {error_logs}")
                    current_file_info = self._update_file_info_with_error(current_file_info, error_logs)
                    retry_count += 1
            except Exception as e:
                logging.error(f"Workflow Exception: {e}")
                return {'status': 'error', 'message': str(e)}
                
        return {'status': 'error', 'message': f'Max retries exceeded.'}

    def _generate_codes_with_llm(self, prompt: str) -> Dict[str, str]:
        """
        Calls the LLM and extracts code from either Tool Calls or JSON.
        """
        try:
            # 1. Call Model
            response = self.model.generate_content(prompt)
            
            # DEBUG LOG: See what the LLM actually said
            content_str = response.text if hasattr(response, 'text') else str(response)
            logging.info(f"[PlottingAgent] Raw LLM Response: {content_str[:500]}...")

            # 2. Strategy A: Check for Tool Calls (Priority)
            tool_calls = getattr(response, 'tool_calls', [])
            
            # Gemini/Vertex AI specific structure check
            if not tool_calls and hasattr(response, 'candidates'):
                 candidate = response.candidates[0]
                 parts = getattr(candidate, 'content', {}).get('parts', [])
                 tool_calls = [part for part in parts if hasattr(part, 'function_call')]

            if tool_calls:
                logging.info("[PlottingAgent] Detected Tool Call")
                # Handle both object-style and dict-style access
                call = tool_calls[0]
                if hasattr(call, 'function_call'):
                    args = call.function_call.args
                else:
                    args = getattr(call, 'args', {})

                # Ensure args is a dict
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except:
                        logging.error("[PlottingAgent] Failed to parse tool args string")
                        args = {}
                elif not isinstance(args, dict):
                    # Try converting to dict if it's a protobuf map (common in Google ADK)
                    if hasattr(args, 'items'):
                        args = dict(args.items())
                    else:
                        args = {}

                return {
                    'extractor_code': args.get('extractor_code', ''),
                    'plotter_code': args.get('plotter_code', '')
                }

            # 3. Strategy B: Fallback to JSON Text Parsing
            logging.info("[PlottingAgent] No Tool Call, trying JSON parse")
            content = content_str
            json_match = re.search(r'```(?:json)?\s*({.*?})\s*```', content, re.DOTALL)
            if not json_match:
                json_match = re.search(r'(\{.*\})', content, re.DOTALL)
            
            if json_match:
                return json.loads(json_match.group(1))

            logging.warning("[PlottingAgent] Failed to extract code from response")
            return {}

        except Exception as e:
            logging.error(f"[PlottingAgent] LLM Generation Error: {e}")
            return {}

    def _execute_plotting_task_via_mcp(self, extractor_code: str, plotter_code: str, file_path: str) -> Dict[str, Any]:
        """Execute the tool found in self.tools"""
        
        # Search in self.tools first (populated by super().__init__)
        target_tool = next((t for t in self.tools if getattr(t, 'name', '') == "execute_plotting_task"), None)
        
        # Fallback to private toolset if self.tools is empty/mangled
        if not target_tool:
            candidates = []
            if isinstance(self._plotting_toolset, list):
                candidates = self._plotting_toolset
            elif hasattr(self._plotting_toolset, 'tools'):
                candidates = self._plotting_toolset.tools
            else:
                candidates = [self._plotting_toolset]
            target_tool = next((t for t in candidates if getattr(t, 'name', '') == "execute_plotting_task"), None)

        if not target_tool:
            return {'status': 'error', 'message': 'Tool execute_plotting_task not found'}
            
        try:
            logging.info(f"[PlottingAgent] Executing tool with file: {file_path}")
            # Execute
            return target_tool.func(
                extractor_code=extractor_code,
                plotter_code=plotter_code,
                file_path=file_path
            )
        except Exception as e:
            return {'status': 'error', 'message': str(e), 'logs': str(e)}

    def _update_file_info_with_error(self, file_info: Dict, error_logs: str) -> Dict:
        new_info = file_info.copy()
        if 'metadata' not in new_info: new_info['metadata'] = {}
        new_info['metadata']['last_error'] = error_logs
        # Add context to help LLM fix it
        new_info['error_context'] = f"\nPREVIOUS CODE FAILED.\nERROR LOGS:\n{error_logs}\nFix the code based on these logs."
        return new_info


def init_plotting_agent(llm_config=None) -> BaseAgent:
    """Initialize Plotting Agent"""
    return PlottingAgent(llm_config)
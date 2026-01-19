def build_coding_prompt(user_request: str, file_preview_info: dict) -> str:
    """
    Builds a coding prompt for generating extractor and plotter code based on user request and file info.
    
    Args:
        user_request: The user's plotting request
        file_preview_info: Information about the file obtained from utils.peek_file
        
    Returns:
        Formatted prompt string for the LLM
    """
    preview = file_preview_info['preview']
    metadata = file_preview_info['metadata']
    
    system_prompt = """
You are an expert Python programmer. Your task is to visualize the provided data.

**INSTRUCTIONS:**
1. Analyze the file preview.
2. Write `extractor_code` to read the file and create a DataFrame named `data_df`.
3. Write `plotter_code` to visualize `data_df`.
4. **SUBMIT** these codes by calling the `execute_plotting_task` tool.

**CRITICAL RULES:**
- **DO NOT** leave arguments empty. You MUST write actual Python code.
- **DO NOT** output Markdown explanation. Just call the tool.
- In `extractor_code`, use pandas.
- In `plotter_code`, use matplotlib/seaborn and save to the filename specified in the wrapper (or just `plt.savefig`).

**Example of Tool Call (Mental Sandbox):**
execute_plotting_task(
    extractor_code="import pandas as pd\\ndf = pd.read_csv('...')", 
    plotter_code="import matplotlib.pyplot as plt\\n...", 
    file_path="..."
)
"""

    file_info_prompt = f"""
File Information:
- Extension: {metadata['extension']}
- Encoding: {metadata['encoding']}
- Line Count: {metadata['line_count']}
- Size: {metadata['size']} bytes
- Detected Delimiter: {metadata['delimiter']}
- Header: {metadata['header'] if metadata['header'] else 'No clear header detected'}

File Preview (first {min(50, metadata['line_count'])} lines):
```
{preview}
```

User Request: {user_request}
"""
    
    return f"{system_prompt}\n\n{file_info_prompt}"
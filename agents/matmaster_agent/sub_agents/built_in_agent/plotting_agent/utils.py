import os
import csv
from typing import Dict, Any
from pathlib import Path

def detect_encoding_from_file(file_path: str) -> str:
    """Detect encoding by trying a priority list."""
    encodings = ['utf-8', 'utf-8-sig', 'gbk', 'gb18030', 'big5', 'latin-1']
    for enc in encodings:
        try:
            with open(file_path, 'r', encoding=enc) as f:
                f.read(2048)
            return enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    return 'utf-8' # Fallback

def peek_file(file_path: str, n_lines: int = 50) -> Dict[str, Any]:
    """Reads the first n_lines of a file with robust encoding handling."""
    file_path_obj = Path(file_path)
    
    # 1. Detect Encoding (No chardet)
    encoding = detect_encoding_from_file(file_path)
    
    # 2. Read Lines
    lines = []
    try:
        with open(file_path, 'r', encoding=encoding, errors='replace') as f:
            for i, line in enumerate(f):
                if i >= n_lines:
                    break
                lines.append(line.rstrip('\n\r'))
    except Exception as e:
        return {'preview': f"Error reading file: {str(e)}", 'metadata': {}}
    
    # 3. Detect Delimiter (Simple Heuristic)
    delimiter = None
    header = []
    if file_path_obj.suffix.lower() in ['.csv', '.txt', '.dat', '.tsv'] and lines:
        sample_line = lines[0]
        delimiters = [',', '\t', ';', '|']
        counts = {d: sample_line.count(d) for d in delimiters if sample_line.count(d) > 0}
        
        if counts:
            delimiter = max(counts, key=counts.get)
            try:
                header = next(csv.reader([sample_line], delimiter=delimiter))
            except:
                pass
    
    return {
        'preview': '\n'.join(lines),
        'metadata': {
            'encoding': encoding,
            'extension': file_path_obj.suffix,
            'line_count': len(lines),
            'delimiter': delimiter,
            'header': header,
            'size': os.path.getsize(file_path) if os.path.exists(file_path) else 0
        }
    }
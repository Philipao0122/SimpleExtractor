import os
import sys
from pathlib import Path

def main():
    try:
        # Get the directory of the current script
        script_dir = Path(__file__).parent
        input_file = script_dir / 'extracted_texts.txt'
        
        # Read the input file
        with open(input_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Process the content (this is where you'd add your Gemini API integration)
        # For now, we'll just return the content as is
        print("Respuesta del modelo:")
        print(content)
        
        return 0
        
    except Exception as e:
        print(f"Error: {str(e)}", file=sys.stderr)
        return 1

if __name__ == '__main__':
    sys.exit(main())

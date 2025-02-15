import datetime
import glob
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import subprocess
import sys
import os
from typing import Optional

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

url = "https://llmfoundry.straive.com/openai/v1/chat/completions"

api_key = os.getenv("AIPROXY_TOKEN")


async def identify_task(task: str) -> dict:
    try:
        functions = [
            {
                "name": "run_datagen",
                "description": "Run datagen.py script with user email as argument",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "script_path":{
                            "type": "string",
                            "description": "Full Path to the script file"
                        },
                        "email": {
                            "type": "string",
                            "description": "User's email address"
                        }
                    },
                    "required": ["script_path", "email"]
                }
            },
            {
                "name": "format_markdown",
                "description": "Format markdown file using prettier",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Path to the markdown file to format"
                        },
                        "library":{
                            "type": "string",
                            "description": "The library used for formatting",
                            "default": "prettier"
                        },
                        "version":{
                            "type": "string",
                            "description": "Version of the library used for formatting",
                            "default": "3.4.2"
                        }
                    },
                    "required": ["file_path", "library", "version"]
                }
            },
            {
                "name": "count_specific_day",
                "description": "Count occurrences of a specific day in a list of dates",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input_file": {
                            "type": "string",
                            "description": "Path to input dates file"
                        },
                        "output_file": {
                            "type": "string",
                            "description": "Path to output count file"
                        },
                        "day_to_count": {
                            "type": "string",
                            "description": "Name of the day to count (e.g., 'monday', 'tuesday', etc.). If not specified or invalid, returns empty string",
                            "enum": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", ""]
                        }
                    },
                    "required": ["input_file", "output_file", "day_to_count"]
                }
            },
            {
                "name": "sort_contacts",
                "description": "Sort contacts by last_name and first_name",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input_file": {
                            "type": "string",
                            "description": "Path to input contacts JSON."
                        },
                        "output_file": {
                            "type": "string",
                            "description": "Path to output sorted JSON. If not specified or invalid or without extension, returns empty string"
                        }
                    },
                    "required": ["input_file", "output_file"]
                }
            },
            {
                "name": "get_recent_logs",
                "description": "Get first lines of 10 most recent log files",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "logs_directory": {
                            "type": "string",
                            "description": "Directory containing log files."
                        },
                        "output_file": {
                            "type": "string",
                            "description": "Path to output file. If not specified or invalid or without extension, returns empty string"
                        }
                    },
                    "required": ["logs_directory", "output_file"]
                }
            },
            {
                "name": "create_markdown_index",
                "description": "Create index of H1 headers from markdown files",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "docs_directory": {
                            "type": "string",
                            "description": "Directory containing markdown files"
                        },
                        "output_file": {
                            "type": "string",
                            "description": "Path to output index JSON"
                        }
                    },
                    "required": ["docs_directory", "output_file"]
                }
            },
            {
                "name": "extract_email_sender",
                "description": "Extract sender's email address from email content",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input_file": {
                            "type": "string",
                            "description": "Path to email content file"
                        },
                        "output_file": {
                            "type": "string",
                            "description": "Path to output email address file"
                        }
                    },
                    "required": ["input_file", "output_file"]
                }
            },
            {
                "name": "extract_card_number",
                "description": "Extract credit card number from image",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "image_file": {
                            "type": "string",
                            "description": "Path to credit card image"
                        },
                        "output_file": {
                            "type": "string",
                            "description": "Path to output card number file"
                        }
                    },
                    "required": ["image_file", "output_file"]
                }
            },
            {
                "name": "find_similar_comments",
                "description": "Find most similar pair of comments using embeddings",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input_file": {
                            "type": "string",
                            "description": "Path to comments file"
                        },
                        "output_file": {
                            "type": "string",
                            "description": "Path to output similar comments file"
                        }
                    },
                    "required": ["input_file", "output_file"]
                }
            },
            {
                "name": "calculate_gold_ticket_sales",
                "description": "Calculate total sales for Gold ticket type",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "database_file": {
                            "type": "string",
                            "description": "Path to SQLite database file"
                        },
                        "output_file": {
                            "type": "string",
                            "description": "Path to output sales total file"
                        }
                    },
                    "required": ["database_file", "output_file"]
                }
            }
        ]  

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        messages=[
                {"role": "system", "content": "You are a helpful assistant that translates user queries into english, if the query is not in english and processes user queries and maps them to appropriate function calls."},
                {"role": "user", "content": task}
        ]

        payload = {
            "model": "o3-mini",
            "messages": messages,
            "functions": functions,
            "function_call": "auto"
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url=url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            function_call = data['choices'][0]['message'].get('function_call')
            function_name = function_call["name"]
            arguments = json.loads(function_call['arguments'])
            return {"name": function_name, "arguments": arguments}


    except httpx.HTTPStatusError as http_err:
        raise HTTPException(status_code=http_err.response.status_code, 
                          detail=f"HTTP error occurred: {http_err}")
    except Exception as err:
        raise HTTPException(status_code=500, 
                          detail=f"An error occurred: {str(err)}")

async def install_requirements(requirements: list):
    try:
        for req in requirements:
            if req and req.strip():
                subprocess.check_call([sys.executable, "-m", "pip", "install", req.strip()])
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, 
                          detail=f"Failed to install requirements: {str(e)}")

async def execute_code(code: str) -> str:
    try:
        with open("temp_code.py", "w") as f:
            f.write(code)
        
        result = subprocess.run([sys.executable, "temp_code.py"], 
                              capture_output=True, 
                              text=True)
        
        os.remove("temp_code.py")
        
        if result.returncode != 0:
            raise HTTPException(status_code=400, 
                              detail=f"Task execution failed: {result.stderr}")
        
        return result.stdout
    except Exception as e:
        raise HTTPException(status_code=500, 
                          detail=f"Code execution error: {str(e)}")

async def run_datagen(script_path: str, email: str):
    try:
        if script_path == "" or not script_path:
            raise HTTPException(status_code=400, detail=f"Error downloading files: script path not provided")
        if email == "" or not email:
            raise HTTPException(status_code=400, detail=f"Error downloading files: email not provided")
        command = [
            "uv", "run", 
            f"{script_path}", 
            f"{email}"
        ]
        result = subprocess.run(command, check=True, text=True, capture_output=True)
        return {
            "status": "success",
            "message": f"downloaded input files",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

def count_specific_day(input_file_path: str, output_file_path: str, day_name: str):

    if "data" not in output_file_path:
        raise HTTPException(status_code=400, detail=f"Not configured to process files outside '/data'")
    if day_name == "" or not day_name:
        raise HTTPException(status_code=400, detail=f"Invalid day") 

    day_mapping = {
        'monday': 0,
        'tuesday': 1,
        'wednesday': 2,
        'thursday': 3,
        'friday': 4,
        'saturday': 5,
        'sunday': 6
    }
    
    # Validate input
    day_name = day_name.lower()
    if day_name not in day_mapping:
        raise HTTPException(status_code=400, 
                detail="Bad Request response: Invalid day")

    try:
        with open(input_file_path, 'r') as f:
            dates = f.readlines()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found at {input_file_path}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid input file '{input_file_path}': {str(e)}")
    
    day_count = sum(1 for date in dates 
                    if datetime.strptime(date.strip(), '%Y-%m-%d').weekday() == day_mapping[day_name])
    
    output_file = output_file_path
    with open(output_file, 'a') as f:
        f.write(str(day_count)+ '\n')
    
    return {
        "status": "success",
        "message": f"updated file: {output_file}",
    }

def sort_contacts(input_file_path: str, output_file_path):
    if output_file_path == "" or not output_file_path:
        raise HTTPException(status_code=400, detail=f"invalid output filename") 
    if "data" not in input_file_path:
        raise HTTPException(status_code=400, detail=f"Not configured to process files outside '/data'")
    
    if "data" not in output_file_path:
        raise HTTPException(status_code=400, detail=f"Not configured to process files outside '/data'")

    try:
        with open(input_file_path, 'r') as f:
            contacts = json.load(f)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found at {input_file_path}")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in file '{input_file_path}': {str(e)}")

    sorted_contacts = sorted(contacts, 
                           key=lambda x: (x['last_name'], x['first_name']))
    
    with open(output_file_path, 'a') as f:
        if f.tell() != 0:
            f.write('\n')
        json.dump(sorted_contacts, f, indent=2)

def get_recent_logs(input_file_path: str, output_file_path: str):

    if output_file_path == "" or not output_file_path:
        raise HTTPException(status_code=400, detail=f"invalid output filename") 

    if not os.path.exists(input_file_path):
        raise HTTPException(status_code=404, detail=f"Logs directory {input_file_path} not found")

    try:
        log_files = glob.glob(os.path.join(input_file_path, '*.log'))       
        if not log_files:
            raise HTTPException(status_code=404, detail="No .log files found in /data/logs/")

        recent_logs = sorted(log_files, 
                           key=os.path.getmtime, 
                           reverse=True)[:10]
        
        with open(output_file_path, 'w') as out:
            for log in recent_logs:
                try:
                    with open(log, 'r') as f:
                        first_line = f.readline().strip()
                        out.write(f"{first_line}\n")
                except IOError as e:
                    print(f"Error reading file {log}: {str(e)}")
                except UnicodeDecodeError as e:
                    print(f"Error decoding file {log}: {str(e)}")

    except IOError as e:
        raise HTTPException(status_code=500, 
                          detail=f"Error writing to output file: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, 
                          detail=f"Unexpected error: {str(e)}")

async def format_markdown(file_path: str, library: str, version: str):
    try:
        if "data" not in file_path:
            raise HTTPException(status_code=400, detail=f"not configured to process files outside '/data'")
        
        if library == "" or not library:
            raise HTTPException(status_code=400, detail=f"Error formatting file: library not provided")
       
        library_with_version = f"{library}@{version}"

        run_command(f"npm install {library_with_version}")
        run_command(f"npx {library_with_version} --check {file_path}")
        run_command(f"npx {library_with_version} --write {file_path}")
        
        return {
            "status": "success",
            "message": f"Formatted file: {file_path}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
def run_command(command):
    try:
        result = subprocess.run(command, shell=True, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Error: {result.stderr}")
        return result.stdout
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/run")
async def run_task(task: str):
    try:
        llm_response = await identify_task(task)
        function_name = llm_response["name"]
        function_args = llm_response["arguments"]
        func = globals().get(function_name)
        if not func or not callable(func):
            raise HTTPException(status_code=400, 
                            detail="Bad Request response: undefined function")
        result = await func(**function_args)
        return result
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, 
                          detail=f"Internal server error: {str(e)}")

@app.get("/read")
async def read_file(path: str):
    full_path = os.path.abspath(path)
    print(f"Requested path: {path}")
    print(f"Absolute path exists: {os.path.exists(full_path)}, {full_path}")
    
    try:
        with open(full_path, "r") as f:
            return f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="")
    except Exception as e:
        raise HTTPException(status_code=500, detail="")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
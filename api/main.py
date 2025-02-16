import asyncio
from datetime import datetime
import glob
import json
from pathlib import Path
import re
import sqlite3
import aiofiles
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

BASE_DIR = Path("/data").resolve()

async def is_file_empty_or_nonexistent(file_path: str) -> bool:
    try:
        async with aiofiles.open(file_path, 'r') as file:
            first_character = await file.read(1)
            return not bool(first_character)
    except FileNotFoundError:
        return True

def validate_path(file_path: str) -> bool:
    resolved_path = Path(file_path).resolve()
    return BASE_DIR in resolved_path.parents

def is_directory_exists(directory_path: str) -> bool:
    return os.path.isdir(directory_path)

async def identify_task(task: str) -> dict:
    try:

        async with aiofiles.open("./functions.txt", 'r') as f:
            content = await f.read()
        functions = json.loads(content)

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
        raise HTTPException(status_code=500, 
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
        if not script_path:
            raise HTTPException(status_code=400, detail="Error downloading files: script path not provided")
        if not email:
            raise HTTPException(status_code=400, detail="Error downloading files: email not provided")
        
        command = ["uv", "run", script_path, email]
        
        proc = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        
        if proc.returncode != 0:
            raise HTTPException(status_code=500, detail=f"Script error: {stderr.decode().strip()}")
        
        return {
            "status": "success",
            "message": "downloaded input files",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
    
def parse_date(date_str):
    date_formats = [
        "%Y-%m-%d",
        "%b %d, %Y",
        "%d-%b-%Y",
        "%Y/%m/%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y/%m/%d",
        "%b %d, %Y %H:%M:%S",
        "%d-%b-%Y %H:%M:%S",
        "%b-%d-%Y"
    ]
    for fmt in date_formats:
        try:
            return datetime.strptime(date_str.strip(), fmt)
        except ValueError:
            continue
    return None

async def count_specific_day(input_file_path: str, output_file_path: str, day_to_count: str):

    if not validate_path(input_file_path) or not validate_path(output_file_path):
        raise HTTPException(status_code=400, detail=f"Not configured to process files outside '/data'")
    
    if not day_to_count:
        raise HTTPException(status_code=400, detail=f"Invalid day") 
    
    is_valid_output_file = await is_file_empty_or_nonexistent(output_file_path)

    if not is_valid_output_file :
        raise HTTPException(status_code=400, detail="Overwriting file is not allowed. Use a different name for the output file")

    day_mapping = {
        'monday': 0,
        'tuesday': 1,
        'wednesday': 2,
        'thursday': 3,
        'friday': 4,
        'saturday': 5,
        'sunday': 6
    }
    
    day_to_count = day_to_count.lower()
    if day_to_count not in day_mapping:
        raise HTTPException(status_code=400, detail="Bad Request response: Invalid day")

    try:
        async with aiofiles.open(input_file_path, 'r') as f:
            content = await f.read()
        dates = content.splitlines()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found at {input_file_path}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid input file '{input_file_path}': {str(e)}")
    
    
    day_count = sum(1 for date in dates if (parsed_date := parse_date(date)) and parsed_date.weekday() == day_mapping[day_to_count])

    
    async with aiofiles.open(output_file_path, 'w') as f:
        await f.write(str(day_count))
    
    return {
        "status": "success",
        "message": f"file created at: {output_file_path}",
    }

async def sort_contacts(input_file_path: str, output_file_path):

    if not output_file_path:
        raise HTTPException(status_code=400, detail=f"invalid output filename") 
    
    if not validate_path(input_file_path) or not validate_path(output_file_path):
        raise HTTPException(status_code=400, detail=f"Not configured to process files outside '/data'")

    is_valid_output_file = await is_file_empty_or_nonexistent(output_file_path)

    if not is_valid_output_file :
        raise HTTPException(status_code=400, detail="Overwriting file is not allowed. Use a different name for the output file")  

    try:
        async with aiofiles.open(input_file_path, 'r') as f:
            content = await f.read()
        contacts = json.loads(content)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"File not found at {input_file_path}")
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Invalid JSON in file '{input_file_path}': {str(e)}")

    sorted_contacts = sorted(contacts, 
                           key=lambda x: (x['last_name'], x['first_name']))
    
    async with aiofiles.open(output_file_path, 'w') as f:
        await f.write(json.dumps(sorted_contacts))

    return {
        "status": "success",
        "message": f"file created at: {output_file_path}",
    }

async def get_recent_logs(logs_directory: str, output_file_path: str):

    if not output_file_path:
        raise HTTPException(status_code=400, detail=f"invalid output filename") 
    
    if not validate_path(logs_directory) or not validate_path(output_file_path):
        raise HTTPException(status_code=400, detail=f"Not configured to process files outside '/data'")

    if not is_directory_exists(logs_directory):
        raise HTTPException(status_code=404, detail=f"Logs directory {logs_directory} not found")
    
    is_valid_output_file = await is_file_empty_or_nonexistent(output_file_path)

    if not is_valid_output_file :
        raise HTTPException(status_code=400, detail="Overwriting file is not allowed. Use a different name for the output file")

    try:
        log_files = await asyncio.to_thread(
            glob.glob, os.path.join(logs_directory, '*.log')
        )      
        if not log_files:
            raise HTTPException(status_code=404, detail=f"No .log files found in {logs_directory}")

        recent_logs = await asyncio.to_thread(
            sorted, log_files, key=os.path.getmtime, reverse=True
        )
        recent_logs = recent_logs[:10]
        
        async with aiofiles.open(output_file_path, 'w') as out:
            for log in recent_logs:
                try:
                    async with aiofiles.open(log, 'r') as f:
                        first_line = await f.readline()
                        first_line = first_line.strip()
                        await out.write(f"{first_line}\n")
                except IOError as e:
                    print(f"Error reading file {log}: {str(e)}")
                except UnicodeDecodeError as e:
                    print(f"Error decoding file {log}: {str(e)}")

        return {
            "status": "success",
            "message": f"file created at: {output_file_path}",
        }

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

async def create_markdown_index(docs_directory: str, output_file_path):

    if "data" not in output_file_path:
        raise HTTPException(status_code=400, detail=f"Not configured to process files outside '/data'")
    
    if output_file_path == "" or not output_file_path:
        raise HTTPException(status_code=400, detail=f"invalid output filename")
    
    if os.path.exists(output_file_path) and os.path.getsize(output_file_path) > 0:
        raise HTTPException(status_code=400, detail="Overwritting file is not allowed. use a differnt name for output file")
    
    if "data" not in docs_directory:
        raise HTTPException(status_code=400, detail=f"Not configured to process files outside '/data'")

    if not os.path.exists(docs_directory):
        raise HTTPException(status_code=404, detail=f"Docs directory {docs_directory} not found")
    
    try:
        docs_path = Path(docs_directory)
        index = {}
        
        for md_file in docs_path.glob('**/*.md'):
            relative_path = str(md_file.relative_to(docs_path))
            with open(md_file, 'r') as f:
                content = f.read()
                h1_match = re.search(r'^#\s+(.+)$', content, re.MULTILINE)
                if h1_match:
                    index[relative_path] = h1_match.group(1)
        
        with open(output_file_path, 'w') as f:
            json.dump(index, f)
        return {
            "status": "success",
            "message": f"file created at: {output_file_path}",
        } 
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

async def extract_email_sender(input_file_path: str, output_file_path):

    if output_file_path == "" or not output_file_path:
        raise HTTPException(status_code=400, detail=f"invalid output filename") 
    if "data" not in input_file_path:
        raise HTTPException(status_code=400, detail=f"Not configured to process files outside '/data'")
    
    if "data" not in output_file_path:
        raise HTTPException(status_code=400, detail=f"Not configured to process files outside '/data'")

    if os.path.exists(output_file_path) and os.path.getsize(output_file_path) > 0:
        raise HTTPException(status_code=400, detail="Overwritting file is not allowed. use a differnt name for output file")   

    try:
        with open(input_file_path, 'r') as file:
            email_content = file.read()

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        messages=[
                {"role": "system", "content": "You are a helpful assistant. extract only the sender/from email address(eg., name@xmail.com, yyyy@gmail.com), from the given email"},
                {"role": "user", "content": email_content}
        ]

        payload = {
            "model": "o3-mini",
            "messages": messages
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url=url, json=payload, headers=headers, timeout=30)
            response.raise_for_status()
            data = response.json()

            sender_email = data['choices'][0]['message'].get('content')        
            with open(output_file_path, 'w') as file:
               file.write(sender_email)

            return {
            "status": "success",
            "message": f"file created at: {output_file_path}",
        } 
        
    except httpx.HTTPStatusError as http_err:
        raise HTTPException(status_code=500, 
                          detail=f"HTTP error occurred: {http_err}")   
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="")
    except Exception as e:
        raise HTTPException(status_code=500, detail="")   

async def calculate_gold_ticket_sales(db_file_path: str, output_file_path):

    if "data" not in db_file_path:
        raise HTTPException(status_code=400, detail=f"not configured to process files outside '/data'")
    
    if "data" not in output_file_path:
        raise HTTPException(status_code=400, detail=f"Not configured to process files outside '/data'")
    
    if output_file_path == "" or not output_file_path:
        raise HTTPException(status_code=400, detail=f"invalid output filename")
    
    if os.path.exists(output_file_path) and os.path.getsize(output_file_path) > 0:
        raise HTTPException(status_code=400, detail="Overwritting file is not allowed. use a differnt name for output file")
    
    try:
        conn = sqlite3.connect(db_file_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT SUM(units * price)
            FROM tickets
            WHERE type = 'Gold'
        """)
        
        total = cursor.fetchone()[0] 
        total = total if total is not None else 0

        with open(output_file_path, 'w') as f:
            f.write(str(total))

        return {
            "status": "success",
            "message": f"file created at: {output_file_path}",
        }     
    except sqlite3.Error as e:
        raise HTTPException(status_code=500, 
                          detail=f"Internal server error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, 
                          detail=f"Internal server error: {str(e)}")
    finally:
        if 'conn' in locals() and conn:
            conn.close()


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
        async with aiofiles.open(full_path, mode="r") as f:
            return await f.read()
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="")
    except Exception as e:
        raise HTTPException(status_code=500, detail="")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
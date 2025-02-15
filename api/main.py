import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx
import openai
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

os.environ["AIPROXY_TOKEN"] = ""
api_key = os.getenv("AIPROXY_TOKEN")

with open('prompt.txt', 'r') as file:
    prompt = file.read()

async def identify_task(task: str) -> dict:
    try:

        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "code_response",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "requirements": {
                            "type": "array",
                            "items": {
                                "type": "string"
                            }
                        },
                        "code": {
                            "type": "string"
                        }
                    },
                    "required": ["requirements", "code"],
                    "additionalProperties": False
                }
            }
        }

        functions = [
            {
                "name": "run_datagen",
                "description": "Run datagen.py script with user email as argument",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path":{
                            "type": "string",
                            "description": "Path to the script file"
                        },
                        "email": {
                            "type": "string",
                            "description": "User's email address"
                        }
                    },
                    "required": ["path", "email"]
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
                "name": "count_wednesdays",
                "description": "Count Wednesdays in a list of dates",
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
                        }
                    },
                    "required": ["input_file", "output_file"]
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
                            "description": "Path to input contacts JSON"
                        },
                        "output_file": {
                            "type": "string",
                            "description": "Path to output sorted JSON"
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
                            "description": "Directory containing log files"
                        },
                        "output_file": {
                            "type": "string",
                            "description": "Path to output file"
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
                {"role": "system", "content": "You are a helpful assistant that processes user queries and maps them to appropriate function calls."},
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

@app.post("/run")
async def run_task(task: str):
    try:
        llm_response = await identify_task(task)
        return{"output": llm_response}
        await install_requirements(llm_response["requirements"])
        result = await execute_code(llm_response["code"])
        return {"status": "success", "output": result}
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, 
                          detail=f"Internal server error: {str(e)}")

@app.get("/read")
async def read_file(path: str):
    try:
        with open(path, "r") as f:
            content = f.read()
        return {"status": "success", "content": content}
    except FileNotFoundError:
        raise HTTPException(status_code=404, 
                          detail="File not found")
    except Exception as e:
        raise HTTPException(status_code=500, 
                          detail=f"Error reading file: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
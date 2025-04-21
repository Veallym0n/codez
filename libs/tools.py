import os
import glob
import tempfile
import fnmatch
import asyncio

class TerminalTools:

    auto_approve = False

    cwd = os.getcwd()

    tools = [
        {
            'type': 'function',
            'function': {
            "name": "approve",
            "description": "Ask for user confirmation before performing actions",
            "parameters": {
                "type": "object",
                "properties": {
                "content": {
                    "type": "string",
                    "description": "The action description to be approved"
                    }
                },
                "required": ["content"]
            }
            }
        },
        {
            'type': 'function',
            'function': {
            "name": "list_files",
            "description": "List files in the current directory including subdirectories",
            "parameters": {
                "type": "object",
                "properties": {
                "pattern": {
                    "type": "string",
                    "description": "Optional glob pattern to filter files"
                    }
                }
            }
            }
        },
        {
            'type': 'function',
            'function': {
            "name": "read_file",
            "description": "Read the content of a file",
            "parameters": {
                "type": "object",
                "properties": {
                "filename": {
                    "type": "string",
                    "description": "Name of the file to read"
                    }
                },
                "required": ["filename"]
            }
            }
        },
        {
            'type': 'function',
            'function': {
            "name": "write_file",
            "description": "Write content to a file",
            "parameters": {
                "type": "object",
                "properties": {
                "filename": {
                    "type": "string",
                    "description": "Name of the file to write"
                },
                "content": {
                    "type": "string",
                    "description": "Content to write to the file"
                    }
                },
                "required": ["filename", "content"]
            }
            }
        },
        {
            'type': 'function',
            'function': {
            "name": "git_diff",
            "description": "Compare files using git diff",
            "parameters": {
                "type": "object",
                "properties": {
                "filename": {
                    "type": "string",
                    "description": "Name of the file to check diff"
                    }
                },
                "required": ["filename"]
            }
            }
        },
        {
            'type': 'function',
            'function': {
            "name": "search_files",
            "description": "Search files for code snippets including subdirectories",
            "parameters": {
                "type": "object",
                "properties": {
                "pattern": {
                    "type": "string", 
                    "description": "File pattern to search in (e.g., '*.py')"
                    },
                "query": {
                    "type": "string",
                    "description": "Text to search for"
                    }
                },
                "required": ["pattern", "query"]
            }
            }
        },
        {
            'type': 'function',
            'function': {
            "name": "execute_command",
            "description": "Execute a system command using bash -lc ",
            "parameters": {
                "type": "object",
                "properties": {
                "command": {
                    "type": "string",
                    "description": "Command to execute"
                    }
                },
                "required": ["command"]
            }
            }
        },
        {
            'type': 'function',
            'function': {
                "name": "patch_file",
                "description": "Apply a patch to a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "filename": {
                            "type": "string",
                            "description": "Name of the file to patch"
                            },
                        "patch_content": {
                            "type": "string",
                            "description": "The patch content to apply"
                            }
                    },
                    "required": ["filename", "patch_content"]
                }
            }
        },
        {
            'type': 'function',
            'function': {
                "name": "get_current_time",
                "description": "Get the current system time in ISO 8601 format",
                "parameters": {
                    "type": "object",
                    "properties": {}
                }
            }
        },
        {
            'type': 'function',
            'function': {
                'name': 'search_engine',
                'description': 'Search the Internet content using exa.ai. You will analyze the user\'s query and find the correct keywords for searching.',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'keyword': {
                            'type': 'string',
                            'description': 'Keyword to search for'
                        }
                    },
                    'required': ['keyword']
                }
            }
        },
        {
            'type': 'function',
            'function': {
                'name': 'fetch_url',
                'description': 'Fetch the content of a URL using HTTP GET method',
                'parameters': {
                    'type': 'object',
                    'properties': {
                        'url': {
                            'type': 'string',
                            'description': 'URL to fetch'
                        }
                    },
                    'required': ['url']
                }
            }
        }
    ]

    @staticmethod
    async def approve(content):
        print(f"\n[APPROVAL NEEDED] {content}")
        if TerminalTools.auto_approve:
            print("Auto-approval is enabled. Proceeding without user confirmation.")
            return True
        response = input("Do you approve this action? [Yes/No]: ").strip().lower()
        return response in ["yes", "y"]

    @staticmethod
    async def list_files(pattern="*"):
        # Use recursive glob to include subdirectories
        if pattern:
            return glob.glob(pattern, recursive=True)
        
        # If no pattern specified, list all files including in subdirectories
        all_files = []
        for root, _, files in os.walk('.'):
            for file in files:
                all_files.append(os.path.join(root, file))
        return all_files

    @staticmethod
    async def read_file(filename):
        try:
            with open(filename, 'r', encoding='utf-8') as file:
                return file.read()
        except Exception as e:
            return f"Error reading file: {str(e)}"

    @staticmethod
    async def write_file(filename, content):
        approved = await TerminalTools.approve(f"Writing to file {filename}")
        if not approved:
            return "Write operation cancelled by user."
        
        try:
            # Ensure directory exists
            real_filename = os.path.abspath(filename)
            pathfolder = os.path.dirname(real_filename)
            os.makedirs(pathfolder, exist_ok=True)
            print(f"Writing to {real_filename}")
            with open(real_filename, 'w+', encoding='utf-8') as file:
                file.write(content)
            return f"Successfully wrote to {filename}"
        except Exception as e:
            return f"Error writing to file: {str(e)}"
    
    @staticmethod
    async def git_diff(filename):
        try:
            proc = await asyncio.create_subprocess_exec(
                'git', 'diff', filename, 
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            return stdout.decode() if stdout else "No differences or not a git repository."
        except Exception as e:
            return f"Error executing git diff: {str(e)}"

    @staticmethod
    async def search_files(pattern, query):
        results = {}
        # Find all files in current directory and subdirectories that match pattern
        for root, _, files in os.walk('.'):
            for file in files:
                file_path = os.path.join(root, file)
                if fnmatch.fnmatch(file, pattern):
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            content = f.read()
                            if query in content:
                                lines = content.split('\n')
                                matching_lines = []
                                for i, line in enumerate(lines):
                                    if query in line:
                                        start = max(0, i - 2)
                                        end = min(len(lines), i + 3)
                                        context = lines[start:end]
                                        matching_lines.append({
                                            'line_number': i + 1,
                                            'context': '\n'.join(context)
                                        })
                                results[file_path] = matching_lines
                    except Exception:
                        pass
        return results
    
    @staticmethod
    async def execute_command(command):
        approved = await TerminalTools.approve(f"Executing command: {command}")
        if not approved:
            return "Command execution cancelled by user."
        
        try:
            proc = await asyncio.create_subprocess_shell(
                f"bash -lc '{command}'",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            return f"Exit code: {proc.returncode}\nOutput: {stdout.decode()}\nErrors: {stderr.decode()}"
        except Exception as e:
            return f"Error executing command: {str(e)}"
    
    @staticmethod
    async def patch_file(filename, patch_content):
        approved = await TerminalTools.approve(f"Applying patch to file {filename}")
        if not approved:
            return "Patch operation cancelled by user."
        
        try:
            # Write patch to a temporary file
            with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
                temp_path = temp_file.name
                temp_file.write(patch_content)
            
            # Apply the patch using the patch command
            proc = await asyncio.create_subprocess_exec(
                'patch', filename, temp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            # Clean up the temporary file
            os.unlink(temp_path)
            
            if proc.returncode == 0:
                return f"Successfully patched {filename}\n{stdout.decode()}"
            else:
                return f"Error applying patch: {stderr.decode()}"
        except Exception as e:
            return f"Error patching file: {str(e)}"

    @staticmethod
    async def get_current_time():
        import datetime
        current_time = datetime.datetime.now().isoformat()
        return current_time


    @staticmethod
    async def search_engine(keyword):
        from duckduckgo_search import DDGS
        initArguments = {}
        if any(os.environ.get(p) for p in ['HTTP_PROXY', 'HTTPS_PROXY']):
            initArguments['proxy'] = os.environ.get('HTTPS_PROXY')
        ddgs = DDGS(**initArguments)
        return ddgs.text(keyword, max_results=20)

    @staticmethod
    async def fetch_url(url):
        import httpx
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                if response.status_code == 200:
                    return response.text
                else:
                    return f"Error fetching URL: {response.status_code}"
        except Exception as e:
            return f"Error fetching URL: {str(e)}"






    @staticmethod
    async def execute(name, args):
        '''这个不是函数，这个是正统的函数调用'''
        method = getattr(TerminalTools, name, None)
        if method and callable(method):
            try:
                return await method(**args)
            except Exception as e:
                raise ValueError(f"Error executing function {name} with args {args}, error: {str(e)}")
        else:
            raise ValueError(f"Function {name} not found")



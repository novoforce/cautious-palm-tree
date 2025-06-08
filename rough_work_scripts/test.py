import asyncio
# Assuming the ToolboxClient class definition you provided is in a file 
# named 'toolbox_mcp.py' in the same directory or accessible in PYTHONPATH.
# If it's part of an installed package 'toolbox_core', then the original import is fine.
# Given the prompt "here is the code of toolbox mcp:", we'll assume 'toolbox_mcp.py'.
# from toolbox_mcp import ToolboxClient 
from toolbox_core import ToolboxClient

async def main():
    # Replace with the actual URL where your Toolbox service is running.
    # The example URL "https://toolbox-254584089613.us-central1.run.app/"
    # must be an active Toolbox service endpoint for this code to work.
    toolbox_service_url = "https://toolbox-254584089613.us-central1.run.app/"
    # For local testing, you might use something like "http://localhost:5000"

    async with ToolboxClient(toolbox_service_url) as toolbox:
        try:
            print(f"Fetching available tools from the default toolset at {toolbox_service_url}...")
            
            # The ToolboxClient does not have a 'list_tools' method.
            # To get a list of tool names, load a toolset (e.g., the default one)
            # and then extract the names from the loaded tools.
            # This will load all ToolboxTool objects from the default toolset.
            loaded_tools = await toolbox.load_toolset('my-toolset') 
            # print("Loaded tools:",loaded_tools[0].__name__)
            # print('dir:>',dir(loaded_tools[0]))
            # print('p:>',loaded_tools[0]._params)
            print("Loaded tools from the default toolset:",loaded_tools)

        except Exception as e:
            print(f"An error occurred: {e}")
            print("Please check if the Toolbox service is running and accessible at the specified URL.")
            print("If the default toolset requires specific authentication or parameters for loading,")
            print("they might need to be provided to toolbox.load_toolset().")


if __name__ == "__main__":
    asyncio.run(main())
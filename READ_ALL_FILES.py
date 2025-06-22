import os

def read_all_files(root_dir, exclude_files=None, exclude_dirs=None):
    if exclude_files is None:
        exclude_files = ['.pyc', '.json', '.png', '.pptx', '.env', '.gitignore', 'dockerfile']
    if exclude_dirs is None:
        exclude_dirs = ['__pycache__', 'env', '.git']

    all_content = []

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Exclude directories
        dirnames[:] = [d for d in dirnames if d not in exclude_dirs]

        for filename in filenames:
            # Exclude files
            if any(filename.lower() == ext for ext in exclude_files) or \
               any(filename.endswith(ext) for ext in exclude_files):
                continue

            # Get the full file path
            file_path = os.path.join(dirpath, filename)
            relative_path = os.path.relpath(file_path, root_dir)

            try:
                with open(file_path, 'r', encoding='utf-8') as file:
                    file_content = file.read()
                    all_content.append(f"File: {relative_path}\n{file_content}\n")
            except UnicodeDecodeError:
                print(f"Could not read file {file_path}: Not a text file or not UTF-8 encoded.")
            except Exception as e:
                print(f"Could not read file {file_path}: {e}")

    return ''.join(all_content)

def export_to_txt(content, output_file):
    try:
        with open(output_file, 'w', encoding='utf-8') as file:
            file.write(content)
        print(f"Content successfully exported to {output_file}")
    except Exception as e:
        print(f"Could not write to file {output_file}: {e}")

# Example usage
if __name__ == "__main__":
    root_directory = '.'  # Root directory of the project
    output_file = 'READ_ALL_FILES_output.txt'  # Name of the output file
    exclude_files = ['.pyc', '.json', '.png', '.pptx', '.env', '.gitignore', 'dockerfile', output_file, 'READ_ALL_FILES.py','requirements.txt']

    content = read_all_files(root_directory, exclude_files=exclude_files)
    export_to_txt(content, output_file)

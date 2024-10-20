import os
import zipfile

def zip_directory(root_dir, zip_filename, include_dirs):
    if os.path.exists(zip_filename):
        print(f"{zip_filename} already exists...")
        os.remove(zip_filename)

    with zipfile.ZipFile(zip_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(root_dir):
            exclude = True
            if root in include_dirs:
                for file in files:
                    print(root, dirs, file)
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, root_dir)
                    zipf.write(file_path, arcname)

if __name__ == "__main__":
    root_dir = '.'  
    zip_filename = 'sunscan_backend_source.zip' 
    include_dirs = [
        './app',
        './webapp/dist',
        './webapp/dist/assets'
    ]
    
    zip_directory(root_dir, zip_filename, include_dirs)
    print(f"Archive {zip_filename} ok.")

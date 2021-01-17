import os, tempfile;
tempdir = tempfile.gettempdir()

for filename in os.listdir(tempdir):
    path = os.path.join(tempdir, filename)
    if os.path.isfile(path):
        print(f"=================== {filename} =================")
        with open(path) as f: 
            print(f.read())


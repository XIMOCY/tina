from typing import Union,Generator
import importlib
from ..core.processFiles import fileToTxtByExten

def readLoogText(path:str = None,URL:str = None) -> Union[Generator,list[str]]:
    if path:
        return fileToTxtByExten(path, isClean=True, isSegments=True, n=100, step=None, is_yield=False)
    elif URL:
        urllib_request = importlib.import_module('urllib.request')
        urlopen = urllib_request.urlopen
        URLError = urllib_request.URLError
        try:
            response = urlopen(URL)
            content = response.read()
            file_path = os.path.join(os.getcwd(),'temp.pdf')
            with open(file_path, 'wb') as f:
                f.write(content)
            return fileToTxtByExten(file_path, isClean=True, isSegments=True, n=100, step=None, is_yield=False)
        except URLError as e:
            print(f"Error: {e}")

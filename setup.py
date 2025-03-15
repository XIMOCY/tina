from setuptools import setup, find_packages

setup(
name='tina',
version='0.2.0',
packages=find_packages(),
install_requires=[
    'httpx',
    'diskcache==5.6.3',
    'faiss-cpu==1.9.0.post1',
    'Jinja2==3.1.5',
    'lxml==5.3.0',
    'MarkupSafe==3.0.2',
    'numpy==2.2.1',
    'packaging==24.2',
    'PyPDF2==3.0.1',
    'python-docx==1.1.2',
   'setuptools==75.1.0',
    'typing_extensions==4.12.2',
    'wheel==0.44.0'
],

description='tina is in your computer!',
long_description=open('README.md',encoding="utf-8").read(),
url='https://gitee.com/wang-churi/tina',
author='王出日',
author_email='wangchuri@163.com',
classifiers=[
'Programming Language :: Python :: 3',
'License :: OSI Approved :: Apache 2.0',
'Operating System :: OS Independent',
],
python_requires='>=3.10',
)
